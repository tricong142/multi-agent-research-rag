"""Parse and ground scientific assertions from the constrained JSON protocol."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from copy import copy
import re
import unicodedata


# This tokenizer preserves hyphenated terms and decimal/fraction literals.
_TOKEN = re.compile(r"[+−-]?\d+(?:[.,/]\d+)*|[^\W\d_]+(?:[-‐‑][^\W\d_]+)*|[^\s\w]", re.UNICODE)
_FUNCTION_WORDS = frozenset('a an the of in on at by as is are was were be been to for and or that this here'.split())
_NEGATION = frozenset({'no', 'not', 'never', 'without', 'neither', 'nor'})
_EXCLUSIVE = frozenset({'only', 'solely', 'exclusively', 'just'})
_TRADEOFF = ('at', 'the', 'cost', 'of')
PLURAL_REFERENCES = frozenset({'them', 'these', 'those', 'both', 'they'})
_CLAUSE_CUES = (('without',), ('despite',), ('regardless', 'of'), ('although',), ('even', 'though'),
                _TRADEOFF)
_CUES = {
    'not': _NEGATION,
    'only': _EXCLUSIVE,
    'gt': frozenset({'above', 'greater', 'higher', 'more', 'over', 'exceeds'}),
    'lt': frozenset({'below', 'less', 'lower', 'under', 'fewer'}),
    'ge': frozenset({'least', 'minimum', '≥'}),
    'le': frozenset({'most', 'maximum', '≤'}),
    'before': frozenset({'before', 'prior', 'first', 'followed', 'phases', 'steps'}),
    'respectively': frozenset({'respectively'}),
}
RELATIONS = ('eq', 'not', 'only', 'gt', 'lt', 'ge', 'le', 'includes', 'before', 'transition', 'respectively')
KINDS = ('text', 'number', 'reference')
MAX_FACTS = 12
MAX_ITEMS = 6
MAX_EVIDENCE = 4
MAX_SPAN = 384
MAX_MENTION = 160
MAX_KEY = 80
_ORDINALS = {name: n for n, name in enumerate(
    'first second third fourth fifth sixth seventh eighth ninth tenth'.split(), 1)}
_CARDINALS = {name: n for n, name in enumerate('zero one two three four five six seven eight nine ten'.split())}


def tokens(text):
    return tuple(m[0].casefold().replace('‑', '-').replace('‐', '-') for m in _TOKEN.finditer(text))


def key_tokens(text):
    words = tokens(unicodedata.normalize('NFKC', text))
    return tuple(word for word in words if any(c.isalnum() for c in word) and word not in _FUNCTION_WORDS)


def literal_spans(texts):
    """Enumerate bounded token-aligned phrases and exact number spellings."""
    phrases, numbers = set(), set()
    for text in texts:
        matches = list(_TOKEN.finditer(text))
        for index, first in enumerate(matches):
            if not any(char.isalnum() for char in first[0]):
                continue
            for last in matches[index:index + 16]:
                if last.end() - first.start() > MAX_MENTION:
                    break
                if any(char.isalnum() for char in last[0]) or last[0] in {'%', ')', ']', '"', "'", '’'}:
                    phrases.add(text[first.start():last.end()])
            try:
                number(first[0])
            except ValueError:
                continue
            numbers.add(first[0])
    return sorted(phrases), sorted(numbers)


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class Mention:
    key: tuple[str, ...]
    span: Span


@dataclass(frozen=True)
class Value:
    kind: str
    mention: Mention
    number: Fraction | None
    unit: str


@dataclass(frozen=True)
class Fact:
    subjects: tuple[Mention, ...]
    property: Mention
    scope: tuple[Mention, ...]
    relation: str
    values: tuple[Value, ...]
    evidence: tuple[Span, ...]


def span_in(text, source, start=0):
    index = source.find(text)
    if index == -1 or source.find(text, index + 1) != -1:
        raise ValueError('unbound_or_ambiguous_span')
    end = index + len(text)
    if any(m.start() < index < m.end() or m.start() < end < m.end() for m in _TOKEN.finditer(source)):
        raise ValueError('partial_token_span')
    return Span(start + index, start + end, text)


def number(text):
    value = text.casefold().replace('−', '-')
    if value.endswith('fold'):
        value = value[:-4].removesuffix('-')
    if value in _ORDINALS or value in _CARDINALS:
        return Fraction((_ORDINALS | _CARDINALS)[value])
    pieces = value.split('/')
    try:
        if len(pieces) > 2 or any(not re.fullmatch(r'[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?', p)
                                  for p in pieces):
            raise ValueError('invalid_numeric_literal')
        values = [Fraction(Decimal(p.replace(',', ''))) for p in pieces]
        return values[0] if len(values) == 1 else values[0] / values[1]
    except (InvalidOperation, ZeroDivisionError) as exc:
        raise ValueError('invalid_numeric_literal') from exc


def _text(value, maximum, *, optional=False):
    if (not isinstance(value, str) or len(value) > maximum or value != value.strip()
            or not value and not optional):
        raise ValueError('invalid_structured_string')
    return value


def _object(value, fields):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError('invalid_structured_fields')


def _items(value, maximum, *, minimum=0):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ValueError('invalid_structured_list')
    return value


def _unit_span(unit, number_span, assertion):
    start = number_span.start - assertion.start
    end = number_span.end - assertion.start
    before = assertion.text[:start].rstrip()
    after = assertion.text[end:].lstrip()
    if after.startswith(('-', '‐', '‑')):
        after = after[1:]
    if after.startswith(unit) and (len(after) == len(unit) or not (after[len(unit)].isalnum() and unit[-1].isalnum())):
        position = len(assertion.text) - len(after)
    elif before.endswith(unit) and (len(before) == len(unit) or not (before[-len(unit)-1].isalnum() and unit[0].isalnum())):
        position = len(before) - len(unit)
    else:
        raise ValueError('unit_not_attached_to_operand')
    return Span(assertion.start + position, assertion.start + position + len(unit), unit)


def _fact(raw, source, *, claim, numeric_binding=False, bind_repeated=False):
    _object(raw, ('evidence', 'subjects', 'property', 'scope', 'relation', 'cue', 'values'))
    evidence = tuple(span_in(_text(s, MAX_SPAN), source)
                     for s in _items(raw['evidence'], MAX_EVIDENCE, minimum=1))
    if len({s.start for s in evidence}) != len(evidence):
        raise ValueError('duplicate_evidence_span')
    # Evidence[0] contains the predicate and operands. Remaining quotes may bind
    # an explicit antecedent or experimental scope in the same paragraph.
    assertion = evidence[0]
    if any('\n\n' in source[min(s.start, assertion.start):max(s.end, assertion.end)] for s in evidence):
        raise ValueError('cross_paragraph_binding')
    spans = []

    def locate(text, candidates, *, anchor=None):
        for quote in candidates:
            if text in quote.text:
                if bind_repeated:
                    hit = _anchored_span(text, quote, anchor)
                else:
                    hit = span_in(text, quote.text, quote.start)
                spans.append(hit)
                return hit
        raise ValueError('slot_outside_evidence')

    def mention(raw_mention, candidates, *, anchor=None):
        _object(raw_mention, ('text', 'key'))
        key = key_tokens(_text(raw_mention['key'], MAX_KEY))
        if not key:
            raise ValueError('empty_semantic_key')
        return Mention(key, locate(_text(raw_mention['text'], MAX_MENTION), candidates, anchor=anchor))

    subjects = tuple(mention(item, evidence) for item in _items(raw['subjects'], MAX_ITEMS, minimum=1))
    property_ = mention(raw['property'], (assertion,))
    scope_items = _items(raw['scope'], MAX_ITEMS)
    if not bind_repeated:
        scope = tuple(mention(item, evidence) for item in scope_items)
    relation = raw['relation']
    if relation not in RELATIONS or claim and relation == 'respectively':
        raise ValueError('invalid_relation')
    cue = _text(raw['cue'], MAX_MENTION, optional=True)
    cue_span = locate(cue, (assertion,), anchor=property_.span) if cue else None
    if relation in _CUES and not _CUES[relation].intersection(tokens(cue)):
        raise ValueError('unbound_relation_cue')

    # A plural anaphor can take its member list from a cited local antecedent.
    member_quotes = evidence if relation == 'includes' and PLURAL_REFERENCES.intersection(
        tokens(assertion.text)
    ) else (assertion,)
    raw_values = _items(raw['values'], MAX_ITEMS, minimum=1)
    if (bind_repeated and relation == 'eq' and len(raw_values) > 1
            and all(isinstance(value, dict) and value.get('kind') == 'number' for value in raw_values)):
        raise ValueError('multiple_scalar_operands_need_fields')
    values = []
    for raw_value in raw_values:
        _object(raw_value, ('kind', 'text', 'key', 'unit'))
        kind = raw_value['kind']
        if kind not in KINDS or kind == 'reference' and not claim:
            raise ValueError('invalid_value_kind')
        candidates = member_quotes if kind == 'text' else (assertion,)
        value = mention({'text': raw_value['text'], 'key': raw_value['key']}, candidates,
                        anchor=property_.span if kind == 'number' and relation == 'eq' else None)
        unit = _text(raw_value['unit'], MAX_KEY, optional=True)
        if unit:
            spans.append(_unit_span(unit, value.span, assertion))
        if kind != 'number' and unit:
            raise ValueError('unexpected_unit')
        unit_key = 'percent' if unit.casefold() in {'%', 'percent', 'per cent'} else ' '.join(key_tokens(unit))
        values.append(Value(kind, value, number(value.span.text) if kind == 'number' else None, unit_key))
    if bind_repeated:
        scope_anchor = values[0].mention.span if len(values) == 1 and values[0].kind == 'number' else property_.span
        scope = tuple(mention(item, evidence, anchor=scope_anchor) for item in scope_items)
    if relation == 'respectively':
        if (len(subjects) != len(values) or len(values) < 2
                or any(s.span.start < assertion.start or s.span.end > assertion.end for s in subjects)
                or not _ordered([s.span for s in subjects]) or not _ordered([v.mention.span for v in values])):
            raise ValueError('invalid_parallel_alignment')
    elif len(subjects) != 1:
        raise ValueError('unexpected_multiple_subjects')
    if relation in {'gt', 'lt', 'ge', 'le'} and (len(values) != 1 or values[0].kind == 'text'):
        raise ValueError('invalid_comparison_operand')
    if relation == 'before' and (len(values) != 2 or any(v.kind != 'text' for v in values)):
        raise ValueError('invalid_order_operands')
    if relation == 'before' and not _ordered([v.mention.span for v in values]):
        raise ValueError('reversed_order_operands')
    if relation == 'transition':
        if len(values) != 2 or any(v.kind != 'number' for v in values):
            raise ValueError('invalid_transition_operands')
        prefixes = [tokens(source[assertion.start:v.mention.span.start]) for v in values]
        if not prefixes[0] or not prefixes[1] or prefixes[0][-1] != 'from' or prefixes[1][-1] != 'to':
            raise ValueError('unbound_transition_direction')
        if numeric_binding:
            for value, cue_word in zip(values, ('from', 'to')):
                prefix = source[assertion.start:value.mention.span.start].rstrip()
                end = assertion.start + len(prefix)
                if source[end-len(cue_word):end].casefold() == cue_word:
                    spans.append(Span(end-len(cue_word), end, source[end-len(cue_word):end]))
    if relation == 'eq' and not _ordered([v.mention.span for v in values]):
        raise ValueError('reversed_value_operands')
    if any(v.kind == 'reference' for v in values) and relation not in {'gt', 'lt', 'ge', 'le'}:
        raise ValueError('invalid_reference_operand')

    # Negation in a scoped condition is valid. Negation in the asserted value
    # must be represented by the fact relation rather than swallowed by a key.
    asserted = set(tokens(property_.span.text)) | {t for v in values for t in tokens(v.mention.span.text)}
    if asserted & _NEGATION and relation != 'not':
        raise ValueError('unrepresented_negation')
    if not claim and relation != 'not':
        predicate = (property_.span, *(v.mention.span for v in values
                                      if assertion.start <= v.mention.span.start < assertion.end))
        start = min(s.start for s in predicate)
        end = max(s.end for s in predicate)
        # Also catch a negation immediately before a selected assertion fragment.
        prefix = list(_TOKEN.finditer(source, max(0, start - MAX_MENTION), start))
        nearest = next((m for m in reversed(prefix) if m[0].casefold() not in _FUNCTION_WORDS), None)
        if nearest and nearest[0].casefold() in _NEGATION:
            start = nearest.start()
        for token in _TOKEN.finditer(source, start, end):
            if (token[0].casefold() in _NEGATION
                    and not any(s.span.start <= token.start() < s.span.end for s in scope)):
                raise ValueError('unrepresented_source_negation')
    qualifiers = [s.span for s in scope] + ([cue_span] if cue_span else [])
    return Fact(subjects, property_, scope, relation, tuple(values), evidence), spans, qualifiers


def _ordered(spans):
    return all(left.end <= right.start for left, right in zip(spans, spans[1:]))


def _anchored_span(text, quote, anchor):
    """Prefer a unique whole-token hit, using a local field only for repeats."""
    boundaries = {i for m in _TOKEN.finditer(quote.text) for i in range(m.start() + 1, m.end())}
    occurrences = list(re.finditer(re.escape(text), quote.text))
    hits = [Span(quote.start + m.start(), quote.start + m.end(), text)
            for m in occurrences if m.start() not in boundaries and m.end() not in boundaries]
    if len(hits) == 1:
        return hits[0]
    if occurrences and not hits:
        raise ValueError('partial_token_span')
    if anchor and quote.start <= anchor.start < anchor.end <= quote.end:
        nearby = []
        for hit in hits:
            if anchor.end <= hit.start:
                gap = quote.text[anchor.end - quote.start:hit.start - quote.start]
            elif hit.end <= anchor.start:
                gap = quote.text[hit.end - quote.start:anchor.start - quote.start]
            elif anchor.start <= hit.start and hit.end <= anchor.end:
                gap = ''
            else:
                continue
            if re.fullmatch(r'\s*(?:(?:of|was|is|equals|set to)\s+|[=:]\s*)?', gap, re.I):
                nearby.append(hit)
        if len(nearby) == 1:
            return nearby[0]
    raise ValueError('unbound_or_ambiguous_span')


def parse_requirements(raw, claim, *, detailed_errors=False, numeric_binding=False, bind_repeated=False):
    _object(raw, ('requirements', 'unresolved'))
    unresolved = _items(raw['unresolved'], MAX_ITEMS)
    if unresolved:
        raise ValueError('unresolved_requirements')
    parsed = [_fact(row, claim, claim=True, numeric_binding=numeric_binding, bind_repeated=bind_repeated)
              for row in _items(raw['requirements'], MAX_FACTS, minimum=1)]
    covered = {i for _, spans, _ in parsed for span in spans for i in range(span.start, span.end)}
    if bind_repeated:
        for fact, _, _ in parsed:
            if fact.relation == 'eq' and len(fact.values) == 1 and fact.values[0].kind == 'number':
                start = fact.values[0].mention.span.start
                cue = re.search(r'\bexactly\s+$', claim[:start], re.I)
                if cue:
                    covered.update(range(cue.start(), start))
    matches = list(_TOKEN.finditer(claim))
    missing = []
    for match in matches:
        token = match[0].casefold()
        if (bind_repeated and token == 's' and match.start() >= 2
                and claim[match.start() - 1] in "'’" and match.start() - 2 in covered):
            continue
        if (token not in _FUNCTION_WORDS and (any(c.isalnum() for c in token) or token in {'%', '≥', '≤'})
                and not all(i in covered for i in range(match.start(), match.end()))):
            missing.append(match[0])
    if missing:
        detail = ': ' + ', '.join(missing) if detailed_errors else ''
        raise ValueError('uncovered_claim_content' + detail)
    claim_tokens = tokens(claim)
    qualifiers = [span for _, _, spans in parsed for span in spans]
    for i, match in enumerate(matches):
        for cue in _CLAUSE_CUES:
            if claim_tokens[i:i + len(cue)] != cue:
                continue
            end = matches[i + len(cue) - 1].end()
            if not any(span.start <= match.start() and end <= span.end for span in qualifiers):
                raise ValueError('unbound_claim_condition')
            if cue == _TRADEOFF:
                predicates = [fact for fact, _, _ in parsed]
                if (not any(f.property.span.end <= match.start() for f in predicates)
                        or not any(f.property.span.start >= match.start()
                                   and all(v.mention.span.start >= end for v in f.values) for f in predicates)):
                    raise ValueError('unbound_tradeoff_requirement')
    return tuple(fact for fact, _, _ in parsed)


def parse_observations(raw, context, *, bind_repeated=False):
    _object(raw, ('facts',))
    return tuple(_fact(row, context, claim=False, bind_repeated=bind_repeated)[0] for row in _items(raw['facts'], MAX_FACTS))


def checked_json_parser(parser, *, filtered_cache=False):
    from lmformatenforcer import CharacterLevelParser
    from lmformatenforcer.jsonschemaparser import JsonSchemaParser
    config = parser.config

    class CheckedParser(CharacterLevelParser):
        """Apply the same grammar checks inside single and multi-character tokens."""

        def __init__(self, state):
            super().__init__(config)
            self.state = state

        def add_character(self, character):
            if character not in self.state.get_allowed_characters():
                raise ValueError('Character violates the JSON grammar')
            return CheckedParser(self.state.add_character(character))

        def get_allowed_characters(self):
            return self.state.get_allowed_characters()

        def can_end(self):
            return self.state.can_end()

        def shortcut_key(self):
            if not filtered_cache:
                return None
            return self.state.shortcut_key() if self._no_pending_whitespace(self.state) else None

        @staticmethod
        def _no_pending_whitespace(state):
            if isinstance(state, JsonSchemaParser):
                return state.num_consecutive_whitespaces == 0
            children = getattr(state, 'parsers', ())
            return bool(children) and all(CheckedParser._no_pending_whitespace(child) for child in children)

    return CheckedParser(parser)


def filtered_token_tree(tree, config):
    """Keep the shared trie and rebuild the request's free-text shortcut cache."""
    from lmformatenforcer.tokenizerprefixtree import JsonFreetextTokenCache

    scoped = copy(tree)
    original = tree.json_freetext_tokens
    cache = JsonFreetextTokenCache(original.use_bitmask, original.vocab_size)
    alphabet = set(config.alphabet) | {'\\'}
    repeated_whitespace = re.compile(r'[ \t\r\n]{' + str(config.max_consecutive_whitespaces + 1) + r'}')
    for token, text in tree.tokens_to_strs.items():
        if set(text) <= alphabet and not repeated_whitespace.search(text):
            cache.add_token(text, token)
    cache.freeze()
    scoped.json_freetext_tokens = cache
    return scoped
