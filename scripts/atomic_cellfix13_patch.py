"""Install shared member semantics into a new copy of immutable cf12."""
from pathlib import Path
from scripts.atomic_cellfix7_patch import replace_once


def apply_patch(root):
    root=Path(root)
    (root/'04_factchecker/inference/assessment_members.py').write_bytes(
        Path(__file__).with_name('atomic_cellfix13_members.py').read_bytes())
    path=root/'04_factchecker/inference/assessment_focus.py'
    text=path.read_text(encoding='utf-8')
    text=replace_once(text,'def focus_issue(result, part, context):\n',
        "def focus_issue(result, part, context):\n    from .assessment_members import empty_identity_required, empty_ledger_issue\n    if empty_identity_required(part,context):\n        return empty_ledger_issue(result)\n")
    text=replace_once(text,"    props = schema['properties']\n",
        "    from .assessment_members import empty_identity_required, constrain_empty_ledger, member_absence_quotes\n    if empty_identity_required(part,context):\n        return constrain_empty_ledger(schema)\n    props = schema['properties']\n")
    text=replace_once(text,"            quotes = [q for q in quote_choices if observation_focus_issue(part,member,[q],truth,context) is None]",
        "            local_absence = member_absence_quotes(part,member,context) if unknown else []\n            choices = local_absence or quote_choices\n            quotes = [q for q in choices if observation_focus_issue(part,member,[q],truth,context) is None]")
    text=replace_once(text,"int(unknown and bool(preferred))","int(unknown and bool(preferred or local_absence))")
    text=replace_once(text,"groups.setdefault((tuple(quotes),required),[])","groups.setdefault((tuple(quotes),required,bool(local_absence)),[])")
    text=replace_once(text,"for (quotes, required), bound_members in groups.items():","for (quotes, required, local_absence), bound_members in groups.items():")
    text=replace_once(text,"            if unknown and preferred:","            if unknown and (preferred or local_absence):")
    text=replace_once(text,"    # An absence assertion is evidence about availability, not an entity name.",
        "    from .assessment_members import member_identity_issue, member_absence_quotes\n    identity_issue = member_identity_issue(part,member,truth,context)\n    if identity_issue:\n        return identity_issue\n    if truth=='unknown':\n        direct = member_absence_quotes(part,member,context)\n        if direct and not any(q in cited for q in direct for cited in quotes):\n            return 'missing_evidence_quote_required'\n    # An absence assertion is evidence about availability, not an entity name.")
    path.write_text(text,encoding='utf-8')
    path=root/'04_factchecker/inference/atomic_verifier.py'
    text=path.read_text(encoding='utf-8')+'''


POLICY = 'atomic-verifier-constrained-v8-cellfix13'
REPAIR_HINTS.update(
    unresolved_target_requires_empty_ledger='The exact target is absent/unbound. Return observations=[], empty incomplete coverage, scope_match=unknown and the bound missing-information reason. Do not invent a member from a measurement or clause.',
    unresolved_target_scope_unknown='An unbound target has scope_match=unknown; an empty ledger cannot claim matched scope.',
    unresolved_target_missing_information='Name the missing target/population binding using the supplied reason code.',
    observation_member_is_not_entity='Use an exact source noun reference for the claimed population, a supported collective group, or a locally anchored name. Fragments, auxiliary-verb tails and quantities are not entities, even for unknown.')
ASSESS_PROMPT += (
    '\\nMEMBER IDENTITY: Source membership is necessary but not sufficient. '
    'A clause fragment or measurement is not an entity. When the exact atomic '
    'target is absent, emit an empty observation ledger with unknown scope and '
    'the required missing target reason; do not replace it with a workload alias. '
    'For unknown population records choose a source noun reference/group/name '
    'and cite its own explicit unreported status when available.\\n')
'''
    path.write_text(text,encoding='utf-8')
    path=root/'04_factchecker/inference/atomic_decoding.py'
    text=path.read_text(encoding='utf-8')+"\n\nDECODER.update(policy='atomic-schema-decoding-v5-cellfix13', member_identity='source_nominal_referents_v1', unresolved_target='empty_unknown_ledger')\n"
    path.write_text(text,encoding='utf-8')
