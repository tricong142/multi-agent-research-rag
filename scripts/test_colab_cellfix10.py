"""Test embedded cf10 bytes and all notebook stage gates without GPU inference."""
import base64
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch
import zipfile

from scripts import test_colab_cellfix3_fresh as h
from scripts.atomic_validation_review import digest

ROOT=Path(__file__).resolve().parents[1]


class Cellfix10NotebookTests(h.FreshColabTests):
    @classmethod
    def setUpClass(cls):
        cls.target_patch=patch.object(h,'TARGET',ROOT/'scripts/colab_atomic_verifier_cellfix10.ipynb')
        cls.target_patch.start();cls.addClassCleanup(cls.target_patch.stop)

    test_exact_extracted_payload_runs_153_tests_and_three_validate_only_modes=None

    def test_partial_regression_report_cannot_freeze_notebook(self):
        from scripts import build_colab_cellfix10 as builder
        with tempfile.TemporaryDirectory(dir=ROOT/'research-runs') as temp:
            folder=Path(temp);(folder/'docs').mkdir()
            (folder/'docs/atomic-verifier-cellfix10-candidate.json').write_text('{"criteria_sha256":"test"}')
            (folder/'docs/atomic-verifier-cellfix10-validation.json').write_text(
                '{"all_regression_passed":true,"regression_scope":"new_only","criteria_sha256":"test"}')
            with patch.object(builder,'ROOT',folder),self.assertRaisesRegex(ValueError,'Validate the final candidate'):
                builder.build()

    def test_payload_hashes_paths_and_release_catalog(self):
        _,cells,values=h.notebook()
        self.assertEqual(len(cells),7)
        for code in cells:compile(code,'cf10-notebook','exec')
        raw=base64.b64decode(values['payload'],validate=True)
        self.assertEqual(digest(raw),values['payload_sha256'])
        candidate=json.loads((ROOT/'docs/atomic-verifier-cellfix10-candidate.json').read_bytes())
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            self.assertIsNone(archive.testzip());self.assertEqual(set(archive.namelist()),set(values['manifest']))
            for name,item in values['manifest'].items():
                blob=archive.read(name);self.assertEqual(len(blob),item['size']);self.assertEqual(digest(blob),item['sha256'])
                self.assertNotIn('..',Path(name).parts);self.assertNotIn('.env',Path(name).parts)
            for name,item in candidate['input_manifest'].items():self.assertEqual(item,values['manifest'][name])
        catalog=ROOT/'docs/atomic-verifier-cellfix10-release.json'
        if not catalog.exists():catalog=ROOT/'research-runs/cellfix10-notebook-draft.json'
        record=json.loads(catalog.read_bytes())
        self.assertEqual(record['payload_files'],values['manifest'])
        for name,expected in record['files'].items():self.assertEqual(digest((ROOT/name).read_bytes()),expected,name)
        self.assertFalse(record['model_inference_completed']);self.assertFalse(record['promoted_to_serving'])

    def test_only_confirmed_smoke_can_run_probe_and_never_full39(self):
        with h.started() as (s,colab,cells):
            s['statuses']={n:{'exit_code':0} for n in h.PREREQUISITES}
            def passed(name,command,**kw):
                if name=='assessment-smoke':
                    p=s['out']/'assessment-smoke';p.mkdir();(p/'metrics.json').write_text('{"automated_gate_pass":true}')
                elif name=='decomposition-probe':
                    p=s['out']/'decomposition-probe';p.mkdir();(p/'metrics.json').write_text('{"automated_gate_pass":true}')
                elif name=='probe-review-form':
                    (s['out']/'decomposition-probe/HUMAN_REVIEW.html').write_text('SIMULATED_FORM_ONLY')
                else:raise AssertionError('Unexpected stage: '+name)
                s['statuses'][name]={'exit_code':0};return 0
            s['run']=Mock(side_effect=passed)
            exec(cells[3],s);exec(cells[4],s);exec(cells[5],s);exec(cells[6],s)
            self.assertEqual([c.args[0] for c in s['run'].call_args_list],['assessment-smoke','decomposition-probe','probe-review-form'])
            self.assertFalse(s['RUN_FULL39']);self.assertFalse(s['RUN_VALIDATION30'])

    def test_new_binding_is_verified_at_startup_and_no_review_upload(self):
        with h.started() as (s,colab,cells):
            lock=json.loads((s['out']/'validation-lock.json').read_bytes())
            self.assertEqual(lock['candidate_criteria_sha256'],s['criteria_sha256'])
            self.assertFalse(lock['new_human_signature_created'])
            self.assertEqual((s['out']/'validation-annotation-review.json').read_bytes(),
                (ROOT/'docs/validation/atomic-cellfix6-v1/annotation-review-cellfix6-v1.json').read_bytes())
            self.assertNotIn('files.upload()',cells[1])

    def test_changed_payload_blocks_gpu_before_any_command(self):
        with h.started() as (s,colab,cells):
            path=s['root']/'validation/cellfix10/binding.json';path.write_bytes(b'{}')
            s['run']=Mock()
            with self.assertRaisesRegex(ValueError,'Frozen input changed'):exec(cells[1],s)
            s['run'].assert_not_called();colab.files.download.assert_called_once()

    def test_full39_and_validation_default_to_skipped_without_upload_or_generation(self):
        with h.started() as (s,colab,cells):
            s['run']=Mock();colab.files.upload=Mock()
            exec(cells[5],s);exec(cells[6],s)
            s['run'].assert_not_called();colab.files.upload.assert_not_called()

    def test_enabled_full39_cannot_bypass_failed_probe(self):
        with h.started() as (s,colab,cells):
            s['run']=Mock();colab.files.upload=Mock()
            with self.assertRaisesRegex(AssertionError,'Probe18 must pass'):
                exec(cells[5].replace('RUN_FULL39 = False','RUN_FULL39 = True',1),s)
            s['run'].assert_not_called();colab.files.upload.assert_not_called()

    def test_enabled_validation_cannot_bypass_failed_full39(self):
        with h.started() as (s,colab,cells):
            s['run']=Mock();colab.files.upload=Mock()
            with self.assertRaisesRegex(AssertionError,'Successful full39'):
                exec(cells[6].replace('RUN_VALIDATION30 = False','RUN_VALIDATION30 = True',1),s)
            s['run'].assert_not_called();colab.files.upload.assert_not_called()

    def test_probe_admission_failure_prevents_full39_command(self):
        with h.started() as (s,colab,cells):
            p=s['out']/'decomposition-probe';p.mkdir();(p/'metrics.json').write_text('{"automated_gate_pass":true}')
            (p/'semantic-review.json').write_text('{"review_completed":false}')
            s['statuses']['decomposition-probe']={'exit_code':0}
            colab.files.upload=Mock(return_value={'bad-review.json':b'{}'})
            s['run']=Mock(side_effect=ValueError('test admission rejected'))
            with self.assertRaisesRegex(ValueError,'admission rejected'):
                exec(cells[5].replace('RUN_FULL39 = False','RUN_FULL39 = True',1),s)
            self.assertEqual([c.args[0] for c in s['run'].call_args_list],['probe-admission'])
            self.assertEqual(json.loads((p/'semantic-review.json').read_text())['review_completed'],False)

    def test_extracted_payload_runs_all_four_validate_only_modes(self):
        _,_,values=h.notebook()
        with tempfile.TemporaryDirectory(dir=ROOT/'research-runs',prefix='cf10-payload-') as temp:
            folder=Path(temp).resolve()
            with zipfile.ZipFile(io.BytesIO(base64.b64decode(values['payload']))) as archive:
                for name in values['manifest']:
                    path=(folder/name).resolve();self.assertTrue(path.is_relative_to(folder))
                    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(archive.read(name))
            command='''import io,importlib.util,json,sys
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from research_rag.evaluation import evaluate_atomic_verifier as r
assert Path(r.__file__).resolve().is_relative_to(Path.cwd())
results={}
for name,flag,n,calls in [('smoke','--assessment-smoke',12,96),('probe','--decomposition-probe',18,36),('full39',None,39,312)]:
 stream=io.StringIO()
 with patch.object(sys,'argv',['check','--validate-only','--output-dir','unused']+([flag] if flag else [])),redirect_stdout(stream):r.main()
 results[name]=json.loads(stream.getvalue());assert results[name]=={'freeze_valid':True,'cases':n,'maximum_calls':calls}
spec=importlib.util.spec_from_file_location('workflow',Path('atomic_workflow_cellfix10.py'))
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
stream=io.StringIO()
with patch.object(sys,'argv',['workflow','--binding-dir','validation/cellfix10','--validate-only']),redirect_stdout(stream):w.main()
results['validation30']=json.loads(stream.getvalue());assert results['validation30']['cases']==30 and results['validation30']['maximum_calls']==240
assert not Path('unused').exists()
print(json.dumps(results))
'''
            env={**os.environ,'PYTHONPATH':str(folder),'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','HF_HOME':str(folder/'hf')}
            result=subprocess.run([sys.executable,'-c',command],cwd=folder,env=env,text=True,capture_output=True,timeout=600)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            (ROOT/'research-runs/cellfix10-payload-validate-only.json').write_text(result.stdout,encoding='utf-8')


def load_tests(loader,tests,pattern):return loader.loadTestsFromTestCase(Cellfix10NotebookTests)


if __name__=='__main__':unittest.main(verbosity=2)
