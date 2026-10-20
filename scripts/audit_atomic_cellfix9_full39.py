"""Audit the received cf9 full39 archive, without weights or new inference."""
from collections import Counter
import importlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import zipfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts.audit_atomic_cellfix3 import extract
from scripts.atomic_validation_review import digest, json_bytes, write_once

RUN = '20261020T110710Z-cf47db2f'
BASE = REPO / 'research-runs' / ('audit-cellfix9-full39-' + RUN)
OUT, SOURCE = BASE / 'artifact', BASE / 'workspace'


def read(name):
    return json.loads((OUT / name).read_bytes())


def lines(name):
    return [json.loads(v) for v in (OUT / name).read_bytes().splitlines()]


def main():
    raw = (REPO.parent / f'output-cellfix9-fresh-{RUN} (3).zip').read_bytes()
    write_once(BASE / 'original-output.zip', raw)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        manifest = json.loads(z.read('output-manifest.json'))
        assert manifest['run_id'] == RUN
        names = [v['path'] for v in manifest['files']]
        assert len(names) == len(set(names))
        assert set(z.namelist()) == set(names) | {'output-manifest.json'}
        for item in manifest['files']:
            blob = z.read(item['path'])
            assert digest(blob) == item['sha256'] and len(blob) == item['size'], item['path']
        extract(z, OUT)
    release = json.loads((REPO / 'docs/atomic-verifier-cellfix9-release.json').read_bytes())
    for name, expected in release['files'].items():
        assert digest((REPO / name).read_bytes()) == expected, name
    payload = (OUT / 'frozen-inputs.zip').read_bytes()
    inputs = read('input-manifest.json')
    assert digest(payload) == release['payload_sha256'] and inputs == release['payload_files']
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        assert set(z.namelist()) == set(inputs)
        extract(z, SOURCE)
    for name, item in inputs.items():
        blob = (SOURCE / name).read_bytes()
        assert len(blob) == item['size'] and digest(blob) == item['sha256'], name
    notebook = read('notebook-provenance.json')
    for key in ('candidate', 'criteria_sha256', 'payload_sha256'):
        assert notebook[key] == release[key]
    parent_raw = (REPO.parent / f'output-cellfix9-fresh-{RUN}.zip').read_bytes()
    write_once(BASE / 'probe-parent-output.zip', parent_raw)
    with zipfile.ZipFile(io.BytesIO(parent_raw)) as z:
        assert json.loads(z.read('output-manifest.json'))['run_id'] == RUN
        for name in z.namelist():
            if name not in ('status.json', 'output-manifest.json'):
                assert z.read(name) == (OUT / name).read_bytes(), name
    for path in (OUT / 'decomposition-probe').iterdir():
        if path.name != 'semantic-review.json':
            assert path.read_bytes() == (OUT / 'reviewed-probe' / path.name).read_bytes()

    sys.path.insert(0, str(SOURCE))
    spec = importlib.util.spec_from_file_location('cf9_audit_workflow', SOURCE / 'atomic_workflow_cellfix9.py')
    w = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w)
    r = w.r
    assert Path(r.__file__).resolve().is_relative_to(SOURCE)
    frozen, all_cases, data, contract, _, baseline, baseline_metrics = r.load_frozen(r.CRITERIA)
    assert r.sha256(r.CRITERIA) == release['criteria_sha256']
    assert w.binding(SOURCE / 'validation/cellfix9') == read('validation-lock.json')
    for remote, local in [('validation-annotation-review.json', 'annotation-review.json'),
                           ('validation-original-lock.json', 'original-lock.json')]:
        assert (OUT / remote).read_bytes() == (SOURCE / 'validation/cellfix9' / local).read_bytes()
    admission = r.require_probe_review(OUT / 'reviewed-probe')
    assert admission == read('verifier39/probe-admission.json')
    review = read('reviewed-probe/semantic-review.json')
    assert review['reviewer_kind'] == 'human' and review['review_completed'] is True
    assert len(review['cases']) == 18 and sum(len(c['judgments']) for c in review['cases']) == 90
    for c in review['cases']:
        assert all(v is True for v in c['judgments'].values()) and c['notes'].strip()

    reports = {}
    records = importlib.import_module('04_factchecker.inference.assessment_decisions').numeric_records
    for folder in ('assessment-smoke', 'decomposition-probe', 'verifier39'):
        probe = folder == 'decomposition-probe'
        if probe:
            effective, cases, path = r.probe_configuration(frozen, all_cases, r.CRITERIA)
            sources = {'probe-claims': path}
        else:
            effective, cases = r.smoke_configuration(frozen, all_cases) if folder == 'assessment-smoke' else (frozen, all_cases)
            sources = data
        assert read(folder + '/cases.json') == cases
        assert read(folder + '/baseline.json') == baseline and read(folder + '/baseline-metrics.json') == baseline_metrics
        assert (OUT / folder / 'criteria.json').read_bytes() == r.CRITERIA.read_bytes()
        assert (OUT / folder / 'contract.json').read_bytes() == contract.read_bytes()
        for name, path in sources.items():
            assert (OUT / folder / (name + '.jsonl')).read_bytes() == path.read_bytes()
        provenance = read(folder + '/provenance.json')
        assert provenance['criteria_sha256'] == release['criteria_sha256']
        assert provenance['source_sha256'] == frozen['source_sha256'] and provenance['prompt_sha256'] == frozen['prompt_sha256']
        assert provenance['serving_modified'] is False
        for key in ('model_files', 'shared_tokenizer_files', 'repo_id', 'revision', 'dtype', 'quantization', 'seed', 'do_sample'):
            assert provenance['model'][key] == baseline['model_metadata'][key], key
        assert provenance['model']['structured_decoder'] == frozen['structured_decoder']
        assert provenance['model']['max_new_tokens'] == frozen['max_new_tokens']
        outputs, events = lines(folder + '/predictions.jsonl'), lines(folder + '/calls.jsonl')
        assert [v['example_id'] for v in outputs] == [v['example_id'] for v in cases]
        traces = [(v['example_id'], t) for v in outputs for t in v['result']['trace']]
        starts = [e for e in events if e['event'] == 'call_started']
        gens = [e for e in events if e['event'] == 'generation']
        finishes = [e for e in events if e['event'] == 'call_finished']
        assert len(traces) == len(starts) == len(gens) == len(finishes)
        issues = Counter()
        citations = numerics = additions = 0
        for i, ((case_id, t), start, gen, finish) in enumerate(zip(traces, starts, gens, finishes), 1):
            assert start['call_id'] == gen['call_id'] == finish['call_id'] == i
            assert start['example_id'] == gen['example_id'] == finish['example_id'] == case_id
            assert start['messages'] == finish['messages'] == t['messages']
            assert start['max_new_tokens'] == gen['max_new_tokens'] == finish['max_new_tokens'] == t['max_new_tokens'] == frozen['max_new_tokens']
            assert gen['json_valid'] is True and gen['parse_error_type'] is None
            assert json.loads(gen['raw_output']) == finish['parsed_output'] == t['output']
            request = json.loads(t['messages'][1]['content'])
            before = json.dumps(t['output'], sort_keys=True)
            try:
                if t['stage'] == 'decompose':
                    r.atomic.normalize_decomposition(t['output'], request['claim'])
                else:
                    checked = r.atomic.assess_part(t['output'], request['part'], request['context'])
                    for obs in checked['observations']:
                        assert all(q in request['context'] for q in obs['quotes'])
                        citations += len(obs['quotes'])
                        additions += len(obs['citation_additions'])
                        for record in records(obs['numeric'], checked['numeric_requirements']):
                            assert record['source_quote'] in request['context']
                            assert record['right']['quote'] in record['source_quote']
                            assert record['left']['quote'] in request['part']['quote'] or record['kind'] == 'change'
                            numerics += 1
            except ValueError as exc:
                assert str(exc) == t.get('validation_issue'), (case_id, str(exc))
            else:
                assert t['valid'] is True and not t.get('validation_issue')
            assert json.dumps(t['output'], sort_keys=True) == before
            issues[t.get('validation_issue') or 'valid'] += 1
        if probe:
            score = r.score_probe(outputs, cases, effective)
            score['generated_tokens'] = sum(g['generated_tokens'] for g in gens)
            score['prompt_tokens'] = sum(g['prompt_tokens'] for g in gens)
            score['checks']['within_measured_token_budget'] = (score['generated_tokens'] <= effective['maximum_generated_tokens']
                and all(g['generated_tokens'] <= frozen['max_new_tokens'] for g in gens))
            score['checks']['structured_decoding_trace_complete'] = r.decoding_trace_complete(gens, [t['messages'] for _, t in traces], frozen)
            score['checks']['cooperative_deadline_trace_complete'] = all(t.get('cooperative_deadline') is True for _, t in traces)
            score['automated_gate_pass'] = all(score['checks'].values())
        else:
            score = w.measured_score(outputs, cases, effective, events)
        assert score == read(folder + '/metrics.json')
        summary = read(folder + '/summary.json')
        assert summary['experiment_completed'] is True and summary['prediction_count'] == len(cases)
        assert summary['backend_calls'] == len(traces) == score['backend_calls']
        assert summary['automated_gate_pass'] == score['automated_gate_pass']
        assert summary['overall_pass'] is False and summary['human_review'] == 'pending' and summary['promoted_to_serving'] is False
        reviews = lines(folder + '/evidence-review.jsonl')
        assert len(reviews) == len(outputs)
        for output, pending in zip(outputs, reviews):
            assert output['example_id'] == pending['example_id'] and output['result'] == pending['result']
            assert pending['review_status'] == 'pending' and pending['reviewer'] == ''
            assert all(v is None for v in pending['judgments'].values())
        reports[folder] = {'metrics': score, 'call_triplets_reconciled': len(traces), 'validation_issues': dict(issues),
                           'exact_citations_checked': citations, 'numeric_records_checked': numerics,
                           'derived_citation_additions': additions, 'predictions_sha256': r.sha256(OUT / folder / 'predictions.jsonl')}
    status = read('status.json')
    assert status['verifier39']['exit_code'] == 1 and status['verifier39']['state'] == 'failed'
    assert all(v['state'] == 'completed' and v['exit_code'] == 0 for k, v in status.items() if k != 'verifier39')
    regression = (OUT / 'regression.stderr.log').read_text(encoding='utf-8')
    assert 'Ran 291 tests' in regression and regression.rstrip().endswith('OK')
    try:
        w.require_full39(OUT / 'verifier39', OUT / 'reviewed-probe')
    except ValueError as exc:
        block = str(exc)
        assert block == 'Successful full39 is required before validation30'
    else:
        raise AssertionError('Failed full39 must block validation30')
    assert not (OUT / 'validation30').exists() and not (OUT / 'reviewed-verifier39').exists()
    old = REPO / 'research-runs/audit-cellfix8-resume-full39-20261020T095348Z-7974a5cc/artifact/verifier39'
    assert json.loads((old / 'cases.json').read_bytes()) == all_cases
    outputs = lines('verifier39/predictions.jsonl')
    failures = [{'example_id': c['example_id'], 'gold': c['label'], 'prediction': row['result']['assessed_label'],
                 'stop': row['result']['stop_reason'],
                 'issues': [t['validation_issue'] for t in row['result']['trace'] if t.get('validation_issue')]}
                for c, row in zip(all_cases, outputs) if c['label'] != row['result']['assessed_label']]
    report = {'run_id': RUN, 'candidate': release['candidate'], 'zip_sha256': digest(raw),
              'parent_probe_zip_sha256': digest(parent_raw), 'output_files': len(manifest['files']) + 1,
              'input_files': len(inputs), 'all_output_hashes_valid': True, 'all_input_bytes_match_release': True,
              'same_run_probe_preserved': True, 'criteria_sha256': release['criteria_sha256'], 'payload_sha256': release['payload_sha256'],
              'all_predictions_and_calls_replayed': True, 'metrics_recomputed_exactly': True,
              'model_revision_budget_gate_unchanged': True, 'probe_human_admission': admission,
              'remote_regression_tests_passed': 291,
              'remote_validate_only': {k: read(k + '-validate-only.stdout.log') for k in ('smoke', 'probe', 'verifier', 'validation30')},
              'results': reports, 'failed_cases': failures, 'full39_human_review_completed': False,
              'validation30_admission_block': block, 'validation30_inference_present': False,
              'previous_cf8_metrics_same_cases': json.loads((old / 'metrics.json').read_bytes()),
              'new_inference_during_audit': False,
              'limitations': ['Development full39 does not measure generalization to independent validation30.',
                              'Exact quotes and label accuracy do not certify free explanation or missing-information semantics.',
                              'AI audit is not a human full39 signature.',
                              'Manifest consistency is not remote-host attestation.']}
    write_once(REPO / 'docs' / ('atomic-verifier-cellfix9-full39-audit-' + RUN + '.json'), json_bytes(report))
    print(json.dumps({k: v for k, v in report.items() if k not in ('results', 'previous_cf8_metrics_same_cases')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
