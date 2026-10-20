"""Workflow tests with disposable synthetic data; no held-out outcomes or model weights."""
from contextlib import contextmanager
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'research-runs/atomic-cellfix8-candidate/workspace'
sys.path.insert(0,str(SOURCE))
from scripts import atomic_cellfix8_workflow as w
from scripts.atomic_cellfix8_binding import verify


class WorkflowTests(unittest.TestCase):
    def test_original_gold_and_review_binding_are_unchanged(self):
        folder=ROOT/'docs/validation/atomic-cellfix8-v1'
        actual=verify(folder,w.r.sha256(w.r.CRITERIA))
        self.assertFalse(actual['new_human_signature_created'])
        old=ROOT/'docs/validation/atomic-cellfix6-v1'
        for name in ('cases.jsonl','inputs.jsonl','criteria.json'):
            self.assertEqual((folder/'original'/name).read_bytes(),(old/name).read_bytes())
        with self.assertRaises(ValueError):verify(folder,'0'*64)

    def test_validation_configuration_keeps_original_model_budget_and_no_gold_in_inputs(self):
        spec,criteria,cases=w.configuration(ROOT/'docs/validation/atomic-cellfix8-v1')
        frozen,*_=w.r.load_frozen(w.r.CRITERIA)
        for key in ('base_model','base_revision','max_calls_per_case','max_attempts','max_new_tokens','case_deadline_seconds','structured_decoder'):
            self.assertEqual(criteria[key],frozen[key])
        self.assertEqual(len(cases),30);self.assertEqual(criteria['maximum_total_backend_calls'],240)
        self.assertEqual(sum(criteria['dataset_groups'].values()),30)
        self.assertFalse(spec['inference_completed'])

    def test_failed_full39_blocks_validation_before_loader_or_output_creation(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'research-runs') as temp:
            folder=Path(temp)/'full39';folder.mkdir()
            (folder/'summary.json').write_text('{"experiment_completed":true,"automated_gate_pass":false,"prediction_count":39}')
            loader=Mock()
            with self.assertRaisesRegex(ValueError,'Successful full39'):
                w.run_validation(Path(temp)/'must-not-exist',Path(temp)/'probe',folder,ROOT/'docs/validation/atomic-cellfix8-v1',loader)
            loader.assert_not_called();self.assertFalse((Path(temp)/'must-not-exist').exists())

    def test_wrong_review_hash_or_unsigned_review_cannot_admit(self):
        criteria,*_=w.r.load_frozen(w.r.CRITERIA)
        with tempfile.TemporaryDirectory(dir=ROOT/'research-runs') as temp:
            directory=Path(temp);(directory/'predictions.jsonl').write_text('[]')
            review={'criteria_sha256':w.r.sha256(w.r.CRITERIA),'predictions_sha256':'0'*64,
                'reviewer_kind':'human','reviewer':'TEST_ONLY','review_completed':True,'cases':[]}
            (directory/'semantic-review.json').write_text(json.dumps(review))
            with self.assertRaisesRegex(ValueError,'bound to this candidate'):
                w.require_human_review(directory,[],criteria['human_review_rubric'])

    def test_full39_wrong_model_is_rejected_even_with_success_flags(self):
        criteria,cases,_,_,_,baseline,_=w.r.load_frozen(w.r.CRITERIA)
        with tempfile.TemporaryDirectory(dir=ROOT/'research-runs') as temp,patch.object(w.r,'require_probe_review'):
            directory=Path(temp)
            w.r.write_json(directory/'summary.json',{'experiment_completed':True,'automated_gate_pass':True,'prediction_count':39})
            (directory/'criteria.json').write_bytes(w.r.CRITERIA.read_bytes());w.r.write_json(directory/'cases.json',cases)
            w.r.write_json(directory/'provenance.json',{'criteria_sha256':w.r.sha256(w.r.CRITERIA),
                'source_sha256':criteria['source_sha256'],'prompt_sha256':criteria['prompt_sha256'],
                'model':{**baseline['model_metadata'],'revision':'wrong-revision','max_new_tokens':1536,'structured_decoder':criteria['structured_decoder']}})
            with self.assertRaisesRegex(ValueError,'provenance changed'):w.require_full39(directory,Path(temp)/'probe')

    def test_synthetic_end_to_end_validation_loop_saves_blind_calls_and_metrics(self):
        from research_rag.tests.test_atomic_verifier import assessment,observation,part
        frozen,_,_,_,_,baseline,_=w.r.load_frozen(w.r.CRITERIA)
        # One new disposable case tests orchestration, never validation30 quality.
        case={'example_id':'TEST_ONLY','claim':'The audit used handwritten forms.',
              'context':'The audit did not use any handwritten forms.','label':'contradict','dataset_group':'test_paper'}
        criteria={**frozen,'cases_per_backend':1,'min_correct_labels_recognized':1,
                  'maximum_total_backend_calls':8,'maximum_generated_tokens':12288,'dataset_groups':{'test_paper':1}}
        class FakeBackend:
            on_generation=None
            @contextmanager
            def generation_deadline(self,deadline):yield True
            def generate_json(self,messages,*,max_new_tokens):
                payload=json.loads(messages[1]['content'])
                if set(payload)=={'claim'}:
                    value={'parts':[{'quote':case['claim'],'quantifier':'atomic','scope':{'entity':'audit','metric':'used handwritten forms','time':'','condition':''}}],'unresolved':[]}
                else:
                    if set(payload)!={'claim','part','context'}:raise AssertionError('Gold leaked to backend')
                    value=assessment([observation('audit','false',case['context'])])
                self.on_generation({'raw_output':json.dumps(value),'json_valid':True,'parse_error_type':None,
                    'generated_tokens':20,'prompt_tokens':30,'max_new_tokens':max_new_tokens,
                    'structured_decoder':criteria['structured_decoder'],'deadline_stop_enabled':True,
                    'schema_sha256':w.r.decoding.schema_sha256(w.r.decoding.schema_for(messages)[0])})
                return value
        @contextmanager
        def loader(kind,settings):
            yield FakeBackend(),{**baseline['model_metadata'],'structured_decoder':criteria['structured_decoder'],'max_new_tokens':1536}
        with tempfile.TemporaryDirectory(dir=ROOT/'research-runs') as temp,patch.object(w,'configuration',return_value=({'TEST_ONLY':True},criteria,[case])),patch.object(w,'require_full39',return_value={'TEST_ONLY':True}):
            path=Path(temp)/'out'
            result=w.run_validation(path,Path(temp)/'probe',Path(temp)/'full',ROOT/'docs/validation/atomic-cellfix8-v1',loader)
            self.assertTrue(result['experiment_completed']);self.assertTrue(result['automated_gate_pass'])
            self.assertFalse(result['overall_pass']);self.assertFalse(result['promoted_to_serving'])
            metrics=w.read(path/'metrics.json');self.assertEqual(metrics['correct_labels'],1)
            self.assertEqual(metrics['false_support'],0)
            self.assertEqual(len(w.rows(path/'predictions.jsonl')),1)
            template=w.read(path/'semantic-review.json');self.assertFalse(template['review_completed'])
            self.assertTrue((path/'HUMAN_REVIEW.html').exists())
            events=w.rows(path/'calls.jsonl');events[1]['raw_output']='{}'
            with self.assertRaises(ValueError):w.measured_score(w.rows(path/'predictions.jsonl'),[case],criteria,events)


if __name__=='__main__':unittest.main(verbosity=2)
