"""Preserve failed cf11 and freeze general assessment repairs in a new tree."""
import ast
import copy
import json
from pathlib import Path

from scripts.atomic_cellfix12_patch import apply_patch
from scripts.atomic_validation_review import digest, json_bytes, write_once

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'research-runs/audit-cellfix11-full39-20261026T150123Z-615bf4eb'
SOURCE = ROOT/'research-runs/atomic-cellfix12-candidate/workspace'
CRITERIA = 'research_rag/evaluation/atomic_verifier_criteria_v8.json'


def build():
    if (ROOT/'docs/atomic-verifier-cellfix12-release.json').exists():
        raise ValueError('Released candidate is immutable')
    parent = json.loads((ROOT/'docs/atomic-verifier-cellfix11-candidate.json').read_bytes())
    release = json.loads((ROOT/'docs/atomic-verifier-cellfix11-release.json').read_bytes())
    audit = json.loads((ROOT/'docs/atomic-verifier-cellfix11-full39-audit-20261026T150123Z-615bf4eb.json').read_bytes())
    assert digest((BASE/'original-output.zip').read_bytes()) == audit['zip_sha256']
    for name, expected in release['files'].items():
        assert digest((ROOT/name).read_bytes()) == expected, name
    oldvalidation = ROOT/'docs/validation/atomic-cellfix6-v1'
    preservation = {'run_id': audit['run_id'], 'zip_sha256': audit['zip_sha256'],
        'predictions_sha256': digest((BASE/'artifact/verifier39/predictions.jsonl').read_bytes()),
        'metrics': json.loads((BASE/'artifact/verifier39/metrics.json').read_bytes()),
        'parent_criteria_sha256': parent['criteria_sha256'], 'parent_input_manifest': parent['input_manifest'],
        'parent_release_files': release['files'],
        'baseline_outputs_sha256': {p.relative_to(BASE/'artifact').as_posix(): digest(p.read_bytes())
            for p in sorted((BASE/'artifact').rglob('*')) if p.is_file()},
        'validation30_files_sha256': {p.name: digest(p.read_bytes()) for p in sorted(oldvalidation.iterdir()) if p.is_file()}}
    write_once(ROOT/'docs/atomic-verifier-cellfix11-preserved-before-cellfix12.json', json_bytes(preservation))
    for name, item in parent['input_manifest'].items():
        raw = (BASE/'workspace'/name).read_bytes()
        assert len(raw) == item['size'] and digest(raw) == item['sha256'], name
        path = SOURCE/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    apply_patch(SOURCE)
    # Adapt two legacy assertions to the new contract; preserve parent tests/fixtures.
    from scripts.atomic_cellfix7_patch import replace_once
    path = SOURCE/'research_rag/tests/test_atomic_verifier.py'
    text = path.read_text(encoding='utf-8')
    text = replace_once(text,
        "        self.assertEqual(a.assess_part(raw, p, context)['assessed_label'], 'not_enough_info')\n        for scope in ('unknown', 'mismatched'):\n            raw['scope_match'] = scope\n            self.assertEqual(a.assess_part(raw, p, context)['assessed_label'], 'not_enough_info')",
        "        # A wrong-metric numeric citation now requires repair, even if its\n        # failed association previously degraded the observation to unknown.\n        with self.assertRaisesRegex(ValueError, 'observation_evidence_unbound'):\n            a.assess_part(raw, p, context)\n        for scope in ('unknown', 'mismatched'):\n            raw['scope_match'] = scope\n            with self.assertRaisesRegex(ValueError, 'observation_evidence_unbound'):\n                a.assess_part(raw, p, context)")
    path.write_text(text, encoding='utf-8')
    path = SOURCE/'research_rag/tests/test_atomic_assessment_cellfix11.py'
    text = path.read_text(encoding='utf-8')
    text = replace_once(text,
        "    def test_received_foreign_unknown_member_is_rejected(self):\n        raw,payload=trace('scope:condition:not_enough_info');p,ctx=payload['part'],payload['context']",
        "    def test_received_foreign_unknown_member_is_rejected(self):\n        raw,payload=trace('scope:condition:not_enough_info');p,ctx=payload['part'],payload['context']\n        raw['missing_information']=[r.missing_reason(p,ctx)]  # cf12 recognizes unmeasured changes.")
    path.write_text(text, encoding='utf-8')
    test = 'research_rag/tests/test_atomic_assessment_cellfix12.py'
    (SOURCE/test).write_bytes((ROOT/'scripts/test_atomic_cellfix12_assessment.py').read_bytes())
    trace = 'research_rag/tests/fixtures/atomic_cellfix11_full39_traces.json'
    cases = json.loads((BASE/'artifact/verifier39/cases.json').read_bytes())
    rows = [json.loads(s) for s in (BASE/'artifact/verifier39/predictions.jsonl').read_bytes().splitlines()]
    (SOURCE/trace).write_bytes(json_bytes([{'case': c, 'result': r['result']} for c, r in zip(cases, rows)]))
    frozen = json.loads((SOURCE/CRITERIA).read_bytes())
    new = copy.deepcopy(frozen)
    contract = json.loads((SOURCE/'research_rag/evaluation'/new['contract_file']).read_bytes())
    contract.update(version='atomic-contract-constrained-v8-cellfix12', assessment_cellfix12={
        'binding': 'Unknown quotes obey the same member ownership and named-target rules. An unambiguous direct metric/relation absence can omit its event subject; unrelated target quotes cannot.',
        'decisive_witness': 'Atomic root target/property direction facts require known truth when unambiguous. Qualified populations remain conservative; modal, numeric, conditional, conflicting and causal statements are not inferred by this finite qualitative rule.',
        'absence': 'No changes were measured/reported is missing evidence before polarity, never a negative outcome or an entity member. Measured unchanged outcomes remain counterevidence. Shared finite rules constrain validator and decoder.',
        'limits': 'Finite English source clauses, not a general entailment/coreference engine. Local fixtures and token feasibility do not establish GPU label accuracy. New predictions and human reviews remain required.'})
    name = 'atomic_verifier_contract_v8_cellfix12.json'
    (SOURCE/'research_rag/evaluation'/name).write_bytes(json_bytes(contract))
    new.update(version='atomic-verifier-constrained-v8-cellfix12', policy='atomic-verifier-constrained-v8-cellfix12',
        contract_file=name, contract_sha256=digest((SOURCE/'research_rag/evaluation'/name).read_bytes()))
    new['structured_decoder'].update(policy='atomic-schema-decoding-v5-cellfix12',
        unknown_binding='member_quote_joint', absence_truth='unknown_before_polarity')
    extra = [test, trace]
    new['source_sha256'] = {n: digest((SOURCE/n).read_bytes()) for n in list(frozen['source_sha256'])+extra}
    prompt = None
    tree = ast.parse((SOURCE/'04_factchecker/inference/atomic_verifier.py').read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'ASSESS_PROMPT' for t in node.targets):
            try:
                prompt = ast.literal_eval(node.value)
            except ValueError:
                pass
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name) and node.target.id == 'ASSESS_PROMPT':
            prompt += ast.literal_eval(node.value)
    assert isinstance(prompt, str)
    new['prompt_sha256']['assess'] = digest(prompt.encode())
    new['limitations'] += [contract['assessment_cellfix12']['limits']]
    changed = {'version','policy','contract_file','contract_sha256','structured_decoder','source_sha256','prompt_sha256','limitations'}
    assert all(new[k] == frozen[k] for k in frozen.keys()-changed), 'Model/data/budget/gate changed'
    assert new['prompt_sha256']['decompose'] == frozen['prompt_sha256']['decompose']
    (SOURCE/CRITERIA).write_bytes(json_bytes(new))
    names = sorted(set(parent['input_manifest']) | set(extra) | {'research_rag/evaluation/'+name})
    manifest = {n: {'size': (SOURCE/n).stat().st_size, 'sha256': digest((SOURCE/n).read_bytes())} for n in names}
    report = {'candidate': new['policy'], 'source_root': str(SOURCE), 'criteria_sha256': digest((SOURCE/CRITERIA).read_bytes()),
        'input_manifest': manifest, 'parent_criteria_sha256': parent['criteria_sha256'], 'parent_run': audit['run_id'],
        'model_budget_gate_unchanged': True, 'decomposition_prompt_unchanged': True, 'assessment_prompt_changed': True,
        'validation30_used_for_tuning': False, 'new_model_inference_completed': False, 'promoted_to_serving': False}
    (ROOT/'docs/atomic-verifier-cellfix12-candidate.json').write_bytes(json_bytes(report))
    print(json.dumps({'candidate': new['policy'], 'input_files': len(manifest), 'criteria_sha256': report['criteria_sha256']}))


if __name__ == '__main__':
    build()
