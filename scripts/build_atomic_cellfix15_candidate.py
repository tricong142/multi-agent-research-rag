"""Isolated assessment-only successor to the frozen Cellfix14 release."""
import importlib
import json
from pathlib import Path
import sys

from scripts.build_atomic_cellfix14_candidate import digest, replace

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'research-runs/atomic-cellfix15-candidate/workspace'
CRITERIA = 'research_rag/evaluation/atomic_verifier_criteria_v8.json'


def build():
    if (ROOT/'docs/atomic-verifier-cellfix15-release.json').exists():
        raise ValueError('Released cf15 is immutable')
    parent = json.loads((ROOT/'docs/atomic-verifier-cellfix14-candidate.json').read_bytes())
    release = json.loads((ROOT/'docs/atomic-verifier-cellfix14-release.json').read_bytes())
    for name, expected in release['files'].items():
        assert digest((ROOT/name).read_bytes()) == expected, name
    for name, item in parent['input_manifest'].items():
        raw = (Path(parent['source_root'])/name).read_bytes()
        assert digest(raw) == item['sha256'], name
        path = SOURCE/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    folder = SOURCE/'04_factchecker/inference'
    path = folder/'assessment_focus.py'
    text = path.read_text(encoding='utf-8')
    text = replace(text,
        '    from .assessment_members import member_identity_issue, member_absence_quotes\n',
        '    from .assessment_members import member_identity_issue, member_absence_quotes\n'
        '    # Missing status is local to this member; other members retain known outcomes.\n'
        "    if truth != 'unknown' and member_absence_quotes(part,member,context):\n"
        "        return 'missing_evidence_is_not_false'\n")
    path.write_text(text, encoding='utf-8')
    path = folder/'atomic_verifier.py'
    path.write_text(path.read_text(encoding='utf-8')+"\nPOLICY='atomic-verifier-constrained-v8-cellfix15'\n", encoding='utf-8')
    path = folder/'atomic_decoding.py'
    path.write_text(path.read_text(encoding='utf-8')+"\nDECODER.update(policy='atomic-schema-decoding-v5-cellfix15',member_local_absence='shared_focus_guard_v1')\n", encoding='utf-8')
    extra = ['research_rag/tests/test_atomic_cellfix15.py',
             'research_rag/tests/fixtures/atomic_cellfix14_member_absence.json']
    for name in extra:
        source = ROOT/'scripts'/('test_atomic_cellfix15.py' if name.endswith('.py') else 'fixtures/atomic_cellfix14_member_absence.json')
        (SOURCE/name).write_bytes(source.read_bytes())
    sys.path.insert(0, str(SOURCE))
    a = importlib.import_module('04_factchecker.inference.atomic_verifier')
    d = importlib.import_module('04_factchecker.inference.atomic_decoding')
    path = SOURCE/CRITERIA
    original = json.loads(path.read_bytes())
    criteria = json.loads(path.read_bytes())
    criteria.update(version=a.POLICY, policy=a.POLICY, structured_decoder=d.DECODER)
    # Prompts, model, dataset, score implementation and budgets remain inherited.
    assert criteria['prompt_sha256'] == {'decompose':digest(a.DECOMPOSE_PROMPT.encode()), 'assess':digest(a.ASSESS_PROMPT.encode())}
    criteria['source_sha256'] = {name:digest((SOURCE/name).read_bytes()) for name in list(criteria['source_sha256'])+extra}
    contract = json.loads((path.parent/criteria['contract_file']).read_bytes())
    contract.update(version='atomic-contract-constrained-v8-cellfix15', cellfix15={
        'assessment':'decoder and validator share member-local absence guard; preserve unknown',
        'evaluation':'exposed dev30 remains development; no model inference claim'})
    contract_path = path.parent/'atomic_verifier_contract_v8_cellfix15.json'
    contract_path.write_text(json.dumps(contract, indent=2)+'\n', encoding='utf-8')
    criteria.update(contract_file=contract_path.name, contract_sha256=digest(contract_path.read_bytes()))
    allowed = {'version','policy','structured_decoder','source_sha256','contract_file','contract_sha256'}
    assert all(criteria[k] == original[k] for k in original.keys()-allowed), 'Model/data/prompt/budget/gate changed'
    path.write_text(json.dumps(criteria, indent=2)+'\n', encoding='utf-8')
    names = sorted(set(parent['input_manifest'])|set(extra)|{contract_path.relative_to(SOURCE).as_posix()})
    report = dict(candidate=a.POLICY, source_root=str(SOURCE), parent_criteria_sha256=parent['criteria_sha256'],
        criteria_sha256=digest(path.read_bytes()), input_manifest={n:{'size':(SOURCE/n).stat().st_size,'sha256':digest((SOURCE/n).read_bytes())} for n in names},
        validation30_used_for_tuning=True, evaluation_role='development', new_model_inference_completed=False,
        independent_validation_completed=False, promoted_to_serving=False, parent_release_files=release['files'],
        model_budget_gold_gate_unchanged=True, prompts_unchanged=True)
    (ROOT/'docs/atomic-verifier-cellfix15-candidate.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'candidate':a.POLICY,'inputs':len(names),'criteria_sha256':report['criteria_sha256']}))


if __name__ == '__main__':
    build()
