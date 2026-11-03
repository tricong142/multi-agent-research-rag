"""Finite source-backed member references; uncertainty never invents an entity."""
import re

from .assessment_rules import clauses, contains, scope_conflict
from .assessment_evidence import _head, _noun, _population, metric_present, predicate_truth
from .evidence_screen import WORDS

_DETERMINERS = {'the','a','an','all','every','each','some','other','others','remaining',
    'first','second','third','fourth','fifth','sixth','last','two','three','these','those'}
_CLAUSAL = re.compile(r'\b(?:is|are|was|were|has|have|had|be|been|do|does|did|not|no|never|and|or|from|to|which|that)\b',re.I)


def target_absent(part, context):
    from .atomic_verifier import target_entity, target_members
    return bool(part['quantifier']=='atomic' and target_entity(part) and not target_members(part,context))


def _nominal_member(part, member):
    text=member.strip()
    # Scope stays in its own fields; a matching participial noun modifier is legal.
    for restriction in (part['scope']['time'],part['scope']['condition']):
        if restriction:
            text=re.sub(r'\s+(?:(?:conducted|tested|evaluated|monitored|audited)\s+)?'+re.escape(restriction)+r'$', '',text,flags=re.I)
    if _CLAUSAL.search(text) or not re.fullmatch(r'[\w-]+(?:\s+[\w-]+){0,7}',text):
        return False
    key=re.sub(r'^(?:in|on|under|for)\s+','',part['scope']['condition'],flags=re.I)
    if (key and re.search(r'\b(?:group|cohort|population|set)\s*$',key,re.I)
            and re.sub(r'^the\s+','',text,flags=re.I).casefold()==re.sub(r'^the\s+','',key,flags=re.I).casefold()):
        return True
    text=re.sub(r'^(?:the\s+)?(?:(?:complete|entire|full|remaining)\s+)?(?:set|population|group)\s+of\s+','',text,flags=re.I)
    words=text.split()
    if not words or not re.fullmatch(_noun(_head(part)),words[-1],re.I):
        return False
    modifiers={v.casefold() for v in part['scope']['entity'].split()[:-1]}
    permitted=modifiers | _DETERMINERS | set(WORDS)
    return all(v.casefold() in permitted or v.isdigit() for v in words[:-1])


def member_identity_issue(part, member, truth, context):
    """Known outcomes retain their existing predicate/quantity/coverage guards."""
    if target_absent(part,context):
        return 'unresolved_target_requires_empty_ledger'
    if part['quantifier']=='atomic' or truth!='unknown':
        return None
    for modifier in part['scope']['entity'].split()[:-1]:
        if re.search(r'\b(?:non-|un)'+re.escape(modifier)+r'\b',member,re.I):
            return 'observation_scope_mismatch'
    if _nominal_member(part,member):
        return None
    population=_population(part,context)
    if population and member in population['names']+[population['anchor']]:
        return None
    # shortcut: proper names need a local possessive metric anchor; no general NER.
    if (not _CLAUSAL.search(member)
            and re.fullmatch(r'[A-Z][\w-]*(?:\s+[A-Z][\w-]*){0,2}',member)
            and member.casefold() not in {v.casefold() for v in part['scope']['metric'].split()}):
        for clause in clauses(context):
            possessive=bool(re.search(r'(?<!\w)'+re.escape(member)+r"['’]s\b",clause) and metric_present(part,clause))
            status=bool(re.search(r'(?<!\w)'+re.escape(member)+r'\s+status\s+(?:(?:was|is|has been)\s+)?(?:unreported|unknown|not reported)\b',clause,re.I))
            if (possessive or status) and not scope_conflict(part,clause):
                return None
    return 'observation_member_is_not_entity'


def empty_identity_required(part, context):
    return target_absent(part,context)


def empty_ledger_issue(result):
    if (result['observations'] or result['coverage']['complete'] or result['coverage']['members']
            or result['coverage']['quotes']):
        return 'unresolved_target_requires_empty_ledger'
    if result['scope_match']!='unknown':
        return 'unresolved_target_scope_unknown'
    if not result.get('model_missing_information',result['missing_information']):
        return 'unresolved_target_missing_information'
    return None


def constrain_empty_ledger(schema):
    from .atomic_decoding import obj,array
    props=schema['properties']
    props['scope_match']={'type':'string','enum':['unknown']}
    props['observations']['minItems']=props['observations']['maxItems']=0
    props['coverage']=obj({'complete':{'const':False},
        'members':array({'type':'string'},maximum=0),'quotes':array({'type':'string'},maximum=0)})
    props['missing_information']['minItems']=props['missing_information']['maxItems']=1
    return schema


def member_absence_quotes(part, member, context):
    from .assessment_focus import _direct_absence
    from .atomic_decoding import evidence_passages
    from .numeric_verifier import numeric_requirements
    metric=re.escape(part['scope']['metric'])
    if part['scope']['metric'].casefold() in ('leak','leaked','leaks'):
        metric=r'leak(?:ed|s)?'
    status=re.compile(r'\b'+metric+r'(?:\s+(?:status|results?|measurements?))?\s+'
        r'(?:(?:was|were|is|are|has|have|been)\s+){0,3}'
        r'(?:not (?:reported|measured|evaluated|known|available)|unreported|unmeasured|unknown)\b',re.I)
    own=[c for c in clauses(context) if contains(member,c) and not scope_conflict(part,c)]
    absent=[c for c in own if _direct_absence(part,c) or status.search(c)]
    if not absent or any(c not in absent and metric_present(part,c)
            and (predicate_truth(part,c) is not None or numeric_requirements(c)) for c in own):
        return []
    passages=evidence_passages(context)
    return sorted({min((q for q in passages if c in q and not scope_conflict(part,q)),key=len)
        for c in absent if any(c in q and not scope_conflict(part,q) for q in passages)})
