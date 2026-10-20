"""Preserve audited cf7 and build only the two diagnosed cf8 repairs."""
import copy
import json
from pathlib import Path

from scripts.atomic_cellfix8_patch import apply_patch
from scripts.atomic_validation_review import digest, json_bytes, write_once

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'research-runs/audit-cellfix7-fresh-20261020T033551Z-c7337790'
SOURCE=ROOT/'research-runs/atomic-cellfix8-candidate/workspace'
CRITERIA='research_rag/evaluation/atomic_verifier_criteria_v8.json'


def build():
    if (ROOT/'docs/atomic-verifier-cellfix8-release.json').exists():
        raise ValueError('Released candidate is immutable')
    parent=json.loads((ROOT/'docs/atomic-verifier-cellfix7-candidate.json').read_bytes())
    release=json.loads((ROOT/'docs/atomic-verifier-cellfix7-release.json').read_bytes())
    audit=json.loads((ROOT/'docs/atomic-verifier-cellfix7-smoke-audit-20261020T033551Z-c7337790.json').read_bytes())
    assert digest((BASE/'original-output.zip').read_bytes())==audit['zip_sha256']
    oldvalidation=ROOT/'docs/validation/atomic-cellfix6-v1'
    preservation={'run_id':audit['run_id'],'zip_sha256':audit['zip_sha256'],
        'predictions_sha256':audit['predictions_sha256'],'metrics':audit['metrics'],
        'parent_criteria_sha256':parent['criteria_sha256'],'parent_input_manifest':parent['input_manifest'],
        'parent_release_files':release['files'],
        'validation30_files_sha256':{p.name:digest(p.read_bytes()) for p in sorted(oldvalidation.iterdir()) if p.is_file()}}
    write_once(ROOT/'docs/atomic-verifier-cellfix7-preserved-before-cellfix8.json',json_bytes(preservation))
    for name,item in parent['input_manifest'].items():
        raw=(BASE/'workspace'/name).read_bytes()
        assert len(raw)==item['size'] and digest(raw)==item['sha256'],name
        path=SOURCE/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    apply_patch(SOURCE)
    test='research_rag/tests/test_atomic_assessment_cellfix8.py'
    (SOURCE/test).write_bytes((ROOT/'scripts/test_atomic_cellfix8_assessment.py').read_bytes())
    trace='research_rag/tests/fixtures/atomic_cellfix7_smoke_traces.json'
    cases=json.loads((BASE/'artifact/assessment-smoke/cases.json').read_bytes())
    rows=[json.loads(s) for s in (BASE/'artifact/assessment-smoke/predictions.jsonl').read_bytes().splitlines()]
    (SOURCE/trace).write_bytes(json_bytes([{'case':c,'result':r['result']} for c,r in zip(cases,rows)]))
    frozen=json.loads((SOURCE/CRITERIA).read_bytes())
    new=copy.deepcopy(frozen)
    contract=json.loads((SOURCE/'research_rag/evaluation'/new['contract_file']).read_bytes())
    contract.update(version='atomic-contract-constrained-v8-cellfix8',assessment_cellfix8={
        'json_parser':'Character-checked parser wrapper restricts the LMFE 0.11.3 freetext cache to the request alphabet and whitespace limit. Boundaries traverse the trie. Existing length, field order, numeric and citation constraints remain.',
        'scoped_missing_information':'Finite root subject + exact verb + named property with all local restrictions; contradictory reports retain unknown. Reject nonempty missing information only when finite source evidence decides the current part.',
        'limits':'No general entailment, semantic missing-information classification or new world knowledge. Runtime overhead and model quality require T4 evaluation.'})
    name='atomic_verifier_contract_v8_cellfix8.json'
    (SOURCE/'research_rag/evaluation'/name).write_bytes(json_bytes(contract))
    new.update(version='atomic-verifier-constrained-v8-cellfix8',policy='atomic-verifier-constrained-v8-cellfix8',
        contract_file=name,contract_sha256=digest((SOURCE/'research_rag/evaluation'/name).read_bytes()))
    new['structured_decoder'].update(policy='atomic-schema-decoding-v5-cellfix8',
        json_freetext_policy='character_checked_request_alphabet_cache',scoped_missing_information='reject_when_finite_witness_is_decisive')
    extra=[test,trace,'04_factchecker/inference/decoder_parser.py']
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
    new['limitations'] += [contract['assessment_cellfix8']['limits']]
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
    (ROOT/'docs/atomic-verifier-cellfix8-candidate.json').write_bytes(json_bytes(report))
    print(json.dumps({'candidate':new['policy'],'input_files':len(manifest),'criteria_sha256':report['criteria_sha256']}))


if __name__=='__main__':build()
