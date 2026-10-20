"""Test recovery hashes, actual archived replay, and scripted Colab control flow."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
import warnings
from unittest.mock import Mock,patch
import zipfile

ROOT=Path(__file__).resolve().parents[1]
PACK=ROOT/'docs/reviews/cellfix8-20261020T061934Z-c87bce57/human'


class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code=(PACK/'RESTORE_AND_RUN_FULL39.py').read_text(encoding='utf-8')
        cls.uploads={'renamed archive.zip':(ROOT.parent/'output-cellfix8-fresh-20261020T061934Z-c87bce57 (2).zip').read_bytes(),
                     'semantic-review (1).json':(PACK/'semantic-review.json').read_bytes()}

    def scope(self,base=None):
        code=self.code
        if base is not None:
            self.assertEqual(code.count("Path('/content')"),1)
            code=code.replace("Path('/content')",'Path('+repr(str(base))+')',1)
        scope={'__name__':'TEST_ONLY_resume','run_id':'unrelated-session-run'}
        exec(compile(code,'resume-cell','exec'),scope)
        return scope

    def test_wrong_inputs_create_no_workspace_and_do_not_relabel_run(self):
        scope=self.scope()
        with tempfile.TemporaryDirectory(dir=ROOT/'research-runs',prefix='TEST_ONLY-resume-') as temp:
            for uploads in ({'wrong.zip':b'no'},dict(list(self.uploads.items())[:1])):
                with self.assertRaisesRegex(ValueError,'TWO files'):
                    scope['restore_uploads'](uploads,Path(temp))
            self.assertEqual(list(Path(temp).iterdir()),[])
            self.assertEqual(scope['run_id'],'unrelated-session-run')

    def test_zip_paths_and_duplicate_entries_are_rejected(self):
        scope=self.scope()
        for name in ('../bad','/absolute','C:/bad'):
            stream=io.BytesIO()
            with zipfile.ZipFile(stream,'w') as archive:archive.writestr(name,b'x')
            with self.assertRaisesRegex(ValueError,'Unsafe ZIP'):scope['checked_zip'](stream.getvalue())
        # Windows ZipInfo normalizes separators on write; build a raw ZIP name
        # to exercise the same backslash entry that Linux would receive.
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as archive:archive.writestr('folder/bad',b'x')
        malformed=stream.getvalue().replace(b'folder/bad',b'folder\\bad')
        with self.assertRaisesRegex(ValueError,'Unsafe ZIP'):scope['checked_zip'](malformed)
        stream=io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',UserWarning)
            with zipfile.ZipFile(stream,'w') as archive:
                archive.writestr('same',b'a');archive.writestr('same',b'b')
        with self.assertRaisesRegex(ValueError,'duplicate'):scope['checked_zip'](stream.getvalue())

    def test_restore_preserves_source_review_and_original_stage_history(self):
        scope=self.scope()
        with tempfile.TemporaryDirectory(dir=ROOT/'research-runs',prefix='TEST_ONLY-resume-') as temp:
            run_root,source,out,manifest=scope['restore_uploads'](self.uploads,Path(temp))
            self.assertTrue(run_root.resolve().is_relative_to(Path(temp).resolve()))
            self.assertEqual(len(manifest),111)
            import hashlib
            for name,item in manifest.items():
                self.assertEqual(hashlib.sha256((source/name).read_bytes()).hexdigest(),item['sha256'])
            self.assertEqual((out/'reviewed-probe/semantic-review.json').read_bytes(),self.uploads['semantic-review (1).json'])
            self.assertFalse(json.loads((out/'decomposition-probe/semantic-review.json').read_bytes())['review_completed'])
            self.assertEqual((out/'resume-parent-status.json').read_bytes(),(out/'status.json').read_bytes())
            self.assertEqual((out/'resume-parent-output-manifest.json').read_bytes(),(out/'output-manifest.json').read_bytes())
            self.assertEqual(json.loads((out/'resume-provenance.json').read_bytes())['original_run_id'],scope['AUDITED_RUN'])
            self.assertFalse((out/'verifier39').exists())

    def test_actual_restored_smoke_and_human_admission_replay_without_weights(self):
        scope=self.scope()
        with tempfile.TemporaryDirectory(dir=ROOT/'research-runs',prefix='TEST_ONLY-resume-replay-') as temp:
            _,source,out,_=scope['restore_uploads'](self.uploads,Path(temp))
            env={**os.environ,'PYTHONPATH':str(source),'PYTHONIOENCODING':'utf-8',
                'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','HF_HOME':str(Path(temp)/'hf')}
            completed=subprocess.run([sys.executable,'-c',scope['REPLAY'],str(out)],cwd=source,env=env,
                capture_output=True,text=True,encoding='utf-8',timeout=600)
            self.assertEqual(completed.returncode,0,completed.stdout+completed.stderr)
            result=json.loads((out/'resume-admission.json').read_bytes())
            self.assertTrue(result['smoke_replayed'])
            self.assertEqual(result['probe_human_admission']['reviewer'],'Trí Công')
            self.assertFalse(result['smoke_generated_again']);self.assertFalse(result['probe_generated_again'])
            self.assertFalse((out/'verifier39').exists())
            (PACK/'resume-replay-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

    def controller(self,failed_stage=None):
        with tempfile.TemporaryDirectory(dir=ROOT/'research-runs',prefix='TEST_ONLY-resume-controller-') as temp:
            scope=self.scope(Path(temp))
            files=types.SimpleNamespace(upload=Mock(return_value=self.uploads),download=Mock())
            colab=types.ModuleType('google.colab');colab.files=files
            download=Mock();scope['download_archive']=download
            scope['require_validation_binding']=Mock()
            def run(name,args,**kwargs):
                if name==failed_stage:raise RuntimeError('TEST_ONLY simulated failure')
                if name=='verifier39':
                    out=scope['out']/'verifier39';out.mkdir()
                    # Scripted failure verifies the gate remains false; no model runs.
                    (out/'metrics.json').write_text('{"automated_gate_pass":false,"n":39,"correct_labels":38,"false_support":0,"runtime_failed_rows":0}')
                    return 1
                return 0
            runner=Mock(side_effect=run);scope['run']=runner
            with patch.dict(sys.modules,{'google.colab':colab}),redirect_stdout(io.StringIO()):
                if failed_stage:
                    with self.assertRaisesRegex(RuntimeError,'TEST_ONLY'):scope['main']()
                else:scope['main']()
            names=[c.args[0] for c in runner.call_args_list]
            self.assertEqual(scope['run_id'],scope['AUDITED_RUN'])
            self.assertTrue(scope['RUN_FULL39'])
            self.assertFalse(scope['full39_passed'])
            download.assert_called_once()
            self.assertNotIn('assessment-smoke',names);self.assertNotIn('decomposition-probe',names)
            if failed_stage:
                self.assertNotIn('verifier39',names)
            else:
                self.assertLess(names.index('resume-audited-replay'),names.index('verifier39'))
                torch_call=next(c for c in runner.call_args_list if c.args[0]=='resume-torch')
                self.assertIn('torch==2.10.0',torch_call.args[1])
                self.assertIn('torchvision==0.25.0',torch_call.args[1])
                self.assertIn('https://download.pytorch.org/whl/cu128',torch_call.args[1])

    def test_controller_recovers_other_run_globals_and_keeps_model_failure_gate(self):
        self.controller()

    def test_failed_environment_check_preserves_diagnostics_and_blocks_model(self):
        self.controller('resume-cuda-preflight')

    def test_failed_replay_admission_preserves_diagnostics_and_blocks_model(self):
        self.controller('resume-audited-replay')


if __name__=='__main__':unittest.main(verbosity=2)
