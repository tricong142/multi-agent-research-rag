"""Development regressions from v7 failure modes and new inputs, not held-out quality."""
from contextlib import contextmanager
from copy import deepcopy
import importlib
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from research_rag.tests.test_atomic_verifier import Backend, assessment, numeric, observation, operand, part, run
from research_rag.tests import test_atomic_decoding as token_tests

a = importlib.import_module('04_factchecker.inference.atomic_verifier')
d = importlib.import_module('04_factchecker.inference.atomic_decoding')
n = importlib.import_module('04_factchecker.inference.numeric_verifier')
j = importlib.import_module('04_factchecker.inference.judge')


class AssessmentRepairTests(unittest.TestCase):
    claim = 'The audit evaluated seven models on three datasets.'
    proof = 'The audit evaluated 7 models on 3 datasets.'

    def fixture(self):
        p = part(self.claim, metric='evaluated seven models', condition='on three datasets')
        p['scope']['entity'] = 'audit'
        records = [numeric('value', self.proof, operand(r['value'], r['unit'], r['quote']),
                           operand(r['value'], r['unit'])) for r in n.numeric_requirements(self.claim)]
        raw = assessment([observation('audit', 'true', self.proof, records)])
        return p, raw

    def test_missing_numeric_enters_bounded_repair_and_checks_both_quantities(self):
        p, good = self.fixture()
        bad = deepcopy(good)
        bad['observations'][0]['numeric'] = None
        with self.assertRaisesRegex(ValueError, 'numeric_tool_required'):
            a.assess_part(bad, p, self.proof)
        result, backend = run([{'parts': [p], 'unresolved': []}, bad, good], self.claim, self.proof)
        self.assertEqual(result['assessed_label'], 'support')
        self.assertEqual(result['backend_calls'], 3)
        self.assertEqual(result['trace'][1]['validation_issue'], 'numeric_tool_required')
        self.assertIn('numeric', backend.calls[2][0][-1]['content'].lower())

    def test_missing_one_numeric_requirement_repairs_but_unknown_is_allowed(self):
        p, bad = self.fixture()
        bad['observations'][0]['numeric'].pop()
        with self.assertRaisesRegex(ValueError, 'numeric_requirement_missing'):
            a.assess_part(bad, p, self.proof)
        bad['observations'][0].update(truth='unknown', numeric=None)
        self.assertEqual(a.assess_part(bad, p, self.proof)['assessed_label'], 'not_enough_info')

    def test_missing_numeric_exhaustion_does_not_become_valid_nei_or_support(self):
        p, bad = self.fixture()
        bad['observations'][0]['numeric'] = None
        value, _ = run([{'parts': [p], 'unresolved': []}, bad, bad], self.claim, self.proof)
        self.assertEqual(value['status'], 'incomplete')
        self.assertEqual(value['stop_reason'], 'invalid_output_exhausted')
        self.assertIsNone(value['assessed_label'])

    def test_truncated_assessment_repairs_using_assessment_fields_and_retains_raw(self):
        p, good = self.fixture()
        partial = '{"scope_match":"matched","coverage":{'
        result, backend = run([{'parts': [p], 'unresolved': []},
                               j.ModelOutputError('parse failed', partial), good], self.claim, self.proof)
        self.assertEqual(result['assessed_label'], 'support')
        self.assertEqual(result['backend_calls'], 3)
        self.assertEqual(result['trace'][1]['validation_issue'], 'invalid_json')
        self.assertEqual(result['trace'][1]['raw_output'], partial)
        repair = backend.calls[2][0][-1]['content']
        self.assertIn('scope_match, coverage, observations', repair)
        self.assertNotIn('unresolved', repair)
        self.assertEqual(len(backend.calls[2][0]), 3)

    def test_full_predicate_binds_exactly_without_accepting_different_predicate(self):
        claim = 'The shipment contained 57 tablets.'
        p = part(claim, metric='contained 57 tablets')
        for verb, expected in [('contained exactly', 'support'), ('contained', 'support'),
                               ('discarded', 'not_enough_info')]:
            proof = f'The shipment {verb} 57 tablets.'
            record = numeric('value', proof, operand('57', 'tablets'), operand('57', 'tablets'))
            raw = assessment([observation('shipment', 'true', proof, record)])
            self.assertEqual(a.assess_part(raw, p, proof)['assessed_label'], expected)

    def test_explicit_denial_refutes_without_implicit_unit_conversion(self):
        claim = 'The rehearsal took 11 seconds.'
        p = part(claim, metric='took 11 seconds')
        for proof, expected in [('The rehearsal took 11 minutes, not 11 seconds.', 'contradict'),
                                ('The rehearsal took 11 minutes.', 'not_enough_info'),
                                ('If scheduled, the rehearsal would take 11 minutes, not 11 seconds.', 'not_enough_info'),
                                ('The rehearsal may take 11 minutes, not 11 seconds.', 'not_enough_info'),
                                ('The rehearsal might take 11 minutes, not 11 seconds.', 'not_enough_info'),
                                ('The rehearsal should take 11 minutes, not 11 seconds.', 'not_enough_info')]:
            record = numeric('value', proof, operand('11', 'seconds'), operand('11', 'minutes'))
            raw = assessment([observation('rehearsal', 'false', proof, record)])
            self.assertEqual(a.assess_part(raw, p, proof)['assessed_label'], expected)

    def test_population_count_does_not_force_arithmetic_for_qualitative_property(self):
        claim = 'Every sensor improved precision.'
        proof = 'The fleet comprised 6 sensors. Every sensor improved precision.'
        p = part(claim, quantifier='all', metric='precision')
        raw = assessment([observation('sensor', 'true', proof)], complete=True)
        self.assertEqual(a.assess_part(raw, p, proof)['assessed_label'], 'support')

    def test_real_v7_fabricated_quote_is_rejected_with_safe_specific_feedback(self):
        p, raw = self.fixture()
        raw['observations'][0]['quotes'] = [self.claim]
        with self.assertRaisesRegex(ValueError, 'quote_membership'):
            a.assess_part(raw, p, self.proof)

    def test_exact_v7_cross_sentence_trace_cannot_bypass_numeric_repair(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/atomic_v8_v7_assessments.json').read_text())
        case = next(row for row in fixture['cases'] if row['call_id'] == 26)
        raw = json.loads(case['raw_output'])
        with self.assertRaises(ValueError):
            a.assess_part(raw, case['input']['part'], case['input']['context'])
        # Isolate missing numeric after removing the independently invalid prose length.
        raw['explanation'] = 'Source reports both counts.'
        raw['observations'][0]['explanation'] = 'Source reports both counts.'
        with self.assertRaisesRegex(ValueError, 'numeric_tool_required'):
            a.assess_part(raw, case['input']['part'], case['input']['context'])

    def test_explicit_denial_does_not_override_threshold_or_claim_negation(self):
        for claim in ('Duration was at least 11 seconds.', 'Duration was not 11 seconds.'):
            proof = 'Duration was 15 seconds, not 11 seconds.'
            record = numeric('value', proof, operand('11', 'seconds'), operand('15', 'seconds'))
            self.assertEqual(n.check_numeric(record, claim, proof)['truth'], 'unknown')

    def test_a_proven_false_requirement_can_refute_without_unchecked_remainder(self):
        p, raw = self.fixture()
        proof = self.proof.replace('7 models', '8 models')
        raw['observations'][0]['quotes'] = [proof]
        record = raw['observations'][0]['numeric'][0]
        record['source_quote'] = proof
        record['right'] = operand('8', 'models')
        raw['observations'][0]['numeric'] = [record]
        self.assertEqual(a.assess_part(raw, p, proof)['assessed_label'], 'contradict')


class DeadlineRegressionTests(unittest.TestCase):
    def test_late_invalid_json_has_deadline_reason_even_on_last_attempt(self):
        clock = [0.0]
        class Slow(Backend):
            def generate_json(self, messages, **options):
                clock[0] += 2
                raise j.ModelOutputError('parse failed', '{"parts":[')
        backend = Slow([])
        with patch.object(a.time, 'monotonic', side_effect=lambda: clock[0]):
            result = a.AtomicVerifier(backend, max_calls=8, max_attempts=1, max_new_tokens=1536,
                                      timeout_seconds=1).verify('The service reduced latency.', '')
        self.assertEqual(result['stop_reason'], 'deadline_exceeded')
        self.assertEqual(result['trace'][0]['validation_issue'], 'deadline_exceeded')
        self.assertEqual(result['trace'][0]['raw_output'], '{"parts":[')

    def test_generation_receives_absolute_case_deadline_and_restores_context(self):
        entered = []
        class Aware(Backend):
            @contextmanager
            def generation_deadline(self, deadline):
                entered.append(deadline)
                try:
                    yield
                finally:
                    entered.append('restored')
        claim = 'The service reduced latency.'
        p = part(claim)
        backend = Aware([{'parts': [{k: v for k, v in p.items() if k not in ('start', 'end')}], 'unresolved': []}])
        with patch.object(a.time, 'monotonic', return_value=10):
            result = a.AtomicVerifier(backend, max_calls=2, max_attempts=2, max_new_tokens=1536,
                                      timeout_seconds=7).verify(claim, '', decomposition_only=True)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(entered, [17, 'restored'])

    def test_real_transformers_stopping_list_obeys_absolute_monotonic_clock(self):
        import torch
        from transformers import StoppingCriteriaList
        clock = [10.0]
        criteria = StoppingCriteriaList([d.DeadlineStop(11)])
        ids = torch.zeros((1, 1), dtype=torch.long)
        with patch.object(d.time, 'monotonic', side_effect=lambda: clock[0]):
            self.assertFalse(criteria(ids, None).item())
            clock[0] = 12
            self.assertTrue(criteria(ids, None).item())

    def test_actual_adapter_deadline_keeps_partial_json_generation_trace(self):
        from contextlib import nullcontext
        from transformers import StoppingCriteriaList
        from research_rag.evaluation import evaluate_atomic_verifier as runner
        clock = [0.0]
        class ScriptedModel:
            def generate(self, *, input_ids, stopping_criteria, **options):
                assert isinstance(stopping_criteria, StoppingCriteriaList)
                ids = token_tests.Sequence(input_ids[0])
                for char in '{"parts":[':
                    ids.append(ord(char))
                    clock[0] += .2
                    if any(stop(None, None) for stop in stopping_criteria):
                        break
                return token_tests.Tensor([ids])
        backend = token_tests.token_backend()
        backend.model = ScriptedModel()
        stream, stats = io.StringIO(), []
        traced = runner.RecordingBackend(backend, stream, 'fixture', [0], 8, stats)
        with patch.object(a.time, 'monotonic', side_effect=lambda: clock[0]), patch.dict(
                sys.modules, {'torch': SimpleNamespace(inference_mode=nullcontext)}):
            result = a.AtomicVerifier(traced, max_calls=8, max_attempts=2,
                                      max_new_tokens=1536, timeout_seconds=1).verify('The service reduced latency.', '')
        self.assertEqual(result['stop_reason'], 'deadline_exceeded')
        self.assertEqual(result['backend_calls'], 1)
        self.assertTrue(result['trace'][0]['cooperative_deadline'])
        self.assertIn('raw_output', result['trace'][0])
        self.assertTrue(stats[0]['deadline_stop_enabled'])
        self.assertIsNone(backend._case_deadline)
        events = [json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertEqual([e['event'] for e in events], ['call_started', 'generation', 'call_finished'])

    def test_unsupported_context_stops_before_any_generation(self):
        backend = Backend([])
        result = a.AtomicVerifier(backend, max_calls=8, max_attempts=2, max_new_tokens=1536,
                                  timeout_seconds=180).verify('The service reduced latency.', 'word ' * 601)
        self.assertEqual(result['stop_reason'], 'unsupported_assessment_context')
        self.assertEqual(result['backend_calls'], 0)
        self.assertIsNone(result['assessed_label'])


class AssessmentTokenFilterTests(unittest.TestCase):
    setUp = token_tests.ConstrainedDecodingTests.setUp
    accepts = token_tests.ConstrainedDecodingTests.accepts

    def ordered(self, raw):
        raw = deepcopy(raw)
        for obs in raw['observations']:
            obs['numeric'] = obs.pop('numeric')
        return json.dumps(raw)

    def request(self):
        claim = 'The vessel capacity was 9 liters.'
        return [{'role': 'system', 'content': a.ASSESS_PROMPT}, {'role': 'user', 'content': json.dumps({
            'claim': claim, 'part': part(claim, metric='capacity'), 'context': 'The vessel capacity was 9 liters.'})}]

    def test_non_source_quotes_and_unbounded_explanations_are_filtered(self):
        raw = assessment([observation('vessel', 'unknown', 'The vessel capacity was 9 liters.')])
        request = self.request()
        self.assertTrue(self.accepts(self.ordered(raw), request))
        raw['observations'][0]['quotes'] = ['The vessel capacity was 90 liters.']
        self.assertFalse(self.accepts(self.ordered(raw), request))
        raw['observations'][0]['quotes'] = ['The vessel capacity was 9 liters.']
        raw['explanation'] = 'x' * 1000
        self.assertFalse(self.accepts(self.ordered(raw), request))

    def test_numeric_values_are_source_bound_decimal_strings(self):
        raw = assessment([observation('vessel', 'true', 'The vessel capacity was 9 liters.',
            numeric('value', 'The vessel capacity was 9 liters.', operand('9', 'liters'), operand('9', 'liters')))])
        self.assertTrue(self.accepts(self.ordered(raw), self.request()))
        raw['observations'][0]['numeric']['right']['value'] = 'faster'
        self.assertFalse(self.accepts(self.ordered(raw), self.request()))

    def test_exact_v7_hallucinated_assessment_is_not_decodable(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/atomic_v8_v7_assessments.json').read_text())
        case = next(row for row in fixture['cases'] if row['call_id'] == 14)
        request = [{'role': 'system', 'content': a.ASSESS_PROMPT},
                   {'role': 'user', 'content': json.dumps(case['input'])}]
        self.assertFalse(self.accepts(case['raw_output'], request))

    def test_empty_context_allows_honest_unknown_without_fabricated_evidence(self):
        request = self.request()
        payload = json.loads(request[1]['content'])
        payload['context'] = ''
        request[1]['content'] = json.dumps(payload)
        raw = assessment([], missing=['Source evidence is absent.'], scope='unknown')
        self.assertTrue(self.accepts(self.ordered(raw), request))


class V8RunnerGatesTests(unittest.TestCase):
    def test_smoke_is_only_12_original_contracts_and_cannot_replace_probe(self):
        from research_rag.evaluation import evaluate_atomic_verifier as runner
        criteria, cases, *_ = runner.load_frozen(runner.CRITERIA)
        smoke, selected = runner.smoke_configuration(criteria, cases)
        self.assertEqual(len(selected), 12)
        self.assertEqual(smoke['maximum_total_backend_calls'], 96)
        self.assertEqual(criteria['cases_per_backend'], 39)
        self.assertEqual(criteria['maximum_total_backend_calls'], 312)
        bad = deepcopy(criteria)
        bad['assessment_smoke']['case_ids'].append(bad['assessment_smoke']['case_ids'][0])
        with self.assertRaises(ValueError):
            runner.smoke_configuration(bad, cases)

    def test_missing_stopping_metadata_fails_decoder_admission(self):
        from research_rag.evaluation import evaluate_atomic_verifier as runner
        request = token_tests.messages()
        event = {'structured_decoder': d.DECODER, 'schema_sha256': d.schema_sha256(d.schema_for(request)[0])}
        criteria = {'structured_decoder': d.DECODER, 'require_cooperative_deadline': True}
        self.assertFalse(runner.decoding_trace_complete([event], [request], criteria))
        event['deadline_stop_enabled'] = True
        self.assertTrue(runner.decoding_trace_complete([event], [request], criteria))


if __name__ == '__main__':
    unittest.main()
