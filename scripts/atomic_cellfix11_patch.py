"""Patch a copy of cellfix10; retain every released baseline byte."""
from pathlib import Path
from scripts.atomic_cellfix7_patch import replace_once


def apply_patch(root):
    root=Path(root)
    (root/'04_factchecker/inference/assessment_focus.py').write_bytes(
        Path(__file__).with_name('atomic_cellfix11_focus.py').read_bytes())
    path=root/'04_factchecker/inference/assessment_reporting.py'
    text=path.read_text(encoding='utf-8')
    text=replace_once(text,"REASONS = {", "REASONS = {\n    'causal_relationship': 'Evidence establishing the claimed causal relationship, beyond co-occurrence/correlation',")
    text=replace_once(text,"    # Only explicit source absence licenses these specific reasons.",
        "    from .assessment_focus import causal_claim\n    if causal_claim(part):\n        return 'causal_relationship'\n    # Only explicit source absence licenses these specific reasons.")
    text=replace_once(text,"    return (REASONS[reason] + f\": target={scope['entity']}; predicate/metric={scope['metric']}\"",
        "    relation = ('; claimed relation=' + part['quote']) if reason=='causal_relationship' else ''\n    return (REASONS[reason] + f\": target={scope['entity']}; predicate/metric={scope['metric']}\" + relation")
    path.write_text(text,encoding='utf-8')
    path=root/'04_factchecker/inference/atomic_verifier.py'
    text=path.read_text(encoding='utf-8')
    text+='''


POLICY = 'atomic-verifier-constrained-v8-cellfix11'
from .assessment_focus import focus_issue
_cellfix10_assess = assess_part
def assess_part(raw, part, context):
    result = _cellfix10_assess(raw,part,context)
    issue = focus_issue(result,part,context)
    if issue:
        raise ValueError(issue)
    return result
REPAIR_HINTS.update(
    missing_evidence_quote_required='For unknown cite the exact in-scope clause explicitly stating THIS metric or causal relationship is unreported/unestablished, when supplied by the schema. Another metric result is not that evidence.',
    observation_scope_mismatch='A member of an opposed group/time is out of scope even if truth is unknown. Choose the in-scope member and local absence evidence; never borrow another group.',
    observation_scope_binding_unresolved='Bind the member to its own local source clause and claimed condition/time, including unknown observations. Do not span unrelated clauses or groups.')
ASSESS_PROMPT += (
    '\\nUNKNOWN EVIDENCE: An unknown observation still needs an in-scope member. '
    'Use the exact clause directly stating that the current metric was not '
    'measured/reported, when the schema supplies one. Do not cite another metric. '
    'A causal claim needs evidence for the causal_relationship; co-occurrence '
    'alone is insufficient. Respect the current condition/time even for unknown '
    'truth; another group cannot supply its member. If the context contains '
    'only an opposed scope, retain uncertainty without inventing a member.\\n')
'''
    path.write_text(text,encoding='utf-8')
    path=root/'04_factchecker/inference/atomic_decoding.py'
    text=path.read_text(encoding='utf-8')
    text+='''


from .assessment_focus import constrain_focus
DECODER.update(policy='atomic-schema-decoding-v5-cellfix11',
    unknown_citation='direct_part_absence_when_unambiguous',
    unknown_observation_scope='local_member_clause_including_unknown')
_cellfix10_final_schema = assessment_schema
def assessment_schema(claim, part, context):
    return constrain_focus(_cellfix10_final_schema(claim,part,context),part,context)
'''
    path.write_text(text,encoding='utf-8')
