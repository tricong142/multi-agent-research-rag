"""Post-hoc evidence screening of frozen recorded output; zero model calls."""
from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path

from .compare_blind_verifier import score
from .compare_confidence_backends import sha256, write_json

screen = importlib.import_module('04_factchecker.inference.evidence_screen')
verifier = importlib.import_module('04_factchecker.inference.verifier')
ROOT = Path(__file__).resolve().parents[2]


def run_screen(run_dir: Path, output_dir: Path) -> dict:
    """Gold is used for scoring after the screen, never as its argument."""
    run_dir, output_dir = run_dir.resolve(), output_dir.resolve()
    if output_dir == run_dir or run_dir in output_dir.parents:
        raise ValueError('Keep screening output outside the original recorded run')
    manifest = json.loads((run_dir / 'output-manifest.json').read_text(encoding='utf-8'))
    for row in manifest['files']:
        path = (run_dir / row['path']).resolve()
        if not path.is_relative_to(run_dir) or path.stat().st_size != row['size'] or sha256(path) != row['sha256']:
            raise ValueError('Recorded artifact differs from its output manifest')
    source = run_dir / 'blind-verifier'
    cases = json.loads((source / 'cases.json').read_text(encoding='utf-8'))
    criteria = json.loads((source / 'criteria.json').read_text(encoding='utf-8'))
    predictions = [json.loads(s) for s in (source / 'base_instruct.jsonl').read_text(encoding='utf-8').splitlines()]
    if [r['example_id'] for r in predictions] != [r['example_id'] for r in cases]:
        raise ValueError('Recorded predictions do not match the ordered cases')
    metrics, _ = score(predictions, cases, criteria)
    if metrics != json.loads((source / 'metrics.json').read_text(encoding='utf-8'))['base_instruct']:
        raise ValueError('Recorded classification metrics do not reproduce')
    rows = []
    supports = cleared = false_cleared = blocked_correct = blocked_false = 0
    for case, prediction in zip(cases, predictions):
        decision = verifier.validate_verification(prediction['verification'], case['context']) if prediction['status'] == 'ok' else None
        result = screen.screen_support(case['claim'], case['context'], decision) if decision else {
            'policy': screen.POLICY, 'status': 'verification_failed', 'flags': [], 'numeric_checks': [], 'claim_verified': False}
        if decision and decision.assessed_label == 'support':
            supports += 1
            if result['status'] == 'screen_clear':
                cleared += 1
                false_cleared += case['label'] != 'support'
            else:
                blocked_correct += case['label'] == 'support'
                blocked_false += case['label'] != 'support'
        rows.append({'example_id': case['example_id'], 'claim': case['claim'], 'context': case['context'],
                     'gold_label': case['label'], 'original_verification': prediction['verification'],
                     'screen': result, 'human_review': 'pending'})
    result = {'policy': screen.POLICY, 'experiment': 'post_hoc_offline_diagnostic', 'case_count': len(cases),
              'original_correct_labels': metrics['correct_labels_recognized'],
              'original_false_support': metrics['false_support'], 'candidate_support_count': supports,
              'screen_clear_support_count': cleared, 'false_support_remaining_after_screen': false_cleared,
              'false_support_flagged': blocked_false, 'gold_support_flagged': blocked_correct,
              'gold_support_total': sum(r['label'] == 'support' for r in cases),
              'original_automated_gate_pass': metrics['automated_gate_pass'],
              'human_review': 'pending', 'overall_pass': False, 'promoted_to_serving': False,
              'model_calls': 0, 'cost_usd': None,
              'limitations': ['Screening rules were developed after inspecting this run; this is not a prospective quality measurement.',
                             'Gold support is a dataset label, not an independent semantic review of model evidence.',
                             'A clear screen is not verified entailment. Unmatched numeric grammar and lexical synonyms need review.',
                             'The original labels and 39/39 classification gate are unchanged. Filtering false supports does not repair classification.',
                             'This screen is not enabled in serving; human and independent review remain required.']}
    output_dir.mkdir(parents=True, exist_ok=False)
    write_json(output_dir / 'summary.json', result)
    write_json(output_dir / 'provenance.json', {'original_output_manifest_sha256': sha256(run_dir / 'output-manifest.json'),
        'recorded_prediction_sha256': sha256(source / 'base_instruct.jsonl'),
        'recorded_criteria_sha256': sha256(source / 'criteria.json'),
        'source_sha256': {name: sha256(ROOT / name) for name in (
            '04_factchecker/inference/evidence_screen.py', 'research_rag/evaluation/screen_blind_verifier.py')}})
    with (output_dir / 'screen-review.jsonl').open('x', encoding='utf-8') as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run_screen(args.run_dir, args.output_dir), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
