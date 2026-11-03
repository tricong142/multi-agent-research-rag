"""Synthetic review retries; no held-out data, human signature or inference."""
import ast
from contextlib import contextmanager,redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import shutil
import textwrap
import unittest
from unittest.mock import Mock,patch

from scripts import test_colab_cellfix3_fresh as h

ROOT=Path(__file__).resolve().parents[1]


@contextmanager
def started():
    with patch.object(h,'TARGET',ROOT/'scripts/colab_atomic_verifier_cellfix15.ipynb'),h.started() as (s,colab,cells),redirect_stdout(io.StringIO()):
        full=s['out']/'verifier39';full.mkdir()
        (full/'metrics.json').write_text('{"automated_gate_pass":true}')
        (full/'predictions.jsonl').write_bytes(b'TEST_ONLY_NO_MODEL_PREDICTIONS')
        (full/'semantic-review.json').write_bytes(b'TEST_ONLY_OLD_UNSIGNED_REVIEW')
        s['statuses']['verifier39']={'state':'completed','exit_code':0}
        s['attempts']=s['out']/'review-attempts';s['attempts'].mkdir()
        for n in ast.walk(ast.parse(cells[5])):
            if isinstance(n,ast.FunctionDef) and n.name in ('preserve_review','probe_files','unused_stage'):
                exec(textwrap.dedent(ast.get_source_segment(cells[5],n)),s)
        s['download_archive']=Mock()
        # Nothing here is admitted as an actual human review: gate behavior is
        # independently tested by the workflow tests; this tests orchestration.
        raw=b'{"TEST_ONLY_REVIEW_BYTES_NOT_A_HUMAN_SIGNATURE":true}'
        colab.files.upload=Mock(return_value={'test-only.json':raw})
        yield s,colab,cells[6].replace('RUN_VALIDATION30 = False','RUN_VALIDATION30 = True',1),raw


class Cell7RetryTests(unittest.TestCase):
    def test_failed_review_preflight_preserves_existing_review_and_blocks_validation(self):
        with started() as (s,colab,cell,raw):
            reviewed=s['out']/'reviewed-verifier39';shutil.copytree(s['out']/'verifier39',reviewed)
            old=(reviewed/'semantic-review.json').read_bytes()
            s['statuses']['full39-admission-preflight']={'state':'failed','exit_code':1}
            s['run']=Mock(side_effect=ValueError('TEST_ONLY human review rejected'))
            with self.assertRaisesRegex(ValueError,'human review rejected'):exec(cell,s)
            self.assertEqual(s['run'].call_args.args[0],'full39-admission-preflight-retry-1')
            self.assertEqual((reviewed/'semantic-review.json').read_bytes(),old)
            self.assertFalse((s['out']/'validation30').exists())

    def test_review_retry_keeps_old_logs_and_admits_before_validation_stage(self):
        with started() as (s,colab,cell,raw):
            reviewed=s['out']/'reviewed-verifier39';shutil.copytree(s['out']/'verifier39',reviewed)
            old=(reviewed/'semantic-review.json').read_bytes()
            previous={'state':'failed','exit_code':1}
            s['statuses']['full39-admission']=dict(previous)
            s['statuses']['full39-admission-preflight']=dict(previous)
            (s['out']/'full39-admission.stderr.log').write_bytes(b'OLD_LOG')
            def run(stage,command,**kw):
                self.assertNotIn(stage,s['statuses'])
                s['statuses'][stage]={'state':'TEST_ONLY_SIMULATED'}
                return 0
            s['run']=Mock(side_effect=run)
            exec(cell,s)
            self.assertEqual([c.args[0] for c in s['run'].call_args_list],
                ['full39-admission-preflight-retry-1','full39-admission-retry-1','validation30'])
            self.assertEqual(s['statuses']['full39-admission'],previous)
            self.assertEqual((s['out']/'full39-admission.stderr.log').read_bytes(),b'OLD_LOG')
            self.assertEqual((reviewed/'semantic-review.json').read_bytes(),raw)
            saved=s['attempts']/(hashlib.sha256(old).hexdigest()+'.json')
            self.assertEqual(saved.read_bytes(),old)

    def test_existing_validation_attempt_blocks_before_review_upload(self):
        with started() as (s,colab,cell,raw):
            s['statuses']['validation30']={'state':'interrupted'}
            s['run']=Mock()
            with self.assertRaisesRegex(ValueError,'existing validation30 attempt'):exec(cell,s)
            s['run'].assert_not_called();colab.files.upload.assert_not_called()
            s['download_archive'].assert_called_once()


if __name__=='__main__':unittest.main(verbosity=2)
