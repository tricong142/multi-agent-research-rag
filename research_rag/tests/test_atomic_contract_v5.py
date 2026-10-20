"""Novel scope and multi-quantity regressions; scripted output, no live model."""
from copy import deepcopy
import unittest

from research_rag.tests import test_atomic_decomposition_v5 as regression
from research_rag.tests.test_atomic_decomposition_v5 import plan
from research_rag.tests.test_atomic_verifier import (
    a, n, Backend, assessment, observation, operand, numeric, part,
)


class LocalScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.backend = regression.token_backend()

    accepts = regression.DecompositionV5RegressionTests.accepts

    def split_plan(self, claim, quotes, times, conditions=None):
        parts = []
        for index, quote in enumerate(quotes):
            value = plan(claim, entity='turbine', metric=('vibration', 'output')[index],
                         time=times[index], condition=(conditions or ['', ''])[index])['parts'][0]
            value['quote'] = quote
            parts.append(value)
        return {'parts': parts, 'unresolved': []}

    def test_local_times_stay_bound_to_their_own_clause_in_real_token_filter(self):
        claim = 'The turbine reduced vibration after servicing and increased output before inspection.'
        value = self.split_plan(claim, ['The turbine reduced vibration after servicing',
                                      'and increased output before inspection.'],
                                ['after servicing', 'before inspection'])
        self.assertTrue(self.accepts(claim, value))
        normalized = a.normalize_decomposition(value, claim)
        self.assertEqual([p['scope']['time'] for p in normalized['parts']], ['after servicing', 'before inspection'])
        wrong = deepcopy(value)
        wrong['parts'][1]['scope']['time'] = 'after servicing'
        self.assertFalse(self.accepts(claim, wrong))
        with self.assertRaises(ValueError):
            a.normalize_decomposition(wrong, claim)

    def test_local_scope_is_not_inherited_by_unrestricted_clause(self):
        claim = 'The turbine reduced vibration after servicing and increased output.'
        value = self.split_plan(claim, ['The turbine reduced vibration after servicing',
                                      'and increased output.'], ['after servicing', ''])
        self.assertTrue(self.accepts(claim, value))
        a.normalize_decomposition(value, claim)
        wrong = deepcopy(value)
        wrong['parts'][1]['scope']['time'] = 'after servicing'
        self.assertFalse(self.accepts(claim, wrong))
        with self.assertRaisesRegex(ValueError, 'time_not_applicable'):
            a.normalize_decomposition(wrong, claim)

    def test_dataset_restrictions_are_local_and_leading_dataset_is_shared(self):
        claim = 'The turbine reduced vibration on the Cedar dataset and increased output on the Pine dataset.'
        value = self.split_plan(claim, ['The turbine reduced vibration on the Cedar dataset',
                                      'and increased output on the Pine dataset.'], ['', ''],
                                ['on the Cedar dataset', 'on the Pine dataset'])
        self.assertTrue(self.accepts(claim, value))
        a.normalize_decomposition(value, claim)
        wrong = deepcopy(value)
        wrong['parts'][1]['scope']['condition'] = 'on the Cedar dataset'
        self.assertFalse(self.accepts(claim, wrong))
        with self.assertRaises(ValueError):
            a.normalize_decomposition(wrong, claim)
        claim = 'On the Cedar dataset, the turbine reduced vibration and increased output.'
        value = self.split_plan(claim, ['On the Cedar dataset, the turbine reduced vibration',
                                      'and increased output.'], ['', ''],
                                ['On the Cedar dataset', 'On the Cedar dataset'])
        self.assertTrue(self.accepts(claim, value))
        a.normalize_decomposition(value, claim)

    def test_unrepresentable_times_stop_before_any_backend_call(self):
        claim = 'The turbine reduced vibration after servicing before inspection.'
        backend = Backend([])
        result = a.AtomicVerifier(backend, max_calls=2, max_attempts=2, max_new_tokens=1536,
                                  timeout_seconds=180).verify(claim, '', decomposition_only=True)
        self.assertEqual(result['stop_reason'], 'unsupported_scope_structure')
        self.assertEqual(result['status'], 'incomplete')
        self.assertIsNone(result['assessed_label'])
        self.assertEqual(result['backend_calls'], 0)
        self.assertFalse(backend.calls)
        from research_rag.evaluation import evaluate_atomic_verifier as runner
        criteria = {'policy': a.POLICY, 'max_calls_per_case': 2, 'max_attempts': 2,
                    'max_new_tokens': 1536, 'case_deadline_seconds': 180}
        self.assertIsNone(runner.replay_result(result, claim, '', criteria))


class MultipleQuantityTests(unittest.TestCase):
    claim = 'The report evaluated four models on two datasets.'

    def check(self, proof, counts=('4', '2'), claim=None):
        claim = claim or self.claim
        requirements = n.numeric_requirements(claim)
        records = [numeric('value', proof, operand(r['value'], unit, r['quote']),
                           operand(count, unit))
                   for r, count, unit in zip(requirements, counts, ('models', 'datasets'))]
        return records

    def assess(self, proof, records, claim=None, model_truth='true'):
        claim = claim or self.claim
        p = part(claim, metric='evaluated four models', condition='on two datasets')
        return a.assess_part(assessment([observation('report', model_truth, proof, records)]), p, proof)

    def test_both_independent_counts_are_required_and_individually_computed(self):
        proof = 'The report evaluated 4 models on 2 datasets.'
        records = self.check(proof)
        for record in records:
            self.assertEqual(n.check_numeric(record, self.claim, proof)['truth'], 'true')
        value = self.assess(proof, records)
        self.assertEqual(value['assessed_label'], 'support')
        self.assertEqual([r['quote'] for r in value['numeric_requirements']], ['four models', 'two datasets'])
        for subset in (records[:1], records[1:], records[0]):
            with self.subTest(subset=subset), self.assertRaisesRegex(ValueError, 'numeric_requirement_missing'):
                self.assess(proof, subset)

    def test_wrong_second_count_refutes_even_when_model_says_true(self):
        proof = 'The report evaluated 4 models on 3 datasets.'
        self.assertEqual(self.assess(proof, self.check(proof, ('4', '3')))['assessed_label'], 'contradict')

    def test_equal_numbers_on_different_objects_remain_two_requirements(self):
        claim = self.claim.replace('two', 'four')
        proof = 'The report evaluated 4 models on 4 datasets.'
        records = self.check(proof, ('4', '4'), claim)
        self.assertEqual(self.assess(proof, records, claim)['assessed_label'], 'support')
        with self.assertRaisesRegex(ValueError, 'numeric_requirement_missing'):
            self.assess(proof, records[:1], claim)

    def test_duplicate_checks_swapped_units_and_uncited_evidence_cannot_support(self):
        proof = 'The report evaluated 4 models on 2 datasets.'
        records = self.check(proof)
        with self.assertRaisesRegex(ValueError, 'duplicate_numeric_requirement'):
            self.assess(proof, [records[0], records[0]])
        swapped = deepcopy(records)
        swapped[0]['right'] = records[1]['right']
        self.assertEqual(self.assess(proof, swapped)['assessed_label'], 'not_enough_info')
        self.assertEqual(self.assess(proof, records, model_truth='unknown')['assessed_label'], 'not_enough_info')
        longer = proof + ' A second report evaluated 4 models on 2 datasets.'
        records[0]['source_quote'] = 'A second report evaluated 4 models on 2 datasets.'
        p = part(self.claim, metric='evaluated four models')
        with self.assertRaisesRegex(ValueError, 'numeric_evidence_not_cited'):
            a.assess_part(assessment([observation('report', 'true', proof, records)]), p, longer)

    def test_normalized_part_exposes_requirements_and_numeric_list_passes_decoder(self):
        value = plan(self.claim, entity='report', metric='evaluated four models', condition='on two datasets')
        normalized = a.normalize_decomposition(value, self.claim)
        self.assertEqual(len(normalized['parts'][0]['numeric_requirements']), 2)
        from research_rag.tests.test_atomic_decoding import ConstrainedDecodingTests
        import json
        tester = ConstrainedDecodingTests()
        tester.setUp()
        proof = 'The report evaluated 4 models on 2 datasets.'
        request = [{'role': 'system', 'content': a.ASSESS_PROMPT},
                   {'role': 'user', 'content': json.dumps({'claim': self.claim,
                    'part': normalized['parts'][0], 'context': proof})}]
        output = assessment([observation('report', 'true', proof, self.check(proof))])
        output['observations'] = [{key: obs[key] for key in
            ('member', 'truth', 'quotes', 'explanation', 'numeric')} for obs in output['observations']]
        self.assertTrue(tester.accepts(json.dumps(output), request))

    def test_runtime_records_and_replays_all_numeric_requirements(self):
        proof = 'The report evaluated 4 models on 2 datasets.'
        wire = plan(self.claim, entity='report', metric='evaluated four models', condition='on two datasets')
        raw = assessment([observation('report', 'true', proof, self.check(proof))])
        backend = Backend([wire, raw])
        result = a.AtomicVerifier(backend, max_calls=2, max_attempts=2, max_new_tokens=1536,
                                  timeout_seconds=180).verify(self.claim, proof)
        self.assertEqual(result['assessed_label'], 'support')
        from research_rag.evaluation import evaluate_atomic_verifier as runner
        criteria = {'policy': a.POLICY, 'max_calls_per_case': 2, 'max_attempts': 2,
                    'max_new_tokens': 1536, 'case_deadline_seconds': 180}
        self.assertEqual(runner.replay_result(result, self.claim, proof, criteria), 'support')
        result['trace'][1]['output']['observations'][0]['numeric'].pop()
        with self.assertRaisesRegex(ValueError, 'disagree with replay'):
            runner.replay_result(result, self.claim, proof, criteria)


if __name__ == '__main__':
    unittest.main()
