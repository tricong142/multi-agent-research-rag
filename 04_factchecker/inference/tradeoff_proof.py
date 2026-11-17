"""Recognize an explicit denial of an asserted adverse effect for the same event."""

from .decoder_parser import _NEGATION, _TRADEOFF, number, tokens


_REDUCTION = {'cut', 'reduce', 'reduced', 'decrease', 'decreased', 'lower', 'lowered'}
_ADVERSE = {'worse', 'worsened', 'worsening', 'harm', 'harming', 'degraded', 'degrading'}
_SCOPE = {'in', 'on', 'under', 'during', 'for', 'with'}
_DISCOURSE = {'moreover', 'furthermore', 'however', 'additionally'}
_AUXILIARIES = {('can', 'be'), ('was',), ('were',), ('is',), ('are',)}
_ARTICLES = {'a', 'an', 'the'}
_UNBOUND = _NEGATION | {'and', 'or', 'if', 'only', 'except', 'unless'}
_FACTOR_PREFIX = ('by', 'a', 'factor', 'of')


def _split_once(words, cue):
    positions = [i for i in range(len(words)) if words[i:i + len(cue)] == cue]
    if len(positions) == 1:
        index = positions[0]
        return words[:index], words[index + len(cue):]
    return None


def _nominal(words):
    if words and words[0] in _ARTICLES:
        words = words[1:]
    if words and all(word[0].isalpha() and word not in _UNBOUND for word in words):
        return words
    return ()


def _same_metric(left, right):
    if not left or not right:
        return False
    if left == right:
        return True
    short, long = sorted((left, right), key=len)
    initials = ''.join(piece[0] for word in long for piece in word.split('-') if piece)
    return len(short) == 1 and len(initials) >= 2 and short[0] == initials


def _factor(words):
    if len(words) > 4 and words[-5:-1] == _FACTOR_PREFIX:
        metric, amount = words[:-5], words[-1]
    elif len(words) >= 4 and words[-2:] == ('-', 'fold'):
        metric, amount = words[:-3], words[-3]
    elif len(words) >= 2 and words[-1].endswith('fold'):
        metric, amount = words[:-1], words[-1]
    else:
        return (), None
    try:
        return _nominal(metric), number(amount)
    except ValueError:
        return (), None


def _event(words):
    if len(words) > 2 and words[0] in _DISCOURSE and words[1] == ',':
        words = words[2:]
    scope = ()
    if words and words[0] in _SCOPE:
        parts = _split_once(words, (',',))
        if parts is None:
            return None
        scope, words = parts
        if not _nominal(scope):
            return None
    verbs = [index for index, word in enumerate(words) if word in _REDUCTION]
    if len(verbs) != 1:
        return None
    index = verbs[0]
    before, after = words[:index], words[index + 1:]
    passive = _split_once(after, ('using',))
    if passive is None:
        method = _nominal(before)
        metric, factor = _factor(after)
    else:
        factor_words, method_words = passive
        auxiliary = next((aux for aux in _AUXILIARIES if before[-len(aux):] == aux), ())
        if not auxiliary:
            return None
        method = _nominal(method_words)
        metric = _nominal(before[:-len(auxiliary)])
        measured, factor = _factor(metric + factor_words)
        if measured != metric:
            return None
    if method and metric and factor is not None and factor > 1:
        return scope, method, metric, factor
    return None


def refutes_tradeoff(claim, source):
    """Return a refutation only when the event and explicitly denied side effect bind."""
    requested = _split_once(tokens(claim.strip().removesuffix('.')), _TRADEOFF)
    observed = _split_once(tokens(source.strip().removesuffix('.')), ('without',))
    if requested is None or observed is None:
        return False
    main, cost = requested
    report, denied = observed
    if not cost or not denied or cost[0] not in _ADVERSE or denied[0] not in _ADVERSE:
        return False
    if not _same_metric(_nominal(cost[1:]), _nominal(denied[1:])):
        return False
    expected, actual = _event(main), _event(report)
    return bool(expected and actual and expected[:2] == actual[:2] and expected[3] == actual[3]
                and _same_metric(expected[2], actual[2]))
