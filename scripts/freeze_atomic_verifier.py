"""Freeze schema-constrained decomposition v5 before inference; preserve v1/setup2/v2/v3/v4."""
import hashlib
import importlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
atomic = importlib.import_module('04_factchecker.inference.atomic_verifier')
EVAL = ROOT / 'research_rag/evaluation'
RUN = ROOT / 'research-runs/kaggle-20261012T165922Z'


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
    manifest = json.loads((RUN / 'output-manifest.json').read_text())
    for item in manifest['files']:
        path = (RUN / item['path']).resolve()
        assert path.is_relative_to(RUN) and sha(path) == item['sha256']
    provenance = json.loads((RUN / 'blind-verifier/provenance.json').read_text())
    baseline = {
        'source_run': '20261012T165922Z',
        'source_zip_sha256': '878bad4550f0364224325e5bdfec48a914a00e66e2f1c7a3725863dc7bca37ff',
        'comparison_scope': 'all_cases',
        'input_sha256': {name: sha(EVAL / file) for name, file in (
            ('original_contracts', 'factchecker_contract_cases.jsonl'),
            ('scope_regression', 'blind_verifier_scope_regression_cases.jsonl'))},
        'model_metadata': provenance['models']['base_instruct'],
        'predictions': [json.loads(line) for line in (RUN / 'blind-verifier/base_instruct.jsonl').read_text().splitlines()],
        'note': 'Audited historical inference; not rerun. Token budget/call policy differs in the atomic candidate.'}
    baseline_path = EVAL / 'atomic_verifier_logic_v3_baseline.json'
    save_once(baseline_path, baseline)
    sources = ('04_factchecker/inference/atomic_verifier.py', '04_factchecker/inference/numeric_verifier.py',
               '04_factchecker/inference/evidence_screen.py', '04_factchecker/inference/verifier.py',
               '04_factchecker/inference/judge.py', 'research_rag/evaluation/evaluate_atomic_verifier.py',
               'research_rag/evaluation/compare_blind_verifier.py', 'research_rag/evaluation/compare_factchecker.py',
               'research_rag/evaluation/compare_confidence_backends.py', 'research_rag/local.py',
               'requirements-orchestrator.txt', 'research_rag/tests/test_atomic_verifier.py',
               'research_rag/tests/test_atomic_experiment.py',
               '04_factchecker/inference/atomic_decoding.py', 'research_rag/tests/test_atomic_decoding.py',
               'requirements-atomic-verifier.txt', 'research_rag/tests/test_atomic_decomposition_v5.py')
    legacy = json.loads((EVAL / 'blind_verifier_logic_v3_criteria.json').read_text())
    criteria = {
        'version': 'atomic-verifier-constrained-v5-20261013', 'policy': atomic.POLICY,
        'structured_decoder': importlib.import_module('04_factchecker.inference.atomic_decoding').DECODER,
        'purpose': 'Frozen isolated candidate on 39 inspected development regressions; not independent held-out evaluation',
        'base_model': legacy['base_model'], 'base_revision': legacy['base_revision'],
        'backends': ['base_instruct'], 'seed': 42,
        'cases_per_backend': 39, 'dataset_groups': {'original_contracts': 12, 'scope_regression': 27},
        'contracts_sha256': sha(EVAL / 'factchecker_contract_cases.jsonl'),
        'supplemental_cases_file': 'blind_verifier_scope_regression_cases.jsonl',
        'supplemental_cases_sha256': sha(EVAL / 'blind_verifier_scope_regression_cases.jsonl'),
        'contract_file': 'atomic_verifier_contract_v5.json', 'contract_sha256': sha(EVAL / 'atomic_verifier_contract_v5.json'),
        'baseline_file': baseline_path.name, 'baseline_sha256': sha(baseline_path),
        'source_sha256': {name: sha(ROOT / name) for name in sources},
        'prompt_sha256': {name: hashlib.sha256(prompt.encode()).hexdigest() for name, prompt in (
            ('decompose', atomic.DECOMPOSE_PROMPT), ('assess', atomic.ASSESS_PROMPT))},
        'decomposition_probe': {
            'cases_file': 'decomposition_probe_claims_v2.jsonl',
            'cases_sha256': sha(EVAL / 'decomposition_probe_claims_v2.jsonl'),
            'max_calls_per_case': 2, 'maximum_total_backend_calls': 36,
            'maximum_generated_tokens': 55296, 'process_timeout_seconds': 2400,
            'minimum_valid_decompositions': 18,
            'human_review_rubric': ['factual_predicates_not_fragments', 'all_requirements_preserved',
                'quantifier_preserved', 'entity_metric_binding_correct', 'time_condition_scope_correct'],
            'human_review_acceptance': '18/18 structural pass AND all five judgments true for each claim, with human reviewer and per-claim notes before 39 cases',
            'dataset_status': '18 unique claims from the inspected 39 development cases; not independent held-out data'},
        'max_calls_per_case': 8, 'max_attempts': 2, 'max_new_tokens': 1536,
        'case_deadline_seconds': 180, 'process_timeout_seconds': 5400,
        'maximum_total_backend_calls': 312, 'maximum_generated_tokens': 479232,
        'min_correct_labels_recognized': 39, 'max_false_support': 0, 'max_runtime_failed_rows': 0,
        'human_review_rubric': legacy['human_review_rubric'], 'human_review_required': True,
        'human_review_acceptance': 'All applicable rubric items true for every one of the 39 cases; independent reviewer required before integration',
        'promotion': 'Never automatic; semantic evidence and independent evaluation required before integration',
        'limitations': [
            'All 39 synthetic cases have been inspected and used for development. Independent annotation is pending.',
            'Code validates structure/quotes/arithmetic; semantic decomposition, association and population completeness still depend on the model.',
            'Candidate changes prompting, call count, output contract and token budget together; improvements cannot be attributed to one change.',
            'Per-case deadline rejects late output; outer process deadline interrupts blocking calls and includes model loading/downloads.',
            'More than seven parts or repeated repairs may exhaust the eight-call case budget; incomplete results fail the gate.',
            'English AND/simple numerical grammar can reject valid evidence. Gold-support rejection is reported.',
            'Decomposition is limited to English AND and simple temporal/dataset phrases. A claim without AND is kept as one complete quote, which does not prove semantic atomicity.',
            'Cost USD is unavailable; actual calls/latency and available generation token counts are recorded.',
            'Shared backend adds a default-empty generation hook; constrained decoding is enabled only by the isolated atomic loader, not serving.',
            'Schema decoding prevents many formatting/source/quantifier errors; semantic entailment, binding and coverage still require validation/review. Token limits can truncate JSON.',
            'Constrained source enums cover at most 80 whitespace-separated claim words; longer claims stop with an explicit backend error.',
            'No serving integration, Reader requests or automatic promotion in this experiment.']}
    save_once(EVAL / 'atomic_verifier_criteria_v5.json', criteria)
    print('Frozen:', criteria['version'], 'max calls:', criteria['maximum_total_backend_calls'])


if __name__ == '__main__':
    main()
