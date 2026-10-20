"""Development regressions and token-filter feasibility, not held-out/model quality."""
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import tempfile
import unittest

from research_rag.tests.test_atomic_smoke_cellfix3 import scoped, request
from research_rag.tests.test_atomic_verifier import a, n, assessment, observation, operand, numeric, run
from research_rag.tests import test_atomic_assessment_v8 as h

d = importlib.import_module('04_factchecker.inference.atomic_decoding')


class EvidenceTests(unittest.TestCase):
    def sample(self, context='The relay status was not reported.', truth='false'):
        claim='The relay failed.'
        p=scoped(claim,'relay','failed')
        return claim,p,context,assessment([observation('relay',truth,context)])

    def test_missing_result_cannot_mean_false_or_true(self):
        for truth in ('false','true'):
            claim,p,ctx,raw=self.sample(truth=truth)
            with self.assertRaisesRegex(ValueError,'missing_evidence_is_not_false'):
                a.assess_part(raw,p,ctx)
            raw['observations'][0]['truth']='unknown'
            self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'not_enough_info')

    def test_direct_denial_still_refutes(self):
        claim,p,ctx,raw=self.sample('The relay did not fail.')
        self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'contradict')

    def test_other_members_missing_status_does_not_erase_a_witness(self):
        claim='Some relays failed.';ctx='Relay Amber failed; relay Violet was not evaluated.'
        p=scoped(claim,'relays','failed',quantifier='some')
        self.assertEqual(a.assess_part(assessment([observation('Relay Amber','true',ctx)]),p,ctx)['assessed_label'],'support')

    def test_none_uses_positive_predicate_before_quantifier(self):
        claim='None of the valves leaked.';ctx='Valve Iris leaked. Valve Oak did not.'
        p=scoped(claim,'valves','leaked',quantifier='none')
        bad=assessment([observation('Valve Iris','false',ctx)])
        with self.assertRaisesRegex(ValueError,'positive_predicate_before_quantifier'):
            a.assess_part(bad,p,ctx)
        bad['observations'][0]['truth']='true'
        self.assertEqual(a.assess_part(bad,p,ctx)['assessed_label'],'contradict')

    def test_missing_member_under_none_cannot_be_negative(self):
        claim='None of the valves leaked.';ctx='Iris did not leak, but Oak status was unreported.'
        p=scoped(claim,'valves','leaked',quantifier='none')
        with self.assertRaisesRegex(ValueError,'missing_evidence_is_not_false'):
            a.assess_part(assessment([observation('Oak','false',ctx)]),p,ctx)

    def test_closed_all_some_none_aggregation_is_unchanged(self):
        for quantifier, truths, expected in (
            ('all',['true','true'],'support'),('all',['true','false'],'contradict'),
            ('some',['false','false'],'contradict'),('none',['false','false'],'support')):
            p=scoped('The relays passed.','relays','passed',quantifier=quantifier)
            ctx='The entire fleet was Iris and Oak. ' + ' '.join(
                member + (' passed.' if truth=='true' else ' did not pass.')
                for member,truth in zip(('Iris','Oak'),truths))
            raw=assessment([observation(member,truth,ctx) for member,truth in zip(('Iris','Oak'),truths)],complete=True)
            self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],expected)

    def test_incomplete_population_never_proves_all(self):
        claim='Every relay passed.';ctx='Iris passed; other relays were unreported.'
        p=scoped(claim,'relay','passed',quantifier='all')
        self.assertEqual(a.assess_part(assessment([observation('Iris','true',ctx)]),p,ctx)['assessed_label'],'not_enough_info')

    def test_subset_success_is_not_a_negative_observation(self):
        claim='Every shard improved precision.';ctx='Two shards improved precision.'
        p=scoped(claim,'shard','precision',quantifier='all')
        with self.assertRaisesRegex(ValueError,'observation_polarity_mismatch'):
            a.assess_part(assessment([observation('shards','false',ctx)]),p,ctx)

    def test_single_after_value_is_neither_reduction_nor_counterevidence(self):
        claim='The revision reduced latency.'
        ctx='Latency was 17 ms after the revision. No baseline latency was reported.'
        p=scoped(claim,'revision','latency')
        for truth in ('true','false'):
            with self.assertRaisesRegex(ValueError,'missing_evidence_is_not_false'):
                a.assess_part(assessment([observation('revision',truth,ctx)]),p,ctx)

    def test_month_counterexample_outside_population_repairs(self):
        claim='Every trial in July improved throughput.'
        ctx='The June trial reduced throughput.'
        p=scoped(claim,'trial','throughput',quantifier='all',condition='in July')
        with self.assertRaisesRegex(ValueError,'observation_scope_mismatch'):
            a.assess_part(assessment([observation('trial','false',ctx)]),p,ctx)

    def test_opposed_condition_counterexample_is_rejected(self):
        claim='Every batch in the wet-soil group increased yield.'
        ctx='A dry-soil batch lost yield.'
        p=scoped(claim,'batch','yield',quantifier='all',condition='in the wet-soil group')
        with self.assertRaisesRegex(ValueError,'observation_scope_mismatch'):
            a.assess_part(assessment([observation('batch','false',ctx)]),p,ctx)

    def test_whole_context_does_not_bind_generic_member_to_opposed_groups(self):
        claim='Every batch in the cold-room group improved yield.'
        ctx='Every cold-room batch gained yield. A hot-room batch lost yield.'
        p=scoped(claim,'batch','yield',quantifier='all',condition='in the cold-room group')
        with self.assertRaisesRegex(ValueError,'observation_scope_binding_unresolved'):
            a.assess_part(assessment([observation('batch','false',ctx)]),p,ctx)
        good=assessment([observation('cold-room batch','true',ctx.split('. ')[0]+'.')],complete=True)
        self.assertEqual(a.assess_part(good,p,ctx)['assessed_label'],'support')

    def test_workload_similarity_does_not_invent_identity(self):
        claim='The encoder improved recall.';ctx='On the encoding workload, recall improved.'
        p=scoped(claim,'encoder','recall')
        raw=assessment([observation('workload','true',ctx)])
        self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'not_enough_info')

    def test_repair_and_exhaustion_stay_within_budget(self):
        claim,p,ctx,bad=self.sample();good=deepcopy(bad)
        good['observations'][0]['truth']='unknown'
        good['missing_information']=['The relay outcome was not reported.']
        result,backend=run([{'parts':[p],'unresolved':[]},bad,good],claim,ctx,
            max_new_tokens=1536,timeout_seconds=180)
        self.assertEqual(result['backend_calls'],3)
        self.assertEqual(result['assessed_label'],'not_enough_info')
        self.assertIn('Missing/unreported',backend.calls[-1][0][-1]['content'])
        failed,_=run([{'parts':[p],'unresolved':[]},bad,bad],claim,ctx)
        self.assertEqual(failed['stop_reason'],'invalid_output_exhausted')
        self.assertIsNone(failed['assessed_label'])


class NumericTests(unittest.TestCase):
    def test_temporal_adverbs_are_not_units_but_physical_units_remain_required(self):
        for adverb in ('afterward','afterwards','previously','subsequently','then'):
            ctx='Precision was 0.92 '+adverb+'.'
            self.assertEqual(n.numeric_requirements(ctx)[0]['unit'],'')
            n._operand(operand('0.92'),ctx)
            self.assertTrue(d.operand_schema(ctx))
        with self.assertRaisesRegex(ValueError,'numeric_unit_required'):
            n._operand(operand('24'),'The pressure was 24 pascals.')

    def test_two_metrics_bind_only_the_selected_ordered_pair(self):
        claim='The revision increased precision.'
        ctx='After the revision, precision fell from 0.93 to 0.87, while recall rose from 0.68 to 0.75.'
        record=numeric('change',ctx,operand('0.93'),operand('0.87'))
        self.assertEqual(n.check_numeric(record,claim,ctx,metric='precision')['truth'],'false')
        wrong=numeric('change',ctx,operand('0.68'),operand('0.75'))
        self.assertEqual(n.check_numeric(wrong,claim,ctx,metric='precision')['truth'],'unknown')
        reverse=numeric('change',ctx,operand('0.87'),operand('0.93'))
        self.assertEqual(n.check_numeric(reverse,claim,ctx,metric='precision')['truth'],'unknown')

    def test_repeated_numbers_across_metrics_cannot_be_cross_joined(self):
        claim='The revision increased precision.'
        ctx='Precision rose from 0.71 to 0.89, while recall rose from 0.89 to 0.95.'
        record=numeric('change',ctx,operand('0.71'),operand('0.95'))
        self.assertEqual(n.check_numeric(record,claim,ctx,metric='precision')['truth'],'unknown')

    def test_shared_negation_or_modal_is_not_removed_by_clause_selection(self):
        claim='The revision increased precision.'
        for prefix in ('It is not true that ','It was expected that ','Hypothetically, '):
            ctx=prefix+'precision rose from 0.71 to 0.89, while recall rose from 0.62 to 0.78.'
            record=numeric('change',ctx,operand('0.71'),operand('0.89'))
            self.assertEqual(n.check_numeric(record,claim,ctx,metric='precision')['truth'],'unknown')

    def test_retraction_is_not_discarded(self):
        claim='The revision increased precision.'
        ctx='Precision rose from 0.71 to 0.89, but this measurement was incorrect.'
        record=numeric('change',ctx,operand('0.71'),operand('0.89'))
        self.assertEqual(n.check_numeric(record,claim,ctx,metric='precision')['truth'],'unknown')

    def test_context_can_bind_one_object_modifier_without_dropping_statistic(self):
        claim='The update reduced mean packet latency.'
        for phrase,expected in (('For the same packets and conditions, mean latency','true'),
                ('For different packets, mean latency','unknown'),
                ('For the same packets, median latency','unknown'),('Mean latency','unknown')):
            ctx=phrase+' was 63 ms before the update and 47 ms after it.'
            record=numeric('change',ctx,operand('63','ms'),operand('47','ms'))
            self.assertEqual(n.check_numeric(record,claim,ctx,metric='mean packet latency')['truth'],expected)

    def test_explicit_before_and_after_pair_is_not_split(self):
        claim='The revision reduced latency.';ctx='Latency was 63 ms before revision and 47 ms after revision.'
        record=numeric('change',ctx,operand('63','ms'),operand('47','ms'))
        self.assertEqual(n.check_numeric(record,claim,ctx,metric='latency')['truth'],'true')

    def test_incompatible_units_and_ambiguous_chronology_stay_unknown(self):
        claim='The revision reduced delay.'
        for ctx,left,right in (('Delay fell from 63 ms to 47 seconds.',operand('63','ms'),operand('47','seconds')),
                ('Delay readings were 63 ms and 47 ms.',operand('63','ms'),operand('47','ms'))):
            self.assertEqual(n.check_numeric(numeric('change',ctx,left,right),claim,ctx,metric='delay')['truth'],'unknown')


class TokenTests(unittest.TestCase):
    setUp=h.AssessmentTokenFilterTests.setUp
    accepts=h.AssessmentTokenFilterTests.accepts
    ordered=h.AssessmentTokenFilterTests.ordered

    def test_missing_result_false_is_filtered_but_unknown_has_legal_path(self):
        claim,p,ctx,raw=EvidenceTests().sample()
        self.assertFalse(self.accepts(self.ordered(raw),request(claim,p,ctx)))
        raw['observations'][0]['truth']='unknown'
        self.assertTrue(self.accepts(self.ordered(raw),request(claim,p,ctx)))

    def test_wrong_condition_is_filtered(self):
        claim='Every batch in the wet-soil group improved yield.';ctx='A dry-soil batch lost yield.'
        p=scoped(claim,'batch','yield',quantifier='all',condition='in the wet-soil group')
        raw=assessment([observation('batch','false',ctx)])
        self.assertFalse(self.accepts(self.ordered(raw),request(claim,p,ctx)))

    def test_ordered_pair_filter_rejects_other_metric_and_reversed_operands(self):
        claim='The revision increased precision.'
        ctx='After the revision, precision fell from 0.93 to 0.87, while recall rose from 0.68 to 0.75.'
        p=scoped(claim,'revision','precision')
        raw=assessment([observation('revision','false',ctx,numeric('change',ctx,operand('0.93'),operand('0.87')))])
        self.assertTrue(self.accepts(self.ordered(raw),request(claim,p,ctx)))
        for lhs,rhs in (('0.68','0.75'),('0.87','0.93')):
            bad=deepcopy(raw);bad['observations'][0]['numeric'].update(left=operand(lhs),right=operand(rhs))
            self.assertFalse(self.accepts(self.ordered(bad),request(claim,p,ctx)))

    def test_dimensionless_afterward_has_a_valid_token_path(self):
        claim='The update increased precision.';ctx='Precision rose from 0.71 before the update to 0.88 afterward.'
        p=scoped(claim,'update','precision')
        raw=assessment([observation('update','true',ctx,numeric('change',ctx,operand('0.71'),operand('0.88')))])
        self.assertTrue(self.accepts(self.ordered(raw),request(claim,p,ctx)))
        self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'support')


class TraceAndAnnotationTests(unittest.TestCase):
    def fixtures(self):
        return json.loads((Path(__file__).parent/'fixtures/atomic_cellfix5_full39_assessments.json').read_text())

    def test_real_old_missing_and_scope_errors_enter_repair(self):
        expected={'scope:none:contradict':'positive_predicate_before_quantifier',
            'scope:none:not_enough_info':'missing_evidence_is_not_false',
            'scope:entity:not_enough_info':'missing_evidence_is_not_false',
            'scope:time:support':'observation_scope',
            'scope:condition:support':'observation_scope',
            'scope:time:not_enough_info':'missing_evidence_is_not_false',
            'scope:direction:not_enough_info':'missing_evidence_is_not_false',
            'scope:condition:not_enough_info':'observation_scope',
            'scope:universal:not_enough_info':'observation_polarity_mismatch'}
        for row in self.fixtures():
            c=row['case']
            if c['example_id'] not in expected:continue
            with self.subTest(case=c['example_id']):
                with self.assertRaisesRegex(ValueError,expected[c['example_id']]):
                    p=row['parts'][0];a.assess_part(p['output'],p['part'],c['context'])

    def test_real_numeric_trace_fixes_except_old_afterward_operand_needs_regeneration(self):
        expected={'scope:direction:support':'support','scope:direction:contradict':'contradict',
            'scope:metric:contradict':'contradict'}
        for row in self.fixtures():
            c=row['case']
            if c['example_id'] in expected:
                with self.subTest(case=c['example_id']):
                    p=row['parts'][0]
                    self.assertEqual(a.assess_part(p['output'],p['part'],c['context'])['assessed_label'],expected[c['example_id']])

    def test_annotation_changes_only_two_labels_and_three_rationales(self):
        from research_rag.evaluation import evaluate_atomic_verifier as r
        criteria,cases,*_=r.load_frozen(r.CRITERIA)
        original={f['case']['example_id']:f['case'] for f in self.fixtures()}
        self.assertEqual(sum(c['label']!=original[c['example_id']]['label'] for c in cases),2)
        self.assertEqual(sum('annotation_version' in c for c in cases),3)
        self.assertTrue(all(c['claim']==original[c['example_id']]['claim'] and c['context']==original[c['example_id']]['context'] for c in cases))
        self.assertEqual(criteria['min_correct_labels_recognized'],39)
        self.assertEqual(criteria['max_false_support'],0)

    def test_annotation_bound_to_original_claim_context_and_label(self):
        from research_rag.evaluation import evaluate_atomic_verifier as r
        criteria=json.loads(r.CRITERIA.read_text())
        path=r.CRITERIA.with_name(criteria['annotation_file'])
        original=[f['case'] for f in self.fixtures()]
        with tempfile.TemporaryDirectory() as tmp:
            copy=Path(tmp)/'annotation.json';spec=json.loads(path.read_text())
            for key in ('context_sha256','claim_sha256','original_label'):
                bad=deepcopy(spec);bad['cases'][0][key]='changed';copy.write_text(json.dumps(bad))
                with self.assertRaisesRegex(ValueError,'Adjudication input mismatch'):
                    r.apply_adjudication(original,copy)


if __name__=='__main__':
    unittest.main()
