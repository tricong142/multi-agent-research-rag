"""Exercise the exact generated cell prelude; no GPU/model calls or dataset edits."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

REPO=Path(__file__).resolve().parents[1]
AUDIT=REPO/'research-runs/audit-cellfix2-20261017T085227Z-e0a1ba82'
CELL=REPO/'scripts/colab_v8_assessment_smoke_cellfix3.py'
CRITERIA='research_rag/evaluation/atomic_verifier_criteria_v8.json'


class ParentSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base=REPO/'research-runs/v7-test-tmp'
        base.mkdir(parents=True,exist_ok=True)
        cls.temp=Path(tempfile.mkdtemp(prefix='cellfix3-parent-',dir=base)).resolve()
        assert cls.temp.is_relative_to(base.resolve())
        cls.good=cls.temp/'workspace-cellfix2-recovered'
        shutil.copytree(AUDIT/'workspace',cls.good,ignore=shutil.ignore_patterns('__pycache__'))
        cls.good_out=cls.temp/'output-cellfix2-recovered'
        cls.good_out.mkdir()
        shutil.copyfile(AUDIT/'artifact/input-manifest.json',cls.good_out/'input-manifest.json')
        cls.data=json.loads((cls.good_out/'input-manifest.json').read_text())
        cls.bad=cls.temp/'workspace-stale'
        (cls.bad/CRITERIA).parent.mkdir(parents=True)
        (cls.bad/CRITERIA).write_text('{"policy":"atomic-verifier-constrained-v8-cellfix1"}')
        cls.bad_out=cls.temp/'output-stale'
        cls.bad_out.mkdir()
        (cls.bad_out/'input-manifest.json').write_text('{}')
        source=CELL.read_text(encoding='utf-8')
        cls.prelude=compile(source[:source.index('\nrun_id =')],'<actual-cellfix3-prelude>','exec')

    @classmethod
    def tearDownClass(cls):
        assert cls.temp.is_relative_to((REPO/'research-runs/v7-test-tmp').resolve())
        shutil.rmtree(cls.temp)

    def setUp(self):
        self.colab=types.ModuleType('google.colab')
        self.colab.files=Mock()
        modules=patch.dict('sys.modules',{'google.colab':self.colab})
        modules.start()
        self.addCleanup(modules.stop)

    def scope(self,good=True):
        return dict(root=self.good if good else self.bad,out=self.good_out if good else self.bad_out,
            env={**os.environ,'CF3_PARENT_TEST':'cache-preserved'},manifest=copy.deepcopy(self.data),
            run_root=self.temp,python='unused',run=Mock(),bundle=Mock(),smoke_passed=True)

    def execute(self,scope):
        with patch('builtins.print'):
            exec(self.prelude,scope)
        scope['run'].assert_not_called()
        scope['bundle'].assert_not_called()
        self.colab.files.download.assert_not_called()
        self.assertIs(scope['smoke_passed'],False)
        self.assertEqual(scope['parent']['root'],self.good.resolve())
        self.assertEqual(scope['parent']['manifest'],self.data)
        self.assertEqual(scope['_cellfix3_parent'],scope['parent'])
        self.assertEqual(scope['parent']['env']['CF3_PARENT_TEST'],'cache-preserved')
        return scope

    def test_current_verified_parent(self):
        self.execute(self.scope())

    def test_poisoned_cache_cannot_override_current_verified_parent(self):
        scope=self.scope()
        scope['_cellfix3_parent']=dict(root=self.bad,out=self.bad_out,env={})
        self.execute(scope)

    def test_recovers_verified_cache_when_current_root_is_stale(self):
        scope=self.scope(False)
        scope['_cellfix3_parent']=dict(root=self.good,out=self.good_out,env=scope['env'].copy())
        self.execute(scope)

    def test_discovers_paired_cellfix2_when_both_current_and_cache_are_stale(self):
        scope=self.scope(False)
        scope['_cellfix3_parent']=dict(root=self.bad,out=self.bad_out,env={})
        scope['manifest']={}
        self.execute(scope)

    def test_current_cellfix3_cannot_be_patched_twice(self):
        scope=self.scope(False)
        scope['_cellfix3_parent']=dict(root=self.good,out=self.good_out,env=scope['env'].copy())
        original=(self.bad/CRITERIA).read_bytes()
        try:
            (self.bad/CRITERIA).write_text('{"policy":"atomic-verifier-constrained-v8-cellfix3"}')
            self.execute(scope)
        finally:
            (self.bad/CRITERIA).write_bytes(original)

    def test_corrupted_source_is_rejected_even_when_criteria_hash_matches(self):
        path=self.good/'04_factchecker/inference/numeric_verifier.py'
        original=path.read_bytes();scope=self.scope()
        try:
            path.write_bytes(original+b'\n# tampered test data\n')
            with self.assertRaisesRegex(RuntimeError,'Input integrity mismatch'):
                exec(self.prelude,scope)
            self.assertNotIn('_cellfix3_parent',scope)
            self.assertIs(scope['smoke_passed'],False)
            scope['run'].assert_not_called()
        finally:
            path.write_bytes(original)

    def test_wrong_manifest_is_rejected_despite_good_global_manifest(self):
        path=self.good_out/'input-manifest.json';original=path.read_bytes();scope=self.scope()
        try:
            path.write_text('{}')
            with self.assertRaisesRegex(RuntimeError,'No matching audited input-manifest'):
                exec(self.prelude,scope)
            self.assertNotIn('_cellfix3_parent',scope)
            self.assertIs(scope['smoke_passed'],False)
        finally:
            path.write_bytes(original)

    def test_missing_verified_candidate_reports_actual_hash_and_blocks_smoke(self):
        path=self.good/CRITERIA;original=path.read_bytes();scope=self.scope(False)
        wrong=hashlib.sha256((self.bad/CRITERIA).read_bytes()).hexdigest()
        try:
            path.write_text('{"policy":"unverified"}')
            with self.assertRaisesRegex(RuntimeError,wrong):
                exec(self.prelude,scope)
            self.assertNotIn('_cellfix3_parent',scope)
            self.assertIs(scope['smoke_passed'],False)
            scope['run'].assert_not_called()
        finally:
            path.write_bytes(original)


if __name__=='__main__':
    unittest.main(verbosity=2)
