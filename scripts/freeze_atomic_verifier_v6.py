"""Freeze v6 validator/repair prospectively; retain the preserved v5 experiment."""
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
    previous_path = EVAL / 'atomic_verifier_criteria_v5.json'
    release = json.loads((ROOT / 'docs/atomic-verifier-v5-colab-release.json').read_text())
    assert sha(previous_path) == release['criteria_sha256'], 'Original v5 criteria changed'
    preserved = json.loads((ROOT / 'docs/atomic-verifier-v5-preserved-before-v6.json').read_text())
    snapshot = Path(preserved['snapshot'])
    assert sha(snapshot / 'snapshot-manifest.json') == preserved['manifest_sha256']
    assert (snapshot / previous_path.relative_to(ROOT)).read_bytes() == previous_path.read_bytes()
    previous = json.loads(previous_path.read_text())
    criteria = deepcopy(previous)
    assert atomic.POLICY == 'atomic-verifier-constrained-v6'
    assert decoding.DECODER == previous['structured_decoder'], 'Decoder changes need a separate experiment'
    contract = json.loads((EVAL / previous['contract_file']).read_text())
    contract['version'] = 'atomic-contract-constrained-v6'
    contract['decomposition']['scope_rules'] += (
        ' A bare use/take/contain/evaluate predicate that drops its following object/quantity '
        'raises metric_predicate_incomplete and enters bounded repair. The exact clause-local '
        'predicate span is supplied in validation details. Named properties remain accepted; '
        'this lexical guard is not a full semantic parser.')
    contract_path = EVAL / 'atomic_verifier_contract_v6.json'
    save_once(contract_path, contract)
    sources = list(previous['source_sha256']) + ['research_rag/tests/test_atomic_metric_v6.py']
    criteria.update(version='atomic-verifier-constrained-v6-20261015', policy=atomic.POLICY,
                    contract_file=contract_path.name, contract_sha256=sha(contract_path),
                    source_sha256={name: sha(ROOT / name) for name in sources},
                    prompt_sha256={name: hashlib.sha256(prompt.encode()).hexdigest() for name, prompt in (
                        ('decompose', atomic.DECOMPOSE_PROMPT), ('assess', atomic.ASSESS_PROMPT))})
    assert criteria['prompt_sha256'] == previous['prompt_sha256'], 'Base prompts must stay fixed'
    criteria['limitations'].append(
        'Generic metric validation covers a finite lexical family and exact clause arguments. '
        'It does not establish semantic entailment; decoder enums are unchanged and repair may still exhaust two attempts.')
    versioned = {'version', 'policy', 'contract_file', 'contract_sha256', 'source_sha256', 'limitations'}
    assert all(criteria[k] == previous[k] for k in previous.keys() - versioned)
    target = EVAL / 'atomic_verifier_criteria_v6.json'
    save_once(target, criteria)
    from research_rag.evaluation.evaluate_atomic_verifier import load_frozen
    load_frozen(target)
    print(json.dumps({'version': criteria['version'], 'criteria_sha256': sha(target),
                      'frozen_sources': len(sources), 'decoder_unchanged': True,
                      'model_data_prompts_budgets_unchanged': True}))


if __name__ == '__main__':
    main()
