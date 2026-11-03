"""Compatibility regression tests; no model inference or synthetic human approval."""
import ast
from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch

from scripts.atomic_cellfix15_replay_compat import patch_workflow
from scripts.patch_kaggle_cellfix15_cell7 import helper

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'research-runs/atomic-cellfix15-candidate/workspace'
sys.path.insert(0,str(SOURCE))
RAW=(ROOT/'scripts/atomic_cellfix15_workflow.py').read_bytes()
SCORE={'n':39,'correct_labels':39,'generated_tokens':100,'checks':{'all_labels_correct':True,
       'within_measured_token_budget':True},'automated_gate_pass':True,'usage_complete':True}


class ReplayCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.w=type(sys)('TEST_ONLY_compatible_workflow')
        exec(compile(patch_workflow(RAW),'compatible-workflow','exec'),cls.w.__dict__)
        cls.frozen=cls.w.r.load_frozen(cls.w.r.CRITERIA)

    def admit(self,score,stored,error=False,human_error=False):
        w=self.w;criteria,cases,_,_,_,baseline,_=self.frozen
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)
            (directory/'criteria.json').write_bytes(w.r.CRITERIA.read_bytes())
            (directory/'cases.json').write_text(json.dumps(cases))
            (directory/'summary.json').write_text(json.dumps({'experiment_completed':True,'automated_gate_pass':True,'prediction_count':39}))
            provenance={'criteria_sha256':w.r.sha256(w.r.CRITERIA),'source_sha256':criteria['source_sha256'],
                'prompt_sha256':criteria['prompt_sha256'],'model':dict(baseline['model_metadata'],
                max_new_tokens=criteria['max_new_tokens'],structured_decoder=criteria['structured_decoder'])}
            (directory/'provenance.json').write_text(json.dumps(provenance))
            (directory/'metrics.json').write_text(json.dumps(stored));before=(directory/'metrics.json').read_bytes()
            (directory/'predictions.jsonl').write_text('{}\n');(directory/'calls.jsonl').write_text('')
            human=Mock(side_effect=ValueError('TEST_ONLY human review rejected') if human_error else None,
                       return_value={'reviewer':'TEST_ONLY_NO_HUMAN_SIGNATURE'})
            with patch.object(w.r,'load_frozen',return_value=self.frozen),patch.object(w.r,'require_probe_review'),\
                 patch.object(w,'measured_score',return_value=deepcopy(score)),patch.object(w,'require_human_review',human):
                if error:
                    with self.assertRaisesRegex(ValueError,'Full39 gate failed on replay'):
                        w.require_full39(directory,directory/'probe')
                    human.assert_not_called()
                elif human_error:
                    with self.assertRaisesRegex(ValueError,'human review rejected'):
                        w.require_full39(directory,directory/'probe')
                else:
                    w.require_full39(directory,directory/'probe');human.assert_called_once()
            self.assertEqual((directory/'metrics.json').read_bytes(),before)

    def test_producer_metrics_without_diagnostic_are_accepted(self):
        stored={k:v for k,v in SCORE.items() if k!='usage_complete'}
        self.admit(SCORE,stored)

    def test_metrics_with_matching_diagnostic_remain_accepted(self):
        self.admit(SCORE,SCORE)

    def test_incomplete_usage_cannot_be_omitted_to_pass(self):
        bad=deepcopy(SCORE);bad['usage_complete']=False
        self.admit(bad,{k:v for k,v in SCORE.items() if k!='usage_complete'},error=True)

    def test_explicit_false_diagnostic_is_not_ignored(self):
        self.admit(SCORE,dict(SCORE,usage_complete=False),error=True)

    def test_wrong_labels_or_tokens_still_reject(self):
        for field,value in [('correct_labels',38),('generated_tokens',0)]:
            with self.subTest(field=field):self.admit(SCORE,dict(SCORE,**{field:value}),error=True)

    def test_extra_metric_key_still_rejects(self):
        self.admit(SCORE,dict(SCORE,invented_diagnostic=True),error=True)

    def test_failed_gate_still_rejects_even_when_metrics_match(self):
        score=dict(SCORE,automated_gate_pass=False)
        self.admit(score,score,error=True)

    def test_failed_human_review_still_rejects(self):
        self.admit(SCORE,SCORE,human_error=True)

    def test_altered_workflow_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'original frozen'):patch_workflow(RAW+b'\n')


class Cell7PackagingTests(unittest.TestCase):
    def test_only_cell7_changes_and_flag_stays_false(self):
        old=json.loads((ROOT/'scripts/kaggle_atomic_verifier_cellfix15.ipynb').read_bytes())
        new=json.loads((ROOT/'scripts/kaggle_atomic_verifier_cellfix15_cell7_fix.ipynb').read_bytes())
        index=[i for i,c in enumerate(old['cells']) if c['cell_type']=='code'][6]
        self.assertEqual(old['metadata'],new['metadata'])
        self.assertEqual(len(old['cells']),len(new['cells']))
        for i,(a,b) in enumerate(zip(old['cells'],new['cells'])):
            if i!=index:self.assertEqual(a,b)
        code=''.join(new['cells'][index]['source'])
        self.assertIn('RUN_VALIDATION30 = False',code)
        self.assertEqual(code,(ROOT/'scripts/kaggle_cellfix15_cell7_replay_compat.py').read_text(encoding='utf-8'))
        scope={}
        with redirect_stdout(io.StringIO()):exec(compile(code,'cell7','exec'),scope)
        self.assertFalse(scope['RUN_VALIDATION30'])
        # Exactly one worker-selection line changes below the added helper.
        original=''.join(old['cells'][index]['source'])
        expected=helper()+original.replace("        worker=str(root/'atomic_workflow_cellfix15.py')\n",
                                          '        worker=_cell7_replay_worker()\n',1)
        self.assertEqual(code,expected)

    def test_helper_preserves_original_and_records_worker_idempotently(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'workspace';out=Path(temp)/'out';root.mkdir();out.mkdir()
            original=root/'atomic_workflow_cellfix15.py';original.write_bytes(RAW)
            scope={'root':root,'out':out,'criteria_sha256':'TEST_ONLY',
                   'manifest':{'atomic_workflow_cellfix15.py':{'sha256':hashlib.sha256(RAW).hexdigest()}}}
            exec(helper(),scope)
            with redirect_stdout(io.StringIO()):
                worker=Path(scope['_cell7_replay_worker']())
                self.assertEqual(Path(scope['_cell7_replay_worker']()),worker)
            self.assertEqual(worker.read_bytes(),patch_workflow(RAW))
            self.assertEqual(original.read_bytes(),RAW)
            record=json.loads((worker.parent/'compatibility.json').read_bytes())
            self.assertFalse(record['producer_metrics_modified']);self.assertFalse(record['frozen_inputs_modified'])
            worker.write_bytes(b'TEST_ONLY_COLLISION')
            with self.assertRaisesRegex(ValueError,'Preserve existing'):scope['_cell7_replay_worker']()
            self.assertEqual(worker.read_bytes(),b'TEST_ONLY_COLLISION')
            self.assertEqual(original.read_bytes(),RAW)


if __name__=='__main__':unittest.main(verbosity=2)
