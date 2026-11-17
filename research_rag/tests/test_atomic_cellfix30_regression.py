"""Verify the typed proof engine on the 18 retired v6.1 errors.

The fixture includes independently annotated spans and operands. These tests
measure compilation and decisions, not the model's extraction accuracy.
"""
from copy import deepcopy
from fractions import Fraction
from importlib import import_module
import json
from pathlib import Path
import unittest


parser = import_module('04_factchecker.inference.decoder_parser')
verifier = import_module('04_factchecker.inference.atomic_verifier')
decoder = import_module('04_factchecker.inference.atomic_decoding')
pilot = import_module('scripts.run_factcheck_verdict')
tradeoff = import_module('04_factchecker.inference.tradeoff_proof')
FIXTURE = Path(__file__).with_name('fixtures') / 'atomic_cellfix30_regression.json'
CASES = {row['example_id']: row for row in json.loads(FIXTURE.read_bytes())}


def predict(row):
    requirements = parser.parse_requirements(row['claim_record'], row['claim'])
    observations = parser.parse_observations(row['source_record'], row['context'])
    return verifier.evaluate_structured(requirements, observations)


class StructuredRegressionTests(unittest.TestCase):
    def test_source_id_pilot_refutes_an_explicit_tradeoff(self):
        row = CASES['holdout-v6:025']
        segments = pilot.verdict.source_segments(row['context'])
        citations = [span for fact in row['source_record']['facts'] for span in fact['evidence']]
        ids = [key for key, segment in segments.items() if any(span in segment['text'] for span in citations)]

        def generate(messages):
            self.assertEqual(messages[0]['content'], pilot.verdict.SOURCE_ID_PROMPT)
            return dict(label='support', evidence_ids=ids, confidence=None, reasoning='RTF improves.')

        proposal, final, check = pilot.assess_case(row, generate, evidence_format='ids')
        self.assertEqual((proposal['label'], final['label']), ('support', 'contradict'))
        self.assertEqual(check['method'], 'explicit_tradeoff_refutation')

    def test_direct_tradeoff_refutation_requires_same_experiment_and_metric(self):
        claim = 'Under peak load, the batch scheduler cut elapsed time threefold at the cost of worse memory pressure.'
        source = 'Under peak load, elapsed time was reduced by a factor of 3 using the batch scheduler without worsening MP.'
        self.assertTrue(tradeoff.refutes_tradeoff(claim, source))
        for old, new in (
            ('peak load', 'light load'),
            ('elapsed time', 'response time'),
            ('factor of 3', 'factor of 2'),
            ('batch scheduler', 'job queue'),
            ('worsening MP', 'worsening IO'),
            ('without worsening', 'and did worsen'),
            ('was reduced', 'was never reduced'),
        ):
            with self.subTest(new=new):
                self.assertFalse(tradeoff.refutes_tradeoff(claim, source.replace(old, new)))

    def test_all_eighteen_retired_cases(self):
        self.assertEqual(len(CASES), 18)
        for key, row in CASES.items():
            with self.subTest(example_id=key):
                label, decisions = predict(row)
                self.assertEqual(label, row['label'])
                for decision in decisions:
                    self.assertTrue(decision['source_spans'])
                    for span in decision['source_spans']:
                        self.assertEqual(row['context'][span['start']:span['end']], span['text'])

    def test_claim_coverage_and_hyphenated_terms(self):
        row = deepcopy(CASES['holdout-v6:030'])
        row['claim_record']['requirements'][0]['values'].pop()
        with self.assertRaisesRegex(ValueError, 'uncovered_claim_content'):
            predict(row)
        self.assertIn('one-versus-all', parser.tokens(CASES['holdout-v6:026']['claim']))
        self.assertNotIn('all', parser.tokens(CASES['holdout-v6:026']['claim']))
        row = deepcopy(CASES['holdout-v6:025'])
        first, second = row['claim_record']['requirements']
        row['claim_record']['requirements'].pop()
        with self.assertRaisesRegex(ValueError, 'uncovered_claim_content'):
            predict(row)
        first['scope'].append({'text': second['cue'] + ' ' + second['values'][0]['text'], 'key': 'tradeoff'})
        with self.assertRaisesRegex(ValueError, 'unbound_tradeoff_requirement'):
            predict(row)

    def test_explicit_exclusion_and_negative_qualifiers(self):
        row = deepcopy(CASES['holdout-v6:027'])
        row['source_record']['facts'][0]['relation'] = 'eq'
        row['source_record']['facts'][0]['cue'] = ''
        self.assertEqual(predict(row)[0], 'not_enough_info')
        row = deepcopy(CASES['holdout-v6:025'])
        row['source_record']['facts'][1]['relation'] = 'eq'
        row['source_record']['facts'][1]['cue'] = ''
        with self.assertRaisesRegex(ValueError, 'unrepresented_source_negation'):
            predict(row)

    def test_parallel_values_are_bound_in_textual_order(self):
        row = deepcopy(CASES['holdout-v6:014'])
        row['source_record']['facts'][0]['values'].reverse()
        with self.assertRaisesRegex(ValueError, 'invalid_parallel_alignment'):
            predict(row)
        self.assertEqual(parser.number('3/4'), Fraction(3, 4))
        self.assertEqual(parser.number('6,105'), Fraction(6105))
        self.assertNotEqual(parser.number('65.30'), parser.number('69.05'))
        with self.assertRaisesRegex(ValueError, 'partial_token_span'):
            parser.span_in('105', '6,105 documents')
        with self.assertRaisesRegex(ValueError, 'partial_token_span'):
            parser.span_in('4', 'The value was -4.')
        row = deepcopy(CASES['holdout-v6:016'])
        row['source_record']['facts'][0]['values'].reverse()
        with self.assertRaisesRegex(ValueError, 'unbound_transition_direction'):
            predict(row)

    def test_wrong_scope_and_ambiguous_reports_stay_unknown(self):
        row = deepcopy(CASES['holdout-v6:013'])
        row['source_record']['facts'][0]['scope'][0]['key'] = 'test set'
        self.assertEqual(predict(row)[0], 'not_enough_info')
        row = deepcopy(CASES['holdout-v6:028'])
        source = row['source_record']['facts'][0]
        alternative = deepcopy(source)
        alternative['evidence'][0] = alternative['evidence'][0].replace('3/4', '0.5')
        alternative['values'][0]['text'] = '0.5'
        row['context'] += ' ' + alternative['evidence'][0]
        row['source_record']['facts'].append(alternative)
        self.assertEqual(predict(row)[0], 'not_enough_info')

    def test_syntax_accepts_annotations_and_has_no_verdict_field(self):
        from lmformatenforcer import CharacterLevelParserConfig, JsonSchemaParser

        for row in CASES.values():
            for key, is_claim in (('claim_record', True), ('source_record', False)):
                with self.subTest(example_id=row['example_id'], record=key):
                    raw = json.dumps(row[key], ensure_ascii=False, separators=(',', ':'))
                    config = CharacterLevelParserConfig(force_json_field_order=True)
                    config.alphabet += ''.join(sorted(set(raw) - set(config.alphabet)))
                    state = parser.checked_json_parser(JsonSchemaParser(decoder.structured_schema(claim=is_claim), config))
                    for character in raw:
                        state = state.add_character(character)
                    self.assertTrue(state.can_end())
        with self.assertRaisesRegex(ValueError, 'invalid_structured_fields'):
            parser.parse_observations({'facts': [], 'label': 'support'}, '')

    def test_verifier_passes_source_extractor_roles_without_expected_values(self):
        row = CASES['holdout-v6:027']

        class AnnotationReplay:
            def generate_json(self, messages, *, max_new_tokens):
                if max_new_tokens != 1536:
                    raise AssertionError('Unexpected token budget')
                prompt, payload = messages[0]['content'], json.loads(messages[1]['content'])
                if prompt == verifier.STRUCTURED_CLAIM_PROMPT:
                    if payload != {'claim': row['claim']}:
                        raise AssertionError('Claim input differs from annotation')
                    return row['claim_record']
                if prompt != verifier.STRUCTURED_SOURCE_PROMPT or payload['context'] != row['context']:
                    raise AssertionError('Unexpected source request')
                if 'GPU' in messages[1]['content'] or set(payload) != {'context', 'targets'}:
                    raise AssertionError('Expected device leaked to the extractor')
                return row['source_record']

        node = verifier.AtomicVerifier(AnnotationReplay(), max_calls=8, max_attempts=2,
                                      max_new_tokens=1536, timeout_seconds=180)
        result = node.verify(row['claim'], row['context'], structured=True)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['assessed_label'], 'contradict')
        self.assertEqual(result['backend_calls'], 2)


if __name__ == '__main__':
    unittest.main()
