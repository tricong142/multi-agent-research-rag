"""Schema-constrained decoding for the isolated atomic candidate, not serving."""
from __future__ import annotations

from contextlib import contextmanager
from importlib.metadata import version
import hashlib
import json
import re
import time

from .atomic_verifier import (DECOMPOSE_PROMPT, ASSESS_PROMPT, ASSESSMENT_LIMITS,
                              CaseDeadlineExceeded, STRUCTURED_CLAIM_PROMPT, STRUCTURED_SOURCE_PROMPT,
                              _quantifier, scope_clauses)
from .numeric_verifier import numeric_requirements, _operand
from .judge import TransformersJSONBackend
from .semantic_verdict import (EVIDENCE_CHECK_PROMPT, NUMERIC_CLAIM_PROMPT, NUMERIC_SOURCE_PROMPT,
                               SOURCE_ID_PROMPT, SYSTEM_PROMPT as VERDICT_PROMPT,
                               schema as verdict_schema, segment_schema)
from .source_ledger import (CLAUSE_RETRY_PROMPT, FIXED_CLAUSE_PROMPT, LEDGER_PROMPT, RELATION_PROMPT, fixed_clause_schema,
                            relation_schema, schema as ledger_schema)
from .source_comparison import RECOVERY_PROMPT, recovery_schema

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


def structured_schema(*, claim):
    from .decoder_parser import KINDS, MAX_EVIDENCE, MAX_FACTS, MAX_ITEMS, MAX_KEY, MAX_MENTION, MAX_SPAN, RELATIONS

    mention = obj({'text': bounded_text(MAX_MENTION), 'key': bounded_text(MAX_KEY)})
    value = obj({'kind': {'type': 'string', 'enum': list(KINDS[:-1] if not claim else KINDS)},
                 'text': bounded_text(MAX_MENTION), 'key': bounded_text(MAX_KEY),
                 'unit': {'type': 'string', 'maxLength': MAX_KEY}})
    fact = obj({'evidence': array(bounded_text(MAX_SPAN), minimum=1, maximum=MAX_EVIDENCE),
                'subjects': array(mention, minimum=1, maximum=1 if claim else MAX_ITEMS),
                'property': mention, 'scope': array(mention, maximum=MAX_ITEMS),
                'relation': {'type': 'string', 'enum': list(RELATIONS[:-1] if claim else RELATIONS)},
                'cue': {'type': 'string', 'maxLength': MAX_MENTION},
                'values': array(value, minimum=1, maximum=MAX_ITEMS)})
    if claim:
        return obj({'requirements': array(fact, minimum=1, maximum=MAX_FACTS),
                    'unresolved': array(bounded_text(MAX_SPAN), maximum=MAX_ITEMS)})
    return obj({'facts': array(fact, maximum=MAX_FACTS)})


def numeric_binding_schema(*, claim, texts, segment_ids=(), targets=()):
    from .decoder_parser import MAX_ITEMS, MAX_KEY, MAX_FACTS, RELATIONS, key_tokens, literal_spans, tokens

    texts = tuple(texts)
    phrases, numbers = literal_spans(texts)
    if not phrases:
        raise ValueError('no_grounded_numeric_text')
    literal = {'type': 'string', 'enum': phrases}

    def key_schema(role):
        if claim:
            return bounded_text(MAX_KEY)
        keys = {item for target in targets for item in ([target[role]] if role == 'property' else target[role])}
        if role == 'subjects':
            # A parallel list can contain subjects outside the claim. Keep
            # their own grounded names so the operands can stay in order.
            keys.update(' '.join(key_tokens(phrase)) for phrase in phrases)
        return {'type': 'string', 'enum': sorted(key for key in keys if key) or ['']}

    def mention(role):
        texts_for_role = literal
        if claim and role == 'scope':
            candidates = [phrase for phrase in phrases
                          if not (tokens(phrase)[0] in numbers and any(c.isdigit() for c in tokens(phrase)[0]))]
            texts_for_role = {'type': 'string', 'enum': candidates}
        return obj({'text': texts_for_role, 'key': key_schema(role)})

    textual = obj({'kind': {'type': 'string', 'enum': ['text', 'reference'] if claim else ['text']},
                   'text': literal, 'key': bounded_text(MAX_KEY), 'unit': {'type': 'string', 'enum': ['']}})
    value = textual
    if numbers:
        numeric = obj({'kind': {'type': 'string', 'enum': ['number']},
                       'text': {'type': 'string', 'enum': numbers}, 'key': bounded_text(MAX_KEY),
                       'unit': {'type': 'string', 'enum': sorted({'', '%', *phrases})}})
        value = {'anyOf': [numeric, textual]}
    fields = {} if claim else {
        'evidence_ids': array({'type': 'string', 'enum': list(segment_ids)}, minimum=1, maximum=4),
        'assertion': {'type': 'string', 'enum': ['', *phrases]},
    }
    scope_size = MAX_ITEMS if claim or any(target['scope'] for target in targets) else 0
    has_transition = any({'from', 'to'} <= set(tokens(text)) for text in texts)
    relations = [relation for relation in (RELATIONS[:-1] if claim else RELATIONS)
                 if relation != 'transition' or has_transition]
    parallel = not claim and any('respectively' in tokens(text) for text in texts)
    fields.update(subjects=array(mention('subjects'), minimum=1, maximum=1 if claim else MAX_ITEMS),
                  property=mention('property'), scope=array(mention('scope'), maximum=scope_size),
                  relation={'type': 'string', 'enum': relations},
                  cue={'type': 'string', 'enum': ['', *phrases]},
                  values=array(value, minimum=1, maximum=MAX_ITEMS))
    if not parallel:
        fields['subjects']['maxItems'] = 1
    fact = obj(fields)
    if claim:
        return obj({'requirements': array(fact, minimum=1, maximum=MAX_FACTS),
                    'unresolved': array(bounded_text(160), maximum=MAX_ITEMS)})
    return obj({'facts': array(fact, maximum=MAX_FACTS)})


def schema_for(messages):
    payload = json.loads(messages[1]['content'])
    if messages[0]['content'] == DECOMPOSE_PROMPT and set(payload) == {'claim'}:
        return decomposition_schema(payload['claim']), payload['claim']
    if messages[0]['content'] == ASSESS_PROMPT and set(payload) == {'claim', 'part', 'context'}:
        return assessment_schema(payload['claim'], payload['part'], payload['context']), payload['claim'] + payload['context']
    if (messages[0]['content'] == STRUCTURED_CLAIM_PROMPT and 'claim' in payload
            and set(payload) <= {'claim', 'binding_rules', 'repair'}):
        return structured_schema(claim=True), payload['claim']
    if (messages[0]['content'] == STRUCTURED_SOURCE_PROMPT and {'context', 'targets'} <= set(payload)
            and set(payload) <= {'context', 'targets', 'binding_rules', 'repair'}):
        return structured_schema(claim=False), payload['context']
    if messages[0]['content'] == NUMERIC_CLAIM_PROMPT and 'claim' in payload and set(payload) <= {'claim', 'repair'}:
        return numeric_binding_schema(claim=True, texts=[payload['claim']]), payload['claim']
    if (messages[0]['content'] == NUMERIC_SOURCE_PROMPT and {'segments', 'targets'} <= set(payload)
            and set(payload) <= {'segments', 'targets', 'repair'}):
        segments = payload['segments']
        return numeric_binding_schema(claim=False, texts=segments.values(), segment_ids=segments,
                                      targets=payload['targets']), ''.join(segments.values())
    if messages[0]['content'] == VERDICT_PROMPT and set(payload) == {'claim', 'context'}:
        return verdict_schema(), payload['claim'] + payload['context']
    if messages[0]['content'] in (SOURCE_ID_PROMPT, EVIDENCE_CHECK_PROMPT) and set(payload) == {'claim', 'segments'}:
        ids = payload['segments'] if messages[0]['content'] == SOURCE_ID_PROMPT else None
        return segment_schema(ids), payload['claim'] + ''.join(payload['segments'].values())
    if (messages[0]['content'] == LEDGER_PROMPT and {'claim', 'segments'} <= set(payload)
            and set(payload) <= {'claim', 'segments', 'repair'}):
        segments = payload['segments']
        return ledger_schema(segments), payload['claim'] + ''.join(segments.values())
    if messages[0]['content'] == RELATION_PROMPT and set(payload) == {'claim', 'fragment', 'segments'}:
        return relation_schema(), payload['claim'] + ''.join(payload['segments'].values())
    if messages[0]['content'] == FIXED_CLAUSE_PROMPT and set(payload) == {'claim', 'clause', 'segments'}:
        return (fixed_clause_schema(payload['clause']['clause_id'], payload['segments']),
                payload['claim'] + ''.join(payload['segments'].values()))
    if messages[0]['content'] == CLAUSE_RETRY_PROMPT and set(payload) == {'claim', 'clause', 'segments', 'scope_context'}:
        return (fixed_clause_schema(payload['clause']['clause_id'], payload['segments']),
                payload['claim'] + ''.join(payload['segments'].values()) + ''.join(payload['scope_context'].values()))
    if messages[0]['content'] == RECOVERY_PROMPT and set(payload) == {'claim', 'segments'}:
        return recovery_schema(payload['segments']), payload['claim'] + ''.join(payload['segments'].values())
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
        parser = JsonSchemaParser(schema, config=config)
        prompt = messages[0]['content']
        verdict = prompt in {VERDICT_PROMPT, SOURCE_ID_PROMPT, EVIDENCE_CHECK_PROMPT, LEDGER_PROMPT, RELATION_PROMPT, FIXED_CLAUSE_PROMPT,
                             CLAUSE_RETRY_PROMPT, RECOVERY_PROMPT}
        structured = verdict or prompt in {STRUCTURED_CLAIM_PROMPT, STRUCTURED_SOURCE_PROMPT,
                                          NUMERIC_CLAIM_PROMPT, NUMERIC_SOURCE_PROMPT}
        if structured:
            from .decoder_parser import checked_json_parser, filtered_token_tree
            parser = checked_json_parser(parser, filtered_cache=True)
        enforcer = TokenEnforcer(self.tokenizer_data, parser)
        if structured:
            enforcer.tokenizer_tree = filtered_token_tree(enforcer.tokenizer_tree, config)
        # TokenEnforcer replaces the parser config while initializing its alphabet.
        # Reapply the prospective limits rather than inheriting environment flags.
        enforcer.root_parser.config = config
        def callback(batch_id, input_ids):
            if structured and self._case_deadline is not None and time.monotonic() >= self._case_deadline:
                raise CaseDeadlineExceeded()
            return enforcer.get_allowed_tokens(input_ids.tolist()).allowed_tokens
        policy = 'atomic-structured-json-v1'
        if verdict:
            policy = 'factcheck-verdict-json-v1' if prompt == VERDICT_PROMPT else 'factcheck-source-id-v1'
        decoder = {**DECODER, 'policy': policy} if structured else DECODER
        self.decoding_metadata = {'structured_decoder': decoder, 'schema_sha256': schema_sha256(schema)}
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
