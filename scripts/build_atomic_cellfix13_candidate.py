"""Preserve cf12's failed human review and build shared member identity guards."""
import ast
import copy
import json
from pathlib import Path

from scripts.atomic_cellfix13_patch import apply_patch
from scripts.atomic_validation_review import digest,json_bytes,write_once

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'research-runs/audit-cellfix12-admission-20261027T092904Z-e02b51ab'
SOURCE=ROOT/'research-runs/atomic-cellfix13-candidate/workspace'
CRITERIA='research_rag/evaluation/atomic_verifier_criteria_v8.json'


def build():
    if (ROOT/'docs/atomic-verifier-cellfix13-release.json').exists():
        raise ValueError('Released candidate is immutable')
    parent=json.loads((ROOT/'docs/atomic-verifier-cellfix12-candidate.json').read_bytes())
    release=json.loads((ROOT/'docs/atomic-verifier-cellfix12-release.json').read_bytes())
    audit=json.loads((ROOT/'docs/reviews/cellfix12-full39-20261027T092904Z-e02b51ab/ADMISSION_DIAGNOSIS.json').read_bytes())
    assert digest((BASE/'original-output.zip').read_bytes())==audit['diagnostic_zip_sha256']
    assert digest((BASE/'uploaded-semantic-review.json').read_bytes())==audit['review_sha256']
    for name,expected in release['files'].items():
        assert digest((ROOT/name).read_bytes())==expected,name
    oldvalidation=ROOT/'docs/validation/atomic-cellfix6-v1'
    preservation={'run_id':audit['run_id'],'zip_sha256':audit['diagnostic_zip_sha256'],
        'predictions_sha256':audit['predictions_sha256'],'human_review_sha256':audit['review_sha256'],
        'human_failed_cases':audit['failed_cases'],'parent_release_files':release['files'],
        'parent_input_manifest':parent['input_manifest'],
        'metrics':json.loads((BASE/'artifact/verifier39/metrics.json').read_bytes()),
        'baseline_outputs_sha256':{p.relative_to(BASE/'artifact').as_posix():digest(p.read_bytes())
            for p in sorted((BASE/'artifact').rglob('*')) if p.is_file()},
        'validation30_files_sha256':{p.name:digest(p.read_bytes()) for p in sorted(oldvalidation.iterdir()) if p.is_file()}}
    write_once(ROOT/'docs/atomic-verifier-cellfix12-preserved-before-cellfix13.json',json_bytes(preservation))
    for name,item in parent['input_manifest'].items():
        raw=(Path(parent['source_root'])/name).read_bytes()
        assert len(raw)==item['size'] and digest(raw)==item['sha256'],name
        path=SOURCE/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    apply_patch(SOURCE)
    adapt_legacy_tests(SOURCE)
    test='research_rag/tests/test_atomic_assessment_cellfix13.py'
    (SOURCE/test).write_bytes((ROOT/'scripts/test_atomic_cellfix13_assessment.py').read_bytes())
    trace='research_rag/tests/fixtures/atomic_cellfix12_full39_traces.json'
    cases=json.loads((BASE/'artifact/verifier39/cases.json').read_bytes())
    rows=[json.loads(s) for s in (BASE/'artifact/verifier39/predictions.jsonl').read_bytes().splitlines()]
    (SOURCE/trace).write_bytes(json_bytes([{'case':c,'result':r['result']} for c,r in zip(cases,rows)]))
    frozen=json.loads((SOURCE/CRITERIA).read_bytes());new=copy.deepcopy(frozen)
    contract=json.loads((SOURCE/'research_rag/evaluation'/new['contract_file']).read_bytes())
    contract.update(version='atomic-contract-constrained-v8-cellfix13',assessment_cellfix13={
        'unbound_target':'An absent exact atomic target requires observations=[], empty incomplete coverage, unknown scope and explicit missing binding. No inferred workload/entity alias or quantity stand-in.',
        'unknown_member':'Unknown records use exact source nominal references for the population, explicit collective scope labels, or locally metric-anchored proper names. Clause fragments and quantities cannot stand in for an entity. Shared validator/decoder grammar.',
        'absence_quote':'An unknown named member with directly unreported status cites its own exact source absence even if other population members have known outcomes. Same-member conflicting evidence retains the general ledger.',
        'limits':'Finite English nominal/possessive grammar, not general NER/coreference. Unsupported identity stays unknown; offline feasibility cannot establish GPU quality or human approval.'})
    name='atomic_verifier_contract_v8_cellfix13.json'
    (SOURCE/'research_rag/evaluation'/name).write_bytes(json_bytes(contract))
    new.update(version='atomic-verifier-constrained-v8-cellfix13',policy='atomic-verifier-constrained-v8-cellfix13',
        contract_file=name,contract_sha256=digest((SOURCE/'research_rag/evaluation'/name).read_bytes()))
    new['structured_decoder'].update(policy='atomic-schema-decoding-v5-cellfix13',
        member_identity='source_nominal_referents_v1',unresolved_target='empty_unknown_ledger')
    extra=[test,trace,'04_factchecker/inference/assessment_members.py']
    new['source_sha256']={n:digest((SOURCE/n).read_bytes()) for n in list(frozen['source_sha256'])+extra}
    prompt=None
    for node in ast.parse((SOURCE/'04_factchecker/inference/atomic_verifier.py').read_text(encoding='utf-8')).body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='ASSESS_PROMPT' for t in node.targets):
            try:prompt=ast.literal_eval(node.value)
            except ValueError:pass
        elif isinstance(node,ast.AugAssign) and isinstance(node.target,ast.Name) and node.target.id=='ASSESS_PROMPT':
            prompt+=ast.literal_eval(node.value)
    assert isinstance(prompt,str);new['prompt_sha256']['assess']=digest(prompt.encode())
    new['limitations'] += [contract['assessment_cellfix13']['limits']]
    changed={'version','policy','contract_file','contract_sha256','structured_decoder','source_sha256','prompt_sha256','limitations'}
    assert all(new[k]==frozen[k] for k in frozen.keys()-changed),'Model/data/budget/gate changed'
    assert new['prompt_sha256']['decompose']==frozen['prompt_sha256']['decompose']
    (SOURCE/CRITERIA).write_bytes(json_bytes(new))
    names=sorted(set(parent['input_manifest'])|set(extra)|{'research_rag/evaluation/'+name})
    manifest={n:{'size':(SOURCE/n).stat().st_size,'sha256':digest((SOURCE/n).read_bytes())} for n in names}
    report={'candidate':new['policy'],'source_root':str(SOURCE),'criteria_sha256':digest((SOURCE/CRITERIA).read_bytes()),
        'input_manifest':manifest,'parent_criteria_sha256':parent['criteria_sha256'],'parent_run':audit['run_id'],
        'model_budget_gate_unchanged':True,'decomposition_prompt_unchanged':True,'assessment_prompt_changed':True,
        'legacy_test_contract_updates':['test_atomic_smoke_cellfix3.py','test_atomic_assessment_cellfix6.py','test_atomic_assessment_cellfix10.py'],
        'validation30_used_for_tuning':False,'new_model_inference_completed':False,'promoted_to_serving':False}
    (ROOT/'docs/atomic-verifier-cellfix13-candidate.json').write_bytes(json_bytes(report))
    print(json.dumps({'candidate':new['policy'],'input_files':len(manifest),'criteria_sha256':report['criteria_sha256']}))


def adapt_legacy_tests(source):
    """Keep old bad records as negative controls; add the explicit empty response."""
    from scripts.atomic_cellfix7_patch import replace_once
    folder=source/'research_rag/tests'
    path=folder/'test_atomic_smoke_cellfix3.py';text=path.read_text(encoding='utf-8')
    text=replace_once(text,
        "        self.assertEqual(a.assess_part(raw,p,proof)['assessed_label'],'not_enough_info')\n        self.assertFalse(self.accepts(self.ordered(raw),request(claim,p,proof)))\n        raw['observations'][0]['truth']='unknown'\n        self.assertTrue(self.accepts(self.ordered(raw),request(claim,p,proof)))",
        "        with self.assertRaisesRegex(ValueError,'unresolved_target_requires_empty_ledger'):a.assess_part(raw,p,proof)\n        self.assertFalse(self.accepts(self.ordered(raw),request(claim,p,proof)))\n        raw['observations'][0]['truth']='unknown'\n        self.assertFalse(self.accepts(self.ordered(raw),request(claim,p,proof)))\n        raw=assessment([],scope='unknown',missing=['target_binding_unresolved'])\n        self.assertEqual(a.assess_part(raw,p,proof)['assessed_label'],'not_enough_info')\n        self.assertTrue(self.accepts(self.ordered(raw),request(claim,p,proof)))")
    path.write_text(text,encoding='utf-8')
    path=folder/'test_atomic_assessment_cellfix6.py';text=path.read_text(encoding='utf-8')
    text=replace_once(text,
        "        raw=assessment([observation('workload','true',ctx)])\n        self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'not_enough_info')",
        "        raw=assessment([observation('workload','true',ctx)])\n        with self.assertRaisesRegex(ValueError,'unresolved_target_requires_empty_ledger'):a.assess_part(raw,p,ctx)\n        raw=assessment([],scope='unknown',missing=['target_binding_unresolved'])\n        self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'not_enough_info')")
    path.write_text(text,encoding='utf-8')
    path=folder/'test_atomic_assessment_cellfix10.py';text=path.read_text(encoding='utf-8')
    text=replace_once(text,
        "        good = canonical(raw, p, ctx)\n        result = a.assess_part(good, p, ctx)\n        self.assertEqual(result['assessed_label'], 'not_enough_info')\n        self.assertEqual(result['missing_reason'], 'target_binding_unresolved')",
        "        good = canonical(raw, p, ctx)\n        with self.assertRaisesRegex(ValueError,'unresolved_target_requires_empty_ledger'):a.assess_part(good,p,ctx)\n        good = canonical(assessment([],scope='unknown',missing=['target_binding_unresolved']),p,ctx)\n        result = a.assess_part(good, p, ctx)\n        self.assertEqual(result['assessed_label'], 'not_enough_info')\n        self.assertEqual(result['missing_reason'], 'target_binding_unresolved')")
    text=replace_once(text,
        "        raw = assessment([observation('Peak memory', 'unknown', ctx)], missing=['target_binding_unresolved'])\n        result = a.assess_part(raw, p, ctx)",
        "        raw = assessment([observation('Peak memory', 'unknown', ctx)], missing=['target_binding_unresolved'])\n        with self.assertRaisesRegex(ValueError,'unresolved_target_requires_empty_ledger'):a.assess_part(raw,p,ctx)\n        raw=assessment([],scope='unknown',missing=['target_binding_unresolved'])\n        result = a.assess_part(raw, p, ctx)")
    text=replace_once(text,
        "            raw = canonical(t['output'], payload['part'], payload['context'])\n            self.assertTrue(self.accepts(self.ordered(raw), request(payload['claim'], payload['part'], payload['context'])), cid)",
        "            raw = canonical(t['output'], payload['part'], payload['context'])\n            if cid.startswith('scope:conjunction:'):\n                self.assertFalse(self.accepts(self.ordered(raw),request(payload['claim'],payload['part'],payload['context'])))\n                raw=canonical(assessment([],scope='unknown',missing=['target_binding_unresolved']),payload['part'],payload['context'])\n            self.assertTrue(self.accepts(self.ordered(raw), request(payload['claim'], payload['part'], payload['context'])), cid)")
    path.write_text(text,encoding='utf-8')


if __name__=='__main__':build()
