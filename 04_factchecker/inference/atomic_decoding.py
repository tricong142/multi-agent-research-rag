"""Schema-constrained decoding for the isolated atomic candidate, not serving."""
from __future__ import annotations

from contextlib import contextmanager
from importlib.metadata import version
import hashlib
import json
import re
import time

from .atomic_verifier import (DECOMPOSE_PROMPT, ASSESS_PROMPT, ASSESSMENT_LIMITS,
                              CaseDeadlineExceeded, _quantifier, scope_clauses)
from .numeric_verifier import numeric_requirements, _operand
from .judge import TransformersJSONBackend

DECODER = {'engine': 'lm-format-enforcer', 'version': '0.11.3',
           'interegular': '0.3.3', 'policy': 'atomic-schema-decoding-v5',
           'source_enum_max_words': 80, 'strict_field_order': True,
           'max_consecutive_whitespaces': 4, 'num_beams': 1,
           'repetition_penalty': 1.05, 'assessment_limits': ASSESSMENT_LIMITS,
           'deadline_policy': 'absolute_monotonic_per_decode_step'}


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
    alternatives = []
    for clause in scope_clauses(claim):
        quotes = [v for v in unique if clause['start'] <= claim.find(v)
                  and claim.find(v) + len(v) <= clause['end']]
        scope_values = {'entity': spans, 'metric': [clause['required_metric']] if clause['required_metric'] else spans,
                        'time': clause['time'] or [''],
                        'condition': ([s for s in spans if all(v in s for v in clause['condition'])]
                                      if clause['condition'] else [''] + [s for s in spans
                                          if s in clause['source'] and not re.search(r'\b(?:after|before|during)\b', s, re.I)])}
        if not quotes or any(not values for values in scope_values.values()):
            raise ValueError('unsupported_scope_structure')
        alternatives.append(obj({'quote': {'type': 'string', 'enum': quotes},
            'quantifier': {'type': 'string', 'enum': quantifiers},
            'scope': obj({key: {'type': 'string', 'enum': values} for key, values in scope_values.items()})}))
    part = alternatives[0] if len(alternatives) == 1 else {'anyOf': alternatives}
    return obj({'parts': array(part, minimum=1, maximum=12 if conjunction else 1), 'unresolved': array(TEXT)})


def bounded_text(maximum):
    return {'type': 'string', 'minLength': 1, 'maxLength': maximum}


def source_members(context):
    words = list(re.finditer(r'\S+', context))
    return sorted({context[first.start():last.end()].rstrip(',.;:')
                   for i, first in enumerate(words) for last in words[i:i + 8]
                   if last.end() - first.start() <= ASSESSMENT_LIMITS['member_chars']
                   and context[first.start():last.end()].rstrip(',.;:')})


def evidence_passages(context):
    """Exact whole/adjacent sentences; bounded windows for long sentences."""
    maximum = ASSESSMENT_LIMITS['quote_chars']
    bounds = [0] + [m.end() for m in re.finditer(r'[.!?](?=\s|$)|\n', context)] + [len(context)]
    passages = set()
    for i, start in enumerate(bounds[:-1]):
        sentence = context[start:bounds[i + 1]].strip()
        if len(sentence) > maximum:
            words = list(re.finditer(r'\S+', sentence))
            for j, first in enumerate(words):
                ends = [last.end() for last in words[j:] if last.end() - first.start() <= maximum]
                if ends:
                    passages.add(sentence[first.start():max(ends)])
        for end in bounds[i + 1:]:
            value = context[start:end].strip()
            if len(value) > maximum:
                break
            if value:
                passages.add(value)
    return sorted(passages)


def operand_schema(source):
    alternatives = []
    seen = set()
    for requirement in numeric_requirements(source):
        value = {key: requirement[key] for key in ('value', 'unit', 'quote')}
        identity = tuple(value.values())
        if identity in seen:
            continue
        try:
            _operand(value, source)
        except ValueError:
            continue
        seen.add(identity)
        alternatives.append(obj({key: {'type': 'string', 'enum': [text]} for key, text in value.items()}))
    return alternatives


def assessment_schema(claim, part, context):
    if len(context.split()) > ASSESSMENT_LIMITS['context_words']:
        raise ValueError('unsupported_assessment_context')
    limits = ASSESSMENT_LIMITS
    passages, members = evidence_passages(context), source_members(context)
    quote = {'type': 'string', 'enum': passages} if passages else bounded_text(limits['quote_chars'])
    member = {'type': 'string', 'enum': members} if members else bounded_text(limits['member_chars'])
    evidence = array(quote, maximum=limits['quotes_per_record'] if passages else 0)
    left = operand_schema(part['quote']) + operand_schema(context)
    right = operand_schema(context)
    # No finite source operands means no executable numerical proof, never invented values.
    empty_operand = obj({'value': {'type': 'string', 'enum': ['0']},
                         'unit': {'type': 'string', 'enum': ['']}, 'quote': quote})
    left_schema = {'anyOf': left} if left else empty_operand
    right_schema = {'anyOf': right} if right else empty_operand
    numeric = obj({'kind': {'type': 'string', 'enum': ['value', 'change']},
                   'source_quote': quote, 'left': left_schema, 'right': right_schema})
    numeric_schema = {'anyOf': [{'type': 'null'}, numeric, array(numeric, minimum=1)]} if left and right else {'type': 'null'}
    observation = obj({'member': member, 'truth': {'type': 'string', 'enum': ['true', 'false', 'unknown']},
                       'quotes': evidence, 'explanation': bounded_text(limits['explanation_chars']),
                       'numeric': numeric_schema})
    return obj({'scope_match': {'type': 'string', 'enum': ['matched', 'mismatched', 'unknown']},
                'coverage': obj({'complete': {'type': 'boolean'}, 'members': array(member, maximum=16 if members else 0), 'quotes': evidence}),
                'observations': array(observation, maximum=16 if members else 0),
                'missing_information': array(bounded_text(limits['missing_chars']), maximum=limits['missing_items']),
                'explanation': bounded_text(limits['explanation_chars'])})


def schema_for(messages):
    payload = json.loads(messages[1]['content'])
    if messages[0]['content'] == DECOMPOSE_PROMPT and set(payload) == {'claim'}:
        return decomposition_schema(payload['claim']), payload['claim']
    if messages[0]['content'] == ASSESS_PROMPT and set(payload) == {'claim', 'part', 'context'}:
        return assessment_schema(payload['claim'], payload['part'], payload['context']), payload['claim'] + payload['context']
    raise ValueError('Unsupported constrained atomic request')


def schema_sha256(schema):
    return hashlib.sha256(json.dumps(schema, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class DeadlineStop:
    def __init__(self, deadline):
        self.deadline = deadline

    def __call__(self, input_ids, scores, **kwargs):
        return time.monotonic() >= self.deadline


class ConstrainedAtomicBackend(TransformersJSONBackend):
    def __init__(self, model, tokenizer):
        from lmformatenforcer import TokenEnforcerTokenizerData
        if version('lm-format-enforcer') != DECODER['version'] or version('interegular') != DECODER['interegular']:
            raise ValueError('Structured decoder dependency version differs from frozen policy')
        super().__init__(model, tokenizer)
        self._case_deadline = None
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

    @contextmanager
    def generation_deadline(self, deadline):
        previous, self._case_deadline = self._case_deadline, deadline
        try:
            yield True
        finally:
            self._case_deadline = previous

    def generation_options(self, messages):
        from lmformatenforcer import JsonSchemaParser, CharacterLevelParserConfig, TokenEnforcer
        if self._case_deadline is not None and time.monotonic() >= self._case_deadline:
            raise CaseDeadlineExceeded()
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
        options = {'prefix_allowed_tokens_fn': callback, 'num_beams': DECODER['num_beams'],
                   'repetition_penalty': DECODER['repetition_penalty']}
        if self._case_deadline is not None:
            if time.monotonic() >= self._case_deadline:
                raise CaseDeadlineExceeded()
            from transformers import StoppingCriteriaList
            options['stopping_criteria'] = StoppingCriteriaList([DeadlineStop(self._case_deadline)])
            self.decoding_metadata['deadline_stop_enabled'] = True
        return options


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
