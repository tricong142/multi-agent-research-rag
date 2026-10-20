"""Prepare v8 freeze; an emitted Colab release makes its bytes immutable."""
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


def save(path, value):
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
    if path.exists() and path.read_bytes() != raw and (ROOT / 'docs/atomic-verifier-v8-colab-release.json').exists():
        raise ValueError('Released v8 is immutable; create a new candidate instead: ' + path.name)
    path.write_bytes(raw)


def main():
    a = importlib.import_module('04_factchecker.inference.atomic_verifier')
    d = importlib.import_module('04_factchecker.inference.atomic_decoding')
    preserved = json.loads((ROOT / 'docs/atomic-verifier-v7-preserved-before-next-candidate.json').read_text())
    snapshot = Path(preserved['snapshot'])
    assert sha(snapshot / 'snapshot-manifest.json') == preserved['manifest_sha256']
    assert sha(Path(preserved['archive'])) == preserved['archive_sha256']
    for name, item in json.loads((snapshot / 'snapshot-manifest.json').read_text())['files'].items():
        assert (snapshot / name).stat().st_size == item['size'] and sha(snapshot / name) == item['sha256'], name
    previous_path = EVAL / 'atomic_verifier_criteria_v7.json'
    assert sha(previous_path) == preserved['criteria_sha256']
    previous = json.loads(previous_path.read_text())
    assert a.POLICY == 'atomic-verifier-constrained-v8' and d.DECODER['policy'] == 'atomic-schema-decoding-v5'
    contract = deepcopy(json.loads((EVAL / previous['contract_file']).read_text()))
    contract.update(version='atomic-contract-constrained-v8')
    contract['assessment']['limits'] = dict(a.ASSESSMENT_LIMITS)
    contract['assessment']['numeric_records'] += (
        ' Definitive observations missing required numeric records enter bounded repair instead of valid NEI. '
        'A proved false requirement may refute without checking the remaining conjuncts. '
        'Unknown associations remain unknown. Population counts alone do not force measurement arithmetic.')
    contract['numeric']['binding'] = (
        'Named properties keep literal metric binding. Supported complete take/contain/use/evaluate '
        'predicates bind the same verb family to the observed quantity, permitting exactly. '
        'No relation is established merely by matching a number or unit.')
    contract['numeric']['explicit_denial'] = (
        'A grounded positive observed X followed by not claimed Y refutes an exact, unqualified '
        'claim. Other negation, thresholds, hypothetical context and implicit unit conversion remain unsupported.')
    contract['decoding']['assessment'] = (
        'Exact source sentence/adjacent-sentence enums and bounded windows for long sentences '
        '(384 chars), exact member spans (up to eight words/160 chars), source-derived decimal/unit/quote '
        'operand alternatives, bounded prose/arrays. Validator still checks citation, requirement '
        'coverage and arithmetic; schema does not establish semantic entailment.')
    contract['deadline'] = (
        'Absolute monotonic case deadline forwarded through RecordingBackend to a per-decode-step '
        'Transformers stopping criterion. Late parsed or invalid JSON is rejected with deadline_exceeded; '
        'partial generation and call logs are retained. Preparation checks the same deadline. '
        'This is cooperative and cannot interrupt a hung CUDA kernel; the hard process watchdog remains.')
    contract_path = EVAL / 'atomic_verifier_contract_v8.json'
    save(contract_path, contract)
    criteria = deepcopy(previous)
    names = list(previous['source_sha256']) + [
        'research_rag/tests/test_atomic_assessment_v8.py',
        'research_rag/tests/fixtures/atomic_v8_v7_assessments.json']
    criteria.update(version='atomic-verifier-constrained-v8-20261017', policy=a.POLICY,
        structured_decoder=deepcopy(d.DECODER), contract_file=contract_path.name,
        contract_sha256=sha(contract_path), source_sha256={name: sha(ROOT / name) for name in names},
        prompt_sha256={key: hashlib.sha256(value.encode()).hexdigest() for key, value in (
            ('decompose', a.DECOMPOSE_PROMPT), ('assess', a.ASSESS_PROMPT))}, require_cooperative_deadline=True,
        assessment_smoke={'case_ids': [json.loads(line)['example_id'] for line in
            (EVAL / 'factchecker_contract_cases.jsonl').read_text().splitlines() if line.strip()],
            'process_timeout_seconds': 2400,
            'purpose': 'All 12 original inspected development contracts, not independent validation or full39 admission.'})
    assert criteria['prompt_sha256']['decompose'] == previous['prompt_sha256']['decompose']
    versioned = {'version', 'policy', 'structured_decoder', 'contract_file', 'contract_sha256',
                 'source_sha256', 'prompt_sha256', 'limitations'}
    assert all(criteria[key] == previous[key] for key in previous.keys() - versioned)
    criteria['limitations'] = [value for value in previous['limitations'] if not value.startswith('Per-case deadline rejects')]
    criteria['limitations'] += [
        contract['deadline'],
        'Assessment context is capped at 600 words before any model call. Source passage choices '
        'are bounded to 384 characters, member spans to eight words/160 characters, explanation '
        'to 128 characters and missing information to four 160-character items. Unsupported '
        'context stops explicitly; finite arrays may still exceed the unchanged token budget.',
        'V8 fixes assessment/repair/numeric/deadline together. No new model inference, human '
        'approval, independent validation or production readiness is implied by local regression.',
        'The 12-case assessment smoke is an additional development diagnostic. It does not '
        'replace the fresh 18-claim probe review or the mandatory full39 gate.']
    target = EVAL / 'atomic_verifier_criteria_v8.json'
    save(target, criteria)
    from research_rag.evaluation.evaluate_atomic_verifier import load_frozen, smoke_configuration
    frozen, cases, *_ = load_frozen(target)
    smoke, selected = smoke_configuration(frozen, cases)
    assert len(selected) == 12 and smoke['maximum_total_backend_calls'] == 96
    result = {'version': frozen['version'], 'criteria_sha256': sha(target), 'frozen_files': len(names),
              'v7_snapshot_verified': True, 'model_revision_data_and_budgets_unchanged': True,
              'fresh_gpu_inference_completed': False, 'human_review': 'pending', 'promoted_to_serving': False}
    save(ROOT / 'docs/atomic-verifier-v8-freeze.json', result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
