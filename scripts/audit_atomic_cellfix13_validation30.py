"""Replay the received failed validation run; never rerun inference or alter gold."""
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

RUN = '20261027T151114Z-20ea1926'
BASE = REPO / 'research-runs' / ('audit-cellfix13-validation30-' + RUN)
OUT, SOURCE = BASE / 'artifact', BASE / 'workspace'


def read(name):
    return json.loads((OUT / name).read_bytes())


def lines(name):
    return [json.loads(v) for v in (OUT / name).read_bytes().splitlines()]


def main():
    raw = (REPO.parent / ('output-cellfix13-fresh-' + RUN + ' (5).zip')).read_bytes()
    write_once(BASE / 'original-output.zip', raw)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        manifest = json.loads(z.read('output-manifest.json'))
        assert manifest['run_id'] == RUN
        names = [v['path'] for v in manifest['files']]
        assert len(names) == len(set(names)) and len(z.namelist()) == len(set(z.namelist()))
        assert set(z.namelist()) == set(names) | {'output-manifest.json'}
        for item in manifest['files']:
            blob = z.read(item['path'])
            assert digest(blob) == item['sha256'] and len(blob) == item['size'], item['path']
        extract(z, OUT)
    release = json.loads((REPO / 'docs/atomic-verifier-cellfix13-release.json').read_bytes())
    for name, expected in release['files'].items():
        assert digest((REPO / name).read_bytes()) == expected, name
    payload, inputs = (OUT / 'frozen-inputs.zip').read_bytes(), read('input-manifest.json')
    assert digest(payload) == release['payload_sha256'] and inputs == release['payload_files']
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        assert len(z.namelist()) == len(set(z.namelist())) and set(z.namelist()) == set(inputs)
        extract(z, SOURCE)
    for name, item in inputs.items():
        blob = (SOURCE / name).read_bytes()
        assert digest(blob) == item['sha256'] and len(blob) == item['size'], name
    for key in ('candidate', 'criteria_sha256', 'payload_sha256'):
        assert read('notebook-provenance.json')[key] == release[key]

    sys.path.insert(0, str(SOURCE))
    spec = importlib.util.spec_from_file_location('cf13_validation_audit_worker', SOURCE / 'atomic_workflow_cellfix13.py')
    w = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w)
    r = w.r
    assert Path(r.__file__).resolve().is_relative_to(SOURCE)
    frozen, all_cases, data, contract, _, baseline, baseline_metrics = r.load_frozen(r.CRITERIA)
    assert r.sha256(r.CRITERIA) == release['criteria_sha256']
    binding, validation_criteria, validation_cases = w.configuration(SOURCE / 'validation/cellfix13')
    assert binding == read('validation-lock.json') == read('validation30/validation-binding.json')
    for remote, local in [('validation-annotation-review.json', 'annotation-review.json'),
                          ('validation-original-lock.json', 'original-lock.json')]:
        assert (OUT / remote).read_bytes() == (SOURCE / 'validation/cellfix13' / local).read_bytes()
    for original, reviewed in [('decomposition-probe', 'reviewed-probe'), ('verifier39', 'reviewed-verifier39')]:
        source_files = {p.name: p.read_bytes() for p in (OUT / original).iterdir() if p.name != 'semantic-review.json'}
        copy_files = {p.name: p.read_bytes() for p in (OUT / reviewed).iterdir() if p.name != 'semantic-review.json'}
        assert source_files == copy_files
    probe_admission = r.require_probe_review(OUT / 'reviewed-probe')
    full_admission = w.require_full39(OUT / 'reviewed-verifier39', OUT / 'reviewed-probe')
    assert probe_admission == read('verifier39/probe-admission.json')
    assert full_admission == read('validation30/full39-admission.json')
    for stem, expected in [('probe-admission', probe_admission), ('full39-admission', full_admission)]:
        assert read(stem + '.stdout.log') == expected
        assert read(stem + '-preflight.stdout.log') == expected
    human_reviews = {}
    for folder in ('reviewed-probe', 'reviewed-verifier39'):
        review = read(folder + '/semantic-review.json')
        assert review['reviewer_kind'] == 'human' and review['review_completed'] is True
        assert all(c['notes'].strip() and all(v is True for v in c['judgments'].values()) for c in review['cases'])
        human_reviews[folder] = {'reviewer': review['reviewer'], 'cases': len(review['cases']),
                                  'true_judgments': sum(len(c['judgments']) for c in review['cases']),
                                  'sha256': r.sha256(OUT / folder / 'semantic-review.json')}
    for path in (OUT / 'review-attempts').iterdir():
        assert path.stem == digest(path.read_bytes())

    reports = {}
    records = importlib.import_module('04_factchecker.inference.assessment_decisions').numeric_records
    for folder in ('assessment-smoke', 'decomposition-probe', 'verifier39', 'validation30'):
        print('Replaying', folder, flush=True)
        probe = folder == 'decomposition-probe'
        if probe:
            effective, cases, probe_path = r.probe_configuration(frozen, all_cases, r.CRITERIA)
        elif folder == 'assessment-smoke':
            effective, cases = r.smoke_configuration(frozen, all_cases)
        elif folder == 'validation30':
            effective, cases = validation_criteria, validation_cases
        else:
            effective, cases = frozen, all_cases
        assert read(folder + '/criteria.json') == (effective if folder == 'validation30' else frozen)
        assert read(folder + '/cases.json') == cases
        if folder != 'validation30':
            assert read(folder + '/baseline.json') == baseline
            assert read(folder + '/baseline-metrics.json') == baseline_metrics
            assert (OUT / folder / 'contract.json').read_bytes() == contract.read_bytes()
            for name, path in ({'probe-claims': probe_path} if probe else data).items():
                assert (OUT / folder / (name + '.jsonl')).read_bytes() == path.read_bytes()
        provenance = read(folder + '/provenance.json')
        assert provenance['criteria_sha256'] == release['criteria_sha256']
        assert provenance['source_sha256'] == frozen['source_sha256'] and provenance['prompt_sha256'] == frozen['prompt_sha256']
        assert provenance['serving_modified'] is False
        for key in ('model_files', 'shared_tokenizer_files', 'repo_id', 'revision', 'dtype', 'quantization', 'seed', 'do_sample'):
            assert provenance['model'][key] == baseline['model_metadata'][key], key
        assert provenance['model']['structured_decoder'] == frozen['structured_decoder']
        assert provenance['model']['max_new_tokens'] == frozen['max_new_tokens']
        if folder == 'validation30':
            assert provenance['validation_binding_sha256'] == r.sha256(SOURCE / 'validation/cellfix13/binding.json')
        outputs, events = lines(folder + '/predictions.jsonl'), lines(folder + '/calls.jsonl')
        assert [v['example_id'] for v in outputs] == [v['example_id'] for v in cases]
        starts = [e for e in events if e['event'] == 'call_started']
        finishes = [e for e in events if e['event'] == 'call_finished']
        gens = [e for e in events if e['event'] == 'generation']
        traces = [(v['example_id'], t) for v in outputs for t in v['result']['trace']]
        assert len(traces) == len(starts) == len(finishes)
        assert len(events) == len(starts) + len(finishes) + len(gens)
        generation_by_id = {e['call_id']: e for e in gens}
        assert len(generation_by_id) == len(gens)
        issues, missing_generations = Counter(), []
        citations = numeric_records = additions = 0
        for i, ((cid, trace), start, finish) in enumerate(zip(traces, starts, finishes), 1):
            assert start['call_id'] == finish['call_id'] == i
            assert start['example_id'] == finish['example_id'] == cid
            assert start['messages'] == finish['messages'] == trace['messages']
            assert start['max_new_tokens'] == finish['max_new_tokens'] == trace['max_new_tokens'] == frozen['max_new_tokens']
            request = json.loads(trace['messages'][1]['content'])
            gen = generation_by_id.get(i)
            if gen is None:
                assert 'output' not in trace and finish['error_type'] == 'CaseDeadlineExceeded'
                assert trace['validation_issue'] == 'deadline_exceeded'
                missing_generations.append({'call_id': i, 'example_id': cid, 'elapsed_ms': finish['elapsed_ms']})
            else:
                assert gen['example_id'] == cid and gen['json_valid'] is True and gen['parse_error_type'] is None
                assert json.loads(gen['raw_output']) == finish['parsed_output'] == trace['output']
                assert gen['max_new_tokens'] == frozen['max_new_tokens']
                before = json.dumps(trace['output'], sort_keys=True)
                try:
                    if trace['stage'] == 'decompose':
                        r.atomic.normalize_decomposition(trace['output'], request['claim'])
                    else:
                        checked = r.atomic.assess_part(trace['output'], request['part'], request['context'])
                        for obs in checked['observations']:
                            assert all(q in request['context'] for q in obs['quotes'])
                            citations += len(obs['quotes'])
                            additions += len(obs['citation_additions'])
                            for record in records(obs['numeric'], checked['numeric_requirements']):
                                assert record['source_quote'] in request['context']
                                assert record['right']['quote'] in record['source_quote']
                                numeric_records += 1
                except ValueError as exc:
                    assert trace.get('valid') is not True and str(exc) == trace.get('validation_issue'), (cid, str(exc))
                else:
                    assert trace['valid'] is True and not trace.get('validation_issue')
                assert before == json.dumps(trace['output'], sort_keys=True)
            issues[trace.get('validation_issue') or 'valid'] += 1
        for case, row in zip(cases, outputs):
            r.replay_result(row['result'], case['claim'], case.get('context', ''), effective)
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
        assert summary['backend_calls'] == len(traces) and summary['automated_gate_pass'] == score['automated_gate_pass']
        assert summary['overall_pass'] is False and summary['human_review'] == 'pending' and summary['promoted_to_serving'] is False
        reports[folder] = {'metrics': score, 'call_starts_and_finishes': len(traces), 'generations_measured': len(gens),
                           'validation_issues': dict(issues), 'missing_generation_events': missing_generations,
                           'exact_citations_checked': citations, 'numeric_records_checked': numeric_records,
                           'derived_citation_additions': additions, 'predictions_sha256': r.sha256(OUT / folder / 'predictions.jsonl')}

    outputs, cases = lines('validation30/predictions.jsonl'), validation_cases
    metric = reports['validation30']['metrics']
    per_label = {}
    for label in r.LABELS:
        tp = sum(c['label'] == label == row['result']['assessed_label'] for c, row in zip(cases, outputs))
        predicted = sum(row['result']['assessed_label'] == label for row in outputs)
        actual = sum(c['label'] == label for c in cases)
        per_label[label] = {'precision': tp / predicted if predicted else None, 'recall': tp / actual if actual else None,
                            'gold_count': actual, 'predicted_count': predicted}
    classification = {'per_label': per_label, 'false_support': metric['false_support'],
                      'non_support_gold_count': sum(c['label'] != 'support' for c in cases),
                      'per_paper': metric['dataset_groups'], 'latency_ms': [row['result']['elapsed_ms'] for row in outputs]}
    assert classification == read('validation30/classification.json')
    status = read('status.json')
    assert status['validation30']['state'] == 'failed' and status['validation30']['exit_code'] == 1
    assert all(v['state'] == 'completed' and v['exit_code'] == 0 for k, v in status.items() if k != 'validation30')
    assert 'Ran 385 tests' in (OUT / 'regression.stderr.log').read_text(encoding='utf-8')
    try:
        w.require_human_review(OUT / 'validation30', validation_cases, frozen['human_review_rubric'])
    except ValueError as exc:
        review_block = str(exc)
    else:
        raise AssertionError('Validation review must still be unsigned')
    failed_cases = []
    for c, row in zip(cases, outputs):
        result = row['result']
        if c['label'] != result['assessed_label']:
            failed_cases.append({'example_id': c['example_id'], 'gold': c['label'], 'prediction': result['assessed_label'],
                                 'stop': result['stop_reason'], 'elapsed_ms': result['elapsed_ms']})
    overruns = [{'example_id': row['example_id'], 'elapsed_ms': row['result']['elapsed_ms'],
                 'declared_budget_ms': frozen['case_deadline_seconds'] * 1000}
                for row in outputs if row['result']['elapsed_ms'] > frozen['case_deadline_seconds'] * 1000]
    report = {'run_id': RUN, 'candidate': release['candidate'], 'zip_sha256': digest(raw),
              'output_files': len(manifest['files']) + 1, 'input_files': len(inputs),
              'all_output_hashes_valid': True, 'all_input_bytes_match_release': True,
              'criteria_sha256': release['criteria_sha256'], 'payload_sha256': release['payload_sha256'],
              'all_stored_outputs_replayed': True, 'all_metrics_and_classification_recomputed': True,
              'model_revision_budget_gate_unchanged': True, 'human_admissions': human_reviews,
              'probe_admission': probe_admission, 'full39_admission': full_admission,
              'results': reports, 'failed_cases': failed_cases, 'deadline_overruns': overruns,
              'runtime_failed_rows': metric['runtime_failed_rows'], 'completed_wrong_labels': len(failed_cases) - metric['runtime_failed_rows'],
              'validation30_human_review_completed': False, 'unsigned_validation_review_block': review_block,
              'generations_measured_lower_bound_only': bool(reports['validation30']['missing_generation_events']),
              'measured_tokens_below_cap': metric['generated_tokens'] < validation_criteria['maximum_generated_tokens'],
              'independent_set_exposed': True, 'if_used_for_tuning_retire_to_development': True,
              'ready_for_serving_or_reader_summarizer_integration': False, 'new_inference_during_audit': False,
              'limitations': ['Consistency checks do not attest the remote host.',
                              'Missing generation events prevent certifying total token usage.',
                              'A cooperative deadline flag is not proof of an enforced wall-clock bound.',
                              'AI evidence notes are not human approval.']}
    write_once(REPO / 'docs' / ('atomic-verifier-cellfix13-validation30-audit-' + RUN + '.json'), json_bytes(report))
    print(json.dumps({k: v for k, v in report.items() if k not in ('results', 'failed_cases')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
