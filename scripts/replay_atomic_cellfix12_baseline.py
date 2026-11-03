"""Replay saved ledgers against cf12 guards; this never creates predictions."""
from collections import Counter
import difflib
import importlib
import json
from pathlib import Path
import sys

from scripts.atomic_validation_review import digest, json_bytes

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'research-runs/audit-cellfix11-full39-20261026T150123Z-615bf4eb'
SOURCE = ROOT/'research-runs/atomic-cellfix12-candidate/workspace'
sys.path.insert(0, str(SOURCE))


def main():
    a = importlib.import_module('04_factchecker.inference.atomic_verifier')
    candidate = json.loads((ROOT/'docs/atomic-verifier-cellfix12-candidate.json').read_bytes())
    preserved = json.loads((ROOT/'docs/atomic-verifier-cellfix11-preserved-before-cellfix12.json').read_bytes())
    assert digest((BASE/'original-output.zip').read_bytes()) == preserved['zip_sha256']
    assert digest((BASE/'artifact/verifier39/predictions.jsonl').read_bytes()) == preserved['predictions_sha256']
    for name, expected in preserved['parent_release_files'].items():
        assert digest((ROOT/name).read_bytes()) == expected, name
    for name, expected in preserved['baseline_outputs_sha256'].items():
        assert digest((BASE/'artifact'/name).read_bytes()) == expected, name
    for name, expected in preserved['validation30_files_sha256'].items():
        assert digest((ROOT/'docs/validation/atomic-cellfix6-v1'/name).read_bytes()) == expected, name
    entries = []
    for raw in (BASE/'artifact/verifier39/predictions.jsonl').read_bytes().splitlines():
        row = json.loads(raw)
        for trace in row['result']['trace']:
            if trace['stage'] == 'decompose':
                continue
            payload = json.loads(trace['messages'][1]['content'])
            try:
                result = a.assess_part(trace['output'], payload['part'], payload['context'])
                entry = {'accepted': True, 'replayed_label': result['assessed_label']}
            except ValueError as exc:
                entry = {'accepted': False, 'rejection': str(exc)}
            entries.append({'example_id': row['example_id'], 'part': payload['part']['quote'], **entry})
    rejected = [entry for entry in entries if not entry['accepted']]
    expected = {'scope:entity:support','scope:entity:contradict','scope:condition:not_enough_info'}
    assert expected <= {entry['example_id'] for entry in rejected}, rejected
    folder = ROOT/'docs/reviews/cellfix12-development'
    folder.mkdir(parents=True, exist_ok=True)
    report = {'candidate': candidate['candidate'], 'criteria_sha256': candidate['criteria_sha256'],
        'parent_run': preserved['run_id'], 'saved_assessments': len(entries),
        'outcomes': dict(Counter('accepted' if v['accepted'] else 'rejected' for v in entries)),
        'entries': entries, 'additional_rejections': [v for v in rejected if v['example_id'] not in expected],
        'baseline_and_release_preserved': True,
        'new_predictions_created': False, 'new_model_inference': False, 'validation30_used_for_tuning': False}
    (folder/'BASELINE_TRACE_REPLAY.json').write_bytes(json_bytes(report))
    parent = BASE/'workspace'
    diffs = []
    for name in candidate['input_manifest']:
        if not name.startswith('04_factchecker/inference/') or not name.endswith('.py'):
            continue
        old = (parent/name).read_text(encoding='utf-8')
        new = (SOURCE/name).read_text(encoding='utf-8')
        if old != new:
            diffs.extend(difflib.unified_diff(old.splitlines(True), new.splitlines(True), fromfile='cellfix11/'+name, tofile='cellfix12/'+name))
    (folder/'CODE_DIFF.patch').write_text(''.join(diffs), encoding='utf-8')
    print(json.dumps({k: v for k,v in report.items() if k != 'entries'}))


if __name__ == '__main__':
    main()
