"""Disposable retry orchestration tests; never load a model or create a real review."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

ROOT=Path(__file__).resolve().parents[1]
CODE=(ROOT/'scripts/kaggle_cellfix15_validation30_retry.py').read_text(encoding='utf-8')


class Validation30RetryTests(unittest.TestCase):
    def started(self,temp):
        root=Path(temp)/'workspace';out=Path(temp)/'out';root.mkdir();out.mkdir()
        for name in ('reviewed-probe','reviewed-verifier39'):
            (out/name).mkdir();(out/name/'semantic-review.json').write_bytes(b'TEST_ONLY_REVIEW')
        scope=dict(root=root,out=out,statuses={},run_id='TEST_ONLY',criteria_sha256='TEST_ONLY',python='TEST_PYTHON',
            require_validation_binding=Mock(),_cell7_replay_worker=Mock(return_value='TEST_WORKER'),
            bundle=Mock(),download_archive=Mock(),show_file=Mock())
        def run(stage,command,**kwargs):
            self.assertNotIn(stage,scope['statuses']);scope['statuses'][stage]={'state':'completed','exit_code':0}
            if '--admit-full39' not in command:
                target=Path(command[command.index('--output-dir')+1]);target.mkdir(exist_ok=False)
                (target/'metrics.json').write_text(json.dumps({'n':30,'correct_labels':30,'automated_gate_pass':True}))
                (target/'summary.json').write_text(json.dumps({'experiment_completed':True,'prediction_count':30}))
            return 0
        scope['run']=Mock(side_effect=run)
        return scope

    def test_failed_attempt_is_preserved_and_only_validation_is_rerun(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=self.started(tmp);old=s['out']/'validation30';old.mkdir();(old/'predictions.jsonl').write_bytes(b'TEST_ONLY_PARTIAL')
            s['statuses']['validation30']={'state':'failed','exit_code':1}
            with redirect_stdout(io.StringIO()):exec(CODE,s)
            self.assertEqual((old/'predictions.jsonl').read_bytes(),b'TEST_ONLY_PARTIAL')
            self.assertEqual(s['run'].call_count,2)
            self.assertIn('--admit-full39',s['run'].call_args_list[0].args[1])
            command=s['run'].call_args_list[1].args[1]
            self.assertIn('--binding-dir',command);self.assertNotIn('--assessment-smoke',command)
            target=Path(command[command.index('--output-dir')+1]);self.assertNotEqual(target,old)
            self.assertTrue(target.name.startswith('validation30-retry-'))
            self.assertEqual(s['statuses']['validation30']['exit_code'],1)
            s['download_archive'].assert_called_once()

    def test_completed_failed_gate_is_shown_without_new_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=self.started(tmp);old=s['out']/'validation30';old.mkdir()
            (old/'summary.json').write_text(json.dumps({'experiment_completed':True,'prediction_count':30}))
            (old/'metrics.json').write_text(json.dumps({'n':30,'correct_labels':24,'automated_gate_pass':False}))
            with redirect_stdout(io.StringIO()) as stream:exec(CODE,s)
            s['run'].assert_not_called();self.assertIn('24',stream.getvalue());self.assertIn('false',stream.getvalue())

    def test_running_attempt_blocks_duplicate_in_memory_or_on_disk(self):
        for disk in (False,True):
            with self.subTest(disk=disk),tempfile.TemporaryDirectory() as tmp:
                s=self.started(tmp);state={'validation30':{'state':'running'}}
                if disk:(s['out']/'status.json').write_text(json.dumps(state))
                else:s['statuses'].update(state)
                with redirect_stdout(io.StringIO()),self.assertRaisesRegex(ValueError,'marked running'):exec(CODE,s)
                s['run'].assert_not_called();s['download_archive'].assert_called_once()

    def test_failed_admission_blocks_model_and_preserves_old_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=self.started(tmp);log=s['out']/'validation30.stderr.log';log.write_bytes(b'TEST_ONLY_OLD_ERROR')
            s['run'].side_effect=RuntimeError('TEST_ONLY admission failed')
            with redirect_stdout(io.StringIO()),self.assertRaisesRegex(RuntimeError,'admission failed'):exec(CODE,s)
            self.assertEqual(s['run'].call_count,1)
            self.assertEqual(log.read_bytes(),b'TEST_ONLY_OLD_ERROR')
            self.assertFalse((s['out']/'validation30').exists())

    def test_log_only_previous_failure_can_retry_with_unique_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=self.started(tmp);log=s['out']/'validation30.stdout.log';log.write_bytes(b'TEST_ONLY_PREVIOUS_LOG')
            with redirect_stdout(io.StringIO()):exec(CODE,s)
            self.assertEqual(log.read_bytes(),b'TEST_ONLY_PREVIOUS_LOG')
            records=list(s['out'].glob('validation30-retry-*.retry.json'));self.assertEqual(len(records),1)
            record=json.loads(records[0].read_bytes());self.assertEqual(record['previous_attempts'],['validation30'])
            self.assertEqual(record['evaluation_role'],'development')

    def test_partial_json_from_interrupted_attempt_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=self.started(tmp);old=s['out']/'validation30';old.mkdir()
            (old/'summary.json').write_bytes(b'{"experiment_completed":')
            (old/'metrics.json').write_bytes(b'{')
            s['statuses']['validation30']={'state':'interrupted'}
            with redirect_stdout(io.StringIO()):exec(CODE,s)
            self.assertEqual((old/'summary.json').read_bytes(),b'{"experiment_completed":')
            self.assertEqual((old/'metrics.json').read_bytes(),b'{')
            self.assertEqual(s['run'].call_count,2)


if __name__=='__main__':unittest.main(verbosity=2)
