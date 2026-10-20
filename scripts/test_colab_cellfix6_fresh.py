"""Test the actual embedded payload and fail-closed lifecycle; never run a model."""
import base64
from contextlib import contextmanager
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from scripts import test_colab_cellfix3_fresh as h
from scripts.atomic_validation_review import digest
from scripts.test_atomic_validation_packet import simulated_review

ROOT=Path(__file__).resolve().parents[1]
ORIGINAL_STARTED=h.started


@contextmanager
def reviewed_test_runtime():
    with ORIGINAL_STARTED() as (s,colab,cells):
        # Disposable fixture, removed with the test runtime. Not a user approval.
        (s['out']/'validation-annotation-review.json').write_text(json.dumps(simulated_review()),encoding='utf-8')
        yield s,colab,cells


class Cellfix6NotebookTests(h.FreshColabTests):
    @classmethod
    def setUpClass(cls):
        cls.target_patch=patch.object(h,'TARGET',ROOT/'scripts/colab_atomic_verifier_cellfix6_fresh.ipynb')
        cls.runtime_patch=patch.object(h,'started',reviewed_test_runtime)
        cls.target_patch.start();cls.runtime_patch.start()
        cls.addClassCleanup(cls.runtime_patch.stop);cls.addClassCleanup(cls.target_patch.stop)

    test_exact_extracted_payload_runs_153_tests_and_three_validate_only_modes=None

    def test_payload_hashes_paths_and_release_catalog(self):
        book,cells,v=h.notebook()
        self.assertEqual(len(cells),5)
        for code in cells: compile(code,'cellfix6-notebook','exec')
        raw=base64.b64decode(v['payload'],validate=True)
        self.assertEqual(digest(raw),v['payload_sha256'])
        candidate=json.loads((ROOT/'docs/atomic-verifier-cellfix6-candidate.json').read_text())
        self.assertEqual(v['criteria_sha256'],candidate['criteria_sha256'])
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(set(archive.namelist()),set(v['manifest']))
            self.assertEqual(len(archive.namelist()),99)
            for name,item in v['manifest'].items():
                rel=PurePosixPath(name)
                self.assertFalse(rel.is_absolute() or '..' in rel.parts or '\\' in name)
                self.assertNotIn('.env',rel.parts)
                self.assertFalse(name.endswith(('.safetensors','.bin','.key','.pem')))
                data=archive.read(name)
                self.assertEqual(len(data),item['size']);self.assertEqual(digest(data),item['sha256'])
            for name,item in candidate['input_manifest'].items():
                self.assertEqual(v['manifest'][name],item)
            frozen=json.loads(archive.read('research_rag/evaluation/atomic_verifier_criteria_v8.json'))
            self.assertEqual(frozen['policy'],candidate['candidate'])
            for name,expected in frozen['source_sha256'].items():
                self.assertEqual(digest(archive.read(name)),expected)
        record=json.loads((ROOT/'docs/atomic-verifier-cellfix6-notebook-draft.json').read_text())
        self.assertEqual(record['payload_files'],v['manifest'])
        for name,expected in record['files'].items(): self.assertEqual(digest((ROOT/name).read_bytes()),expected)
        self.assertEqual(record['human_annotation_review'],'pending')
        self.assertFalse(record['model_inference_completed'])
        self.assertFalse(record['full39_runs_automatically'])
        self.assertFalse(record['validation30_runs_automatically'])

    def test_no_review_blocks_validate_smoke_probe_before_subprocess(self):
        for index in (2,3,4):
            with self.subTest(index=index),ORIGINAL_STARTED() as (s,colab,cells):
                s['run']=Mock()
                with self.assertRaisesRegex(ValueError,'pending human review'): exec(cells[index],s)
                s['run'].assert_not_called();colab.files.download.assert_called_once()

    def test_uploaded_template_cannot_start_gpu_install(self):
        with ORIGINAL_STARTED() as (s,colab,cells):
            raw=(ROOT/'docs/validation/atomic-cellfix6-v1/annotation-review.template.json').read_bytes()
            colab.files.upload=Mock(return_value={'review.json':raw})
            s['run']=Mock()
            with self.assertRaisesRegex(ValueError,'human review'): exec(cells[1],s)
            s['run'].assert_not_called();colab.files.download.assert_called_once()

    def test_changed_input_or_review_cannot_reuse_a_previous_lock(self):
        for mutation in ('input','review'):
            with self.subTest(mutation=mutation),reviewed_test_runtime() as (s,colab,cells):
                s['require_validation_review']()
                if mutation=='input':
                    path=s['root']/'validation/atomic-cellfix6-v1/inputs.jsonl'
                    path.write_bytes(path.read_bytes()+b' ')
                else:
                    review=simulated_review();review['decisions'][0]['checks']['gold_label']=False
                    (s['out']/'validation-annotation-review.json').write_text(json.dumps(review))
                s['run']=Mock()
                with self.assertRaises(ValueError): exec(cells[3],s)
                s['run'].assert_not_called()

    def test_extracted_candidate_211_regressions_and_three_cli_validate_modes(self):
        _,_,v=h.notebook()
        with tempfile.TemporaryDirectory(prefix='cf6-payload-',dir=ROOT/'research-runs') as directory:
            runtime=Path(directory).resolve()
            with zipfile.ZipFile(io.BytesIO(base64.b64decode(v['payload']))) as archive:
                for name in v['manifest']:
                    target=(runtime/name).resolve();self.assertTrue(target.is_relative_to(runtime))
                    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(archive.read(name))
            temp=runtime/'test-tmp';temp.mkdir()
            env={**os.environ,'PYTHONPATH':str(runtime),'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1',
                 'HF_HOME':str(runtime/'hf'),'TEMP':str(temp),'TMP':str(temp)}
            check='''import io,json,sys,tempfile,unittest
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import patch
tempfile.tempdir=str(Path.cwd()/'test-tmp')
from research_rag.evaluation import evaluate_atomic_verifier as driver
assert Path(driver.__file__).resolve().is_relative_to(Path.cwd())
criteria,cases,*_=driver.load_frozen(driver.CRITERIA)
modules=[n[:-3].replace('/','.') for n in criteria['source_sha256'] if n.startswith('research_rag/tests/') and n.endswith('.py')]
suite=unittest.defaultTestLoader.loadTestsFromNames(modules)
assert suite.countTestCases()==211
result=unittest.TextTestRunner(verbosity=2).run(suite)
outputs={}
for name,flags,n,calls in [('smoke',['--assessment-smoke'],12,96),('probe',['--decomposition-probe'],18,36),('verifier',[],39,312)]:
    stream=io.StringIO()
    with patch.object(sys,'argv',['evaluate_atomic_verifier','--validate-only','--output-dir',str(Path.cwd()/'unused'),*flags]),redirect_stdout(stream):
        driver.main()
    outputs[name]=json.loads(stream.getvalue())
    assert outputs[name]=={'freeze_valid':True,'cases':n,'maximum_calls':calls}
assert not (Path.cwd()/'unused').exists()
print(json.dumps({'regression_tests':result.testsRun,'regression_passed':result.wasSuccessful(),'validate_only':outputs,'model_inference_completed':False}))
raise SystemExit(0 if result.wasSuccessful() else 1)
'''
            result=subprocess.run([sys.executable,'-c',check],cwd=runtime,env=env,capture_output=True,text=True,timeout=900)
            (ROOT/'research-runs/cellfix6-notebook-payload-regression.log').write_text(result.stdout+result.stderr,encoding='utf-8')
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            report=json.loads(result.stdout.splitlines()[-1]);self.assertTrue(report['regression_passed'])
            (ROOT/'research-runs/cellfix6-notebook-payload-validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')


def load_tests(loader,tests,pattern):
    return loader.loadTestsFromTestCase(Cellfix6NotebookTests)


if __name__=='__main__':
    unittest.main(verbosity=2)
