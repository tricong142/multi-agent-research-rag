"""Shared local scope and explicit-absence checks, including unknown records."""
import re

from .assessment_rules import clauses, contains, scope_conflict, _MISSING
from .assessment_evidence import metric_present, predicate_truth

_CAUSAL = re.compile(r'\b(?:caus(?:e[sd]?|ing)|led to|leads? to|resulted in|causal relationship)\b', re.I)
_ABSENT = r'(?:not (?:reported|measured|evaluated|established|known|available)|unreported|unmeasured|unevaluated|unknown)'


def causal_claim(part):
    return bool(_CAUSAL.search(part['quote']))


def member_scope_issue(part, member, quotes, context):
    """An unknown record still cannot belong to an explicitly opposed scope."""
    if scope_conflict(part, member):
        return 'observation_scope_mismatch'
    if not part['scope']['time'] and not part['scope']['condition']:
        return None
    # Exact local ownership also rejects a source span crossing two sentences.
    source = [c for c in clauses(context) if contains(member, c)]
    if not source:
        return 'observation_scope_binding_unresolved'
    cited = [c for q in quotes for c in clauses(q) if contains(member, c)]
    own = cited or source
    if all(scope_conflict(part, c) for c in own):
        return 'observation_scope_mismatch'
    if any(scope_conflict(part, c) for c in own):
        return 'observation_scope_binding_unresolved'
    return None


def _direct_absence(part, clause):
    metric = re.escape(part['scope']['metric'])
    if re.search(r'(?<!\w)' + metric + r'(?!\w)\s+'
                 r'(?:(?:was|were|is|are|has|have|had|been)\s+){0,3}' + _ABSENT + r'\b', clause, re.I):
        return True
    if re.search(r'\bno\s+' + metric + r'\s+(?:results?|measurements?|data|changes?|evidence)\b', clause, re.I):
        return True
    if causal_claim(part) and re.search(
            r'\b(?:did not|does not|cannot|could not)\s+(?:establish|demonstrate|prove|confirm)\b[^.;]*'
            r'\b(?:causal relationship|causality|causal link)\b'
            r'|\b(?:causal relationship|causality|causal link)\b[^.;]*\b(?:not established|unproven|unknown)\b', clause, re.I):
        return True
    return False


def absence_quotes(part, context):
    """Exact source clauses that directly state the current predicate is missing.

    This selects unknown evidence, not its truth. Competing in-scope positive
    facts keep the general ledger available instead of hiding a conflict.
    """
    from .atomic_verifier import target_entity, target_members, other_named_target, ASSESSMENT_LIMITS
    from .numeric_verifier import numeric_requirements
    if part['quantifier']=='atomic' and target_entity(part) and not target_members(part, context):
        return []
    local = [c for c in clauses(context) if not scope_conflict(part,c) and not other_named_target(part,c)]
    found = [c for c in local if _direct_absence(part,c)]
    if not found:
        return []
    for c in local:
        if c not in found and metric_present(part,c) and not _MISSING.search(c):
            if predicate_truth(part,c) is not None or numeric_requirements(c):
                return []
    # Prefer the intact sentence when it contains no unrelated clause. This
    # preserves "Precision was not measured." exactly, with punctuation.
    exact = []
    for c in found:
        sentence = next((m[0].strip() for m in re.finditer(r'[^.!?]+(?:[.!?](?=\s|$)|$)',context) if c in m[0]),c)
        if scope_conflict(part,sentence) and not scope_conflict(part,c):
            # An unqualified "that group" cannot inherit a foreign antecedent.
            key=re.sub(r'^(?:in|on|under|for)\s+', '', part['scope']['condition'], flags=re.I)
            if not key or not contains(key,c):
                continue
        if clauses(sentence)==[c] or (re.search(r'\b(?:that group|these|those)\b',c,re.I)
                and not any(scope_conflict(part,v) for v in clauses(sentence))):
            quote=sentence
        else:
            quote=c
        if quote in context and len(quote)<=ASSESSMENT_LIMITS['quote_chars']:
            exact.append(quote)
    return sorted(set(exact))


def focus_issue(result, part, context):
    preferred = absence_quotes(part,context)
    for obs in result['observations']:
        issue = member_scope_issue(part,obs['member'],obs['quotes'],context)
        if issue:
            return issue
        if obs['truth']=='unknown' and preferred and not any(
                quote in cited for quote in preferred for cited in obs['quotes']):
            return 'missing_evidence_quote_required'
    if preferred and not result['observations']:
        return 'missing_evidence_quote_required'
    return None


def constrain_focus(schema, part, context):
    from copy import deepcopy
    props = schema['properties']
    preferred = absence_quotes(part,context)
    original = props['observations']['items']
    branches = original.get('anyOf',[original])
    kept = []
    for branch in branches:
        obs = branch['properties']
        unknown = obs['truth']['enum']==['unknown']
        members = [m for m in obs['member'].get('enum',[]) if not scope_conflict(part,m)]
        quote_choices = preferred if unknown and preferred else obs['quotes']['items'].get('enum',[])
        groups = {}
        for member in members:
            quotes = [q for q in quote_choices if member_scope_issue(part,member,[q],context) is None]
            required = max(obs['quotes'].get('minItems',0),int(unknown and bool(preferred)))
            if member_scope_issue(part,member,[],context):
                required = max(1,required)
            if required and not quotes:
                continue
            groups.setdefault((tuple(quotes),required),[]).append(member)
        # Equivalent members share a branch; do not duplicate its numeric schema
        # once per source span, which slows the token filter without adding proof.
        for (quotes, required), bound_members in groups.items():
            fixed = deepcopy(branch)
            values = fixed['properties']
            values['member'] = {'type':'string','enum':bound_members}
            if quotes:
                values['quotes']['items'] = {'type':'string','enum':list(quotes)}
            values['quotes']['minItems'] = required
            if unknown and preferred:
                values['quotes']['maxItems'] = 1
            elif not quotes:
                values['quotes']['maxItems'] = 0
            kept.append(fixed)
    if kept:
        props['observations']['items'] = {'anyOf':kept} if 'anyOf' in original or len(kept)>1 else kept[0]
    elif preferred:
        raise ValueError('unrepresentable_scoped_absence')
    else:
        # A context exclusively about another scope needs no invented witness.
        # Existing decisive-witness validation still rejects an empty dodge.
        props['observations']['minItems'] = 0
        props['observations']['maxItems'] = 0
    return schema
