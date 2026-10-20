"""Finite source-grounded assessment constraints, shared by validator and decoder."""
import re
from .assessment_rules import clauses, contains, scope_conflict, _MISSING
from .numeric_verifier import numeric_requirements, check_numeric, measurement_scope, _NUMERIC_MODAL

_UNCERTAIN = re.compile(r'\b(?:false|incorrect|denied|disputed|retracted|planned|intended|wanted|aimed|hoped|attempted|proposed|alleged|claimed|that)\b',re.I)


def numeric_records(value, requirements):
    if isinstance(value, dict) and 'kind' not in value:
        keys = ['q'+str(i) for i in range(len(requirements))]
        if len(keys) < 2 or set(value) != set(keys):
            raise ValueError('numeric_requirement_ledger_schema')
        records = []
        for key, requirement in zip(keys, requirements):
            record = value[key]
            if record is None:
                continue
            if (not isinstance(record, dict) or record.get('kind') != 'value'
                    or record.get('left') != {k:requirement[k] for k in ('value','unit','quote')}):
                raise ValueError('numeric_requirement_slot_binding')
            records.append(record)
        return records
    return value if isinstance(value, list) else [value] if value is not None else []


def scope_supported(part, text):
    from .atomic_verifier import target_members, other_named_target
    if other_named_target(part,text) or scope_conflict(part,text):
        return False
    words=part['scope']['entity'].split()
    if len(words)>1:
        head,name=' '.join(words[:-1]),words[-1].casefold()
        siblings=re.findall(r'(?<!\w)'+re.escape(head)+r'\s+([\w-]+)',text,re.I)
        if any(s.casefold()!=name for s in siblings):
            return False
    if part['quantifier']=='atomic' and not target_members(part,text):
        return False
    for value in (part['scope']['time'],part['scope']['condition']):
        # A numeric argument is checked in the quantity ledger, not identity.
        if value and not numeric_requirements(value):
            clean = re.sub(r'^(?:on|in|during|under)\s+', '', value, flags=re.I)
            if not contains(clean,text):
                return False
    return True


def numeric_choices(part, context):
    from .atomic_decoding import evidence_passages
    from .atomic_verifier import numeric_metric_matches
    requirements = numeric_requirements(part['quote'])
    groups = [[] for _ in requirements]
    for passage in evidence_passages(context):
        if _UNCERTAIN.search(passage):
            continue
        if not scope_supported(part,passage):
            # shortcut: an immediately described evaluation's second sentence
            # may use its event noun; no aliases or unrelated events are joined.
            if not (part['quantifier']=='atomic' and scope_supported(part,context)
                    and re.match(r'^(?:The )?(?:Evaluation|Assessment) (?:used|included)\b',passage,re.I)
                    and not re.search(r'\b(?:another|other|different)\b',context,re.I)):
                continue
        for index, left in enumerate(requirements):
            for right in numeric_requirements(passage):
                record = {'kind':'value','source_quote':passage,
                          'left':{k:left[k] for k in ('value','unit','quote')},
                          'right':{k:right[k] for k in ('value','unit','quote')}}
                try:
                    checked = check_numeric(record,part['quote'],context,metric=part['scope']['metric'])
                except ValueError:
                    continue
                measurement,_ = measurement_scope(record,part['quote'],part['scope']['metric'])
                local=True
                for restriction in (part['scope']['time'],part['scope']['condition']):
                    if restriction and not numeric_requirements(restriction):
                        clean=re.sub(r'^(?:on|in|during|under)\s+','',restriction,flags=re.I)
                        local=local and contains(clean,measurement)
                if not local:
                    continue
                if (numeric_metric_matches(part,record,requirements)
                        and checked['truth'] != 'unknown'):
                    item = (record,checked['truth'])
                    if item not in groups[index]:
                        groups[index].append(item)
    return groups


def direct_truth(part, text, member):
    """Only explicit verb/object or simple quality predicates; never causal inference."""
    if _MISSING.search(text) or _UNCERTAIN.search(text) or re.search(_NUMERIC_MODAL,text,re.I):
        return None
    subject=r'^(?:The |the |A |a |An |an )?'+re.escape(member)+r'\s+'
    metric = part['scope']['metric'].strip()
    families = {'used':r'use[sd]?', 'uses':r'use[sd]?', 'use':r'use[sd]?',
                'retained':r'retain(?:s|ed)?', 'retains':r'retain(?:s|ed)?',
                'remained':r'remain(?:s|ed)?', 'recorded':r'record(?:s|ed)?'}
    words = metric.split(maxsplit=1)
    if len(words)==2 and words[0].casefold() in families:
        verb, obj = families[words[0].casefold()], re.escape(words[1])
        stem = {'used':'use','uses':'use','use':'use','retained':'retain','retains':'retain',
                'remained':'remain','recorded':'record'}[words[0].casefold()]
        negative = r'\b(?:did|does|do)\s+not\s+'+stem+r'\s+(?:any\s+)?'+obj+r'(?!\w)'
        positive = r'\b'+verb+r'\s+'+obj+r'(?!\w)'
        if re.search(subject+negative,text,re.I):
            return 'false'
        if re.search(subject+positive,text,re.I) and not re.search(r'\b(?:not|never|without|no)\b',text,re.I):
            return 'true'
    if metric.casefold()=='improved':
        if re.search(subject+r'(?:did not improve|failed to improve|worsened|degraded|became less accurate|got worse)\b',text,re.I):
            return 'false'
        if re.search(subject+r'improved\b',text,re.I) and not re.search(r'\b(?:not|never|without|no)\b',text,re.I):
            return 'true'
    return None


def decision_evidence(part, context):
    """Return a finite decidable witness set or None; do not interpret free explanations."""
    from .atomic_verifier import target_members, ASSESSMENT_LIMITS
    words=part['scope']['entity'].split()
    # shortcut: qualified populations need semantic membership review; do not
    # force certainty from a substring such as certified inside non-certified.
    if len(words)>1 and not all(w[:1].isupper() for w in words):
        return None
    if not scope_supported(part,context):
        return None
    requirements = numeric_requirements(part['quote'])
    if requirements and part['quantifier']=='atomic':
        groups = numeric_choices(part,context)
        states = [{truth for _,truth in group} for group in groups]
        # Multiple candidate values or missing operands retain model uncertainty.
        if states and all(len(s)==1 for s in states):
            truth = 'false' if any(s=={'false'} for s in states) else 'true'
            return {'truth':truth,'members':target_members(part,context),'numeric':True,
                    'quotes':sorted({r['source_quote'] for group in groups for r,_ in group})}
        return None
    facts = []
    for clause in clauses(context):
        if len(clause)>ASSESSMENT_LIMITS['quote_chars']:
            continue
        if scope_conflict(part,clause):
            continue
        if part['quantifier']=='atomic':
            members = target_members(part,clause)
        else:
            noun = part['scope']['entity'].strip()
            singular = noun[:-1] if noun.endswith('s') else noun
            members = [m[0] for m in re.finditer(r'(?<!\w)(?:a |an |the )?(?:(?:first|second|third|fourth|fifth|last) )?'
                +re.escape(singular)+r'(?:\s+[A-Z0-9][\w-]*)?(?!\w)',clause)] if singular else []
        for member in members:
            truth = direct_truth(part,clause,member)
            if truth:
                facts.append((truth,[member],clause))
    if not facts:
        return None
    if part['quantifier']!='atomic':
        reports = {}
        for truth,members,_ in facts:
            for member in members:
                reports.setdefault(member.casefold(),set()).add(truth)
        facts = [f for f in facts if all(len(reports[m.casefold()])==1 for m in f[1])]
        if not facts:
            return None
    if part['quantifier']=='atomic':
        states = {truth for truth,_,_ in facts}
        if len(states)!=1:
            return None
        chosen = facts
    elif part['quantifier']=='all':
        chosen = [f for f in facts if f[0]=='false']
    elif part['quantifier'] in ('some','none'):
        chosen = [f for f in facts if f[0]=='true']
    else:
        return None
    if not chosen:
        return None
    return {'truth':chosen[0][0],'members':sorted({m for _,members,_ in chosen for m in members}),
            'numeric':False,'quotes':sorted({clause for _,_,clause in chosen})}


def assessment_issue(raw, part, context):
    evidence = decision_evidence(part,context)
    if evidence is None:
        return None
    if raw['scope_match']!='matched':
        return 'scope_is_not_agreement'
    observations = raw['observations']
    if any(o.get('model_truth')=='unknown' and o.get('numeric') is not None for o in observations):
        return None  # Preserve an explicitly unresolved legacy numeric association.
    if not any(o['truth']==evidence['truth'] and any(contains(m,o['member']) or contains(o['member'],m)
        for m in evidence['members']) for o in observations):
        return 'decisive_witness_missing_or_unknown'
    return None
