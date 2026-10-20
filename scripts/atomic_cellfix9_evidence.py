"""Finite clause ownership and closed-population witnesses; no general entailment."""
import re

from .assessment_rules import clauses, contains, scope_conflict, _MISSING
from .numeric_verifier import direction, numeric_requirements, _NUMERIC_MODAL
from .evidence_screen import WORDS

_MODAL = re.compile(_NUMERIC_MODAL + r'|\b(?:planned|proposed|alleged|claimed|disputed|false|incorrect|denied|retracted|not true|which|who)\b', re.I)
_UP = r'improv(?:ed|es?)|increas(?:ed|es?)|rose|raised|gained|higher|better'
_DOWN = r'decreas(?:ed|es?)|reduc(?:ed|es?)|fell|lowered|lost|worsened|worse|slower|less accurate'
_COUNT = r'(?:\d+|' + '|'.join(WORDS) + r')'


def _modal(text):
    # May inside an explicit month phrase is not the modal verb "may".
    return _MODAL.search(re.sub(r'\b(?:in|during)\s+May\b', '', text, flags=re.I))


def local_clauses(text):
    # Split coordinated results, not lists of names or a verb's object.
    return [v.strip(' ,') for c in clauses(text) for v in re.split(
        r'\band\s+(?=(?:one|two|three|four|five|each|every|all|the third)\b[^.;]*\b(?:improved|reduced|gained|lost|increased|decreased)\b)', c, flags=re.I)]


def metric_present(part, text):
    metric = part['scope']['metric']
    if contains(metric, text):
        return True
    # shortcut: recall/recalling and leak/leaked/leaks are the only inflections
    # beyond exact metrics here; unsupported paraphrases remain model judgments.
    if metric.casefold() == 'recall' and re.search(r'\brecalling\b', text, re.I):
        return True
    if metric.casefold() in ('leaked', 'leak', 'leaks') and re.search(r'\bleak(?:ed|s)?\b', text, re.I):
        return True
    return False


def predicate_truth(part, text):
    """Truth of the positive predicate, independent of ALL/SOME/NONE."""
    if _MISSING.search(text) or _modal(text) or scope_conflict(part, text):
        return None
    metric = part['scope']['metric'].casefold()
    if metric in ('leak', 'leaked', 'leaks'):
        if re.search(r'\b(?:no leaks?|did not leak|never leaked|had no leaks?)\b', text, re.I):
            return 'false'
        if re.search(r'\bleaked\b', text, re.I):
            return 'true'
        return None
    requested = direction(part['quote'])
    if requested is None and re.search(r'\b(?:improv\w*|gain\w*)\b', part['quote'], re.I):
        requested = 'increase'
    if metric == 'improved':
        has_metric = True
    else:
        has_metric = metric_present(part, text)
    if not has_metric or not requested:
        return None
    up = bool(re.search(r'\b(?:' + _UP + r')\b', text, re.I))
    down = bool(re.search(r'\b(?:' + _DOWN + r')\b', text, re.I))
    unchanged = bool(re.search(r'\b(?:unchanged|stayed the same|did not improve)\b', text, re.I))
    if re.search(r'\bdid not improve\b', text, re.I):
        up = False
    if re.search(r'\b(?:not|never|no)\b', text, re.I) and not unchanged:
        return None
    states = (['increase'] if up else []) + (['decrease'] if down else []) + (['unchanged'] if unchanged else [])
    return ('true' if states[0] == requested else 'false') if len(states) == 1 else None


def owned_clauses(member, quotes):
    return [c for q in quotes for c in local_clauses(q) if contains(member, c)]


def citation_issue(part, member, quotes, truth):
    if truth == 'unknown':
        return None
    own = owned_clauses(member, quotes)
    if part['quantifier']!='atomic' and re.search(r'\b'+_noun(_head(part))+r'\b',member,re.I):
        pieces = [c for q in quotes for c in local_clauses(q)]
        if any(scope_conflict(part,c) for c in pieces) and any(not scope_conflict(part,c) for c in pieces):
            return 'observation_scope_binding_unresolved'
    if not own:
        return 'observation_evidence_unbound'
    if all(scope_conflict(part, c) for c in own):
        return 'observation_scope_mismatch'
    values = {v for c in own if (v := predicate_truth(part, c)) is not None}
    if len(values) == 1 and truth not in values:
        return 'observation_polarity_mismatch'
    # Exact member presence in a roster is not a predicate witness. Apply this
    # only to known property/verb heads; arbitrary semantic relations stay open.
    from .atomic_verifier import _PROPERTY_HEADS
    known = (contains(part['scope']['metric'],part['quote'])
             and part['scope']['metric'].split()[-1].casefold() in _PROPERTY_HEADS | {'improved', 'leaked'})
    numeric_head = part['scope']['metric'].split()[-1]
    numeric_bound = any(numeric_requirements(c) and contains(numeric_head,c) for c in own)
    if known and not numeric_bound and not any(metric_present(part, c) or part['scope']['metric']=='improved' and predicate_truth(part, c) for c in own):
        return 'observation_predicate_not_grounded'
    return None


def _head(part):
    word = part['scope']['entity'].split()[-1].casefold()
    if word.endswith(('ches','shes','xes','zes','sses')):
        return word[:-2]
    if word.endswith('ies'):
        return word[:-3]+'y'
    return word[:-1] if word.endswith('s') else word


def _noun(head):
    plural = head[:-1]+'ies' if head.endswith('y') else head+'es' if head.endswith(('ch','sh','x','z','s')) else head+'s'
    return '(?:'+re.escape(head)+'|'+re.escape(plural)+')'


def _restricted(part, text):
    if scope_conflict(part, text):
        return False
    for value in (part['scope']['time'], part['scope']['condition']):
        if value and not numeric_requirements(value):
            key = re.sub(r'^(?:on|in|during|under)\s+', '', value, flags=re.I)
            if not contains(key, text):
                return False
    return True


def _population(part, context):
    """One explicit population only; never join different source populations."""
    head = _head(part)
    if not re.fullmatch('[a-z-]+', head):
        return None
    sentences = [m[0].strip() for m in re.finditer(r'[^.!?]+(?:[.!?](?=\s|$)|$)', context) if m[0].strip()]
    populations = []
    for i, sentence in enumerate(sentences):
        if scope_conflict(part, sentence):
            continue
        count = re.search(r'\bexactly\s+(' + _COUNT + r')\s+(?:[a-z-]+\s+){0,3}' + _noun(head) + r'\b', sentence, re.I)
        roster = re.search(r'(?:\b(?:were|was)\s+|:\s*)([A-Z][\w-]*(?:,\s*[A-Z][\w-]*)*(?:,?\s+and\s+[A-Z][\w-]*))\s*[.!]?$', sentence)
        declared = bool(re.search(r'\b'+_noun(head)+r'\b',sentence,re.I))
        # A previously named audited set is explicit, but unrelated generic
        # "set" sentences are never assigned to a qualified population.
        named_set = re.search(r'\bcomplete\s+([a-z-]+)\s+set\b', sentence, re.I)
        declared = declared or bool(named_set and contains(named_set[1], part['scope']['entity']))
        if any(not contains(w,sentence) for w in part['scope']['entity'].split()[:-1]):
            continue
        if not declared or not (count or roster):
            continue
        names = re.split(r',\s*|\s+and\s+', roster[1]) if roster else []
        names = [n.strip() for n in names if n.strip()]
        n = int(count[1]) if count and count[1].isdigit() else WORDS.get(count[1].lower()) if count else len(names)
        if not n or n > 16 or names and len(names) != n:
            continue
        # Restrict to this declaration and its immediately following sentences;
        # a different explicit scope terminates the inheritance window.
        local = [sentence]
        for next_sentence in sentences[i+1:i+3]:
            if scope_conflict(part, next_sentence):
                break
            time = part['scope']['time']
            if time and re.match(r'^(?:after|before)\b',time,re.I) and re.search(r'\b(?:after|before)\b',next_sentence,re.I) and not contains(time,next_sentence):
                break
            local.append(next_sentence)
        text = ' '.join(local)
        if not _restricted(part, text):
            continue
        anchor = re.sub(r'^exactly\s+', '', count[0], flags=re.I) if count else roster[1]
        if len(anchor) > 160 or len(text) > 384 or text not in context:
            continue
        populations.append({'anchor': anchor, 'names': names, 'count': n, 'text': text})
    return populations[0] if len(populations) == 1 else None


def population_witness(part, context):
    if part['quantifier'] == 'atomic' or re.search(r'\b(?:not|never|without)\b', part['quote'], re.I):
        return None
    for modifier in part['scope']['entity'].split()[:-1]:
        if re.search(r'\b(?:non-|un)'+re.escape(modifier)+r'\b',context,re.I):
            return None
    pop = _population(part, context)
    if not pop:
        return None
    text, names = pop['text'], pop['names']
    if _MISSING.search(text) or _modal(text):
        return None
    if re.search(r'\b(?:some|several|most|few|subset|selected|remaining|except|only)\b',text,re.I):
        return None
    from .atomic_verifier import numeric_proof_required
    if numeric_proof_required(part,[text]):
        return None  # Do not force numeric=null where a measurement ledger is required.
    values = []
    # Explicit collective result must refer to this entire declared population.
    collective = []
    for clause in local_clauses(text):
        if re.search(r'\b(?:each|all|every|any of these)\b', clause, re.I):
            if re.search(r'\b(?:these|those|each of|and each)\b|^each\b', clause, re.I) or contains(_head(part), clause) or contains(_head(part)+'s', clause):
                counts = [q for q in numeric_requirements(clause)
                          if re.fullmatch(_noun(_head(part)),q['unit'],re.I)]
                if any(q['value']!=str(pop['count']) for q in counts):
                    continue
                value = predicate_truth(part, clause)
                if value:
                    collective.append(value)
    if collective and len(set(collective)) == 1:
        # A second opposed outcome inside this same population invalidates a
        # collective shortcut. Out-of-scope sentences were removed above.
        opposed = [predicate_truth(part, c) for c in local_clauses(text)]
        if any(v is not None and v != collective[0] for v in opposed):
            return None
        return {'truth': collective[0], 'members': [pop['anchor']], 'quotes': [text],
                'complete': True, 'numeric': False, 'population': True}
    if names:
        for name in names:
            states = set()
            for clause in owned_clauses(name, [text]):
                pieces = re.split(r'\band\s+(?=(?:stayed|remained|became)\s+(?:unchanged|slower|faster)|(?:increased|decreased|reduced)\s+on\b)', clause, flags=re.I)
                for piece in pieces:
                    if not contains(name, piece):
                        continue
                    if len(pieces)>1 and metric_present(part, clause) and not metric_present(part, piece):
                        piece = part['scope']['metric'] + ' ' + piece
                    value = predicate_truth(part, piece)
                    if value:
                        states.add(value)
            values.append(next(iter(states)) if len(states)==1 else None)
        decisive = 'false' if part['quantifier']=='all' else 'true'
        if decisive in values:
            return {'truth': decisive, 'members': [names[values.index(decisive)]], 'quotes': [text],
                    'complete': False, 'numeric': False, 'population': True}
        if None not in values and len(set(values)) == 1:
            return {'truth': values[0], 'members': [pop['anchor']], 'quotes': [text],
                    'complete': True, 'numeric': False, 'population': True}
    else:
        decisive = 'false' if part['quantifier']=='all' else 'true'
        found = []
        for clause in local_clauses(text):
            if predicate_truth(part, clause) != decisive:
                continue
            member = re.search(r'\b(?:(?:a|the)\s+)?(?:first|second|third|fourth|fifth|one)(?:\s+'+re.escape(_head(part))+r')?\b', clause, re.I)
            if member:
                found.append(member[0])
        if found:
            return {'truth': decisive, 'members': [found[0]], 'quotes': [text],
                    'complete': False, 'numeric': False, 'population': True}
    return None


def change_witness(part, context):
    if (part['quantifier']!='atomic' or numeric_requirements(part['quote']) or not direction(part['quote'])
            or re.search(r'\b(?:not|never|without)\b',part['quote'],re.I)):
        return None
    from .assessment_decisions import scope_supported
    from .atomic_decoding import evidence_passages
    from .atomic_verifier import numeric_metric_matches, target_members
    from .numeric_verifier import check_numeric
    results = []
    for passage in evidence_passages(context):
        if not scope_supported(part, passage) or _modal(passage):
            continue
        operands = numeric_requirements(passage)
        if len(operands)>16:
            continue
        for left in operands:
            for right in operands:
                record = {'kind':'change','source_quote':passage,
                          'left':{k:left[k] for k in ('value','unit','quote')},
                          'right':{k:right[k] for k in ('value','unit','quote')}}
                try:
                    checked = check_numeric(record,part['quote'],context,metric=part['scope']['metric'])
                except ValueError:
                    continue
                if checked['truth']!='unknown' and numeric_metric_matches(part,record,[]):
                    results.append((checked['truth'], passage))
    if results and len({truth for truth,_ in results})==1:
        return {'truth':results[0][0], 'members':target_members(part,context),
                'quotes':sorted({text for _,text in results}), 'numeric':True}
    return None


def population_issue(raw, part, context):
    witness = population_witness(part, context)
    if witness:
        expected = witness['truth']
        q = part['quantifier']
        closure_needed = q == 'all' and expected == 'true' or q in ('some','none') and expected == 'false'
        if raw['scope_match'] != 'matched':
            return 'scope_is_not_agreement'
        supported = any(o['truth'] == expected and o['member'] in witness['members']
                        and (not closure_needed or all(any(q in cited for cited in o['quotes']) for q in witness['quotes']))
                        for o in raw['observations'])
        # Complete individual ledgers remain replayable; the decoder's single
        # collective witness is a compact serialization, not a new truth rule.
        pop = _population(part, context)
        individuals = bool(pop and pop['names'] and raw['coverage']['complete']
            and set(raw['coverage']['members']) == set(pop['names'])
            and {o['member'] for o in raw['observations']} == set(pop['names'])
            and all(o['truth']==expected and citation_issue(part,o['member'],o['quotes'],expected) is None
                    for o in raw['observations']))
        if not supported and not individuals:
            return 'population_witness_missing'
        if closure_needed and not individuals and (not raw['coverage']['complete'] or set(raw['coverage']['members']) != set(witness['members'])):
            return 'population_closure_required'
        if raw['missing_information']:
            return 'irrelevant_missing_information'
    return None


def missing_issue(raw, part, context):
    text = ' '.join(raw['missing_information'] + [raw['explanation']] + [o['explanation'] for o in raw['observations']])
    # Reject invented author/year citations rather than treating free text as
    # source evidence. Other prose semantics still require independent review.
    for match in re.finditer(r'\b[A-Z][a-z]+(?:\s+et al\.)?\s*\(\d{4}\)', text):
        if match[0] not in context and match[0] not in part['quote']:
            return 'unattributed_prose_citation'
    from .atomic_verifier import _PROPERTY_HEADS
    wanted = set(re.findall(r'[a-z]+', part['scope']['metric'].lower())) & _PROPERTY_HEADS
    for missing in raw['missing_information']:
        mentioned = set(re.findall(r'[a-z]+', missing.lower())) & _PROPERTY_HEADS
        if wanted and mentioned and not wanted & mentioned:
            return 'missing_information_wrong_metric'
    return None
