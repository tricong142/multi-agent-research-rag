"""Metric regressions from v6 traces and novel claims; no live model inference."""
from copy import deepcopy
import importlib
import json
import unittest

from research_rag.evaluation import evaluate_atomic_verifier as runner
from research_rag.tests.test_atomic_decomposition_v5 import plan
from research_rag.tests.test_atomic_decoding import Sequence, messages, token_backend
from research_rag.tests.test_atomic_verifier import Backend, assessment, observation, operand, numeric


a = importlib.import_module('04_factchecker.inference.atomic_verifier')

# Literal claim/entity/metric values checked against run 20261015T155608Z-9262cfd5.
# Keep regression fixtures independent of the user's downloaded ZIP.
V6_DRAFTS = (
    ('Training took 12 seconds.', 'Training', ('took', 'took'), 'took 12 seconds'),
    ('The sample contained 240 documents.', 'sample',
     ('contained', '240 documents'), 'contained 240 documents'),
)

NOVEL_PREDICATES = (
    ('Compilation took seven minutes.', 'Compilation', 'took seven minutes', '', ''),
    ('The archive contained 31 files.', 'archive', 'contained 31 files', '', ''),
    ('The batch takes eight hours.', 'batch', 'takes eight hours', '', ''),
    ('The archive contains three folders.', 'archive', 'contains three folders', '', ''),
    ('The study used five sensors.', 'study', 'used five sensors', '', ''),
    ('The study uses six sensors.', 'study', 'uses six sensors', '', ''),
    ('The report evaluates four models on two datasets.', 'report',
     'evaluates four models', '', 'on two datasets'),
    ('The survey evaluated five sensors after servicing.', 'survey',
     'evaluated five sensors', 'after servicing', ''),
)


class MetricV7RegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.backend = token_backend()

    def accepts(self, claim, value):
        callback = self.backend.generation_options(messages(claim))['prefix_allowed_tokens_fn']
        ids = Sequence([ord('P')])
        for char in json.dumps(value, separators=(',', ':')):
            if ord(char) not in callback(0, ids):
                return False
            ids.append(ord(char))
        return 0 in callback(0, ids)

    def verify(self, claim, outputs, context=''):
        backend = Backend(outputs)
        result = a.AtomicVerifier(backend, max_calls=2, max_attempts=2, max_new_tokens=1536,
                                  timeout_seconds=180).verify(claim, context, decomposition_only=True)
        criteria = {'policy': a.POLICY, 'max_calls_per_case': 2, 'max_attempts': 2,
                    'max_new_tokens': 1536, 'case_deadline_seconds': 180}
        self.assertIsNone(runner.replay_result(result, claim, context, criteria))
        return result, backend

    def test_v6_real_drafts_fail_validator_and_real_token_filter(self):
        for claim, entity, drafts, full in V6_DRAFTS:
            for metric in dict.fromkeys(drafts):
                with self.subTest(claim=claim, metric=metric):
                    raw = plan(claim, entity=entity, metric=metric)
                    with self.assertRaisesRegex(ValueError, 'metric_predicate_incomplete'):
                        a.normalize_decomposition(raw, claim)
                    self.assertFalse(self.accepts(claim, raw))
                    details = a.validation_detail(raw, claim, 'metric_predicate_incomplete')
                    self.assertTrue(any(issue.get('field') == 'parts[0].scope.metric' and
                                        issue.get('required_source') == [full]
                                        for issue in details['issues']))
            good = plan(claim, entity=entity, metric=full)
            self.assertTrue(self.accepts(claim, good))
            self.assertEqual(a.normalize_decomposition(good, claim)['parts'][0]['scope']['metric'], full)

    def test_novel_incomplete_predicates_fail_without_claim_specific_rules(self):
        for claim, entity, full, time, condition in NOVEL_PREDICATES:
            verb, argument = full.split(' ', 1)
            for metric in (verb, argument, argument.split(' ', 1)[0], argument.split(' ', 1)[1]):
                with self.subTest(claim=claim, metric=metric):
                    bad = plan(claim, entity=entity, metric=metric, time=time, condition=condition)
                    with self.assertRaisesRegex(ValueError, 'metric_predicate_incomplete'):
                        a.normalize_decomposition(bad, claim)
            good = plan(claim, entity=entity, metric=full, time=time, condition=condition)
            self.assertEqual(a.normalize_decomposition(good, claim)['parts'][0]['scope']['metric'], full)

    def test_real_token_filter_excludes_quantity_and_object_fragments_on_novel_claims(self):
        for claim, entity, full, time, condition in NOVEL_PREDICATES:
            for metric, expected in ((full, True), (full.split(' ', 1)[1], False),
                                     (full.split(' ')[-1], False)):
                with self.subTest(claim=claim, metric=metric):
                    raw = plan(claim, entity=entity, metric=metric, time=time, condition=condition)
                    self.assertEqual(self.accepts(claim, raw), expected)

    def test_named_properties_and_percentage_memory_claims_remain_valid(self):
        for claim, entity, metric, condition in (
            ('Model Birch achieved 91% accuracy.', 'Model Birch', 'accuracy', ''),
            ('The proxy reduced latency.', 'proxy', 'latency', ''),
            ('The vessel contained pressure.', 'vessel', 'pressure', ''),
            ('The system used memory efficiently.', 'system', 'memory', ''),
            ('Model Birch uses 25% less memory.', 'Model Birch', 'memory', ''),
            ('The survey evaluated latency on two datasets.', 'survey', 'latency', 'on two datasets'),
            ('Compilation duration was 9 seconds.', 'Compilation', 'duration', ''),
            ('The system used two gigabytes of memory.', 'system', 'memory', ''),
        ):
            with self.subTest(claim=claim):
                raw = plan(claim, entity=entity, metric=metric, condition=condition)
                self.assertTrue(self.accepts(claim, raw))
                self.assertEqual(a.normalize_decomposition(raw, claim)['parts'][0]['scope']['metric'], metric)

    def test_repair_from_bare_verb_to_full_predicate_succeeds_within_two_calls(self):
        claim = 'Compilation took seven minutes after migration.'
        bad = plan(claim, entity='Compilation', metric='took', time='after migration')
        good = deepcopy(bad)
        good['parts'][0]['scope']['metric'] = 'took seven minutes'
        result, backend = self.verify(claim, [bad, good])
        self.assertEqual((result['status'], result['backend_calls']), ('completed', 2))
        self.assertEqual(result['trace'][0]['validation_issue'], 'metric_predicate_incomplete')
        self.assertEqual(result['decomposition']['parts'][0]['scope']['time'], 'after migration')
        repair = backend.calls[1][0][-1]['content']
        self.assertIn('parts[0].scope.metric', repair)
        self.assertIn('took seven minutes', repair)

    def test_v6_repair_sequences_exhaust_budget_without_accepting_quantity_only(self):
        for claim, entity, metrics, _ in V6_DRAFTS:
            with self.subTest(claim=claim):
                outputs = [plan(claim, entity=entity, metric=metric) for metric in metrics]
                result, backend = self.verify(claim, outputs, claim)
                self.assertEqual((result['status'], result['backend_calls']), ('incomplete', 2))
                self.assertEqual(result['stop_reason'], 'invalid_output_exhausted')
                self.assertIsNone(result['decomposition'])
                self.assertIsNone(result['assessed_label'])
                self.assertEqual([event['validation_issue'] for event in result['trace']],
                                 ['metric_predicate_incomplete'] * 2)
                self.assertTrue(all(set(json.loads(request[1]['content'])) == {'claim'}
                                    for request, _ in backend.calls))

    def test_quantity_only_draft_repairs_to_complete_predicate(self):
        claim = 'The archive contained 31 files.'
        bad = plan(claim, entity='archive', metric='31 files')
        good = plan(claim, entity='archive', metric='contained 31 files')
        result, _ = self.verify(claim, [bad, good])
        self.assertEqual((result['status'], result['backend_calls']), ('completed', 2))
        self.assertEqual(result['decomposition']['parts'][0]['scope']['metric'], 'contained 31 files')

    def test_each_and_clause_keeps_its_metric_and_local_time(self):
        claim = 'The archive contained 31 files after migration and used two datasets before inspection.'
        first = plan(claim, entity='archive', metric='contained 31 files', time='after migration')['parts'][0]
        first['quote'] = 'The archive contained 31 files after migration'
        second = plan(claim, entity='archive', metric='used two datasets', time='before inspection')['parts'][0]
        second['quote'] = 'and used two datasets before inspection.'
        raw = {'parts': [first, second], 'unresolved': []}
        self.assertTrue(self.accepts(claim, raw))
        normalized = a.normalize_decomposition(raw, claim)
        self.assertEqual([p['scope']['time'] for p in normalized['parts']],
                         ['after migration', 'before inspection'])
        self.assertEqual([p['numeric_requirements'][0]['quote'] for p in normalized['parts']],
                         ['31 files', 'two datasets'])
        for index in (0, 1):
            bad = deepcopy(raw)
            bad['parts'][index]['scope']['metric'] = raw['parts'][1 - index]['scope']['metric']
            self.assertFalse(self.accepts(claim, bad))
            with self.assertRaisesRegex(ValueError, 'metric_predicate_incomplete'):
                a.normalize_decomposition(bad, claim)
            bad = deepcopy(raw)
            bad['parts'][index]['scope']['time'] = raw['parts'][1 - index]['scope']['time']
            self.assertFalse(self.accepts(claim, bad))
            with self.assertRaises(ValueError):
                a.normalize_decomposition(bad, claim)

    def test_quantified_population_and_leading_shared_time_survive_metric_restriction(self):
        claim = 'After calibration, every inspected batch contained three samples and used two sensors.'
        first = plan(claim, entity='inspected batch', metric='contained three samples',
                     time='After calibration', quantifier='all')['parts'][0]
        first['quote'] = 'After calibration, every inspected batch contained three samples'
        second = deepcopy(first)
        second.update(quote='and used two sensors.')
        second['scope']['metric'] = 'used two sensors'
        raw = {'parts': [first, second], 'unresolved': []}
        self.assertTrue(self.accepts(claim, raw))
        parts = a.normalize_decomposition(raw, claim)['parts']
        self.assertEqual([p['quantifier'] for p in parts], ['all', 'all'])
        self.assertEqual([p['scope']['time'] for p in parts], ['After calibration'] * 2)
        self.assertEqual([p['scope']['entity'] for p in parts], ['inspected batch'] * 2)
        bad = deepcopy(raw)
        bad['parts'][0]['scope']['entity'] = 'batch'
        with self.assertRaisesRegex(ValueError, 'population_modifier_missing'):
            a.normalize_decomposition(bad, claim)

    def test_count_predicate_preserves_all_some_and_none_quantifiers(self):
        for claim, quantifier in (
            ('All archives contained 31 files.', 'all'),
            ('Some archives contained 31 files.', 'some'),
            ('None of the archives contained 31 files.', 'none'),
            ('No archives contained 31 files.', 'none'),
        ):
            with self.subTest(claim=claim):
                raw = plan(claim, entity='archives', metric='contained 31 files', quantifier=quantifier)
                self.assertTrue(self.accepts(claim, raw))
                self.assertEqual(a.normalize_decomposition(raw, claim)['parts'][0]['quantifier'], quantifier)

    def test_decimal_duration_and_verbs_inside_time_restrictions(self):
        for claim, metric, time in (
            ('Compilation took 1.5 seconds.', 'took 1.5 seconds', ''),
            ('The run took 3 seconds after the worker used 4 sensors.', 'took 3 seconds',
             'after the worker used 4 sensors'),
        ):
            with self.subTest(claim=claim):
                raw = plan(claim, entity='Compilation' if not time else 'run', metric=metric, time=time)
                self.assertTrue(self.accepts(claim, raw))
                self.assertEqual(a.normalize_decomposition(raw, claim)['parts'][0]['scope']['metric'], metric)
                raw['parts'][0]['scope']['metric'] = metric.split(' ', 1)[1]
                self.assertFalse(self.accepts(claim, raw))
                with self.assertRaisesRegex(ValueError, 'metric_predicate_incomplete'):
                    a.normalize_decomposition(raw, claim)

    def test_model_scope_cannot_hide_source_predicate_requirement(self):
        claim = 'Training took 12 seconds.'
        for entity, condition in (('Training', 'took'), (claim, ''), (claim, 'took 12 seconds')):
            with self.subTest(entity=entity, condition=condition):
                raw = plan(claim, entity=entity, metric='12 seconds', condition=condition)
                with self.assertRaisesRegex(ValueError, 'metric_predicate_incomplete'):
                    a.normalize_decomposition(raw, claim)
                self.assertFalse(self.accepts(claim, raw))

    def test_two_quantities_still_need_two_evidence_checks(self):
        claim = 'The report evaluated four models on two datasets.'
        raw = plan(claim, entity='report', metric='evaluated four models', condition='on two datasets')
        self.assertTrue(self.accepts(claim, raw))
        part = a.normalize_decomposition(raw, claim)['parts'][0]
        self.assertEqual([r['quote'] for r in part['numeric_requirements']], ['four models', 'two datasets'])
        proof = 'The report evaluated 4 models on 2 datasets.'
        checks = [numeric('value', proof, operand(r['value'], unit, r['quote']), operand(count, unit))
                  for r, count, unit in zip(part['numeric_requirements'], ('4', '2'), ('models', 'datasets'))]
        assessed = a.assess_part(assessment([observation('report', 'true', proof, checks)]), part, proof)
        self.assertEqual(assessed['assessed_label'], 'support')
        for selected in (checks[:1], checks[1:]):
            with self.subTest(selected=selected):
                with self.assertRaisesRegex(ValueError, 'numeric_requirement_missing'):
                    a.assess_part(assessment([observation('report', 'true', proof, selected)]), part, proof)

    def test_unsupported_negated_duration_stops_before_calling_model(self):
        claim = 'The batch did not take seven minutes.'
        result, backend = self.verify(claim, [])
        self.assertEqual(result['stop_reason'], 'unsupported_metric_structure')
        self.assertEqual(result['status'], 'incomplete')
        self.assertEqual(result['backend_calls'], 0)
        self.assertIsNone(result['assessed_label'])
        self.assertFalse(backend.calls)
        with self.assertRaisesRegex(ValueError, 'unsupported_metric_structure'):
            self.backend.generation_options(messages(claim))


if __name__ == '__main__':
    unittest.main()
