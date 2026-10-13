"""Experimental conservative support screen, not an entailment verifier.

It only raises review flags; it never assigns a replacement label. Numerical
presence and lexical overlap cannot establish that evidence entails a claim.
"""
from __future__ import annotations

from decimal import Decimal
import re

from .verifier import Verification, validate_verification


POLICY = 'evidence-screen-v1'
NUMBER = r'[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?'
DIGITS = re.compile(r'(?<![\w.])(' + NUMBER + r')(?:\s*(%|percent\b))?(?!\w|\.\d)', re.I)
WORDS = dict(zip('zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty'.split(), range(21)))
FUNCTION_WORDS = set('a an the and or but on in of for to from with by at as than its it that this these those all every each some none no one after before same'.split())
DIRECTION_WORDS = {'reduced': 'decrease', 'reduce': 'decrease', 'decreased': 'decrease', 'decrease': 'decrease',
                   'lowered': 'decrease', 'lower': 'decrease', 'increased': 'increase', 'increase': 'increase',
                   'raised': 'increase', 'raise': 'increase', 'unchanged': 'unchanged'}
FUNCTION_WORDS.update(DIRECTION_WORDS)
FUNCTION_WORDS.update('uses use used retains retain retained became become was is were are has had improved improves worsened'.split())
BEFORE_AFTER = re.compile(
    r'(?P<metric>[A-Za-z][A-Za-z -]{0,70})\s+(?:was|is)\s+(?P<before>' + NUMBER + r')\s+'
    r'(?P<before_unit>[A-Za-z]+)\s+before\s+(?P<event>[A-Za-z -]{1,60}?)\s+and\s+'
    r'(?P<after>' + NUMBER + r')\s+(?P<after_unit>[A-Za-z]+)\s+after\b', re.I)


def terms(text: str) -> set[str]:
    return {w for w in re.findall(r'[a-z]+', text.casefold()) if w not in FUNCTION_WORDS and w not in WORDS}


def quantities(text: str, *, claim: bool = False) -> set[tuple[Decimal, str]]:
    # Existential thresholds are logical operators, not measured quantities.
    if claim:
        text = re.sub(r'\b(?:at least one|one or more)\b', '', text, flags=re.I)
    values = {(Decimal(m.group(1).replace(',', '')), 'percent' if m.group(2) else 'number')
              for m in DIGITS.finditer(text)}
    values.update((Decimal(WORDS[w]), 'number') for w in re.findall(r'[a-z]+', text.casefold()) if w in WORDS)
    return values


def screen_support(claim: str, context: str, decision: Verification) -> dict:
    """Only claim/context/validated output cross this boundary, never gold labels."""
    if not isinstance(claim, str) or not claim.strip() or not isinstance(context, str):
        raise ValueError('Provide a nonempty claim and string context')
    if not isinstance(decision, Verification):
        raise ValueError('Provide a validated Verification')
    validate_verification(decision.as_dict(), context)
    if decision.assessed_label != 'support':
        return {'policy': POLICY, 'status': 'not_support', 'flags': [],
                'numeric_checks': [], 'claim_verified': False}
    quotes = '\n'.join(decision.evidence_quotes)
    flags, numeric_checks = [], []
    missing = quantities(claim, claim=True) - quantities(quotes)
    if missing:
        flags.append({'code': 'claim_quantity_not_quoted', 'quantities': [
            {'value': str(value), 'kind': kind} for value, kind in sorted(missing)]})
    parts = re.split(r'\s+and\s+', claim, flags=re.I)
    if len(parts) > 1:
        for part in parts:
            if terms(part) and not terms(part).intersection(terms(quotes)):
                flags.append({'code': 'conjunct_lexical_gap', 'claim_fragment': part})
    requested = {DIRECTION_WORDS[w] for w in re.findall(r'[a-z]+', claim.casefold()) if w in DIRECTION_WORDS}
    matches = [(quote, m) for quote in decision.evidence_quotes for m in BEFORE_AFTER.finditer(quote)]
    qualified = re.search(r'\b(?:not|never|no|none|all|every|each|some|at least|one or more)\b', claim, re.I)
    if len(requested) == 1 and len(parts) == 1 and len(matches) == 1 and not qualified:
        quote, match = matches[0]
        unit_before, unit_after = match['before_unit'].casefold(), match['after_unit'].casefold()
        # This first screen does not infer scope, convert units or combine measurements.
        if not terms(match['metric']).intersection(terms(claim)) or not terms(match['event']).issubset(terms(claim)):
            flags.append({'code': 'numeric_scope_requires_review', 'quote': quote})
        elif unit_before != unit_after:
            flags.append({'code': 'numeric_units_require_review', 'quote': quote})
        else:
            before, after = (Decimal(match[k].replace(',', '')) for k in ('before', 'after'))
            observed = 'increase' if after > before else 'decrease' if after < before else 'unchanged'
            expected = next(iter(requested))
            numeric_checks.append({'before': str(before), 'after': str(after), 'unit': unit_before,
                                   'observed_direction': observed, 'requested_direction': expected, 'quote': quote})
            if observed != expected:
                flags.append({'code': 'numeric_direction_conflict', 'observed_direction': observed,
                              'requested_direction': expected, 'quote': quote})
    return {'policy': POLICY, 'status': 'review_required' if flags else 'screen_clear',
            'flags': flags, 'numeric_checks': numeric_checks, 'claim_verified': False}
