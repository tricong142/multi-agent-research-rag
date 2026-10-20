"""Cf7 development regressions: real cf6 failures and new independent sentences."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import unittest

from research_rag.tests.test_atomic_smoke_cellfix3 import scoped, request
from research_rag.tests.test_atomic_verifier import assessment, observation, numeric, operand, run
from research_rag.tests import test_atomic_assessment_v8 as h

a=importlib.import_module('04_factchecker.inference.atomic_verifier')
d=importlib.import_module('04_factchecker.inference.atomic_decoding')
rules=importlib.import_module('04_factchecker.inference.assessment_decisions')


class DecisionTests(unittest.TestCase):
    def test_real_wrong_scope_and_unknown_enter_repair(self):
        fixtures=json.loads((Path(__file__).parent/'fixtures/atomic_cellfix6_smoke_traces.json').read_text())
        rejected=set()
        for row in fixtures:
            if row['case']['label']==row['result']['assessed_label']:continue
            for event in row['result']['trace']:
                if event['stage']=='decompose' or not event.get('valid'):continue
                payload=json.loads(event['messages'][1]['content'])
                with self.subTest(case=row['case']['example_id'],stage=event['stage']):
                    with self.assertRaises(ValueError):a.assess_part(event['output'],payload['part'],payload['context'])
                rejected.add(row['case']['example_id'])
        self.assertEqual(len(rejected),5)

    def test_explicit_denial_matches_scope_and_refutes(self):
        claim='The audit used handwritten forms.';ctx='The audit did not use any handwritten forms.'
        p=scoped(claim,'audit','used handwritten forms')
        good=assessment([observation('audit','false',ctx)])
        self.assertEqual(a.assess_part(good,p,ctx)['assessed_label'],'contradict')
        for scope in ('mismatched','unknown'):
            bad=deepcopy(good);bad['scope_match']=scope
            with self.assertRaisesRegex(ValueError,'scope_is_not_agreement'):a.assess_part(bad,p,ctx)

    def test_missing_or_modal_evidence_keeps_unknown(self):
        claim='The audit used handwritten forms.';p=scoped(claim,'audit','used handwritten forms')
        for ctx in ('The audit protocol was not reported.','The audit might use handwritten forms.'):
            self.assertIsNone(rules.decision_evidence(p,ctx))
            raw=assessment([observation('audit','unknown',ctx)])
            self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'not_enough_info')

    def test_different_target_and_time_never_get_forced(self):
        p=scoped('During March, the audit used forms.','audit','used forms',time='During March')
        for ctx in ('During April, the audit did not use forms.','During March, another audit did not use forms.'):
            self.assertIsNone(rules.decision_evidence(p,ctx))

    def test_same_member_conflicting_reports_remain_unknown(self):
        p=scoped('The review used checklists.','review','used checklists')
        ctx='The review used checklists. The review did not use checklists.'
        self.assertIsNone(rules.decision_evidence(p,ctx))

    def test_one_counterexample_refutes_all_without_roster(self):
        claim='All channels improved after calibration.'
        ctx='Two channels improved after calibration, but a third channel worsened.'
        p=scoped(claim,'channels','improved',quantifier='all',time='after calibration')
        raw=assessment([observation('a third channel','false',ctx)])
        self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'contradict')
        bad=deepcopy(raw);bad['observations'][0]['truth']='unknown'
        with self.assertRaisesRegex(ValueError,'decisive_witness'):a.assess_part(bad,p,ctx)

    def test_counterexample_outside_explicit_time_is_not_forced(self):
        p=scoped('During April, all channels improved.','channels','improved',quantifier='all',time='During April')
        self.assertIsNone(rules.decision_evidence(p,'During March, a channel worsened.'))

    def test_conflicting_reports_for_same_named_member_stay_unknown(self):
        p=scoped('All channels improved.','channels','improved',quantifier='all')
        self.assertIsNone(rules.decision_evidence(p,'Channel A improved. Channel A worsened.'))

    def test_false_wrapper_plans_and_other_actor_never_force_support(self):
        p=scoped('The audit used forms.','audit','used forms')
        for ctx in ('It is false that the audit used forms.', 'The audit planned to use forms.',
                    'The audit documented a team which used forms.'):
            with self.subTest(context=ctx):self.assertIsNone(rules.decision_evidence(p,ctx))

    def test_embedded_denial_is_not_treated_as_root_clause_counterevidence(self):
        p=scoped('The audit used forms.','audit','used forms')
        self.assertIsNone(rules.decision_evidence(p,'It is not true the audit did not use forms.'))

    def test_qualified_population_substring_cannot_force_support(self):
        p=scoped('Some certified probes improved.','certified probes','improved',quantifier='some')
        self.assertIsNone(rules.decision_evidence(p,'A non-certified probe improved.'))

    def test_two_named_targets_or_planned_numbers_keep_uncertainty(self):
        p=scoped('Model Hazel retained 83% accuracy.','Model Hazel','accuracy')
        for ctx in ('Model Hazel was discussed. Model Alder retained 83% accuracy.',
                    'Model Hazel planned to retain 83% accuracy.'):
            with self.subTest(context=ctx):self.assertIsNone(rules.decision_evidence(p,ctx))

    def test_quantity_in_other_time_cannot_borrow_the_requested_time_from_another_metric(self):
        p=scoped('The audit retained 83% accuracy after calibration.','audit','accuracy',time='after calibration')
        ctx='The audit retained 83% accuracy before calibration. After calibration, latency was measured.'
        self.assertIsNone(rules.decision_evidence(p,ctx))

    def test_counterexample_before_the_claimed_event_cannot_refute_after(self):
        claim='All channels improved after calibration.'
        ctx='Two channels improved after calibration, but a third channel worsened before calibration.'
        p=scoped(claim,'channels','improved',quantifier='all',time='after calibration')
        self.assertIsNone(rules.decision_evidence(p,ctx))
        raw=assessment([observation('a third channel','false',ctx)])
        with self.assertRaisesRegex(ValueError,'observation_scope'):a.assess_part(raw,p,ctx)


class LedgerTests(unittest.TestCase):
    def sample(self):
        claim='The survey evaluated five encoders on three corpora.'
        ctx='Five encoders were evaluated in the survey. Evaluation used three corpora.'
        p=scoped(claim,'survey','evaluated five encoders',condition='on three corpora')
        records=[numeric('value',ctx,operand('5','encoders','five encoders'),operand('5','encoders','Five encoders')),
                 numeric('value',ctx,operand('3','corpora','three corpora'),operand('3','corpora','three corpora'))]
        return claim,p,ctx,assessment([observation('survey','true',ctx,dict(q0=records[0],q1=records[1]))])

    def test_two_sentences_bind_two_distinct_requirements(self):
        _,p,ctx,raw=self.sample()
        result=a.assess_part(raw,p,ctx)
        self.assertEqual(result['assessed_label'],'support')
        self.assertEqual(len(result['observations'][0]['numeric_result']),2)

    def test_duplicate_slot_and_omitted_key_rejected(self):
        _,p,ctx,raw=self.sample()
        for mutation in ('duplicate','omit'):
            bad=deepcopy(raw);ledger=bad['observations'][0]['numeric']
            if mutation=='duplicate':ledger['q1']=ledger['q0']
            else:del ledger['q1']
            with self.assertRaisesRegex(ValueError,'numeric_requirement'):a.assess_part(bad,p,ctx)

    def test_legacy_complete_list_remains_replayable(self):
        _,p,ctx,raw=self.sample();raw['observations'][0]['numeric']=list(raw['observations'][0]['numeric'].values())
        self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'support')

    def test_missing_second_quantity_stays_nei(self):
        _,p,_,_=self.sample();ctx='Five encoders were evaluated in the survey.'
        self.assertIsNone(rules.decision_evidence(p,ctx))
        raw=assessment([observation('survey','unknown',ctx)])
        self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'not_enough_info')

    def test_legacy_numeric_association_unknown_is_never_promoted(self):
        _,p,ctx,raw=self.sample();raw['observations'][0]['truth']='unknown'
        self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'not_enough_info')


class TokenTests(unittest.TestCase):
    setUp=h.AssessmentTokenFilterTests.setUp
    accepts=h.AssessmentTokenFilterTests.accepts
    ordered=h.AssessmentTokenFilterTests.ordered

    def test_keyed_ledger_accepts_correct_and_blocks_duplicate(self):
        claim,p,ctx,raw=LedgerTests().sample()
        self.assertTrue(self.accepts(self.ordered(raw),request(claim,p,ctx)))
        raw['observations'][0]['numeric']['q1']=raw['observations'][0]['numeric']['q0']
        self.assertFalse(self.accepts(self.ordered(raw),request(claim,p,ctx)))

    def test_decisive_denial_cannot_be_decoded_as_mismatched_unknown(self):
        claim='The audit used handwritten forms.';ctx='The audit did not use any handwritten forms.'
        p=scoped(claim,'audit','used handwritten forms')
        good=assessment([observation('audit','false',ctx)])
        self.assertTrue(self.accepts(self.ordered(good),request(claim,p,ctx)))
        good['scope_match']='mismatched'
        self.assertFalse(self.accepts(self.ordered(good),request(claim,p,ctx)))

    def test_unknown_remains_decodable_for_genuinely_missing_metric(self):
        claim='The audit used handwritten forms.';ctx='The audit protocol was not reported.'
        p=scoped(claim,'audit','used handwritten forms')
        raw=assessment([observation('audit','unknown',ctx)])
        self.assertTrue(self.accepts(self.ordered(raw),request(claim,p,ctx)))

    def test_false_multi_quantity_needs_a_real_counterexample_not_all_null(self):
        claim,p,_,_=LedgerTests().sample();ctx='The survey evaluated six encoders.'
        raw=assessment([observation('survey','false',ctx,{'q0':None,'q1':None})])
        self.assertFalse(self.accepts(self.ordered(raw),request(claim,p,ctx)))

    def test_false_single_requirement_can_refute_with_other_requirement_missing(self):
        claim,p,_,_=LedgerTests().sample();ctx='The survey evaluated six encoders.'
        record=numeric('value',ctx,operand('5','encoders','five encoders'),operand('6','encoders','six encoders'))
        raw=assessment([observation('survey','false',ctx,{'q0':record,'q1':None})])
        self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'contradict')
        self.assertTrue(self.accepts(self.ordered(raw),request(claim,p,ctx)))


class RepairTests(unittest.TestCase):
    def test_real_unknown_style_repairs_without_changing_budget(self):
        claim='The audit used handwritten forms.';ctx='The audit did not use any handwritten forms.'
        p=scoped(claim,'audit','used handwritten forms')
        bad=assessment([observation('audit','unknown',ctx)]);bad['scope_match']='mismatched'
        good=assessment([observation('audit','false',ctx)])
        result,_=run([{'parts':[p],'unresolved':[]},bad,good],claim,ctx)
        self.assertEqual(result['assessed_label'],'contradict')
        self.assertEqual(result['backend_calls'],3)
        self.assertEqual(result['trace'][1]['validation_issue'],'scope_is_not_agreement')

    def test_bad_repair_exhausts_instead_of_silently_passing_as_nei(self):
        claim='The audit used handwritten forms.';ctx='The audit did not use any handwritten forms.'
        p=scoped(claim,'audit','used handwritten forms')
        bad=assessment([observation('audit','unknown',ctx)])
        result,_=run([{'parts':[p],'unresolved':[]},bad,bad],claim,ctx)
        self.assertEqual(result['stop_reason'],'invalid_output_exhausted')
        self.assertIsNone(result['assessed_label'])
