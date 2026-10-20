"""Real token-filter tests with a tiny tokenizer; no weights or live inference."""
from contextlib import nullcontext
from copy import deepcopy
import importlib
import json
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

a = importlib.import_module('04_factchecker.inference.atomic_verifier')
d = importlib.import_module('04_factchecker.inference.atomic_decoding')
j = importlib.import_module('04_factchecker.inference.judge')


class Sequence(list):
    def tolist(self):
        return list(self)


class Tensor:
    def __init__(self, rows):
        self.rows = rows
        self.shape = (len(rows), len(rows[0]))

    def __getitem__(self, index):
        return self.rows[index]


class TinyTokenizer:
    eos_token_id = 0
    all_special_ids = [0]

    def __len__(self):
        return 128

    def encode(self, text):
        return [ord(c) for c in text]

    def decode(self, ids, **options):
        return ''.join(chr(i) for i in ids if i)

    def apply_chat_template(self, messages, **options):
        return 'P'

    def __call__(self, text, **options):
        return {'input_ids': Tensor([self.encode(text)])}


def token_backend():
    # Exercise LMFE's real list-token path without importing its optional torch
    # bitmask implementation; model execution is separately scripted below.
    original = __import__
    def import_without_torch(name, *args, **kwargs):
        if name == 'torch':
            raise ImportError('Torch bitmasks are outside these token-filter tests')
        return original(name, *args, **kwargs)
    with patch('builtins.__import__', side_effect=import_without_torch):
        return d.ConstrainedAtomicBackend(None, TinyTokenizer())


def messages(claim='The lamp brightness increased.'):
    return [{'role': 'system', 'content': a.DECOMPOSE_PROMPT},
            {'role': 'user', 'content': json.dumps({'claim': claim})}]


def plan(claim='The lamp brightness increased.'):
    return {'parts': [{'quote': claim, 'quantifier': 'atomic',
                      'scope': {'entity': 'lamp', 'metric': 'brightness', 'time': '', 'condition': ''}}], 'unresolved': []}


class ConstrainedDecodingTests(unittest.TestCase):
    def setUp(self):
        self.backend = token_backend()

    def accepts(self, output, request=None):
        callback = self.backend.generation_options(request or messages())['prefix_allowed_tokens_fn']
        ids = Sequence([ord('P')])
        for char in output:
            if ord(char) not in callback(0, ids):
                return False
            ids.append(ord(char))
        return 0 in callback(0, ids)

    def test_valid_json_can_end_but_missing_quote_or_extra_brace_cannot(self):
        text = json.dumps(plan(), separators=(',', ':'))
        self.assertTrue(self.accepts(text))
        self.assertFalse(self.accepts(text.replace('"unresolved":', '"unresolved:')))
        self.assertFalse(self.accepts(text + '}'))
        self.assertFalse(self.accepts(text[:-1]))

    def test_source_and_quantifier_enum_prevent_unseen_values_without_gold(self):
        for field, value in [('quote', 'The lamp got brighter.'), ('quantifier', 'all')]:
            bad = plan()
            bad['parts'][0][field] = value
            self.assertFalse(self.accepts(json.dumps(bad)))
        bad = plan()
        bad['parts'][0]['scope']['entity'] = 'Lamp'
        self.assertFalse(self.accepts(json.dumps(bad)))

    def test_required_keys_types_and_empty_parts_are_rejected(self):
        for bad in [dict(parts=[], unresolved=[]), {'parts': plan()['parts']},
                    {**plan(), 'label': 'support'}]:
            self.assertFalse(self.accepts(json.dumps(bad)))
        bad = plan()
        bad['parts'][0]['scope'] = 'entity'
        self.assertFalse(self.accepts(json.dumps(bad)))

    def test_single_clause_coverage_enforced_but_semantic_binding_still_needs_review(self):
        bad = plan()
        bad['parts'][0]['quote'] = 'The lamp'
        self.assertFalse(self.accepts(json.dumps(bad)))
        with self.assertRaisesRegex(ValueError, 'uncovered_claim_content'):
            a.normalize_decomposition(bad, 'The lamp brightness increased.')
        bad = plan()
        bad['parts'][0]['scope']['metric'] = 'increased'
        # Valid structure/source still cannot prove entity/property semantics.
        self.assertTrue(self.accepts(json.dumps(bad)))

    def test_explicit_word_limit_and_supported_quantifiers_are_frozen(self):
        with self.assertRaises(ValueError):
            d.decomposition_schema(' '.join(['word'] * 81))
        for claim, quantifier in [('Every lamp shone.', 'all'), ('Some lamps shone.', 'some'),
                                  ('None of the lamps shone.', 'none'), ('The lamp shone.', 'atomic')]:
            schema = d.decomposition_schema(claim)
            self.assertEqual(schema['properties']['parts']['items']['properties']['quantifier']['enum'], [quantifier])

    def test_assessment_numeric_union_and_type_constraints(self):
        request = [{'role': 'system', 'content': a.ASSESS_PROMPT},
                   {'role': 'user', 'content': json.dumps({'claim': 'The lamp brightness increased.',
                       'part': plan()['parts'][0], 'context': 'The lamp brightness increased.'})}]
        value = {'scope_match': 'matched', 'coverage': {'complete': False, 'members': [], 'quotes': []},
                 'observations': [{'member': 'lamp', 'truth': 'unknown', 'quotes': [],
                    'explanation': 'Missing measurement.', 'numeric': None}],
                 'missing_information': ['Measurement.'], 'explanation': 'Missing evidence.'}
        self.assertTrue(self.accepts(json.dumps(value), request))
        bad = deepcopy(value)
        bad['observations'][0]['truth'] = True
        self.assertFalse(self.accepts(json.dumps(bad), request))
        value['observations'][0]['numeric'] = {'kind': 'value', 'source_quote': 'Brightness was 8.',
            'left': {'value': '8', 'unit': '', 'quote': '8'}, 'right': {'value': '8', 'unit': '', 'quote': '8'}}
        self.assertFalse(self.accepts(json.dumps(value), request))
        payload = json.loads(request[1]['content'])
        payload['context'] += ' Brightness was 8.'
        request[1]['content'] = json.dumps(payload)
        self.assertTrue(self.accepts(json.dumps(value), request))

    def test_actual_adapter_passes_filter_and_records_schema_hash(self):
        tokenizer = TinyTokenizer()
        target = json.dumps(plan(), separators=(',', ':'))
        class ScriptedModel:
            def generate(self, *, input_ids, prefix_allowed_tokens_fn, max_new_tokens, do_sample, pad_token_id,
                         num_beams, repetition_penalty):
                assert num_beams == 1 and repetition_penalty == 1.05
                self.options = (max_new_tokens, do_sample)
                ids = Sequence(input_ids[0])
                for token in tokenizer.encode(target):
                    assert token in prefix_allowed_tokens_fn(0, ids)
                    ids.append(token)
                assert tokenizer.eos_token_id in prefix_allowed_tokens_fn(0, ids)
                ids.append(tokenizer.eos_token_id)
                return Tensor([ids])
        model = ScriptedModel()
        backend = d.ConstrainedAtomicBackend(model, tokenizer)
        events = []
        backend.on_generation = events.append
        with patch.dict(sys.modules, {'torch': SimpleNamespace(inference_mode=nullcontext)}):
            result = backend.generate_json(messages(), max_new_tokens=1536)
        self.assertEqual(result, plan())
        self.assertEqual(model.options, (1536, False))
        self.assertEqual(events[0]['structured_decoder'], d.DECODER)
        self.assertEqual(events[0]['schema_sha256'], d.schema_sha256(d.schema_for(messages())[0]))

    def test_serving_backend_uses_no_constraint_options_and_unknown_request_stops(self):
        self.assertEqual(j.TransformersJSONBackend(None, None).generation_options(messages()), {})
        request = messages()
        request[1]['content'] = '{"claim":"The lamp shone.","label":"support"}'
        with self.assertRaises(ValueError):
            self.backend.generation_options(request)


if __name__ == '__main__':
    unittest.main()
