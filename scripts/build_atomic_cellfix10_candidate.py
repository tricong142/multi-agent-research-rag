"""Preserve audited cf9 full39 and build shared cf10 assessment repairs."""
import copy
import json
from pathlib import Path

from scripts.atomic_cellfix10_patch import apply_patch
from scripts.atomic_validation_review import digest, json_bytes, write_once

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'research-runs/audit-cellfix9-full39-20261020T110710Z-cf47db2f'
SOURCE=ROOT/'research-runs/atomic-cellfix10-candidate/workspace'
CRITERIA='research_rag/evaluation/atomic_verifier_criteria_v8.json'


def build():
    if (ROOT/'docs/atomic-verifier-cellfix10-release.json').exists():
        raise ValueError('Released candidate is immutable')
    parent=json.loads((ROOT/'docs/atomic-verifier-cellfix9-candidate.json').read_bytes())
    release=json.loads((ROOT/'docs/atomic-verifier-cellfix9-release.json').read_bytes())
    audit=json.loads((ROOT/'docs/atomic-verifier-cellfix9-full39-audit-20261020T110710Z-cf47db2f.json').read_bytes())
    assert digest((BASE/'original-output.zip').read_bytes())==audit['zip_sha256']
    oldvalidation=ROOT/'docs/validation/atomic-cellfix6-v1'
    preservation={'run_id':audit['run_id'],'zip_sha256':audit['zip_sha256'],
        'predictions_sha256':digest((BASE/'artifact/verifier39/predictions.jsonl').read_bytes()),'metrics':json.loads((BASE/'artifact/verifier39/metrics.json').read_bytes()),
        'parent_criteria_sha256':parent['criteria_sha256'],'parent_input_manifest':parent['input_manifest'],
        'parent_release_files':release['files'],
        'validation30_files_sha256':{p.name:digest(p.read_bytes()) for p in sorted(oldvalidation.iterdir()) if p.is_file()}}
    write_once(ROOT/'docs/atomic-verifier-cellfix9-preserved-before-cellfix10.json',json_bytes(preservation))
    for name,item in parent['input_manifest'].items():
        raw=(BASE/'workspace'/name).read_bytes()
        assert len(raw)==item['size'] and digest(raw)==item['sha256'],name
        path=SOURCE/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    apply_patch(SOURCE)
    test='research_rag/tests/test_atomic_assessment_cellfix10.py'
    (SOURCE/test).write_bytes((ROOT/'scripts/test_atomic_cellfix10_assessment.py').read_bytes())
    trace='research_rag/tests/fixtures/atomic_cellfix9_full39_traces.json'
    cases=json.loads((BASE/'artifact/verifier39/cases.json').read_bytes())
    rows=[json.loads(s) for s in (BASE/'artifact/verifier39/predictions.jsonl').read_bytes().splitlines()]
    (SOURCE/trace).write_bytes(json_bytes([{'case':c,'result':r['result']} for c,r in zip(cases,rows)]))
    frozen=json.loads((SOURCE/CRITERIA).read_bytes())
    new=copy.deepcopy(frozen)
    contract=json.loads((SOURCE/'research_rag/evaluation'/new['contract_file']).read_bytes())
    contract.update(version='atomic-contract-constrained-v8-cellfix10',assessment_cellfix10={
        'binding':'Joint member/predicate/citation choices, local member clauses, prefix and suffix named targets. Roster-only quotes cannot establish outcomes.',
        'polarity':'Positive predicate truth before ALL/SOME/NONE. Do not borrow another member polarity from a mixed quote.',
        'coverage':'A unique complete selection-set roster can bind the queried selected population under the user-adjudicated discourse convention. No closure without every member outcome. Explicit competing sets, missing outcomes and inconsistent scopes prevent forcing.',
        'missing_information':'Decoder emits part-bound missing reason codes; validator rejects mismatched codes. Raw legacy prose remains in trace and still passes existing guards before rendering.',
        'prose':'Decoder emits neutral evidence-note constants. User explanations derive from the validated label, positive predicate truth, coverage and numeric ledger. Raw prose is retained in model_explanation/model_missing_information for audit, not evidence.',
        'limits':'Finite English grammar and scoped selection-set convention, not general coreference or entailment. Renderer correctness does not prove ledger semantics. GPU predictions and independent human review remain required.'})
    name='atomic_verifier_contract_v8_cellfix10.json'
    (SOURCE/'research_rag/evaluation'/name).write_bytes(json_bytes(contract))
    new.update(version='atomic-verifier-constrained-v8-cellfix10',policy='atomic-verifier-constrained-v8-cellfix10',
        contract_file=name,contract_sha256=digest((SOURCE/'research_rag/evaluation'/name).read_bytes()))
    new['structured_decoder'].update(policy='atomic-schema-decoding-v5-cellfix10',
        member_predicate_binding='local_clause_no_unrelated_fallback',
        population_coverage='explicit_closed_collective_witness',
        missing_information_scope='part_bound_reason_code',prose='validated_ledger_renderer_v1')
    adjudication='research_rag/evaluation/atomic_cellfix10_closure_adjudication.json'
    (SOURCE/adjudication).write_bytes(json_bytes({
        'kind':'human_annotation_clarification','case_id':'scope:existential:contradict',
        'user_confirmation':'Xác nhận audited set là toàn bộ cache nodes trong claim',
        'gold_changed':False,'context_changed':False,
        'policy':'A unique complete selection-set roster may refer to the selected population in the supplied claim; full outcome coverage and consistent scope are still mandatory.',
        'runtime_case_override':False}))
    extra=[test,trace,'04_factchecker/inference/assessment_reporting.py',adjudication]
    new['source_sha256']={n:digest((SOURCE/n).read_bytes()) for n in list(frozen['source_sha256'])+extra}
    # Read the actual final prompt instead of keeping a second prompt literal.
    import ast
    tree=ast.parse((SOURCE/'04_factchecker/inference/atomic_verifier.py').read_text(encoding='utf-8'))
    prompt=None
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='ASSESS_PROMPT' for t in node.targets):
            try: prompt=ast.literal_eval(node.value)
            except ValueError: pass
        elif isinstance(node,ast.AugAssign) and isinstance(node.target,ast.Name) and node.target.id=='ASSESS_PROMPT':
            prompt+=ast.literal_eval(node.value)
    assert isinstance(prompt,str)
    new['prompt_sha256']['assess']=digest(prompt.encode())
    new['limitations'] += [contract['assessment_cellfix10']['limits']]
    changed={'version','policy','contract_file','contract_sha256','structured_decoder','source_sha256','prompt_sha256','limitations'}
    assert all(new[k]==frozen[k] for k in frozen.keys()-changed),'Model/data/budget/gate changed'
    assert new['prompt_sha256']['decompose']==frozen['prompt_sha256']['decompose']
    (SOURCE/CRITERIA).write_bytes(json_bytes(new))
    names=sorted(set(parent['input_manifest'])|set(extra)|{'research_rag/evaluation/'+name})
    manifest={n:{'size':(SOURCE/n).stat().st_size,'sha256':digest((SOURCE/n).read_bytes())} for n in names}
    report={'candidate':new['policy'],'source_root':str(SOURCE),'criteria_sha256':digest((SOURCE/CRITERIA).read_bytes()),
        'input_manifest':manifest,'parent_criteria_sha256':parent['criteria_sha256'],'parent_run':audit['run_id'],
        'model_budget_gate_unchanged':True,'decomposition_prompt_unchanged':True,'assessment_prompt_changed':True,
        'validation30_used_for_tuning':False,'new_model_inference_completed':False,'promoted_to_serving':False}
    (ROOT/'docs/atomic-verifier-cellfix10-candidate.json').write_bytes(json_bytes(report))
    print(json.dumps({'candidate':new['policy'],'input_files':len(manifest),'criteria_sha256':report['criteria_sha256']}))


if __name__=='__main__':build()
