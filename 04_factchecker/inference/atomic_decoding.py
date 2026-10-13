"""Schema-constrained decoding for the isolated atomic candidate, not serving."""
from __future__ import annotations

from contextlib import contextmanager
from importlib.metadata import version
import hashlib
import json
import re

from .atomic_verifier import DECOMPOSE_PROMPT, ASSESS_PROMPT, _quantifier, scope_restrictions
from .judge import TransformersJSONBackend

DECODER = {'engine': 'lm-format-enforcer', 'version': '0.11.3',
           'interegular': '0.3.3', 'policy': 'atomic-schema-decoding-v2',
           'source_enum_max_words': 80, 'strict_field_order': True,
           'max_consecutive_whitespaces': 4, 'num_beams': 1,
           'repetition_penalty': 1.05}


def obj(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties),
            'additionalProperties': False}


def array(items, *, minimum=0, maximum=16):
    return {'type': 'array', 'items': items, 'minItems': minimum, 'maxItems': maximum}


TEXT = {'type': 'string'}


def claim_spans(claim):
    words = list(re.finditer(r'\S+', claim))
    if not words or len(words) > DECODER['source_enum_max_words']:
        raise ValueError('Claim exceeds the frozen constrained-decoder word limit')
    spans = {claim}
    for word in words:
        for last in words:
            if last.end() <= word.start():
                continue
            value = claim[word.start():last.end()]
            spans.add(value)
            trimmed = value.rstrip(',.;:')
            if trimmed:
                spans.add(trimmed)
    return sorted(spans)


def decomposition_schema(claim):
    spans = claim_spans(claim)
    conjunction = bool(re.search(r'\band\b', claim, re.I))
    unique = [v for v in spans if claim.find(v, claim.find(v) + 1) == -1] if conjunction else [claim]
    quantifier = _quantifier(claim)
    quantifiers = [quantifier] if quantifier is not None else ['atomic', 'all', 'some', 'none']
    restrictions = scope_restrictions(claim)
    scope_values = {key: spans + ([''] if key in ('time', 'condition') else [])
                    for key in ('entity', 'metric', 'time', 'condition')}
    if restrictions['time']:
        scope_values['time'] = (restrictions['time'] if len(restrictions['time']) == 1 else
                               [s for s in spans if all(v in s for v in restrictions['time'])])
    if restrictions['condition']:
        scope_values['condition'] = [s for s in spans if all(v in s for v in restrictions['condition'])]
    else:
        scope_values['condition'] = [s for s in scope_values['condition']
                                     if not re.search(r'\b(?:after|before|during)\b', s, re.I)]
    part = obj({'quote': {'type': 'string', 'enum': unique},
                'quantifier': {'type': 'string', 'enum': quantifiers},
                'scope': obj({key: {'type': 'string', 'enum': values} for key, values in scope_values.items()})})
    return obj({'parts': array(part, minimum=1, maximum=12 if conjunction else 1), 'unresolved': array(TEXT)})


def assessment_schema():
    operand = obj({'value': TEXT, 'unit': TEXT, 'quote': TEXT})
    numeric = obj({'kind': {'type': 'string', 'enum': ['value', 'change']},
                   'source_quote': TEXT, 'left': operand, 'right': operand})
    observation = obj({'member': TEXT, 'truth': {'type': 'string', 'enum': ['true', 'false', 'unknown']},
                       'quotes': array(TEXT), 'explanation': TEXT,
                       'numeric': {'anyOf': [{'type': 'null'}, numeric]}})
    return obj({'scope_match': {'type': 'string', 'enum': ['matched', 'mismatched', 'unknown']},
                'coverage': obj({'complete': {'type': 'boolean'}, 'members': array(TEXT), 'quotes': array(TEXT)}),
                'observations': array(observation), 'missing_information': array(TEXT), 'explanation': TEXT})


def schema_for(messages):
    payload = json.loads(messages[1]['content'])
    if messages[0]['content'] == DECOMPOSE_PROMPT and set(payload) == {'claim'}:
        return decomposition_schema(payload['claim']), payload['claim']
    if messages[0]['content'] == ASSESS_PROMPT and set(payload) == {'claim', 'part', 'context'}:
        return assessment_schema(), payload['claim'] + payload['context']
    raise ValueError('Unsupported constrained atomic request')


def schema_sha256(schema):
    return hashlib.sha256(json.dumps(schema, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class ConstrainedAtomicBackend(TransformersJSONBackend):
    def __init__(self, model, tokenizer):
        from lmformatenforcer import TokenEnforcerTokenizerData
        if version('lm-format-enforcer') != DECODER['version'] or version('interegular') != DECODER['interegular']:
            raise ValueError('Structured decoder dependency version differs from frozen policy')
        super().__init__(model, tokenizer)
        # Build the 150k-token prefix tree once per loaded tokenizer, not per call.
        # LMFE 0.11.3's convenience adapter imports tokenization_utils, removed
        # in Transformers 5. Use its public core and the documented HF callback.
        zero = tokenizer.encode('0')[-1]
        specials = set(tokenizer.all_special_ids)
        vocabulary = []
        for token_id in range(len(tokenizer)):
            if token_id not in specials:
                after_zero = tokenizer.decode([zero, token_id])[1:]
                alone = tokenizer.decode([token_id])
                vocabulary.append((token_id, after_zero, len(after_zero) > len(alone)))
        self.tokenizer_data = TokenEnforcerTokenizerData(vocabulary,
            lambda ids: tokenizer.decode(ids).rstrip('\ufffd'), tokenizer.eos_token_id, False, len(tokenizer))

    def generation_options(self, messages):
        from lmformatenforcer import JsonSchemaParser, CharacterLevelParserConfig, TokenEnforcer
        schema, source = schema_for(messages)
        config = CharacterLevelParserConfig()
        config.force_json_field_order = DECODER['strict_field_order']
        config.max_consecutive_whitespaces = DECODER['max_consecutive_whitespaces']
        config.alphabet += ''.join(sorted(set(source) - set(config.alphabet)))
        enforcer = TokenEnforcer(self.tokenizer_data, JsonSchemaParser(schema, config=config))
        # TokenEnforcer replaces the parser config while initializing its alphabet.
        # Reapply the prospective limits rather than inheriting environment flags.
        enforcer.root_parser.config = config
        def callback(batch_id, input_ids):
            return enforcer.get_allowed_tokens(input_ids.tolist()).allowed_tokens
        self.decoding_metadata = {'structured_decoder': DECODER, 'schema_sha256': schema_sha256(schema)}
        return {'prefix_allowed_tokens_fn': callback, 'num_beams': DECODER['num_beams'],
                'repetition_penalty': DECODER['repetition_penalty']}


def constrained_loader(loader):
    @contextmanager
    def load(kind, criteria):
        if criteria['structured_decoder'] != DECODER:
            raise ValueError('Frozen decoder policy changed')
        with loader(kind, criteria) as (backend, metadata):
            constrained = ConstrainedAtomicBackend(backend.model, backend.tokenizer)
            try:
                yield constrained, {**metadata, 'structured_decoder': DECODER}
            finally:
                constrained.model = None
    return load
