"""Generic metric repair on novel inputs; no live model or changed decoder."""
from copy import deepcopy
import importlib
import json
import unittest

from research_rag.evaluation import evaluate_atomic_verifier as runner
from research_rag.tests.test_atomic_decomposition_v5 import plan
from research_rag.tests.test_atomic_verifier import Backend


a = importlib.import_module('04_factchecker.inference.atomic_verifier')


class MetricV6RegressionTests(unittest.TestCase):
    def test_bare_predicates_drop_objects_and_quantities_on_novel_claims(self):
        for claim, entity, verb, full in (
            ('Compilation took seven minutes.', 'Compilation', 'took', 'took seven minutes'),
            ('The archive contained 31 files.', 'archive', 'contained', 'contained 31 files'),
            ('The audit used expert annotations.', 'audit', 'used', 'used expert annotations'),
            ('The survey evaluated five sensors.', 'survey', 'evaluated', 'evaluated five sensors'),
            ('Every worker uses protective gloves.', 'worker', 'uses', 'uses protective gloves'),
            ('The batch takes eight hours.', 'batch', 'takes', 'takes eight hours'),
            ('The archive contains three folders.', 'archive', 'contains', 'contains three folders'),
        ):
            with self.subTest(claim=claim):
                raw = plan(claim, entity=entity, metric=verb,
                           quantifier='all' if claim.startswith('Every') else 'atomic')
                with self.assertRaisesRegex(ValueError, 'metric_predicate_incomplete'):
                    a.normalize_decomposition(raw, claim)
                detail = a.validation_detail(raw, claim, 'metric_predicate_incomplete')
                self.assertTrue(any(issue.get('field') == 'parts[0].scope.metric' and
                                    issue.get('required_source') == [full] for issue in detail['issues']))
                raw['parts'][0]['scope']['metric'] = full
                self.assertEqual(a.normalize_decomposition(raw, claim)['parts'][0]['scope']['metric'], full)

    def test_named_properties_and_predicates_without_missing_arguments_still_pass(self):
        for claim, entity, metric in (
            ('Model Birch achieved 91% accuracy.', 'Model Birch', 'accuracy'),
            ('The proxy reduced latency.', 'proxy', 'latency'),
            ('The vessel contained pressure.', 'vessel', 'pressure'),
            ('The system used memory efficiently.', 'system', 'memory'),
            ('The signal failed.', 'signal', 'failed'),
            ('Fuel use declined.', 'Fuel use', 'use'),
        ):
            with self.subTest(claim=claim):
                self.assertEqual(len(a.normalize_decomposition(plan(claim, entity=entity, metric=metric), claim)['parts']), 1)

    def test_verb_in_condition_or_entity_is_not_mistaken_for_predicate(self):
        claim = 'The field named used increased after migration.'
        raw = plan(claim, entity='field named used', metric='used', time='after migration')
        self.assertIsNone(a.metric_predicate_requirement(raw['parts'][0]['scope'], claim))
        self.assertEqual(len(a.normalize_decomposition(raw, claim)['parts']), 1)
        claim = 'The sample was contained after inspection.'
        raw = plan(claim, entity='sample', metric='contained', time='after inspection')
        self.assertIsNone(a.metric_predicate_requirement(raw['parts'][0]['scope'], claim))

    def test_repair_uses_exact_clause_argument_and_preserves_other_restrictions(self):
        claim = 'Compilation took seven minutes after migration.'
        bad = plan(claim, entity='Compilation', metric='took', time='after migration')
        good = deepcopy(bad)
        good['parts'][0]['scope']['metric'] = 'took seven minutes'
        backend = Backend([bad, good])
        result = a.AtomicVerifier(backend, max_calls=2, max_attempts=2, max_new_tokens=1536,
                                  timeout_seconds=180).verify(claim, '', decomposition_only=True)
        self.assertEqual((result['status'], result['backend_calls']), ('completed', 2))
        first, second = result['trace']
        self.assertEqual(first['validation_issue'], 'metric_predicate_incomplete')
        self.assertEqual(second['attempt'], 2)
        repair = backend.calls[1][0][-1]['content']
        self.assertIn('took seven minutes', repair)
        self.assertIn('parts[0].scope.metric', repair)
        self.assertEqual(result['decomposition']['parts'][0]['scope']['time'], 'after migration')
        criteria = {'policy': a.POLICY, 'max_calls_per_case': 2, 'max_attempts': 2, 'max_new_tokens': 1536,
                    'case_deadline_seconds': 180}
        self.assertIsNone(runner.replay_result(result, claim, '', criteria))

    def test_repair_exhaustion_is_incomplete_and_never_assesses_evidence(self):
        claim = 'The archive contained 31 files.'
        bad = plan(claim, entity='archive', metric='contained')
        backend = Backend([bad, bad])
        result = a.AtomicVerifier(backend, max_calls=2, max_attempts=2, max_new_tokens=1536,
                                  timeout_seconds=180).verify(claim, claim)
        self.assertEqual((result['status'], result['backend_calls']), ('incomplete', 2))
        self.assertIsNone(result['assessed_label'])
        self.assertTrue(all(set(json.loads(messages[1]['content'])) == {'claim'} for messages, _ in backend.calls))

    def test_invalid_metric_and_local_time_issues_are_reported_together(self):
        claim = 'The archive contained 31 files after migration.'
        raw = plan(claim, entity='archive', metric='contained')
        details = a.validation_detail(raw, claim, 'metric_predicate_incomplete')
        self.assertTrue({'metric_predicate_incomplete', 'shared_time_required'} <=
                        {issue['code'] for issue in details['issues']})

    def test_and_clause_repair_does_not_take_argument_or_time_from_other_part(self):
        claim = 'The archive contained 31 files after migration and used two datasets before inspection.'
        first = plan(claim, entity='archive', metric='contained', time='after migration')['parts'][0]
        first['quote'] = 'The archive contained 31 files after migration'
        second = plan(claim, entity='archive', metric='used two datasets', time='before inspection',
                      condition='used two datasets')['parts'][0]
        second['quote'] = 'and used two datasets before inspection.'
        # Dataset grammar recognizes on/using/under only; this argument stays in metric.
        second['scope']['condition'] = ''
        raw = {'parts': [first, second], 'unresolved': []}
        detail = a.validation_detail(raw, claim, 'metric_predicate_incomplete')
        required = [issue['required_source'] for issue in detail['issues'] if issue.get('field') == 'parts[0].scope.metric']
        self.assertEqual(required, [['contained 31 files']])
        first['scope']['metric'] = 'contained 31 files'
        parts = a.normalize_decomposition(raw, claim)['parts']
        self.assertEqual([part['scope']['time'] for part in parts], ['after migration', 'before inspection'])
        self.assertEqual([len(part['numeric_requirements']) for part in parts], [1, 1])


if __name__ == '__main__':
    unittest.main()
