"""Disposable notebook orchestration tests; never execute model inference."""
from contextlib import contextmanager, redirect_stdout
import ast
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock
from types import SimpleNamespace
import time

ROOT = Path(__file__).resolve().parents[1]
CELL = (ROOT/'scripts/colab_cellfix11_cell6.py').read_text(encoding='utf-8').replace('RUN_FULL39 = False','RUN_FULL39 = True',1)


@contextmanager
def started():
    with tempfile.TemporaryDirectory(dir=ROOT/'research-runs', prefix='TEST_ONLY-cell6-') as directory:
        base = Path(directory)
        out = base/'out'
        probe = out/'decomposition-probe'
        probe.mkdir(parents=True)
        (probe/'criteria.json').write_text('{"TEST_ONLY":true}')
        (probe/'predictions.jsonl').write_text('{"TEST_ONLY":true}\n')
        (probe/'HUMAN_REVIEW.html').write_text('TEST_ONLY')
        (probe/'metrics.json').write_text(json.dumps({
            'n':18,'valid_decompositions':18,'automated_gate_pass':True}))
        review = {'criteria_sha256':hashlib.sha256((probe/'criteria.json').read_bytes()).hexdigest(),
                  'predictions_sha256':hashlib.sha256((probe/'predictions.jsonl').read_bytes()).hexdigest(),
                  'reviewer_kind':'human','reviewer':'TEST_ONLY_NOT_A_HUMAN_SIGNATURE',
                  'review_completed':True}
        payload = json.dumps(review).encode()
        files = Mock()
        files.upload.return_value = {'arbitrary-name.json':payload}
        scope = {'out':out,'root':base/'workspace','python':'TEST_ONLY_PYTHON',
                 'run_id':'TEST_ONLY_CURRENT_RUN','files':files,
                 'statuses':{'decomposition-probe':{'exit_code':0}},
                 'require_validation_binding':Mock(),'download_archive':Mock()}

        def run(stage, command, **kw):
            assert stage not in scope['statuses'], 'Preserve the previous stage; start a fresh run for retries'
            scope['statuses'][stage] = {'state':'TEST_ONLY_RECORDED'}
            if stage.startswith('probe-admission'):
                if not json.loads(payload)['review_completed']:
                    raise ValueError('TEST_ONLY human admission rejected')
            elif stage == 'verifier39':
                path=out/'verifier39'
                path.mkdir(exist_ok=False)
                (path/'metrics.json').write_text(json.dumps({'n':39,'correct_labels':36,
                    'false_support':0,'runtime_failed_rows':2,'automated_gate_pass':False}))
                return 1
            else:
                raise AssertionError('Unexpected inference/review stage: '+stage)
            return 0
        scope['run'] = Mock(side_effect=run)
        with redirect_stdout(io.StringIO()):
            yield scope, review, payload


class Cell6RetryTests(unittest.TestCase):
    def test_existing_same_probe_and_review_can_run_without_clobber(self):
        with started() as (s, review, payload):
            path=s['out']/'reviewed-probe'
            shutil.copytree(s['out']/'decomposition-probe',path)
            (path/'semantic-review.json').write_bytes(payload)
            original=(path/'predictions.jsonl').read_bytes()
            exec(CELL,s)
            self.assertEqual((path/'predictions.jsonl').read_bytes(),original)
            self.assertEqual((path/'semantic-review.json').read_bytes(),payload)
            self.assertEqual([c.args[0] for c in s['run'].call_args_list],
                ['probe-admission-preflight','probe-admission','verifier39'])
            self.assertFalse(s['full39_passed'])
            s['download_archive'].assert_called_once()

    def test_previous_failed_review_is_preserved_before_admitted_replacement(self):
        with started() as (s, review, payload):
            path=s['out']/'reviewed-probe'
            shutil.copytree(s['out']/'decomposition-probe',path)
            old=b'{"TEST_ONLY_OLD_REVIEW":true}'
            (path/'semantic-review.json').write_bytes(old)
            exec(CELL,s)
            saved=s['out']/'review-attempts'/(hashlib.sha256(old).hexdigest()+'.json')
            self.assertEqual(saved.read_bytes(),old)
            self.assertEqual((path/'semantic-review.json').read_bytes(),payload)

    def test_wrong_predictions_hash_stops_before_existing_folder_is_changed(self):
        with started() as (s, review, payload):
            path=s['out']/'reviewed-probe'
            shutil.copytree(s['out']/'decomposition-probe',path)
            (path/'semantic-review.json').write_bytes(b'OLD')
            review['predictions_sha256']='0'*64
            s['files'].upload.return_value={'wrong.json':json.dumps(review).encode()}
            with self.assertRaisesRegex(ValueError,'does not match'):
                exec(CELL,s)
            self.assertEqual((path/'semantic-review.json').read_bytes(),b'OLD')
            s['run'].assert_not_called()
            s['files'].download.assert_called_once_with(str(s['out']/'decomposition-probe/HUMAN_REVIEW.html'))
            s['download_archive'].assert_called_once()

    def test_different_probe_cannot_be_reused(self):
        with started() as (s, review, payload):
            path=s['out']/'reviewed-probe'
            shutil.copytree(s['out']/'decomposition-probe',path)
            (path/'predictions.jsonl').write_bytes(b'DIFFERENT')
            with self.assertRaisesRegex(ValueError,'differs from the current probe'):
                exec(CELL,s)
            s['run'].assert_not_called()
            self.assertEqual((path/'predictions.jsonl').read_bytes(),b'DIFFERENT')

    def test_failed_preflight_does_not_overwrite_previous_review_or_run_model(self):
        with started() as (s, review, payload):
            path=s['out']/'reviewed-probe'
            shutil.copytree(s['out']/'decomposition-probe',path)
            (path/'semantic-review.json').write_bytes(b'OLD')
            s['run'].side_effect=ValueError('TEST_ONLY human admission rejected')
            with self.assertRaisesRegex(ValueError,'human admission rejected'):
                exec(CELL,s)
            self.assertEqual((path/'semantic-review.json').read_bytes(),b'OLD')
            self.assertEqual([c.args[0] for c in s['run'].call_args_list],['probe-admission-preflight'])
            self.assertFalse((s['out']/'verifier39').exists())

    def test_existing_full39_is_never_overwritten_or_rerun(self):
        with started() as (s, review, payload):
            (s['out']/'verifier39').mkdir()
            with self.assertRaisesRegex(ValueError,'verifier39 attempt already exists'):
                exec(CELL,s)
            s['files'].upload.assert_not_called()
            s['run'].assert_not_called()

    def test_probe_gate_and_frozen_input_gate_still_block(self):
        for frozen_failure in (False,True):
            with started() as (s, review, payload):
                if frozen_failure:
                    s['require_validation_binding'].side_effect=ValueError('TEST_ONLY changed payload')
                else:
                    s['statuses']['decomposition-probe']['exit_code']=1
                with self.assertRaises(ValueError):
                    exec(CELL,s)
                s['run'].assert_not_called()
                s['files'].upload.assert_not_called()
                s['download_archive'].assert_called_once()

    def test_existing_admission_statuses_and_log_only_collisions_get_unique_names(self):
        with started() as (s, review, payload):
            prior={'state':'failed','exit_code':1}
            s['statuses']['probe-admission']=dict(prior)
            s['statuses']['probe-admission-preflight']={'state':'completed','exit_code':0}
            (s['out']/'probe-admission-retry-1.stderr.log').write_bytes(b'PREVIOUS_LOG')
            exec(CELL,s)
            self.assertEqual([c.args[0] for c in s['run'].call_args_list],
                ['probe-admission-preflight-retry-1','probe-admission-retry-2','verifier39'])
            self.assertEqual(s['statuses']['probe-admission'],prior)
            self.assertEqual((s['out']/'probe-admission-retry-1.stderr.log').read_bytes(),b'PREVIOUS_LOG')

    def test_existing_verifier_status_blocks_even_without_output_directory(self):
        with started() as (s, review, payload):
            s['statuses']['verifier39']={'state':'interrupted'}
            with self.assertRaisesRegex(ValueError,'verifier39 attempt already exists'):
                exec(CELL,s)
            s['files'].upload.assert_not_called()
            s['run'].assert_not_called()

    def test_actual_frozen_run_helper_preserves_collided_stages_and_exclusive_logs(self):
        book=json.loads((ROOT/'scripts/colab_atomic_verifier_cellfix11.ipynb').read_bytes())
        setup=next(c['source'] for c in book['cells'] if c['cell_type']=='code')
        setup=''.join(setup) if isinstance(setup,list) else setup
        helper=next(ast.get_source_segment(setup,n) for n in ast.parse(setup).body
                    if isinstance(n,ast.FunctionDef) and n.name=='run')
        self.assertIn('assert name not in statuses',helper)
        self.assertIn(".open('x')",helper)
        with started() as (s, review, payload):
            # Reproduce the user state with the exact released helper, rather
            # than a mock that silently accepts duplicate stage names.
            old={'state':'failed','exit_code':1,'elapsed_ms':7}
            s['statuses']['probe-admission']=dict(old)
            s['statuses']['probe-admission-preflight']={'state':'completed','exit_code':0}
            for name in ('probe-admission','probe-admission-preflight'):
                for suffix in ('.stdout.log','.stderr.log'):
                    (s['out']/(name+suffix)).write_bytes(b'KEEP_OLD_LOG')
            (s['out']/'probe-admission-retry-1.stdout.log').write_bytes(b'LOG_ONLY')
            (s['root']).mkdir()
            launched=[]

            def popen(command, **kw):
                launched.append(command)
                if '--output-dir' in command:
                    full=s['out']/'verifier39';full.mkdir(exist_ok=False)
                    (full/'metrics.json').write_text(json.dumps({'automated_gate_pass':False}))
                return SimpleNamespace(wait=lambda **opts:0,pid=-1)

            s.update(time=time,env={},bundle=Mock(),
                subprocess=SimpleNamespace(Popen=popen,TimeoutExpired=TimeoutError))
            exec(helper,s)
            exec(CELL,s)
            self.assertEqual(s['statuses']['probe-admission'],old)
            self.assertEqual(s['statuses']['probe-admission-retry-2']['exit_code'],0)
            self.assertEqual(s['statuses']['probe-admission-preflight-retry-1']['exit_code'],0)
            self.assertEqual(len(launched),3)
            for name in ('probe-admission','probe-admission-preflight'):
                for suffix in ('.stdout.log','.stderr.log'):
                    self.assertEqual((s['out']/(name+suffix)).read_bytes(),b'KEEP_OLD_LOG')


if __name__=='__main__':
    unittest.main(verbosity=2)
