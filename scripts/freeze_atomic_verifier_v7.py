"""Freeze v7 metric validation/decoding after verifying the preserved v6 run."""
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
EVAL = ROOT / 'research_rag/evaluation'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_once(path, value):
    data = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError('Frozen version already exists with different bytes: ' + path.name)
    else:
        path.write_bytes(data)


def main():
    atomic = importlib.import_module('04_factchecker.inference.atomic_verifier')
    decoding = importlib.import_module('04_factchecker.inference.atomic_decoding')
    previous_path = EVAL / 'atomic_verifier_criteria_v6.json'
    release = json.loads((ROOT / 'docs/atomic-verifier-v6-colab-release.json').read_text())
    assert sha(previous_path) == release['criteria_sha256'], 'Original v6 criteria changed'
    preserved = json.loads((ROOT / 'docs/atomic-verifier-v6-preserved-before-v7.json').read_text())
    snapshot = Path(preserved['snapshot'])
    manifest_path = snapshot / 'snapshot-manifest.json'
    assert sha(manifest_path) == preserved['manifest_sha256']
    assert sha(Path(preserved['archive'])) == preserved['archive_sha256']
    for name, item in json.loads(manifest_path.read_text())['files'].items():
        raw = (snapshot / name).read_bytes()
        assert len(raw) == item['size'] and hashlib.sha256(raw).hexdigest() == item['sha256'], name
    assert (snapshot / previous_path.relative_to(ROOT)).read_bytes() == previous_path.read_bytes()
    assert preserved['validation']['v6_predictions_replayed'] == 18
    previous = json.loads(previous_path.read_text())
    criteria = deepcopy(previous)
    assert atomic.POLICY == 'atomic-verifier-constrained-v7'
    assert decoding.DECODER['policy'] == 'atomic-schema-decoding-v4'
    assert {k: v for k, v in decoding.DECODER.items() if k != 'policy'} == {
        k: v for k, v in previous['structured_decoder'].items() if k != 'policy'}
    contract = json.loads((EVAL / previous['contract_file']).read_text())
    assert (snapshot / 'research_rag/evaluation' / previous['contract_file']).read_bytes() == (EVAL / previous['contract_file']).read_bytes()
    contract['version'] = 'atomic-contract-constrained-v7'
    old_guard = ' A bare use/take/contain/evaluate predicate'
    assert old_guard in contract['decomposition']['scope_rules']
    contract['decomposition']['scope_rules'] = contract['decomposition']['scope_rules'].split(old_guard)[0] + (
        ' A source-derived clause-local rule requires the complete metric predicate for '
        'supported positive take-duration and contain/use/evaluate immediate count-plus-object '
        'forms. Validator and decoder use the same helper: neither a bare verb nor a '
        'quantity/object fragment satisfies that requirement. Named properties remain '
        'accepted. Structural failures enter bounded repair with the required source span. '
        'This finite grammar is not a complete semantic parser; other predicate meanings '
        'still require individual human review.')
    contract_path = EVAL / 'atomic_verifier_contract_v7.json'
    save_once(contract_path, contract)
    sources = list(previous['source_sha256']) + ['research_rag/tests/test_atomic_metric_v7.py']
    assert len(sources) == len(set(sources))
    criteria.update(version='atomic-verifier-constrained-v7-20261016', policy=atomic.POLICY,
                    structured_decoder=deepcopy(decoding.DECODER),
                    contract_file=contract_path.name, contract_sha256=sha(contract_path),
                    source_sha256={name: sha(ROOT / name) for name in sources},
                    prompt_sha256={name: hashlib.sha256(prompt.encode()).hexdigest() for name, prompt in (
                        ('decompose', atomic.DECOMPOSE_PROMPT), ('assess', atomic.ASSESS_PROMPT))})
    assert criteria['prompt_sha256'] == previous['prompt_sha256'], 'Base prompts must stay fixed'
    criteria['limitations'] = [value for value in criteria['limitations']
                              if not value.startswith('Generic metric validation covers a finite lexical family')]
    criteria['limitations'].append(
        'Complete metric predicate constraints cover only supported positive duration/count '
        'forms. Sharing this requirement with decoder enums prevents those fragments but '
        'does not establish semantic entailment or guarantee a passed probe. Two attempts '
        'and mandatory review of every actual prediction remain unchanged.')
    versioned = {'version', 'policy', 'structured_decoder', 'contract_file', 'contract_sha256',
                 'source_sha256', 'limitations'}
    assert all(criteria[k] == previous[k] for k in previous.keys() - versioned)
    target = EVAL / 'atomic_verifier_criteria_v7.json'
    save_once(target, criteria)
    from research_rag.evaluation.evaluate_atomic_verifier import load_frozen
    load_frozen(target)
    print(json.dumps({'version': criteria['version'], 'criteria_sha256': sha(target),
                      'frozen_sources': len(sources), 'decoder_policy': decoding.DECODER['policy'],
                      'model_data_prompts_budgets_unchanged': True, 'v6_snapshot_verified': True}))


if __name__ == '__main__':
    main()
