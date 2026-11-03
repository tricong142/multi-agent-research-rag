"""Only cell 6; synthetic review bytes never act as a real human approval."""
from contextlib import contextmanager,redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock,patch

from scripts import test_cellfix14_cell6 as original

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'scripts/kaggle_cellfix14_cell6_review_upload.py').read_text(encoding='utf-8')
ACTIVE=SOURCE.replace('RUN_FULL39 = False','RUN_FULL39 = True',1)


class Widget:
    def __init__(self,**kwargs):self.value=();self.options=kwargs


@contextmanager
def started():
    with original.started() as (scope,review,payload):
        scope['read_review']=Mock(side_effect=lambda path:scope['files'].upload())
        scope['show_file']=scope['files'].download
        widgets=ModuleType('ipywidgets');widgets.FileUpload=Widget
        display=ModuleType('IPython.display');display.display=Mock()
        with patch.dict(sys.modules,{'ipywidgets':widgets,'IPython.display':display}),redirect_stdout(io.StringIO()):
            yield scope,review,payload


class UploadTests(unittest.TestCase):
    def test_blank_path_waits_for_upload_without_model_or_error(self):
        with started() as (s,review,payload):
            exec(ACTIVE,s)
            s['run'].assert_not_called();s['read_review'].assert_not_called()
            self.assertFalse((s['out']/'verifier39').exists())
            self.assertIn('_cellfix14_probe_review_upload',s)
            self.assertFalse(s['full39_passed'])

    def test_upload_formats_7_and_8_resume_same_cell_and_preserve_helpers_for_cell7(self):
        for version in (7,8):
            with self.subTest(version=version),started() as (s,review,payload):
                exec(ACTIVE,s)
                widget=s['_cellfix14_probe_review_upload']['widget']
                widget.value=({'review.json':{'content':payload}} if version==7 else
                              ({'name':'review.json','content':memoryview(payload)},))
                exec(ACTIVE,s)
                self.assertEqual([c.args[0] for c in s['run'].call_args_list],
                    ['probe-admission-preflight','probe-admission','verifier39'])
                self.assertEqual((s['out']/'reviewed-probe/semantic-review.json').read_bytes(),payload)
                for name in ('preserve_review','probe_files','unused_stage'):self.assertTrue(callable(s[name]))

    def test_uploaded_wrong_hash_never_runs_admission_or_model(self):
        with started() as (s,review,payload):
            exec(ACTIVE,s);review['predictions_sha256']='0'*64
            s['_cellfix14_probe_review_upload']['widget'].value=({'name':'wrong.json','content':json.dumps(review).encode()},)
            with self.assertRaisesRegex(ValueError,'does not match'):exec(ACTIVE,s)
            s['run'].assert_not_called()

    def test_widget_from_another_run_is_not_reused(self):
        with started() as (s,review,payload):
            exec(ACTIVE,s);widget=s['_cellfix14_probe_review_upload']['widget']
            widget.value=({'name':'old.json','content':payload},)
            s['run_id']='TEST_ONLY_ANOTHER_RUN';exec(ACTIVE,s)
            self.assertIsNot(s['_cellfix14_probe_review_upload']['widget'],widget)
            s['run'].assert_not_called()

    def test_missing_widget_dependency_leaves_explicit_path_available(self):
        with started() as (s,review,payload),patch.dict(sys.modules,{'ipywidgets':None}):
            exec(ACTIVE,s);s['run'].assert_not_called()
            self.assertNotIn('_cellfix14_probe_review_upload',s)

    def test_all_other_notebook_cells_and_released_bytes_are_preserved(self):
        old=json.loads((ROOT/'scripts/kaggle_atomic_verifier_cellfix14.ipynb').read_bytes())
        new=json.loads((ROOT/'scripts/kaggle_atomic_verifier_cellfix14_cell6_fix.ipynb').read_bytes())
        changes=[i for i,(a,b) in enumerate(zip(old['cells'],new['cells'])) if a!=b]
        indices=[i for i,c in enumerate(old['cells']) if c['cell_type']=='code']
        self.assertEqual(changes,[indices[5]]);self.assertEqual(old['metadata'],new['metadata'])
        record=json.loads((ROOT/'docs/atomic-verifier-cellfix14-kaggle-validation.json').read_bytes())
        raw=(ROOT/'scripts/kaggle_atomic_verifier_cellfix14.ipynb').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),record['sha256'])


def load_tests(loader,tests,pattern):
    # Reuse all 10 original retry, hash, admission and overwrite protections.
    source=ACTIVE.replace('PROBE_REVIEW_PATH = ""','PROBE_REVIEW_PATH = "/TEST_ONLY/review.json"',1)
    old_started=original.started
    @contextmanager
    def path_started():
        with old_started() as (s,review,payload):
            s['read_review']=lambda path:s['files'].upload()
            s['show_file']=s['files'].download
            yield s,review,payload
    class ExistingGuards(original.Cell6RetryTests):
        def setUp(self):
            p=patch.object(original,'CELL',source);p.start();self.addCleanup(p.stop)
            p=patch.object(original,'started',path_started);p.start();self.addCleanup(p.stop)
    return unittest.TestSuite([loader.loadTestsFromTestCase(UploadTests),loader.loadTestsFromTestCase(ExistingGuards)])


if __name__=='__main__':unittest.main()
