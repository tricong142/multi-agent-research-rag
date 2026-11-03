"""Patch a new copy of cf11; never mutate the released candidate."""
from pathlib import Path
from scripts.atomic_cellfix7_patch import replace_once


def apply_patch(root):
    root = Path(root)
    path = root/'04_factchecker/inference/assessment_rules.py'
    text = path.read_text(encoding='utf-8')
    text = replace_once(text, "r'unreported|unmeasured|unevaluated|unknown|'",
        "r'unreported|unmeasured|unevaluated|unknown|'\n"
        "    r'no (?:\\w+[ -]){0,5}changes?\\s+(?:was|were|has been|have been)\\s+(?:measured|reported|evaluated|recorded)|'")
    path.write_text(text, encoding='utf-8')
    path = root/'04_factchecker/inference/assessment_decisions.py'
    text = path.read_text(encoding='utf-8')
    text = replace_once(text, "if len(words)>1 and not all(w[:1].isupper() for w in words):",
        "if len(words)>1 and not all(w[:1].isupper() for w in words) and (part['quantifier']!='atomic' or re.search(r'(?<!\\w)(?:non-|un)'+re.escape(part['scope']['entity']),context,re.I)):")
    text = replace_once(text, "            truth = direct_truth(part,clause,member)",
        "            truth = direct_truth(part,clause,member)\n"
        "            if truth is None and part['quantifier']=='atomic':\n"
        "                from .assessment_focus import atomic_property_truth\n"
        "                truth = atomic_property_truth(part,clause,member)")
    path.write_text(text, encoding='utf-8')
    path = root/'04_factchecker/inference/assessment_focus.py'
    text = path.read_text(encoding='utf-8')
    text = replace_once(text, "    if not part['scope']['time'] and not part['scope']['condition']:",
        "    from .atomic_verifier import other_named_target, target_members\n"
        "    if part['quantifier']=='atomic' and target_members(part,context):\n"
        "        if any(other_named_target(part,q) for q in quotes):\n"
        "            return 'observation_target_mismatch'\n"
        "    unowned = [q for q in quotes if not any(contains(member,c) for c in clauses(q))]\n"
        "    if unowned:\n"
        "        # An explicit metric/relation absence may omit the event subject.\n"
        "        preferred = absence_quotes(part,context)\n"
        "        if not preferred or not all(any(a in q for a in preferred) for q in quotes):\n"
        "            return 'observation_evidence_unbound'\n"
        "    if not part['scope']['time'] and not part['scope']['condition']:")
    text = replace_once(text,
        "    if re.search(r'\\bno\\s+' + metric + r'\\s+(?:results?|measurements?|data|changes?|evidence)\\b', clause, re.I):",
        "    if re.search(r'\\bno\\s+' + metric + r'\\s+(?:results?|measurements?|data|evidence)\\b', clause, re.I) or (\n"
        "            re.search(r'\\bno\\s+' + metric + r'\\s+changes?\\b',clause,re.I)\n"
        "            and _MISSING.search(clause)):")
    text = replace_once(text,
        "        if c not in found and metric_present(part,c) and not _MISSING.search(c):",
        "        if causal_claim(part) and not _CAUSAL.search(c):\n"
        "            continue  # Co-occurring property changes do not establish cause.\n"
        "        if c not in found and metric_present(part,c) and not _MISSING.search(c):")
    text = replace_once(text,
        "        if not preferred or not all(any(a in q for a in preferred) for q in quotes):",
        "        from .numeric_verifier import numeric_requirements\n"
        "        from .assessment_decisions import numeric_choices\n"
        "        numeric_sources = {r['source_quote'] for group in numeric_choices(part,context) for r,_ in group} if numeric_requirements(part['quote']) else set()\n"
        "        if not all(q in numeric_sources or any(a in q for a in preferred) for q in unowned):")
    text = replace_once(text, "        if obs['truth']=='unknown' and preferred and not any(",
        "        issue = observation_focus_issue(part,obs['member'],obs['quotes'],obs['truth'],context)\n"
        "        if issue:\n"
        "            return issue\n"
        "        if obs['truth']=='unknown' and preferred and not any(")
    text = replace_once(text,
        "            quotes = [q for q in quote_choices if member_scope_issue(part,member,[q],context) is None]",
        "            truth = obs['truth']['enum'][0]\n"
        "            quotes = [q for q in quote_choices if observation_focus_issue(part,member,[q],truth,context) is None]")
    text = replace_once(text,
        "            if member_scope_issue(part,member,[],context):",
        "            if observation_focus_issue(part,member,[],truth,context):")
    text += '''


def observation_focus_issue(part, member, quotes, truth, context):
    issue = member_scope_issue(part,member,quotes,context)
    if issue:
        return issue
    # An absence assertion is evidence about availability, not an entity name.
    if _MISSING.search(member) and re.search(r'\\b(?:was|were|is|are|has been|have been)\\b',member,re.I):
        return 'observation_member_is_not_entity'
    if truth!='unknown' and absence_quotes(part,context):
        return 'missing_evidence_is_not_false'
    own = [c for q in quotes for c in clauses(q) if contains(member,c)]
    relevant = [c for c in own if metric_present(part,c) or _direct_absence(part,c)] or own
    if truth!='unknown' and relevant and all(_direct_absence(part,c) for c in relevant):
        return 'missing_evidence_is_not_false'
    return None


def atomic_property_truth(part, text, member):
    """Root subject + exact property direction only; no inferred coreference."""
    from .assessment_decisions import scope_supported
    from .numeric_verifier import numeric_requirements
    if (numeric_requirements(part['quote']) or numeric_requirements(text)
            or causal_claim(part) or not scope_supported(part,text)):
        return None
    if re.search(r'(?<!\\w)(?:non-|un)'+re.escape(member),text,re.I):
        return None
    clean = text.strip(' .,;:')
    for restriction in (part['scope']['time'],part['scope']['condition']):
        if restriction:
            clean = re.sub(r'^'+re.escape(restriction)+r'\\s*,?\\s*','',clean,flags=re.I)
            clean = re.sub(r'\\s*,?\\s*'+re.escape(restriction)+r'$','',clean,flags=re.I)
    subject = r'(?:the\\s+)?'+re.escape(member)
    metric = re.escape(part['scope']['metric'])
    verb = r'(?:increased|decreased|reduced|rose|fell|gained|lost|remained unchanged|stayed the same)'
    shape = subject+r"(?:'s\\s+"+metric+r'\\s+'+verb+r'|\\s+'+verb+r'\\s+(?:its\\s+)?'+metric+r')'
    if not re.fullmatch(shape,clean,re.I):
        return None
    # The claim must also be a direct predicate about this exact target/property.
    claim = part['quote'].strip(' .,;:')
    for restriction in (part['scope']['time'],part['scope']['condition']):
        if restriction:
            claim = re.sub(r'^'+re.escape(restriction)+r'\\s*,?\\s*','',claim,flags=re.I)
            claim = re.sub(r'\\s*,?\\s*'+re.escape(restriction)+r'$','',claim,flags=re.I)
    if not re.fullmatch(shape,claim,re.I):
        return None
    return predicate_truth(part,text)
'''
    path.write_text(text, encoding='utf-8')
    path = root/'04_factchecker/inference/atomic_verifier.py'
    text = path.read_text(encoding='utf-8')
    text += '''


POLICY = 'atomic-verifier-constrained-v8-cellfix12'
REPAIR_HINTS.update(
    observation_evidence_unbound='Bind the quote to this member, not another target. Explicit metric/relation absence may omit the event subject only when locally unambiguous.',
    observation_member_is_not_entity='A clause stating that measurements were not reported is not an entity. Select the in-scope entity/group; retain unknown for missing measurements.',
    missing_evidence_is_not_false='Missing/unreported measurements are unknown, not true or false. A measured unchanged result or explicit denial is different and can be counterevidence.',
    decisive_witness_missing_or_unknown='Use the explicit in-scope target/property result already present; unknown cannot discard a decisive witness.')
ASSESS_PROMPT += (
    '\\nBINDING: Every quoted result belongs to its own member. Unknown does not '
    'permit another named target quote or omission of a direct decisive result. '
    'A sentence saying measurements were not made is evidence of uncertainty, '
    'never a false outcome or an entity name. Measured no-change results and '
    'explicit denials remain actual counterevidence.\\n')
'''
    path.write_text(text, encoding='utf-8')
    path = root/'04_factchecker/inference/atomic_decoding.py'
    text = path.read_text(encoding='utf-8')
    text += "\n\nDECODER.update(policy='atomic-schema-decoding-v5-cellfix12', unknown_binding='member_quote_joint', absence_truth='unknown_before_polarity')\n"
    path.write_text(text, encoding='utf-8')
