"""Contract/arithmetic tests with fake model output, not model quality evaluation."""
from copy import deepcopy
import importlib
import json
import re
import unittest
from unittest.mock import patch


a = importlib.import_module('04_factchecker.inference.atomic_verifier')
n = importlib.import_module('04_factchecker.inference.numeric_verifier')
ModelOutputError = importlib.import_module('04_factchecker.inference.judge').ModelOutputError


class Backend:
    def __init__(self, outputs):
        self.outputs, self.calls = iter(outputs), []

    def generate_json(self, messages, **options):
        self.calls.append((messages, options))
        result = next(self.outputs)
        if isinstance(result, Exception):
            raise result
        return deepcopy(result)


def part(claim, quote=None, quantifier='atomic', metric='latency', time='', condition=''):
    quote = quote or claim
    start = claim.index(quote)
    return {'start': start, 'end': start + len(quote), 'quote': quote, 'quantifier': quantifier,
            'scope': {'entity': 'service' if 'service' in claim else claim.split()[0],
                      'metric': metric, 'time': time, 'condition': condition}}


def observation(member='service', truth='true', quote='The service reduced latency.', numeric=None):
    return {'member': member, 'truth': truth, 'quotes': [quote], 'numeric': numeric,
            'explanation': 'Synthetic fixture evidence.'}


def assessment(observations=None, *, complete=False, missing=None, scope='matched'):
    observations = observations if observations is not None else [observation()]
    return {'scope_match': scope,
            'coverage': {'complete': complete, 'members': [o['member'] for o in observations] if complete else [],
                         'quotes': [observations[0]['quotes'][0]] if complete and observations else []},
            'observations': observations, 'missing_information': missing or [],
            'explanation': 'Synthetic fixture, not a model prediction.'}


def operand(value, unit='', quote=None):
    return {'value': value, 'unit': unit, 'quote': quote or value + (' ' + unit if unit else '')}


def numeric(kind, proof, left, right):
    return {'kind': kind, 'source_quote': proof, 'left': left, 'right': right}


def run(outputs, claim='The service reduced latency.', context='The service reduced latency.', **options):
    # Existing canonical span fixtures are sent using the v2 model-facing contract.
    outputs = [{**raw, 'parts': [{k: v for k, v in p.items() if k not in ('start', 'end')}
                for p in raw['parts']]} if isinstance(raw, dict) and 'parts' in raw else raw for raw in outputs]
    backend = Backend(outputs)
    settings = dict(max_calls=8, max_attempts=2, max_new_tokens=1200, timeout_seconds=30)
    settings.update(options)
    result = a.AtomicVerifier(backend, **settings).verify(claim, context)
    return result, backend


class NumericVerifierTests(unittest.TestCase):
    def test_decimal_directions_and_equality_override_incorrect_model_arithmetic(self):
        claim = 'The service reduced latency.'
        for end, truth, delta in [('55', 'false', '13'), ('31', 'true', '-11'), ('42', 'false', '0')]:
            proof = f'Latency was 42 ms before tuning and {end} ms after tuning.'
            data = numeric('change', proof, operand('42', 'ms'), operand(end, 'ms'))
            value = n.check_numeric(data, claim, proof)
            self.assertEqual((value['truth'], value['delta']), (truth, delta))
            raw = assessment([observation(quote=proof, numeric=data)])
            result = a.assess_part(raw, part(claim), 'service. ' + proof)
            self.assertEqual(result['assessed_label'], 'support' if truth == 'true' else 'contradict')
            self.assertEqual(result['observations'][0]['model_truth'], 'true')

    def test_fraction_math_uses_decimal_and_order_is_source_bound(self):
        claim = 'Precision increased.'
        proof = 'Precision rose from 0.81 to 0.86.'
        raw = numeric('change', proof, operand('0.81'), operand('0.86'))
        result = n.check_numeric(raw, claim, proof)
        self.assertEqual((result['truth'], result['delta']), ('true', '0.05'))
        reversed_raw = {**raw, 'left': raw['right'], 'right': raw['left']}
        self.assertEqual(n.check_numeric(reversed_raw, claim, proof)['reason'], 'unbound_before_after_order')

    def test_exact_value_and_reported_percentage_require_grounding(self):
        for observed in ('94', '89'):
            claim, proof = 'Accuracy was 94%.', f'Accuracy was {observed}%.'
            raw = numeric('value', proof, operand('94', '%', '94%'), operand(observed, '%', observed + '%'))
            self.assertEqual(n.check_numeric(raw, claim, proof)['truth'], 'true' if observed == '94' else 'false')
        claim, proof = 'The service uses 25% less memory.', 'The service uses 25% less memory.'
        raw = numeric('value', proof, operand('25', '%', '25%'), operand('25', '%', '25%'))
        self.assertEqual(n.check_numeric(raw, claim, proof)['truth'], 'true')
        self.assertEqual(n.check_numeric({**raw, 'source_quote': 'Memory is 25%.'}, claim, 'Memory is 25%.')['truth'], 'unknown')

    def test_forged_values_and_quotes_are_rejected(self):
        claim, proof = 'Latency was 42 ms.', 'Latency was 55 ms.'
        raw = numeric('value', proof, operand('42', 'ms'), operand('55', 'ms'))
        mutations = [
            {**raw, 'right': operand('42', 'ms', '55 ms')},
            {**raw, 'source_quote': 'Latency was 42 ms.'},
            {**raw, 'right': operand('NaN', 'ms', '55 ms')},
            {**raw, 'right': operand('55', 'seconds', '55 ms')},
            {**raw, 'right': operand('55')},
        ]
        for bad in mutations:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                n.check_numeric(bad, claim, proof)

    def test_units_thresholds_and_missing_comparison_fail_closed(self):
        proof = 'Latency was 42 ms before tuning and 31 seconds after tuning.'
        raw = numeric('change', proof, operand('42', 'ms'), operand('31', 'seconds'))
        self.assertEqual(n.check_numeric(raw, 'Latency decreased.', proof)['reason'], 'unit_mismatch_no_conversion')
        proof = 'Accuracy was 94%.'
        raw = numeric('value', proof, operand('94', '%', '94%'), operand('94', '%', '94%'))
        self.assertEqual(n.check_numeric(raw, 'Accuracy was at least 94%.', proof)['truth'], 'unknown')
        proof = 'Latency is 31 ms after tuning; previous latency is unknown.'
        raw = numeric('change', proof, operand('31', 'ms'), operand('31', 'ms'))
        self.assertEqual(n.check_numeric(raw, 'Latency decreased.', proof)['truth'], 'unknown')

    def test_cannot_extract_partial_number_or_ignore_negation(self):
        raw = numeric('value', 'Accuracy was 94%.', operand('4', '%', '4%'), operand('4', '%', '4%'))
        with self.assertRaises(ValueError):
            n.check_numeric(raw, 'Accuracy was 4%.', 'Accuracy was 94%.')
        raw = numeric('value', 'Accuracy was 94%.', operand('94', '%', '94%'), operand('94', '%', '94%'))
        self.assertEqual(n.check_numeric(raw, 'Accuracy was not 94%.', 'Accuracy was 94%.')['truth'], 'unknown')
        for source, selected in [('Ratio was 94.1.', '94'), ('Ratio was -5.', '5'), ('Ratio was 1,000.', '000')]:
            raw = numeric('value', source, operand('5'), operand(str(int(selected)), quote=selected))
            with self.subTest(source=source), self.assertRaises(ValueError):
                n.check_numeric(raw, 'Ratio was 5.', source)

    def test_hypothetical_change_and_symbolic_threshold_are_not_exact_facts(self):
        proof = 'Latency would fall from 42 ms to 31 ms.'
        raw = numeric('change', proof, operand('42', 'ms'), operand('31', 'ms'))
        self.assertEqual(n.check_numeric(raw, 'Latency decreased.', proof)['reason'], 'qualified_numeric_evidence')
        proof = 'Accuracy was 94%.'
        raw = numeric('value', proof, operand('94', '%', '94%'), operand('94', '%', '94%'))
        self.assertEqual(n.check_numeric(raw, 'Accuracy >= 94%.', proof)['truth'], 'unknown')


class AtomicContractTests(unittest.TestCase):
    def test_missing_and_part_quantity_or_condition_is_rejected(self):
        claim = 'After tuning, the service reduced memory and retained 94% accuracy.'
        first = part(claim, 'After tuning, the service reduced memory', metric='memory', time='After tuning')
        second = part(claim, 'retained 94% accuracy.', metric='accuracy', time='After tuning')
        self.assertEqual(a.validate_parts({'parts': [first, second], 'unresolved': []}, claim), [first, second])
        bad = [
            {'parts': [first], 'unresolved': []},
            {'parts': [part(claim, metric='memory', time='After tuning')], 'unresolved': []},
            {'parts': [first, {**second, 'scope': {**second['scope'], 'time': ''}}], 'unresolved': []},
            {'parts': [first, {**second, 'start': second['start'] + 1}], 'unresolved': []},
        ]
        for raw in bad:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                a.validate_parts(raw, claim)
        # Dropping a unit symbol into a gap is not valid coverage.
        claim = 'Accuracy was 94%'
        with self.assertRaisesRegex(ValueError, 'uncovered_claim_content'):
            a.validate_parts({'parts': [part(claim, 'Accuracy was 94', metric='Accuracy')], 'unresolved': []}, claim)

    def test_quantifier_and_shared_condition_are_required(self):
        claim = 'Every low-temperature service reduced latency.'
        p = part(claim, quantifier='all', condition='low-temperature')
        a.validate_parts({'parts': [p], 'unresolved': []}, claim)
        for bad in ({**p, 'quantifier': 'atomic'}, {**p, 'scope': {**p['scope'], 'condition': ''}}):
            with self.assertRaises(ValueError):
                a.validate_parts({'parts': [bad], 'unresolved': []}, claim)

    def test_and_aggregation_keeps_missing_accuracy_unknown(self):
        claim = 'The service reduced memory and retained accuracy.'
        p1 = part(claim, 'The service reduced memory', metric='memory')
        p2 = part(claim, 'retained accuracy.', metric='accuracy')
        plan = {'parts': [p1, p2], 'unresolved': []}
        context = 'The service reduced memory. Accuracy was not measured.'
        first = assessment([observation(quote='The service reduced memory.')])
        for truth, expected in [('unknown', 'not_enough_info'), ('false', 'contradict'), ('true', 'support')]:
            second = assessment([observation(truth=truth, quote='Accuracy was not measured.')],
                                missing=['Accuracy after tuning.'] if truth == 'unknown' else [])
            # true/false are injected output to test aggregation, not entailment.
            result, backend = run([plan, first, second], claim, context)
            self.assertEqual(result['assessed_label'], expected)
            self.assertEqual(result['backend_calls'], 3)
            self.assertFalse(result['claim_verified'])
            self.assertFalse(result['promoted_to_serving'])
            self.assertEqual(len(backend.calls), 3)

    def test_quantifiers_use_witness_counterexample_and_complete_population(self):
        context = 'A improved. B worsened. The complete set is A and B.'
        for q, values, complete, expected in [
            ('all', ['true'], False, 'not_enough_info'), ('all', ['false'], False, 'contradict'),
            ('all', ['true', 'true'], True, 'support'),
            ('some', ['false'], False, 'not_enough_info'), ('some', ['true', 'false'], False, 'support'),
            ('some', ['false', 'false'], True, 'contradict'), ('some', ['false', 'unknown'], True, 'not_enough_info'),
            ('none', ['false'], False, 'not_enough_info'), ('none', ['true'], False, 'contradict'),
            ('none', ['false', 'false'], True, 'support'),
        ]:
            observations = [observation(member=m, truth=t, quote=context) for m, t in zip(('A', 'B'), values)]
            p = part('A improved.', quantifier=q, metric='improved')
            with self.subTest(q=q, values=values, complete=complete):
                result = a.assess_part(assessment(observations, complete=complete), p, context)
                self.assertEqual(result['assessed_label'], expected)

    def test_complete_coverage_cannot_omit_member_or_use_missing_quote(self):
        context = 'A improved. B worsened. The complete set is A and B.'
        p = part('Some service improved latency.', quantifier='some')
        raw = assessment([observation('A', 'false', context)], complete=True)
        raw['coverage']['members'].append('B')
        with self.assertRaisesRegex(ValueError, 'incomplete_coverage_ledger'):
            a.assess_part(raw, p, context)
        raw['coverage']['members'].pop()
        raw['coverage']['quotes'] = []
        with self.assertRaises(ValueError):
            a.assess_part(raw, p, context)

    def test_bad_scope_conflicting_evidence_and_metric_mismatch_are_unknown(self):
        claim, context = 'The service increased precision.', 'Recall rose from 0.64 to 0.79. The service was tested.'
        p = part(claim, metric='precision')
        proof = 'Recall rose from 0.64 to 0.79.'
        num = numeric('change', proof, operand('0.64'), operand('0.79'))
        raw = assessment([observation(quote=proof, numeric=num)])
        self.assertEqual(a.assess_part(raw, p, context)['assessed_label'], 'not_enough_info')
        for scope in ('unknown', 'mismatched'):
            raw['scope_match'] = scope
            self.assertEqual(a.assess_part(raw, p, context)['assessed_label'], 'not_enough_info')
        raw = assessment([observation('A', 'true', 'A improved.'), observation('B', 'false', 'B worsened.')])
        self.assertEqual(a.assess_part(raw, p, 'A improved. B worsened.')['assessed_label'], 'not_enough_info')

    def test_numbers_cannot_bypass_tool_and_unknown_association_stays_unknown(self):
        claim, proof = 'The service reduced latency.', 'The service latency fell from 42 ms to 31 ms.'
        p = part(claim)
        raw = assessment([observation(quote=proof)])
        self.assertIn('numeric_tool_required', a.assess_part(raw, p, proof)['validation_issues'])
        raw['observations'][0]['numeric'] = numeric('change', proof, operand('42', 'ms'), operand('31', 'ms'))
        raw['observations'][0]['truth'] = 'unknown'
        self.assertEqual(a.assess_part(raw, p, proof)['assessed_label'], 'not_enough_info')

    def test_invalid_quotes_unknown_keys_and_duplicate_members_are_rejected(self):
        claim = 'The service reduced latency.'
        raw = assessment()
        duplicate = deepcopy(raw)
        duplicate['observations'] *= 2
        badquote = deepcopy(raw)
        badquote['observations'][0]['quotes'] = ['Invented evidence.']
        for bad in ({**raw, 'assessed_label': 'support'}, duplicate, badquote, None):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                a.assess_part(bad, part(claim), claim)


class AtomicRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.claim = 'The service reduced latency.'
        self.plan = {'parts': [part(self.claim)], 'unresolved': []}

    def test_blinding_and_repair_trace(self):
        result, backend = run([{}, self.plan, assessment()])
        self.assertEqual(result['assessed_label'], 'support')
        self.assertEqual(result['trace'][0]['validation_issue'], 'decomposition_schema')
        self.assertIn('decomposition_schema', backend.calls[1][0][-1]['content'])
        self.assertIn('Root must have exactly', backend.calls[1][0][-1]['content'])
        self.assertEqual([set(json.loads(messages[1]['content'])) for messages, _ in backend.calls],
                         [{'claim'}, {'claim'}, {'claim', 'part', 'context'}])
        self.assertTrue(all(opts == {'max_new_tokens': 1200} for _, opts in backend.calls))
        json.dumps(result)

    def test_budget_and_invalid_output_do_not_return_partial_support(self):
        result, _ = run([self.plan], max_calls=1)
        self.assertEqual(result['stop_reason'], 'call_budget_exhausted')
        self.assertIsNone(result['assessed_label'])
        result, _ = run([{}, {}], max_attempts=2)
        self.assertEqual(result['stop_reason'], 'invalid_output_exhausted')
        self.assertEqual(result['backend_calls'], 2)
        self.assertIsNone(result['assessed_label'])

    def test_parser_errors_repair_but_backend_errors_do_not_and_are_redacted(self):
        result, _ = run([ModelOutputError('parse failed', 'invalid JSON'), self.plan, assessment()])
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['trace'][0]['validation_issue'], 'invalid_json')
        for error in (RuntimeError('secret=DO_NOT_LOG'), ValueError('secret=DO_NOT_LOG')):
            result, backend = run([error])
            self.assertEqual(result['stop_reason'], 'backend_error')
            self.assertEqual(len(backend.calls), 1)
            self.assertNotIn('DO_NOT_LOG', json.dumps(result))

    def test_deadline_rejects_late_output_and_stops_following_calls(self):
        clock = [0.0]
        class SlowBackend(Backend):
            def generate_json(self, messages, **options):
                clock[0] += 2
                return super().generate_json(messages, **options)
        backend = SlowBackend([self.plan])
        with patch.object(a.time, 'monotonic', side_effect=lambda: clock[0]):
            result = a.AtomicVerifier(backend, max_calls=5, max_attempts=2,
                                      max_new_tokens=1200, timeout_seconds=1).verify(self.claim, self.claim)
        self.assertEqual(result['stop_reason'], 'deadline_exceeded')
        self.assertEqual(result['backend_calls'], 1)
        self.assertIsNone(result['assessed_label'])

    def test_unresolved_plan_stops_without_part_calls(self):
        result, backend = run([{**self.plan, 'unresolved': ['The intended entity is ambiguous.']}])
        self.assertEqual(result['stop_reason'], 'unresolved_decomposition')
        self.assertEqual(len(backend.calls), 1)

    def test_invalid_configuration_or_input_calls_no_model(self):
        backend = Backend([])
        defaults = dict(max_calls=5, max_attempts=2, max_new_tokens=1200, timeout_seconds=30)
        for override in ({'max_calls': 0}, {'max_attempts': True}, {'max_new_tokens': -1}, {'timeout_seconds': float('nan')}):
            with self.assertRaises(ValueError):
                a.AtomicVerifier(backend, **{**defaults, **override})
        with self.assertRaises(ValueError):
            a.AtomicVerifier(backend, **defaults).verify('', '')
        self.assertFalse(backend.calls)


class QuoteDecompositionTests(unittest.TestCase):
    def wire(self, claim, quote=None):
        p = part(claim, quote, metric='latency')
        return {k: v for k, v in p.items() if k not in ('start', 'end')}

    def test_exact_unicode_offsets_and_scope_are_derived_without_mutating_model_output(self):
        claim = 'The service Ω reduced latency.'
        raw = {'parts': [self.wire(claim)], 'unresolved': []}
        before = deepcopy(raw)
        result = a.normalize_decomposition(raw, claim)
        self.assertEqual(raw, before)
        self.assertEqual((result['parts'][0]['start'], result['parts'][0]['end']), (0, len(claim)))
        self.assertEqual(result['parts'][0]['scope'], raw['parts'][0]['scope'])

    def test_model_offsets_wrong_scope_and_ambiguous_or_forged_quotes_rejected(self):
        claim = 'The service reduced latency.'
        good = self.wire(claim)
        for bad, issue in [({**good, 'start': 0}, 'model_part_schema'),
                ({**good, 'scope': 'entity'}, 'scope_schema'),
                ({**good, 'quote': 'The service improved latency.'}, 'quote_not_in_claim')]:
            with self.subTest(issue=issue), self.assertRaisesRegex(ValueError, issue):
                a.normalize_decomposition({'parts': [bad], 'unresolved': []}, claim)
        repeated = 'The service reduced latency and the service reduced latency.'
        with self.assertRaisesRegex(ValueError, 'ambiguous_quote'):
            a.normalize_decomposition({'parts': [self.wire(repeated, 'reduced latency')], 'unresolved': []}, repeated)

    def test_source_order_overlap_omission_and_split_token_are_rejected(self):
        claim = 'The service reduced latency and retained precision.'
        first = self.wire(claim, 'The service reduced latency')
        second = {**self.wire(claim, 'retained precision.'), 'scope': {**first['scope'], 'metric': 'precision'}}
        a.normalize_decomposition({'parts': [first, second], 'unresolved': []}, claim)
        for parts in ([second, first], [first, first], [first],
                      [{**first, 'quote': 'The service reduced latenc'}, second]):
            with self.subTest(parts=parts), self.assertRaises(ValueError):
                a.normalize_decomposition({'parts': parts, 'unresolved': []}, claim)

    def test_prompt_examples_pass_code_contract_and_are_not_probe_claims(self):
        examples = re.findall(r'Example input: (.+)\nExample output:\n(.+)', a.DECOMPOSE_PROMPT)
        self.assertEqual(len(examples), 5)
        for input_text, output_text in examples:
            a.normalize_decomposition(json.loads(output_text), json.loads(input_text)['claim'])

    def test_repair_contains_prior_output_and_specific_scope_hint(self):
        claim = 'The service reduced latency.'
        good = {'parts': [self.wire(claim)], 'unresolved': []}
        bad = {'parts': [{**good['parts'][0], 'scope': 'entity'}], 'unresolved': []}
        backend = Backend([bad, good])
        result = a.AtomicVerifier(backend, max_calls=2, max_attempts=2, max_new_tokens=1536,
                                  timeout_seconds=180).verify(claim, '', decomposition_only=True)
        self.assertEqual(result['status'], 'completed')
        self.assertIsNone(result['assessed_label'])
        self.assertEqual(result['parts'], [])
        repair = backend.calls[1][0]
        self.assertEqual(json.loads(repair[2]['content']), bad)
        self.assertIn('must be an OBJECT', repair[3]['content'])
        self.assertEqual(json.loads(repair[1]['content']), {'claim': claim})

    def test_parser_repair_is_bounded_and_unresolved_does_not_pass_probe(self):
        claim = 'The service reduced latency.'
        raw = {'parts': [self.wire(claim)], 'unresolved': ['Ambiguous subject.']}
        backend = Backend([ModelOutputError('bad', '{bad:' + 'x' * 7000), raw])
        result = a.AtomicVerifier(backend, max_calls=2, max_attempts=2, max_new_tokens=1536,
                                  timeout_seconds=180).verify(claim, '', decomposition_only=True)
        self.assertEqual(result['stop_reason'], 'unresolved_decomposition')
        self.assertEqual(result['status'], 'incomplete')
        self.assertEqual(len(backend.calls[1][0]), 3)
        self.assertNotIn('{bad:', json.dumps(backend.calls[1][0]))
        self.assertIn('double-quote EVERY key', backend.calls[1][0][2]['content'])
        self.assertIn('"unresolved":[]', backend.calls[1][0][2]['content'])

    def test_leading_and_is_connector_but_inner_and_requires_separate_predicates(self):
        claim = 'The service reduced latency and retained precision.'
        first = self.wire(claim, 'The service reduced latency')
        second = {**self.wire(claim, 'and retained precision.'), 'scope': {**first['scope'], 'metric': 'precision'}}
        raw = {'parts': [first, second], 'unresolved': []}
        plan = a.normalize_decomposition(raw, claim)
        self.assertEqual(plan['parts'][1]['quote'], 'and retained precision.')
        self.assertEqual(claim[plan['parts'][1]['start']:plan['parts'][1]['end']], second['quote'])
        with self.assertRaisesRegex(ValueError, 'unsplit_conjunction'):
            a.normalize_decomposition({'parts': [self.wire(claim)], 'unresolved': []}, claim)

    def test_case_sensitive_scope_repair_points_to_specific_field(self):
        claim = 'Service latency improved.'
        good = {'parts': [{**self.wire(claim), 'scope': {'entity': 'Service', 'metric': 'latency', 'time': '', 'condition': ''}}], 'unresolved': []}
        bad = deepcopy(good)
        bad['parts'][0]['scope']['entity'] = 'service'
        backend = Backend([bad, good])
        result = a.AtomicVerifier(backend, max_calls=2, max_attempts=2, max_new_tokens=1536,
                                  timeout_seconds=180).verify(claim, '', decomposition_only=True)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['trace'][0]['validation_detail']['field'], 'parts[0].scope.entity')
        self.assertIn('parts[0].scope.entity', backend.calls[1][0][-1]['content'])
        self.assertIn('capitalization', backend.calls[1][0][-1]['content'])

    def test_dataset_condition_cannot_be_stored_in_time_or_omitted(self):
        claim = 'On the Maple dataset, the service improved latency.'
        p = self.wire(claim)
        p['scope']['condition'] = 'On the Maple dataset'
        a.normalize_decomposition({'parts': [p], 'unresolved': []}, claim)
        bad = deepcopy(p)
        bad['scope'].update(condition='', time='On the Maple dataset')
        with self.assertRaisesRegex(ValueError, 'dataset_in_time'):
            a.normalize_decomposition({'parts': [bad], 'unresolved': []}, claim)
        bad['scope']['time'] = ''
        with self.assertRaisesRegex(ValueError, 'dataset_condition_required'):
            a.normalize_decomposition({'parts': [bad], 'unresolved': []}, claim)


if __name__ == '__main__':
    unittest.main()
