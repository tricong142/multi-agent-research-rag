"""Validate the exact fresh notebook payload and stage guards without GPU inference."""
import ast
import base64
from contextlib import contextmanager, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
import zipfile

ROOT=Path(__file__).resolve().parents[1]
TARGET=ROOT/'scripts/colab_atomic_verifier_cellfix3_fresh.ipynb'
PREREQUISITES=('gpu-host','venv','bootstrap','torch','runtime','pip-check','pip-freeze',
    'regression','cuda-preflight','probe-validate-only','smoke-validate-only','verifier-validate-only','pinned-model-cache')


def notebook():
    book=json.loads(TARGET.read_text(encoding='utf-8'))
    cells=[c['source'] for c in book['cells'] if c['cell_type']=='code']
    values={t.id:ast.literal_eval(n.value) for n in ast.parse(cells[0]).body
        if isinstance(n,ast.Assign) for t in n.targets if isinstance(t,ast.Name)
        and t.id in ('payload','payload_sha256','manifest','criteria_sha256')}
    return book,cells,values


@contextmanager
def started():
    _,cells,_=notebook()
    with tempfile.TemporaryDirectory(prefix='cf3-fresh-',dir=ROOT/'research-runs') as directory:
        base=Path(directory).resolve()
        assert base.is_relative_to((ROOT/'research-runs').resolve())
        colab=types.ModuleType('google.colab');colab.files=types.SimpleNamespace(download=Mock())
        scope={}
        marker="Path('/content')"
        assert cells[0].count(marker)==1
        # Remap only the Colab filesystem mount for a Windows/local test.
        source=cells[0].replace(marker,'Path('+repr(str(base))+')',1)
        with patch.dict(sys.modules,{'google.colab':colab}),redirect_stdout(io.StringIO()):
            exec(compile(source,'<fresh-setup>','exec'),scope)
            yield scope,colab,cells


class FreshColabTests(unittest.TestCase):
    def test_payload_hashes_paths_and_release_catalog(self):
        book,cells,v=notebook()
        self.assertEqual(len(cells),5)
        for c in cells: compile(c,'fresh-notebook-cell','exec')
        self.assertEqual(book['metadata']['accelerator'],'GPU')
        payload=base64.b64decode(v['payload'],validate=True)
        self.assertEqual(hashlib.sha256(payload).hexdigest(),v['payload_sha256'])
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(set(archive.namelist()),set(v['manifest']))
            self.assertEqual(len(archive.namelist()),78)
            for name,item in v['manifest'].items():
                path=PurePosixPath(name)
                self.assertFalse(path.is_absolute() or '..' in path.parts or '\\' in name)
                self.assertNotIn('.env',path.parts)
                self.assertFalse(name.endswith(('.safetensors','.bin','.pem','.key')))
                data=archive.read(name)
                self.assertEqual(len(data),item['size'])
                self.assertEqual(hashlib.sha256(data).hexdigest(),item['sha256'])
            name='research_rag/evaluation/atomic_verifier_criteria_v8.json'
            self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(),v['criteria_sha256'])
            frozen=json.loads(archive.read(name))
            self.assertEqual(frozen['policy'],'atomic-verifier-constrained-v8-cellfix3')
            self.assertEqual(len(frozen['source_sha256']),32)
            self.assertTrue(set(frozen['source_sha256'])<=set(v['manifest']))
            for name,digest in frozen['source_sha256'].items():
                self.assertEqual(v['manifest'][name]['sha256'],digest)
        release=ROOT/'docs/atomic-verifier-cellfix3-fresh-colab-release.json'
        if not release.exists(): release=ROOT/'research-runs/atomic-cellfix3-fresh-draft-release.json'
        record=json.loads(release.read_text())
        self.assertEqual(record['payload_files'],v['manifest'])
        for name,digest in record['files'].items():
            self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),digest)
        self.assertFalse(record['previous_session_required'])
        self.assertFalse(record['fresh_gpu_inference_completed'])
        self.assertFalse(record['full39_runs_automatically'])

    def test_setup_runs_without_any_previous_session_state(self):
        with started() as (s,colab,cells):
            _,_,v=notebook()
            self.assertNotIn('_cellfix3_parent',s)
            self.assertFalse(s['smoke_passed'])
            self.assertEqual(s['statuses'],{})
            for name,item in v['manifest'].items():
                p=s['root']/name
                self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),item['sha256'])
            self.assertEqual(hashlib.sha256((s['out']/'frozen-inputs.zip').read_bytes()).hexdigest(),v['payload_sha256'])
            self.assertTrue(s['out'].with_suffix('.zip').exists())
            self.assertNotIn('_find_cellfix3_parent',cells[0])
            colab.files.download.assert_not_called()

    def test_smoke_cannot_start_without_prerequisites_and_archives(self):
        with started() as (s,colab,cells):
            s['run']=Mock()
            with self.assertRaisesRegex(AssertionError,'Complete cells 1-3'):
                exec(cells[3],s)
            s['run'].assert_not_called()
            self.assertFalse(s['smoke_passed'])
            colab.files.download.assert_called_once()
            exec(cells[4],s)
            s['run'].assert_not_called()

    def test_quality_failure_blocks_probe_without_extra_assertion(self):
        with started() as (s,colab,cells):
            s['statuses']={n:{'exit_code':0} for n in PREREQUISITES}
            s['smoke_passed']=True
            def failed(name,cmd,**kw):
                self.assertEqual(name,'assessment-smoke')
                self.assertEqual(kw['timeout'],2520)
                self.assertIn('--assessment-smoke',cmd)
                folder=s['out']/'assessment-smoke';folder.mkdir()
                (folder/'metrics.json').write_text(json.dumps({'automated_gate_pass':False,'simulated_lifecycle_only':True}))
                s['statuses'][name]={'exit_code':1}
                return 1
            s['run']=Mock(side_effect=failed)
            exec(cells[3],s)
            self.assertFalse(s['smoke_passed'])
            exec(cells[4],s)
            self.assertEqual(s['run'].call_count,1)
            colab.files.download.assert_called_once()

    def test_only_confirmed_smoke_can_run_probe_and_never_full39(self):
        with started() as (s,colab,cells):
            s['statuses']={n:{'exit_code':0} for n in PREREQUISITES}
            def passed(name,cmd,**kw):
                self.assertNotIn('--worker',cmd)
                self.assertNotIn('--probe-dir',cmd)
                self.assertEqual(kw['timeout'],2520)
                if name=='assessment-smoke':
                    folder=s['out']/'assessment-smoke';folder.mkdir()
                    (folder/'metrics.json').write_text(json.dumps({'automated_gate_pass':True,'simulated_lifecycle_only':True}))
                else:
                    self.assertEqual(name,'decomposition-probe')
                    self.assertIn('--decomposition-probe',cmd)
                    folder=s['out']/'decomposition-probe';folder.mkdir()
                    (folder/'summary.json').write_text('{"human_review":"pending","simulated_lifecycle_only":true}')
                s['statuses'][name]={'exit_code':0}
                return 0
            s['run']=Mock(side_effect=passed)
            exec(cells[3],s);self.assertTrue(s['smoke_passed'])
            exec(cells[4],s)
            self.assertEqual([c.args[0] for c in s['run'].call_args_list],['assessment-smoke','decomposition-probe'])
            self.assertEqual(colab.files.download.call_count,2)

    def test_stale_success_flag_cannot_override_saved_failed_metrics(self):
        with started() as (s,colab,cells):
            s['smoke_passed']=True
            s['statuses']['assessment-smoke']={'exit_code':0}
            folder=s['out']/'assessment-smoke';folder.mkdir()
            (folder/'metrics.json').write_text('{"automated_gate_pass":false}')
            s['run']=Mock()
            exec(cells[4],s)
            self.assertFalse(s['smoke_passed'])
            s['run'].assert_not_called()

    def test_infrastructure_failure_downloads_diagnostics(self):
        for index in (1,2,3):
            with self.subTest(cell=index+1),started() as (s,colab,cells):
                s['statuses']={n:{'exit_code':0} for n in PREREQUISITES}
                s['run']=Mock(side_effect=RuntimeError('injected infrastructure failure'))
                with self.assertRaisesRegex(RuntimeError,'injected infrastructure failure'):
                    exec(cells[index],s)
                self.assertTrue(s['out'].with_suffix('.zip').exists())
                colab.files.download.assert_called_once()

    def test_exact_extracted_payload_runs_153_tests_and_three_validate_only_modes(self):
        _,_,v=notebook()
        with tempfile.TemporaryDirectory(prefix='cf3-payload-',dir=ROOT/'research-runs') as directory:
            runtime=Path(directory).resolve()
            assert runtime.is_relative_to((ROOT/'research-runs').resolve())
            with zipfile.ZipFile(io.BytesIO(base64.b64decode(v['payload']))) as archive:
                for name in v['manifest']:
                    p=(runtime/name).resolve()
                    self.assertTrue(p.is_relative_to(runtime))
                    p.parent.mkdir(parents=True,exist_ok=True)
                    p.write_bytes(archive.read(name))
            temp=runtime/'test-tmp';temp.mkdir()
            env={**os.environ,'PYTHONPATH':str(runtime),'HF_HUB_OFFLINE':'1',
                'TRANSFORMERS_OFFLINE':'1','HF_HOME':str(runtime/'hf'),'TEMP':str(temp),'TMP':str(temp)}
            frozen=json.loads((runtime/'research_rag/evaluation/atomic_verifier_criteria_v8.json').read_text())
            modules=[p[:-3].replace('/','.') for p in frozen['source_sha256']
                if p.startswith('research_rag/tests/') and p.endswith('.py')]
            check='''import json,sys,unittest
from pathlib import Path
from research_rag.evaluation import evaluate_atomic_verifier as driver
assert Path(driver.__file__).resolve().is_relative_to(Path.cwd())
suite=unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:])
assert suite.countTestCases()==153
result=unittest.TextTestRunner(verbosity=2).run(suite)
print(json.dumps({'executed':result.testsRun}))
raise SystemExit(0 if result.wasSuccessful() else 1)
'''
            result=subprocess.run([sys.executable,'-c',check,*modules],cwd=runtime,env=env,
                capture_output=True,text=True,timeout=900)
            (ROOT/'research-runs/cellfix3-fresh-payload-regression.log').write_text(result.stdout+result.stderr,encoding='utf-8')
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(json.loads(result.stdout.splitlines()[-1])['executed'],153)
            outputs={}
            for name,flag,cases,calls in (('probe','--decomposition-probe',18,36),('smoke','--assessment-smoke',12,96),('verifier',None,39,312)):
                command=[sys.executable,'-m','research_rag.evaluation.evaluate_atomic_verifier',
                    '--output-dir',str(runtime/'unused'),'--validate-only']
                if flag: command.append(flag)
                result=subprocess.run(command,cwd=runtime,env=env,capture_output=True,text=True,timeout=300)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                outputs[name]=json.loads(result.stdout)
                self.assertEqual(outputs[name],{'freeze_valid':True,'cases':cases,'maximum_calls':calls})
                self.assertFalse((runtime/'unused').exists())
            (ROOT/'research-runs/cellfix3-fresh-payload-validation.json').write_text(json.dumps({
                'frozen_regression_tests_passed':153,'validate_only':outputs,'model_inference_completed':False},indent=2)+'\n')


if __name__=='__main__':
    unittest.main(verbosity=2)
