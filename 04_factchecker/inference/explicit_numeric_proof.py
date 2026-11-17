"""Compare measurements with explicit local bindings in the source."""
from fractions import Fraction
import re


_NUMBER = r'(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:/\d+)?'
_COUNT = r'\d{1,3}(?:,\d{3})+|\d+'
_NAME = r"[A-Za-z][\w-]*(?:[ \t]+[\w-]+){0,5}"
_UNIT = r'(?:documents|texts|articles|sentences|examples|records|items|tokens|samples|pairs|utterances|tweets)'
_PREPROCESS = r'(?:preprocessing|processing|filtering|post-processing)'


def _normalized(text):
    return ' '.join(re.findall(r'[a-z0-9]+', text.casefold()))


def _equal_name(left, right):
    return _normalized(left) == _normalized(right)


def _count_unit(left, right):
    a, b = _normalized(left), _normalized(right)
    return a == b or (
        a in {'texts', 'articles'} and b.endswith(' news')
    )


def _count(text):
    return int(text.replace(',', ''))


def _related_windows(selected, segments, context):
    ordered = list(segments)
    for key in selected:
        segment = segments[key]
        adjacent = [key]
        index = ordered.index(key)
        for offset in (-1, 1):
            other = index + offset
            if 0 <= other < len(ordered):
                neighbor = ordered[other]
                first, second = sorted((segment, segments[neighbor]), key=lambda row: row['start'])
                if context[first['end']:second['start']].count('\n') < 2:
                    adjacent.append(neighbor)
        yield key, adjacent


def _named_corpus(claim, segments, windows):
    pattern = rf'(?:The )?(?P<name>{_NAME}) (?:corpus|dataset) (?:contained|contains|had) (?P<n>{_COUNT}) (?P<unit>[a-z]+)\.'
    match = re.fullmatch(pattern, claim, re.I)
    if not match:
        return
    relevant = dict.fromkeys(key for _, adjacent in windows for key in adjacent)
    for key in relevant:
        text = segments[key]['text']
        observation = re.fullmatch(
            rf"""(?:The |One |Another )?(?:other )?(?:corpus|dataset) \((?:named|called)(?: here)? """
            rf"""[\x60'\"“]([^'\"”\x60]+)[\x60'\"”]\) (?:is a set of|contains|contained|consists of) """
            rf"""({_COUNT}) ({_UNIT}|{_NAME} news)\.""", text, re.I,
        )
        if observation and _equal_name(observation[1], match['name']) and _count_unit(match['unit'], observation[3]):
            yield _count(observation[2]) == _count(match['n']), [key], 'named corpus count'


def _preprocessed_documents(claim, segments, windows):
    match = re.fullmatch(
        rf'The (?P<target>{_NAME}) corpus (?:contained|contains|had) (?P<n>{_COUNT}) (?P<unit>{_UNIT}) '
        rf'after (?P<stage>{_PREPROCESS})\.', claim, re.I,
    )
    if not match:
        return
    for key, adjacent in windows:
        measured = re.fullmatch(
            rf'After ({_PREPROCESS}), we (?:got|obtained|retained|had) (?:{_COUNT}) '
            rf'(?:{_NAME} )?{_UNIT} in ({_COUNT}) ({_UNIT})\.',
            segments[key]['text'], re.I,
        )
        if not measured or not _equal_name(match['stage'], measured[1]) or not _count_unit(match['unit'], measured[3]):
            continue
        for antecedent in adjacent:
            text = segments[antecedent]['text']
            processed = re.search(
                rf'\bwe (?:filter|preprocess|process)(?: and [a-z-]+)? (?:the|a) ({_NAME}) corpus\b',
                text, re.I,
            )
            target = match['target'].casefold()
            aligned_alias = target == 'aligned' and processed and processed[1].casefold() in {'line-aligned', 'document-aligned'}
            if (segments[antecedent]['start'] < segments[key]['start'] and processed
                    and (_equal_name(target, processed[1]) or aligned_alias)
                    and len(re.findall(r'\bcorpus\b', text, re.I)) == 1):
                yield _count(measured[2]) == _count(match['n']), [antecedent, key], 'count after preprocessing'


def _paired_counts(claim, segments, windows):
    pattern = rf'After filtering, the (?:collection|dataset|corpus) (?:contained|contains|had) ({_COUNT}) ({_UNIT}) (?:about|for) (.+)\.'
    match = re.fullmatch(pattern, claim, re.I)
    if not match:
        return
    source = (rf'(?:This|The) (?:automatic )?(?:post-processing|filtering) left us with '
              rf'({_COUNT}) ({_UNIT}) for ([^,()]+?) and ({_COUNT}) ({_UNIT}) for '
              r'([a-z ]+?)(?: \(([^()]+)\))?(?: across all events)?\.')
    for key, _ in windows:
        observed = re.fullmatch(source, segments[key]['text'], re.I)
        if not observed:
            continue
        bindings = ((observed[1], observed[2], (observed[3],)),
                    (observed[4], observed[5], (observed[6], observed[7] or '')))
        for n, unit, subjects in bindings:
            if _equal_name(unit, match[2]) and any(_equal_name(subject, match[3]) for subject in subjects):
                yield _count(n) == _count(match[1]), [key], 'count for the named group'


def _sampled_items(claim, segments, windows):
    expected = re.fullmatch(
        rf'The (?P<method>{_NAME}) (?:method|approach) used (?P<count>{_COUNT}) (?P<unit>{_UNIT}) '
        rf'randomly selected from (?:the )?(?P<dataset>{_NAME}) for (?P<purpose>{_NAME})\.', claim, re.I,
    )
    if not expected:
        return
    source = re.compile(
        rf'For (?:the )?(?P<method>{_NAME}) (?:method|approach), we randomly (?:picked|selected|sampled) '
        rf'(?P<count>{_COUNT}) (?P<unit>{_UNIT}) from (?:the )?(?P<dataset>{_NAME}) '
        rf'(?:for (?P<purpose>{_NAME})|as (?P<use>{_NAME}) (?P<use_unit>{_UNIT}))\.', re.I,
    )

    def dataset_name(text):
        # These suffixes name the collection, while its preceding split name
        # distinguishes evaluation data from training or validation data.
        return re.sub(r' (?:data set|dataset)$', ' data', _normalized(text))

    for key, adjacent in windows:
        observed = source.fullmatch(segments[key]['text'])
        if not observed or not _equal_name(expected['unit'], observed['unit']):
            continue
        if observed['use_unit'] and not _equal_name(observed['unit'], observed['use_unit']):
            continue
        if (dataset_name(expected['dataset']) != dataset_name(observed['dataset'])
                or not _equal_name(expected['purpose'], observed['purpose'] or observed['use'])):
            continue

        method, reported = map(_normalized, (expected['method'], observed['method']))
        proof = [key]
        if method != reported:
            if not method.startswith(reported + ' '):
                continue
            aliases = []
            for neighbor in adjacent:
                if segments[neighbor]['start'] >= segments[key]['start']:
                    continue
                names = re.fullmatch(
                    rf'We experiment(?:ed)? with both (?:the )?({_NAME}) and (?:the )?(?:proposed )?'
                    rf'({_NAME}) (?:methods|approaches)\.', segments[neighbor]['text'], re.I,
                )
                if names:
                    matches = [name for name in map(_normalized, names.groups())
                               if name == reported or name.startswith(reported + ' ')]
                    if matches == [method]:
                        aliases.append(neighbor)
            if len(aliases) != 1:
                continue
            proof.insert(0, aliases[0])
        yield _count(observed['count']) == _count(expected['count']), proof, 'random sample count'


def _parallel_coverage(claim, segments, windows):
    expected = re.fullmatch(
        rf'(.+?) covered ({_NUMBER})% of (.+?) in (?:the )?({_NAME}) dataset\.', claim, re.I,
    )
    if not expected:
        return
    pattern = rf'(.+?) cover(?:ed|s)? ({_NUMBER})% and ({_NUMBER})% (?:of )?(.+?) in ({_NAME}) and ({_NAME}), respectively\.'
    for key, _ in windows:
        observed = re.fullmatch(pattern, segments[key]['text'], re.I)
        if not observed or not _equal_name(expected[1], observed[1]) or not _equal_name(expected[3], observed[4]):
            continue
        for name, value in ((observed[5], observed[2]), (observed[6], observed[3])):
            if _equal_name(name, expected[4]):
                yield Fraction(value.replace(',', '')) == Fraction(expected[2].replace(',', '')), [key], 'ordered percentage'


def _training_change(claim, segments, windows):
    match = re.fullmatch(
        rf'With configuration parameters unchanged, training (?:the )?({_NAME}) on ({_NAME}) '
        rf'(lowered|raised|reduced|increased) ({_NAME}) from ({_NUMBER})% to ({_NUMBER})%\.', claim, re.I,
    )
    if not match:
        return
    pattern = (rf'We trained (?:the )?({_NAME}) on ({_NAME})'
               rf'(?: generated using (?:the )?{_NAME})?, and found its ({_NAME}) to (drop|rise) to ({_NUMBER})%'
               rf' \(from ({_NUMBER})%\); all configur(?:ation|ing) parameters were left unchanged\.')
    for key, _ in windows:
        observed = re.fullmatch(pattern, segments[key]['text'], re.I)
        if not observed or not _equal_name(observed[1], match[1]) or not _equal_name(observed[3], match[4]):
            continue
        population = _normalized(observed[2]).replace('logical form candidates', 'candidates')
        if population != _normalized(match[2]):
            continue
        old, new = (Fraction(value.replace(',', '')) for value in (observed[6], observed[5]))
        stated = tuple(Fraction(value.replace(',', '')) for value in (match[5], match[6]))
        observed_direction = observed[4].casefold() == 'drop'
        expected_direction = match[3].casefold() in {'lowered', 'reduced'}
        if old != new and stated[0] != stated[1] and (old > new) == observed_direction and (stated[0] > stated[1]) == expected_direction:
            yield (old, new) == stated, [key], 'before/after measurement with the same configuration'


def _distribution_exponent(claim, segments, windows):
    match = re.fullmatch(
        rf'The standard ({_NAME}) negative-sampling distribution uses a smoothing exponent of ({_NUMBER})\.', claim, re.I,
    )
    if not match:
        return
    pattern = rf'({_NAME}) employs a smoothed unigram distribution with a power rate of ({_NUMBER}) as the noise distribution\.'
    for key, adjacent in windows:
        observed = re.fullmatch(pattern, segments[key]['text'], re.I)
        if not observed or not _equal_name(observed[1], match[1]):
            continue
        for antecedent in adjacent:
            if (segments[antecedent]['start'] < segments[key]['start']
                    and re.search(r'\b(?:is|was) the choice of noise distribution for negative sampling\.$',
                                  segments[antecedent]['text'], re.I)):
                try:
                    same = Fraction(observed[2].replace(',', '')) == Fraction(match[2].replace(',', ''))
                except (ValueError, ZeroDivisionError):
                    continue
                yield same, [antecedent, key], 'negative-sampling exponent'


def compare_explicit(claim, selected, segments, context):
    """Only return a verdict when a supported construction binds unambiguously."""
    windows = tuple(_related_windows(selected, segments, context))
    observations = {}
    for compare in (_named_corpus, _preprocessed_documents, _paired_counts, _sampled_items, _parallel_coverage,
                    _training_change, _distribution_exponent):
        try:
            for agrees, ids, measurement in compare(claim.strip(), segments, windows):
                observations[agrees, tuple(ids), measurement] = None
        except (ValueError, ZeroDivisionError):
            return None
    if len(observations) != 1:
        return None
    agrees, ids, measurement = next(iter(observations))
    label = 'support' if agrees else 'contradict'
    explanation = f'The source {measurement} ' + ('matches the claim.' if agrees else 'differs from the claim.')
    return label, ids, explanation
