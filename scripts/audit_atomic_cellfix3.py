"""Audit the received cellfix3 smoke archive without running model inference."""
import collections
import hashlib
import importlib
import io
import json
from pathlib import Path, PurePosixPath
import sys
import zipfile

REPO = Path(__file__).resolve().parents[1]
RUN = '20261017T101839Z-a9590fe1'
ARCHIVE = Path.home() / 'Downloads' / ('output-cellfix3-fresh-' + RUN + '.zip')
BASE = REPO / 'research-runs' / ('audit-cellfix3-fresh-' + RUN)
ROOT, OUT = BASE / 'workspace', BASE / 'artifact'
sha = lambda b: hashlib.sha256(b).hexdigest()


def extract(archive, target):
    names = archive.namelist()
    assert archive.testzip() is None and len(names) == len(set(names))
    for name in names:
        rel = PurePosixPath(name)
        assert not rel.is_absolute() and '..' not in rel.parts and '\\' not in name
        path = (target / rel).resolve()
        assert path.is_relative_to(target.resolve())
        path.parent.mkdir(parents=True, exist_ok=True)
        data = archive.read(name)
        if path.exists():
            assert path.read_bytes() == data, 'Existing audit file differs: ' + name
        else:
            path.write_bytes(data)
    return names


def main():
    with zipfile.ZipFile(ARCHIVE) as archive:
        manifest = json.loads(archive.read('output-manifest.json'))
        assert manifest['run_id'] == RUN
        assert set(archive.namelist()) == {r['path'] for r in manifest['files']} | {'output-manifest.json'}
        for r in manifest['files']:
            data = archive.read(r['path'])
            assert len(data) == r['size'] and sha(data) == r['sha256'], r['path']
        names = extract(archive, OUT)
        payload = archive.read('frozen-inputs.zip')
        inputs = json.loads(archive.read('input-manifest.json'))
    release = json.loads((REPO / 'docs/atomic-verifier-cellfix3-fresh-colab-release.json').read_text())
    assert inputs == release['payload_files'] and sha(payload) == release['payload_sha256']
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert set(archive.namelist()) == set(inputs)
        extract(archive, ROOT)
    for name, item in inputs.items():
        data = (ROOT / name).read_bytes()
        assert len(data) == item['size'] and sha(data) == item['sha256'], name

    read = lambda n: json.loads((OUT / n).read_text(encoding='utf-8'))
    lines = lambda n: [json.loads(s) for s in (OUT / n).read_text(encoding='utf-8').splitlines()]
    sys.path.insert(0, str(ROOT))
    e = importlib.import_module('research_rag.evaluation.evaluate_atomic_verifier')
    criteria_path = ROOT / 'research_rag/evaluation/atomic_verifier_criteria_v8.json'
    frozen, all_cases, data_inputs, contract, _, baseline, baseline_metrics = e.load_frozen(criteria_path)
    effective, cases = e.smoke_configuration(frozen, all_cases)
    assert cases == read('assessment-smoke/cases.json')
    assert baseline == read('assessment-smoke/baseline.json')
    assert baseline_metrics == read('assessment-smoke/baseline-metrics.json')
    for name, path in data_inputs.items():
        assert (OUT / ('assessment-smoke/' + name + '.jsonl')).read_bytes() == path.read_bytes()
    assert (OUT / 'assessment-smoke/contract.json').read_bytes() == contract.read_bytes()
    assert (OUT / 'assessment-smoke/criteria.json').read_bytes() == criteria_path.read_bytes()
    assert sha(criteria_path.read_bytes()) == release['criteria_sha256']
    provenance = read('assessment-smoke/provenance.json')
    assert provenance['criteria_sha256'] == release['criteria_sha256']
    assert provenance['source_sha256'] == frozen['source_sha256']
    assert provenance['prompt_sha256'] == frozen['prompt_sha256']
    model = provenance['model']
    keys = ('model_files','shared_tokenizer_files','repo_id','revision','dtype','quantization','seed','do_sample')
    pairing = {k: model[k] == baseline['model_metadata'][k] for k in keys}
    assert all(pairing.values()) and pairing == provenance['historical_model_pairing']
    assert model['repo_id'] == frozen['base_model'] and model['revision'] == frozen['base_revision']
    assert model['structured_decoder'] == frozen['structured_decoder']
    assert model['max_new_tokens'] == frozen['max_new_tokens'] and model['seed'] == frozen['seed']

    rows = lines('assessment-smoke/predictions.jsonl')
    metrics = e.score(rows, cases, effective)  # Includes exact decision replay.
    events = lines('assessment-smoke/calls.jsonl')
    starts = [r for r in events if r['event'] == 'call_started']
    gens = [r for r in events if r['event'] == 'generation']
    finishes = [r for r in events if r['event'] == 'call_finished']
    traces = [(r['example_id'], t) for r in rows for t in r['result']['trace']]
    assert len(starts) == len(gens) == len(finishes) == len(traces) == 29
    issues = collections.Counter()
    citations = numeric = 0
    for i, ((cid, t), start, gen, finish) in enumerate(zip(traces, starts, gens, finishes), 1):
        assert start['call_id'] == gen['call_id'] == finish['call_id'] == i
        assert start['example_id'] == gen['example_id'] == finish['example_id'] == cid
        assert start['messages'] == t['messages']
        assert gen['json_valid'] is True
        assert json.loads(gen['raw_output']) == finish['parsed_output'] == t['output']
        assert start['max_new_tokens'] == gen['max_new_tokens'] == finish['max_new_tokens'] == frozen['max_new_tokens']
        p = json.loads(t['messages'][1]['content'])
        try:
            if t['stage'] == 'decompose':
                e.atomic.normalize_decomposition(t['output'], p['claim'])
            else:
                e.atomic.assess_part(t['output'], p['part'], p['context'])
        except ValueError as exc:
            assert str(exc) == t['validation_issue'], (cid, str(exc))
        else:
            assert t.get('valid') is True
        issues[t.get('validation_issue', 'valid')] += 1
        if t['stage'] != 'decompose':
            for obs in t['output']['observations']:
                assert obs['member'] in p['context']
                for quote in obs['quotes']:
                    assert quote in p['context']
                    citations += 1
                records = obs['numeric'] if isinstance(obs['numeric'], list) else [obs['numeric']] if obs['numeric'] else []
                for record in records:
                    assert record['source_quote'] in p['context']
                    assert record['right']['quote'] in record['source_quote']
                    assert record['left']['quote'] in p['part']['quote'] or record['kind'] == 'change'
                    numeric += 1
    metrics['generated_tokens'] = sum(g['generated_tokens'] for g in gens)
    metrics['prompt_tokens'] = sum(g['prompt_tokens'] for g in gens)
    metrics['checks']['within_measured_token_budget'] = metrics['generated_tokens'] <= effective['maximum_generated_tokens'] and all(g['generated_tokens'] <= frozen['max_new_tokens'] for g in gens)
    metrics['checks']['structured_decoding_trace_complete'] = e.decoding_trace_complete(gens, [t['messages'] for _, t in traces], frozen)
    metrics['checks']['cooperative_deadline_trace_complete'] = all(t['cooperative_deadline'] for _, t in traces)
    metrics['automated_gate_pass'] = all(metrics['checks'].values())
    assert metrics == read('assessment-smoke/metrics.json')
    reviews = lines('assessment-smoke/evidence-review.jsonl')
    for case, row, review in zip(cases, rows, reviews):
        assert row['example_id'] == review['example_id'] == case['example_id']
        assert row['result'] == review['result']
        assert review['review_status'] == 'pending' and review['reviewer'] == ''
        assert all(v is None for v in review['judgments'].values())
    stages = read('status.json')
    for name, status in stages.items():
        assert status['exit_code'] == (1 if name == 'assessment-smoke' else 0), name
    log = (OUT/'regression.stderr.log').read_text(encoding='utf-8')
    assert 'Ran 153 tests' in log and log.rstrip().endswith('OK')
    validations = {}
    for name, count, calls in (('probe',18,36),('smoke',12,96),('verifier',39,312)):
        validations[name] = read(name+'-validate-only.stdout.log')
        assert validations[name] == {'freeze_valid': True, 'cases': count, 'maximum_calls': calls}
    report = {
        'run_id': RUN, 'zip_sha256': sha(ARCHIVE.read_bytes()),
        'archive_files': len(names), 'all_output_hashes_valid': True,
        'all_input_bytes_match_released_payload': True, 'input_files': len(inputs),
        'frozen_source_files': len(frozen['source_sha256']),
        'criteria_sha256': release['criteria_sha256'], 'load_frozen_passed': True,
        'all_predictions_replayed': True, 'all_29_call_triplets_match_raw_and_trace': True,
        'metrics_recomputed_exactly': True, 'model_pairing': pairing, 'metrics': metrics,
        'stage_issues': dict(issues), 'exact_source_citations_checked': citations,
        'colab_recorded_regression_tests_passed': 153, 'colab_validate_only': validations,
        'source_grounded_numeric_records_checked': numeric,
        'per_case': [{'example_id': r['example_id'], 'gold': c['label'],
            'prediction': r['result']['assessed_label'], 'stop_reason': r['result']['stop_reason'],
            'issues': [t['validation_issue'] for t in r['result']['trace'] if t.get('validation_issue')]}
            for c, r in zip(cases, rows)],
        'new_gpu_inference_during_audit': False, 'human_review': 'pending',
        'probe18_current_candidate': None, 'full39_current_candidate': None,
        'promoted_to_serving': False,
        'limitations': ['Hashes verify consistency with the local frozen release, not remote execution authenticity.',
            '12 development smoke cases are not independent evaluation or full39 evidence.'],
    }
    path = REPO / 'docs' / ('atomic-verifier-cellfix3-smoke-audit-' + RUN + '.json')
    path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'report': str(path), 'metrics': metrics, 'stage_issues': dict(issues)}, indent=2))


if __name__ == '__main__':
    main()
