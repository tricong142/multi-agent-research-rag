"""Source offsets for measurements; identifiers are not executable quantities."""
import re
from decimal import Decimal

from .evidence_screen import DIGITS, WORDS, quantities

_STOP = set('and or but of for with from to in on at by than as after before during '
            'is are was were be been being has have had do does did '
            'achieved achieves used uses contains contained consisted consisting '
            'reported measured obtained reached scored lasts lasted trained '
            'visible each all every only not less more per '
            'afterward afterwards previously subsequently then under '
            'improved improves increased increases decreased decreases reduced reduces '
            'retained retains maintained maintains remained remains rose fell gained gains '
            'recorded reported achieved reached scored evaluated paired include includes including'.split())
_DURATION = re.compile(r'\b(half|quarter|one|two|three|four|five|six|seven|eight|nine|ten|\d+(?:\.\d+)?)-(hour|minute|second)s?\b', re.I)


def numeric_requirements(text):
    excluded = [m.span() for m in re.finditer(r'\b(?:at least one|one or more)\b', text, re.I)]
    # Section/figure IDs are references, even though they contain decimal digits.
    excluded += [m.span() for m in re.finditer(
        r'\b(?:sections?|figures?|tables?|rows?|models?)\s+(?:[A-Za-z][\w-]*\d[\w-]*|'
        r'\d+(?:\s*[-–]\s*\d+)?(?:\s*[,/]\s*\d+)*)', text, re.I)]
    excluded += [m.span() for m in re.finditer(r'\b[A-Za-z][\w-]*-\d[\w-]*\b', text)]
    durations = list(_DURATION.finditer(text))
    matches = list(DIGITS.finditer(text)) + list(re.finditer(r'\b(?:'+'|'.join(WORDS)+r')\b', text, re.I))
    result = []
    for m in sorted(matches, key=lambda v: v.start()):
        if any(a <= m.start() < b for a,b in excluded) or any(d.start() <= m.start() < d.end() for d in durations):
            continue
        value, kind = next(iter(quantities(m[0])))
        end, unit = m.end(), '%' if '%' in m[0] else 'percent' if kind=='percent' else ''
        if kind != 'percent':
            tail = text[end:]
            duration = re.match(r'\s+(?:half|quarter|one|two|three|\d+)-(?:hour|minute|second)s?\s+',tail,re.I)
            offset = duration.end() if duration else 0
            words = []
            for word in re.finditer(r'[A-Za-z]+(?:-[A-Za-z]+)*', tail[offset:]):
                gap = tail[offset:][0 if not words else words[-1].end():word.start()]
                if gap.strip() or word[0].casefold() in _STOP or word[0].casefold() in WORDS:
                    break
                words.append(word)
                if len(words)==4: break
            if words:
                unit = tail[offset+words[0].start():offset+words[-1].end()]
                end += offset+words[-1].end()
            if not unit and result:
                previous=result[-1]
                gap=text[previous['end']:m.start()]
                after=text[m.end():]
                before_ref=re.fullmatch(r'\s*,\s*of\s+(?:which|these|those)\s*',gap,re.I)
                after_ref=re.fullmatch(r'\s*,\s*',gap) and re.match(r'\s+of\s+(?:which|these|those)\b',after,re.I)
                if previous['unit'] and (before_ref or after_ref):
                    unit=previous['unit']
        result.append(dict(start=m.start(),end=end,quote=text[m.start():end],value=str(value),unit=unit,kind=kind))
    for m in durations:
        if any(a <= m.start() < b for a,b in excluded): continue
        value = {'half':Decimal('.5'),'quarter':Decimal('.25')}.get(m[1].casefold())
        if value is None: value=Decimal(WORDS[m[1].casefold()] if m[1].casefold() in WORDS else m[1])
        result.append(dict(start=m.start(),end=m.end(),quote=m[0],value=str(value),unit=m[2],kind='number'))
    return sorted(result,key=lambda v:v['start'])


def compatible_count_units(claimed,observed):
    """Extra source modifiers may narrow a count object; missing/different modifiers cannot."""
    left=claimed.casefold().split();right=observed.casefold().split()
    if not left or not right or left[-1]!=right[-1] or not left[-1].endswith('s'):
        return False
    physical={'ms','s','seconds','minutes','hours','days','weeks','months','years','liters','meters','grams','watts'}
    if left[-1] in physical:return claimed.casefold()==observed.casefold()
    sequence=iter(right)
    return all(any(word==candidate for candidate in sequence) for word in left)


def grounded_operand(raw, source, previous):
    """Accept a compound measurement only when the shared extractor reconstructs it."""
    if isinstance(raw,dict) and set(raw)=={'value','unit','quote'}:
        quote=raw['quote']
        if isinstance(quote,str) and quote in source and any(
            {k:r[k] for k in ('value','unit','quote')}==raw for r in numeric_requirements(source)):
            if len(quote)<=2000 and len(raw['unit'])<=40:
                unit=raw['unit'].casefold()
                return Decimal(raw['value']),'%' if unit=='percent' else unit,quote
    return previous(raw,source)
