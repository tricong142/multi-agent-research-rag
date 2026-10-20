"""Exercise the shipped candidate, plus the existing notebook lifecycle guards."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts import test_colab_cellfix3_fresh as h

ROOT = Path(__file__).resolve().parents[1]


class Cellfix4FreshTests(h.FreshColabTests):
    @classmethod
    def setUpClass(cls):
        cls.target_patch = patch.object(h, 'TARGET', ROOT/'scripts/colab_atomic_verifier_cellfix4_fresh.ipynb')
        cls.target_patch.start()
        cls.addClassCleanup(cls.target_patch.stop)

    def test_payload_hashes_paths_and_release_catalog(self):
        book,cells,v = h.notebook()
        self.assertEqual(len(cells),5)
        for c in cells: compile(c,'cellfix4-cell','exec')
        self.assertEqual(book['metadata']['accelerator'],'GPU')
        payload=base64.b64decode(v['payload'],validate=True)
        self.assertEqual(hashlib.sha256(payload).hexdigest(),v['payload_sha256'])
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(set(archive.namelist()),set(v['manifest']))
            self.assertEqual(len(archive.namelist()),81)
            for name,item in v['manifest'].items():
                rel=PurePosixPath(name)
                self.assertFalse(rel.is_absolute() or '..' in rel.parts or '\\' in name)
                self.assertNotIn('.env',rel.parts)
                self.assertFalse(name.endswith(('.safetensors','.bin','.pem','.key')))
                data=archive.read(name)
                self.assertEqual(len(data),item['size'])
                self.assertEqual(hashlib.sha256(data).hexdigest(),item['sha256'])
            data=archive.read('research_rag/evaluation/atomic_verifier_criteria_v8.json')
            self.assertEqual(hashlib.sha256(data).hexdigest(),v['criteria_sha256'])
            frozen=json.loads(data)
            self.assertEqual(frozen['policy'],'atomic-verifier-constrained-v8-cellfix4')
            self.assertEqual(len(frozen['source_sha256']),34)
            for name,digest in frozen['source_sha256'].items():
                self.assertEqual(v['manifest'][name]['sha256'],digest)
        path=ROOT/'docs/atomic-verifier-cellfix4-fresh-colab-release.json'
        if not path.exists(): path=ROOT/'research-runs/atomic-cellfix4-fresh-draft-release.json'
        release=json.loads(path.read_text())
        self.assertEqual(release['payload_files'],v['manifest'])
        for name,digest in release['files'].items():
            self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),digest)
        self.assertFalse(release['previous_session_required'])
        self.assertFalse(release['full39_runs_automatically'])
        self.assertFalse(release['fresh_gpu_inference_completed'])
        parent=json.loads((ROOT/'research-runs/audit-cellfix3-fresh-20261017T101839Z-a9590fe1/workspace/research_rag/evaluation/atomic_verifier_criteria_v8.json').read_text())
        changed={'version','policy','structured_decoder','contract_file','contract_sha256','source_sha256','prompt_sha256','limitations'}
        for key in parent.keys()-changed:
            self.assertEqual(frozen[key],parent[key],key)
        self.assertEqual(frozen['prompt_sha256']['decompose'],parent['prompt_sha256']['decompose'])

    test_exact_extracted_payload_runs_153_tests_and_three_validate_only_modes = None

    def test_exact_extracted_payload_runs_166_tests_and_three_validate_only_modes(self):
        # Override the historical method while retaining its six lifecycle checks.
        _,_,v=h.notebook()
        with tempfile.TemporaryDirectory(prefix='cf4-payload-',dir=ROOT/'research-runs') as directory:
            runtime=Path(directory).resolve()
            self.assertTrue(runtime.is_relative_to((ROOT/'research-runs').resolve()))
            with zipfile.ZipFile(io.BytesIO(base64.b64decode(v['payload']))) as archive:
                for name in v['manifest']:
                    p=(runtime/name).resolve()
                    self.assertTrue(p.is_relative_to(runtime))
                    p.parent.mkdir(parents=True,exist_ok=True)
                    p.write_bytes(archive.read(name))
            temp=runtime/'test-tmp';temp.mkdir()
            env={**os.environ,'PYTHONPATH':str(runtime),'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1',
                 'HF_HOME':str(runtime/'hf'),'TEMP':str(temp),'TMP':str(temp)}
            frozen=json.loads((runtime/'research_rag/evaluation/atomic_verifier_criteria_v8.json').read_text())
            modules=[p[:-3].replace('/','.') for p in frozen['source_sha256']
                     if p.startswith('research_rag/tests/') and p.endswith('.py')]
            check='''import json,sys,unittest
from pathlib import Path
from research_rag.evaluation import evaluate_atomic_verifier as driver
assert Path(driver.__file__).resolve().is_relative_to(Path.cwd())
suite=unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:])
assert suite.countTestCases()==166
result=unittest.TextTestRunner(verbosity=2).run(suite)
print(json.dumps({'executed':result.testsRun}))
raise SystemExit(0 if result.wasSuccessful() else 1)
'''
            result=subprocess.run([sys.executable,'-c',check,*modules],cwd=runtime,env=env,
                                  capture_output=True,text=True,timeout=900)
            (ROOT/'research-runs/cellfix4-fresh-payload-regression.log').write_text(result.stdout+result.stderr,encoding='utf-8')
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(json.loads(result.stdout.splitlines()[-1])['executed'],166)
            outputs={}
            for name,flag,cases,calls in (('probe','--decomposition-probe',18,36),('smoke','--assessment-smoke',12,96),('verifier',None,39,312)):
                cmd=[sys.executable,'-m','research_rag.evaluation.evaluate_atomic_verifier',
                     '--output-dir',str(runtime/'unused'),'--validate-only']
                if flag: cmd.append(flag)
                result=subprocess.run(cmd,cwd=runtime,env=env,capture_output=True,text=True,timeout=300)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                outputs[name]=json.loads(result.stdout)
                self.assertEqual(outputs[name],{'freeze_valid':True,'cases':cases,'maximum_calls':calls})
                self.assertFalse((runtime/'unused').exists())
            (ROOT/'research-runs/cellfix4-fresh-payload-validation.json').write_text(json.dumps({
                'criteria_sha256':v['criteria_sha256'],'payload_sha256':v['payload_sha256'],
                'frozen_regression_tests_passed':166,'validate_only':outputs,'model_inference_completed':False},indent=2)+'\n')


def load_tests(loader, tests, pattern):
    # Do not accidentally execute the imported historical class a second time.
    return loader.loadTestsFromTestCase(Cellfix4FreshTests)


if __name__=='__main__':
    unittest.main(verbosity=2)
