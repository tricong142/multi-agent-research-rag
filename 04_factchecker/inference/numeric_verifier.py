"""Conservative, source-checked Decimal comparisons for the experimental verifier."""
from __future__ import annotations

from decimal import Decimal, localcontext
import re

from .evidence_screen import DIGITS, DIRECTION_WORDS, WORDS, quantities


def numeric_requirements(claim_part: str) -> list[dict]:
    """Keep quantity occurrences and their immediate unit/object, including repeats."""
    excluded = [m.span() for m in re.finditer(r'\b(?:at least one|one or more)\b', claim_part, re.I)]
    matches = list(DIGITS.finditer(claim_part))
    matches += list(re.finditer(r'\b(?:' + '|'.join(WORDS) + r')\b', claim_part, re.I))
    requirements = []
    for match in sorted(matches, key=lambda m: m.start()):
        if any(start <= match.start() < end for start, end in excluded):
            continue
        end = match.end()
        unit = '%' if '%' in match[0] else 'percent' if re.search(r'\bpercent\b', match[0], re.I) else ''
        # shortcut: immediate English unit/count noun only; compound associations
        # remain unknown until a separately evaluated binding grammar is added.
        if not re.search(r'%|\bpercent\b', match[0], re.I):
            tail = re.match(r'\s+([A-Za-z]+)\b', claim_part[end:])
            if tail and tail[1].casefold() not in {'before', 'after', 'to', 'and', 'on', 'in', 'at', 'for', 'with', 'than', 'or'}:
                end += tail.end()
                unit = tail[1]
        quote = claim_part[match.start():end]
        value, kind = next(iter(quantities(match[0])))
        requirements.append({'start': match.start(), 'end': end, 'quote': quote,
                             'value': str(value), 'unit': unit, 'kind': kind})
    return requirements


def direction(text: str) -> str | None:
    values = {DIRECTION_WORDS[w] for w in re.findall(r'[a-z]+', text.lower()) if w in DIRECTION_WORDS}
    values.update({'increase' for _ in re.finditer(r'\b(?:rose|raised|more)\b', text, re.I)})
    values.update({'decrease' for _ in re.finditer(r'\b(?:fell|less)\b', text, re.I)})
    return next(iter(values)) if len(values) == 1 else None


def _occurrences(quote: str, source: str):
    return [m for m in re.finditer(re.escape(quote), source)
            if not (quote[0].isalnum() and m.start() and source[m.start() - 1].isalnum())
            and not (quote[-1].isalnum() and m.end() < len(source) and source[m.end()].isalnum())
            and not (quote[0].isdigit() and m.start() and source[m.start() - 1] in '+-.,')
            and not (quote[-1].isdigit() and re.match(r'[.,]\d', source[m.end():]))]


def _operand(raw: dict, source: str) -> tuple[Decimal, str, str]:
    if not isinstance(raw, dict) or set(raw) != {'value', 'unit', 'quote'}:
        raise ValueError('numeric_operand_schema')
    value, unit, quote = raw['value'], raw['unit'], raw['quote']
    if not all(isinstance(s, str) for s in (value, unit, quote)):
        raise ValueError('numeric_operand_schema')
    if not quote.strip() or len(quote) > 2000 or len(unit) > 40 or not _occurrences(quote, source):
        raise ValueError('numeric_source_membership')
    if not re.fullmatch(r'[+-]?\d+(?:\.\d+)?', value) or len(value) > 60:
        raise ValueError('numeric_value_format')
    number = Decimal(value)
    found = quantities(quote)
    if len(found) != 1 or next(iter(found))[0] != number:
        raise ValueError('numeric_value_not_grounded')
    kind = next(iter(found))[1]
    if kind == 'percent' and unit not in ('%', 'percent'):
        raise ValueError('numeric_unit_not_grounded')
    if kind != 'percent' and unit in ('%', 'percent'):
        raise ValueError('numeric_unit_not_grounded')
    if unit and not (unit == '%' and '%' in quote or re.search(r'(?<!\w)' + re.escape(unit) + r'(?!\w)', quote, re.I)):
        raise ValueError('numeric_unit_not_grounded')
    # Empty units are allowed only for a bare dimensionless number/count.
    words = set(re.findall(r'[a-z]+', quote.lower())) - set(WORDS)
    if not unit and words:
        raise ValueError('numeric_unit_required')
    if not unit:
        for match in _occurrences(quote, source):
            tail = re.match(r'\s*(%|[A-Za-z]+)', source[match.end():])
            if tail and tail[1].casefold() not in {'before', 'after', 'to', 'and', 'on', 'in', 'at', 'for', 'with', 'than'}:
                raise ValueError('numeric_unit_required')
    return number, '%' if unit == 'percent' else unit.casefold(), quote


def check_numeric(raw: dict, claim_part: str, context: str) -> dict:
    """Return unknown on unsupported comparisons; malformed source records raise.

    Scope/metric association is an explicit model judgment in the caller. Exact
    source membership and arithmetic do not independently prove that association.
    """
    if not isinstance(raw, dict) or set(raw) != {'kind', 'source_quote', 'left', 'right'}:
        raise ValueError('numeric_schema')
    kind, proof = raw['kind'], raw['source_quote']
    if kind not in ('value', 'change') or not isinstance(proof, str) or not proof.strip():
        raise ValueError('numeric_schema')
    if len(proof) > 2000 or not _occurrences(proof, context):
        raise ValueError('numeric_source_membership')
    left, left_unit, left_quote = _operand(raw['left'], claim_part if kind == 'value' else proof)
    right, right_unit, right_quote = _operand(raw['right'], proof)
    result = {'kind': kind, 'input': raw, 'truth': 'unknown', 'reason': '',
              'left': str(left), 'right': str(right), 'unit': left_unit}
    if kind == 'value':
        requirements = numeric_requirements(claim_part)
        bound = [r for r in requirements if r['quote'] == left_quote]
        if len(requirements) > 1 and len(bound) != 1:
            return {**result, 'reason': 'numeric_requirement_binding_unresolved'}
        if len(requirements) <= 1 and quantities(claim_part, claim=True) != quantities(left_quote):
            return {**result, 'reason': 'unbound_claim_quantity'}
        if bound:
            result['requirement'] = bound[0]
    if re.search(r'\b(?:not|never|without)\b', claim_part, re.I):
        return {**result, 'reason': 'unsupported_numeric_negation'}
    if re.search(r'[<>\u2260\u2264\u2265\u2248]', claim_part):
        return {**result, 'reason': 'unsupported_comparison_operator'}
    if kind == 'value' and re.search(r'\b(?:about|approximately|between|up to|less than|more than|at least|at most|over|under)\b', claim_part, re.I):
        return {**result, 'reason': 'unsupported_threshold_or_approximation'}
    # shortcut: explicit "observed X, not claimed Y" only; no inferred unit conversion.
    if kind == 'value' and direction(claim_part) is None and (left, left_unit) != (right, right_unit):
        denial = re.search(r'(?<!\w)' + re.escape(right_quote) + r'\s*,?\s+(?:but\s+)?not\s+'
                           + re.escape(left_quote) + r'(?!\w)', proof, re.I)
        remainder = proof[:denial.start()] + proof[denial.end():] if denial else proof
        if denial and not re.search(r'\b(?:not|never|without|hypothetical|would|could|may|might|should|if|expected|predicted|approximately|about)\b', remainder, re.I):
            return {**result, 'truth': 'false', 'reason': 'explicit_quantity_denial'}
    if re.search(r'\b(?:not|never|hypothetical|would|could|may|might|should|if|expected|predicted|approximately|about)\b', proof, re.I):
        return {**result, 'reason': 'qualified_numeric_evidence'}
    if left_unit != right_unit:
        return {**result, 'reason': 'unit_mismatch_no_conversion'}
    if kind == 'value':
        requested = direction(claim_part)
        if requested and direction(proof) != requested:
            return {**result, 'reason': 'reported_change_direction_not_matched'}
        truth = left == right
        return {**result, 'truth': 'true' if truth else 'false', 'reason': 'exact_value_comparison'}

    requested = direction(claim_part)
    if requested is None:
        return {**result, 'reason': 'ambiguous_requested_direction'}
    if quantities(claim_part, claim=True):
        return {**result, 'reason': 'change_amount_requires_additional_rule'}
    # shortcut: two English pair forms only; extend after numerical evaluation.
    # No guessed chronology, cross-sentence joins or automatic unit conversion.
    a, b = re.escape(left_quote), re.escape(right_quote)
    patterns = (
        r'\bfrom\s+' + a + r'\s+(?:before\s+[\w -]{1,80}\s+)?to\s+' + b,
        a + r'\s+before\s+[\w -]{1,80}?\s+and\s+' + b + r'\s+after\b',
    )
    if not any(re.search(p, proof, re.I) for p in patterns):
        return {**result, 'reason': 'unbound_before_after_order'}
    if quantities(proof) != {(left, 'percent' if left_unit == '%' else 'number'),
                             (right, 'percent' if right_unit == '%' else 'number')}:
        return {**result, 'reason': 'ambiguous_numeric_passage'}
    observed = 'increase' if right > left else 'decrease' if right < left else 'unchanged'
    with localcontext() as decimal_context:
        decimal_context.prec = 128  # Operands are bounded to 60 characters each.
        delta = str(right - left)
    return {**result, 'truth': 'true' if observed == requested else 'false',
            'reason': 'ordered_change_comparison', 'requested_direction': requested,
            'observed_direction': observed, 'delta': delta}
