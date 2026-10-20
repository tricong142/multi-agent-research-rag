"""Received failures plus novel development inputs; no held-out validation labels."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import unittest

from research_rag.tests.test_atomic_smoke_cellfix3 import scoped, request
from research_rag.tests.test_atomic_verifier import assessment, observation, run
from research_rag.tests import test_atomic_assessment_v8 as h

a = importlib.import_module('04_factchecker.inference.atomic_verifier')
d = importlib.import_module('04_factchecker.inference.atomic_decoding')
e = importlib.import_module('04_factchecker.inference.assessment_evidence')
r = importlib.import_module('04_factchecker.inference.assessment_reporting')


def traces(cid):
    path = Path(__file__).parent/'fixtures/atomic_cellfix9_full39_traces.json'
    row = next(v for v in json.loads(path.read_bytes()) if v['case']['example_id'] == cid)
    return [(t, json.loads(t['messages'][1]['content'])) for t in row['result']['trace'] if t['stage'] != 'decompose']


def canonical(raw, part, context):
    raw = deepcopy(raw)
    raw['explanation'] = r.ASSESSMENT_NOTE
    for obs in raw['observations']:
        obs['explanation'] = r.OBSERVATION_NOTE
    raw['missing_information'] = [r.missing_reason(part, context)] if raw['missing_information'] else []
    return raw


def closure_sample():
    claim = 'At least one inspected routing relay reduced response time after the revision.'
    ctx = ('The complete inspected set was Copper, Quartz and Zinc. After the revision, '
           'response time increased on Copper and Quartz and stayed unchanged on Zinc.')
    p = scoped(claim, 'inspected routing relay', 'response time', quantifier='some', time='after the revision')
    return claim, p, ctx, assessment([observation('Copper, Quartz and Zinc', 'false', ctx)], complete=True)


class ClosureTests(unittest.TestCase):
    def test_real_some_requires_complete_roster_and_retains_false_truth(self):
        t, payload = traces('scope:existential:contradict')[-1]
        p, ctx = payload['part'], payload['context']
        witness = e.population_witness(p, ctx)
        self.assertEqual(witness['truth'], 'false')
        raw = assessment([observation(witness['members'][0], 'false', witness['quotes'][0])], complete=True)
        result = a.assess_part(raw, p, ctx)
        self.assertEqual(result['assessed_label'], 'contradict')
        self.assertEqual(result['population_binding_basis'], 'unique_complete_selection_set')
        with self.assertRaisesRegex(ValueError, 'population_witness|population_closure'):
            a.assess_part(t['output'], p, ctx)

    def test_new_selection_set_with_mixed_negative_outcomes_closes_some(self):
        _, p, ctx, raw = closure_sample()
        self.assertEqual(a.assess_part(raw, p, ctx)['assessed_label'], 'contradict')

    def test_new_all_member_sentences_fit_full_roster_window(self):
        claim = 'Every inspected relay improved recall.'
        ctx = ('The inspected relays were Copper, Quartz and Zinc. Copper improved recall. '
               'Quartz improved recall. Zinc improved recall.')
        p = scoped(claim, 'inspected relay', 'recall', quantifier='all')
        self.assertEqual(e.population_witness(p, ctx)['truth'], 'true')
        self.assertIsNone(e.population_witness(p, ctx + ' The result for Zinc was retracted.'))

    def test_missing_member_outcome_does_not_close(self):
        _, p, ctx, _ = closure_sample()
        ctx = ctx.replace('and stayed unchanged on Zinc', '. Zinc results were not reported')
        self.assertIsNone(e.population_witness(p, ctx))

    def test_wrong_selector_or_competing_population_does_not_bind(self):
        _, p, ctx, _ = closure_sample()
        for changed in (ctx.replace('complete inspected', 'complete surveyed'),
                        ctx+' Another inspected population was reported.',
                        ctx+' These were storage disks.',
                        ctx.replace('complete inspected', 'partial inspected')):
            with self.subTest(context=changed):
                self.assertIsNone(e.population_witness(p, changed))

    def test_named_types_and_scopes_still_take_precedence(self):
        _, p, ctx, _ = closure_sample()
        for changed in (ctx.replace('After the revision', 'Before the revision'),
                        ctx.replace('After the revision', 'After the repair')):
            self.assertIsNone(e.population_witness(p, changed))

    def test_wrong_member_truth_cannot_pass_despite_canonical_prose(self):
        _, p, ctx, raw = closure_sample()
        raw['observations'][0]['truth'] = 'true'
        with self.assertRaises(ValueError):
            a.assess_part(raw, p, ctx)

    def test_duplicate_member_repairs_within_existing_budget(self):
        claim, p, ctx, good = closure_sample()
        bad = deepcopy(good)
        bad['coverage']['members'] *= 4
        dec = {'parts': [{k: p[k] for k in ('quote', 'quantifier', 'scope')}], 'unresolved': []}
        result, _ = run([dec, bad, good], claim, ctx, max_calls=8, max_attempts=2, max_new_tokens=1536, timeout_seconds=180)
        self.assertEqual((result['assessed_label'], result['backend_calls']), ('contradict', 3))
        self.assertEqual(result['trace'][1]['validation_issue'], 'duplicate_coverage_member')
        result, _ = run([dec, bad, bad], claim, ctx, max_calls=8, max_attempts=2, max_new_tokens=1536, timeout_seconds=180)
        self.assertEqual(result['stop_reason'], 'invalid_output_exhausted')
        self.assertIsNone(result['assessed_label'])


class ReportingTests(unittest.TestCase):
    def test_none_wrong_prose_is_retained_but_not_published_as_evidence(self):
        t, payload = traces('scope:none:support')[-1]
        raw = deepcopy(t['output'])
        result = a.assess_part(raw, payload['part'], payload['context'])
        self.assertEqual(raw, t['output'])
        self.assertEqual(result['assessed_label'], 'support')
        self.assertIn('establishing NONE', result['explanation'])
        self.assertIn('does not satisfy', result['observations'][0]['explanation'])
        self.assertEqual(result['model_explanation'], raw['explanation'])
        self.assertEqual(result['observations'][0]['model_explanation'], raw['observations'][0]['explanation'])

    def test_new_none_and_some_share_positive_predicate_but_different_labels(self):
        ctx = 'The monitored vents were Copper, Quartz and Zinc. The report records no leaks for any of these three vents.'
        for quantifier, claim, expected in (
                ('none', 'None of the monitored vents leaked.', 'support'),
                ('some', 'At least one monitored vent leaked.', 'contradict')):
            p = scoped(claim, 'monitored vents', 'leaked', quantifier=quantifier)
            raw = assessment([observation('Copper, Quartz and Zinc', 'false', ctx)], complete=True)
            raw['explanation'] = 'All members leaked.'
            result = a.assess_part(raw, p, ctx)
            self.assertEqual(result['assessed_label'], expected)
            self.assertNotIn('All members leaked', result['explanation'])

    def test_real_missing_citation_repair_does_not_relax_guard(self):
        t, payload = traces('scope:direction:not_enough_info')[-1]
        raw, p, ctx = t['output'], payload['part'], payload['context']
        with self.assertRaisesRegex(ValueError, 'unattributed_prose_citation'):
            a.assess_part(raw, p, ctx)
        good = canonical(raw, p, ctx)
        result = a.assess_part(good, p, ctx)
        self.assertEqual(result['assessed_label'], 'not_enough_info')
        self.assertEqual(result['missing_reason'], 'comparison_unresolved')
        self.assertNotIn('Shepherd', result['explanation'])
        dec = {'parts': [{k:p[k] for k in ('quote','quantifier','scope')}], 'unresolved': []}
        result, _ = run([dec, raw, good], payload['claim'], ctx, max_calls=8, max_attempts=2, max_new_tokens=1536, timeout_seconds=180)
        self.assertEqual(result['assessed_label'], 'not_enough_info')
        self.assertEqual(result['backend_calls'], 3)

    def test_real_conjunct_requires_identity_instead_of_other_metric(self):
        t, payload = traces('scope:conjunction:not_enough_info')[-1]
        raw, p, ctx = t['output'], payload['part'], payload['context']
        with self.assertRaisesRegex(ValueError, 'missing_information_wrong_metric'):
            a.assess_part(raw, p, ctx)
        good = canonical(raw, p, ctx)
        result = a.assess_part(good, p, ctx)
        self.assertEqual(result['assessed_label'], 'not_enough_info')
        self.assertEqual(result['missing_reason'], 'target_binding_unresolved')
        self.assertIn('memory', result['missing_information'][0])
        self.assertNotIn('token recall', result['missing_information'][0])
        self.assertIn('extractor', result['missing_information'][0])

    def test_new_absent_target_does_not_claim_reported_numbers_are_missing(self):
        claim = 'The scheduler reduced peak memory.'
        ctx = 'Peak memory declined from 8 to 6 gigabytes on the workload.'
        p = scoped(claim, 'scheduler', 'peak memory')
        raw = assessment([observation('Peak memory', 'unknown', ctx)], missing=['target_binding_unresolved'])
        result = a.assess_part(raw, p, ctx)
        self.assertEqual(result['assessed_label'], 'not_enough_info')
        self.assertIn('identifying', result['missing_information'][0])
        self.assertEqual(result['model_missing_information'], raw['missing_information'])

    def test_new_after_only_measurement_is_not_numeric_support(self):
        claim = 'The revision decreased median service latency.'
        ctx = 'Median service latency was 29 milliseconds after the revision. No baseline or comparative change was reported.'
        p = scoped(claim, 'revision', 'median service latency')
        raw = assessment([observation('revision', 'unknown', ctx)], missing=['comparison_unresolved'])
        result = a.assess_part(raw, p, ctx)
        self.assertEqual(result['assessed_label'], 'not_enough_info')
        self.assertIn('baseline/comparison', result['missing_information'][0])

    def test_wrong_reason_code_is_rejected(self):
        claim = 'The scheduler reduced peak memory.'
        ctx = 'Peak memory declined on the workload.'
        p = scoped(claim, 'scheduler', 'peak memory')
        raw = assessment([observation('Peak memory', 'unknown', ctx)], missing=['comparison_unresolved'])
        with self.assertRaisesRegex(ValueError, 'missing_reason_binding'):
            a.assess_part(raw, p, ctx)

    def test_other_metric_baseline_does_not_become_current_missing_reason(self):
        claim = 'The scheduler reduced latency.'
        ctx = 'The scheduler latency result was not measured. No baseline accuracy was reported.'
        p = scoped(claim, 'scheduler', 'latency')
        self.assertEqual(r.missing_reason(p, ctx), 'measurement_unreported')

    def test_other_named_target_missing_measurement_is_not_borrowed(self):
        claim = 'The West relay reduced latency.'
        ctx = 'The West relay was listed. The East relay latency was not measured.'
        p = scoped(claim, 'West relay', 'latency')
        self.assertEqual(r.missing_reason(p, ctx), 'scoped_evidence_unresolved')

    def test_scope_information_is_retained_in_rendered_missing(self):
        claim = 'In the shaded group, the converter improved yield after the overhaul.'
        p = scoped(claim, 'converter', 'yield', condition='In the shaded group', time='after the overhaul')
        ctx = 'The converter yield in the shaded group after the overhaul was not measured.'
        raw = assessment([observation('converter', 'unknown', ctx)], missing=['measurement_unreported'])
        result = a.assess_part(raw, p, ctx)
        for fragment in ('converter', 'yield', 'shaded group', 'after the overhaul'):
            self.assertIn(fragment, result['missing_information'][0])

    def test_rendering_preserves_numeric_checks_and_citations(self):
        t, payload = traces('scope:direction:contradict')[-1]
        result = a.assess_part(t['output'], payload['part'], payload['context'])
        obs = result['observations'][0]
        self.assertEqual(result['assessed_label'], 'contradict')
        self.assertEqual(obs['truth'], 'false')
        self.assertIsNotNone(obs['numeric_result'])
        self.assertEqual(obs['numeric'], t['output']['observations'][0]['numeric'])


class TokenTests(unittest.TestCase):
    setUp = h.AssessmentTokenFilterTests.setUp
    accepts = h.AssessmentTokenFilterTests.accepts
    ordered = h.AssessmentTokenFilterTests.ordered

    def test_new_closed_population_is_feasible_without_duplicate_roster(self):
        claim, p, ctx, raw = closure_sample()
        self.assertTrue(self.accepts(self.ordered(raw), request(claim, p, ctx)))
        raw['coverage']['members'] *= 2
        self.assertFalse(self.accepts(self.ordered(raw), request(claim, p, ctx)))

    def test_fresh_missing_baseline_filters_citation_and_wrong_reason(self):
        claim = 'The revision decreased median service latency.'
        ctx = 'Median service latency was 29 milliseconds after the revision. No baseline or comparative change was reported.'
        p = scoped(claim, 'revision', 'median service latency')
        raw = assessment([observation('revision', 'unknown', ctx)], missing=['comparison_unresolved'])
        msg = request(claim, p, ctx)
        self.assertTrue(self.accepts(self.ordered(raw), msg))
        for missing in ('Kline et al. (2021) reported it.', 'target_binding_unresolved'):
            raw['missing_information'] = [missing]
            self.assertFalse(self.accepts(self.ordered(raw), msg))

    def test_prose_cannot_reverse_truth_or_stop_mid_sentence(self):
        claim, p, ctx, raw = closure_sample()
        for field in ('explanation', 'observation'):
            bad = deepcopy(raw)
            target = bad if field == 'explanation' else bad['observations'][0]
            target['explanation'] = 'There were positive results for all of the'
            self.assertFalse(self.accepts(self.ordered(bad), request(claim, p, ctx)))

    def test_real_failed_inputs_have_valid_new_serializations(self):
        for cid in ('scope:direction:not_enough_info', 'scope:conjunction:not_enough_info'):
            t, payload = traces(cid)[-1]
            raw = canonical(t['output'], payload['part'], payload['context'])
            self.assertTrue(self.accepts(self.ordered(raw), request(payload['claim'], payload['part'], payload['context'])), cid)


if __name__ == '__main__':
    unittest.main()
