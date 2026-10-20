"""Verify the received cf8 recovery ZIP and replay all recorded model calls."""
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

RUN = '20261020T061934Z-c87bce57'
RECOVERY = '20261020T095348Z-7974a5cc'
BASE = REPO / 'research-runs' / ('audit-cellfix8-resume-full39-' + RECOVERY)
OUT, SOURCE = BASE / 'artifact', BASE / 'workspace'
PARENT = REPO / 'research-runs' / ('audit-cellfix8-fresh-' + RUN)
REPORT = REPO / 'docs' / ('atomic-verifier-cellfix8-full39-audit-' + RECOVERY + '.json')


def read(name):
    return json.loads((OUT / name).read_bytes())


def lines(name):
    return [json.loads(s) for s in (OUT / name).read_bytes().splitlines()]


def main():
    name = f'output-cellfix8-resume-full39-{RUN}-{RECOVERY}.zip'
    raw = (REPO.parent / name).read_bytes()
    write_once(BASE / 'original-output.zip', raw)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        manifest = json.loads(z.read('output-manifest.json'))
        assert manifest['run_id'] == RUN
        names = [i['path'] for i in manifest['files']]
        assert len(names) == len(set(names))
        assert set(z.namelist()) == set(names) | {'output-manifest.json'}
        for item in manifest['files']:
            data = z.read(item['path'])
            assert len(data) == item['size'] and digest(data) == item['sha256'], item['path']
        extract(z, OUT)
    release = json.loads((REPO / 'docs/atomic-verifier-cellfix8-release.json').read_bytes())
    payload = (OUT / 'frozen-inputs.zip').read_bytes()
    inputs = read('input-manifest.json')
    assert digest(payload) == release['payload_sha256'] and inputs == release['payload_files']
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        assert set(z.namelist()) == set(inputs)
        extract(z, SOURCE)
    for path, item in inputs.items():
        data = (SOURCE / path).read_bytes()
        assert digest(data) == item['sha256'] and len(data) == item['size'], path

    provenance = read('resume-provenance.json')
    assert provenance['original_run_id'] == RUN and provenance['recovery_id'] == RECOVERY
    assert provenance['parent_zip_sha256'] == digest((PARENT / 'original-output.zip').read_bytes())
    assert provenance['payload_sha256'] == release['payload_sha256']
    assert provenance['criteria_sha256'] == release['criteria_sha256']
    human = (OUT / 'probe-human-review.json').read_bytes()
    assert digest(human) == provenance['human_review_sha256']
    assert human == (REPO / f'docs/reviews/cellfix8-{RUN}/human/semantic-review.json').read_bytes()
    parent = PARENT / 'artifact'
    for original, copy in [('output-manifest.json', 'resume-parent-output-manifest.json'),
                           ('status.json', 'resume-parent-status.json')]:
        assert (parent / original).read_bytes() == (OUT / copy).read_bytes()
    preserved = 0
    for path in parent.rglob('*'):
        if path.is_file() and path.name not in ('output-manifest.json', 'status.json'):
            assert path.read_bytes() == (OUT / path.relative_to(parent)).read_bytes(), str(path)
            preserved += 1
    for path in (parent / 'decomposition-probe').iterdir():
        expected = human if path.name == 'semantic-review.json' else path.read_bytes()
        assert expected == (OUT / 'reviewed-probe' / path.name).read_bytes()

    sys.path.insert(0, str(SOURCE))
    spec = importlib.util.spec_from_file_location('cf8_resume_audit', SOURCE / 'atomic_workflow_cellfix8.py')
    w = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w)
    r = w.r
    assert Path(r.__file__).resolve().is_relative_to(SOURCE)
    criteria, cases, data, contract, _, baseline, baseline_metrics = r.load_frozen(r.CRITERIA)
    assert r.sha256(r.CRITERIA) == release['criteria_sha256']
    assert w.binding(SOURCE / 'validation/cellfix8') == read('validation-lock.json')
    for remote, local in [('validation-annotation-review.json', 'annotation-review.json'),
                           ('validation-original-lock.json', 'original-lock.json')]:
        assert (OUT / remote).read_bytes() == (SOURCE / 'validation/cellfix8' / local).read_bytes()
    admission = r.require_probe_review(OUT / 'reviewed-probe')
    assert admission == read('resume-admission.json')['probe_human_admission'] == read('verifier39/probe-admission.json')
    assert admission['probe_predictions_sha256'] == provenance['probe_predictions_sha256']
    smoke_criteria, smoke_cases = r.smoke_configuration(criteria, cases)
    smoke = w.measured_score(lines('assessment-smoke/predictions.jsonl'), smoke_cases,
                             smoke_criteria, lines('assessment-smoke/calls.jsonl'))
    assert smoke == read('assessment-smoke/metrics.json') and smoke['automated_gate_pass']

    folder = 'verifier39/'
    assert read(folder + 'cases.json') == cases
    assert read(folder + 'baseline.json') == baseline and read(folder + 'baseline-metrics.json') == baseline_metrics
    assert (OUT / folder / 'criteria.json').read_bytes() == r.CRITERIA.read_bytes()
    assert (OUT / folder / 'contract.json').read_bytes() == contract.read_bytes()
    for key, path in data.items():
        assert (OUT / folder / (key + '.jsonl')).read_bytes() == path.read_bytes()
    source = read(folder + 'provenance.json')
    assert source['criteria_sha256'] == release['criteria_sha256']
    assert source['source_sha256'] == criteria['source_sha256'] and source['prompt_sha256'] == criteria['prompt_sha256']
    assert source['serving_modified'] is False
    for key in ('model_files', 'shared_tokenizer_files', 'repo_id', 'revision', 'dtype', 'quantization', 'seed', 'do_sample'):
        assert source['model'][key] == baseline['model_metadata'][key], key
    assert source['model']['structured_decoder'] == criteria['structured_decoder']
    assert source['model']['max_new_tokens'] == criteria['max_new_tokens']
    outputs, events = lines(folder + 'predictions.jsonl'), lines(folder + 'calls.jsonl')
    assert [v['example_id'] for v in outputs] == [c['example_id'] for c in cases]
    metrics = w.measured_score(outputs, cases, criteria, events)
    assert metrics == read(folder + 'metrics.json')
    issues = Counter()
    citations = numeric_count = additions = 0
    records = importlib.import_module('04_factchecker.inference.assessment_decisions').numeric_records
    for row in outputs:
        for trace in row['result']['trace']:
            request = json.loads(trace['messages'][1]['content'])
            before = json.dumps(trace['output'], sort_keys=True)
            try:
                if trace['stage'] == 'decompose':
                    r.atomic.normalize_decomposition(trace['output'], request['claim'])
                else:
                    checked = r.atomic.assess_part(trace['output'], request['part'], request['context'])
                    for observation in checked['observations']:
                        assert all(q in request['context'] for q in observation['quotes'])
                        citations += len(observation['quotes'])
                        additions += len(observation['citation_additions'])
                        for record in records(observation['numeric'], checked['numeric_requirements']):
                            assert record['source_quote'] in request['context']
                            assert record['right']['quote'] in record['source_quote']
                            assert record['left']['quote'] in request['part']['quote'] or record['kind'] == 'change'
                            numeric_count += 1
            except ValueError as exc:
                assert str(exc) == trace.get('validation_issue'), (row['example_id'], str(exc))
            else:
                assert trace['valid'] is True and not trace.get('validation_issue')
            assert json.dumps(trace['output'], sort_keys=True) == before
            issues[trace.get('validation_issue') or 'valid'] += 1
    generations = [e for e in events if e['event'] == 'generation']
    assert len(generations) == metrics['backend_calls']
    assert all(g['json_valid'] is True and g['parse_error_type'] is None for g in generations)
    summary = read(folder + 'summary.json')
    assert summary['experiment_completed'] is True and summary['prediction_count'] == len(cases)
    assert summary['backend_calls'] == metrics['backend_calls']
    assert summary['automated_gate_pass'] == metrics['automated_gate_pass'] is False
    assert summary['status'] == 'automated_gates_failed' and summary['overall_pass'] is False
    assert summary['human_review'] == 'pending' and summary['promoted_to_serving'] is False
    reviews = lines(folder + 'evidence-review.jsonl')
    assert len(reviews) == len(outputs)
    for output, review in zip(outputs, reviews):
        assert output['example_id'] == review['example_id'] and output['result'] == review['result']
        assert review['review_status'] == 'pending' and review['reviewer'] == ''
        assert all(v is None for v in review['judgments'].values())
    status = read('status.json')
    assert status['verifier39']['exit_code'] == 1 and status['verifier39']['state'] == 'failed'
    assert all(v['state'] == 'completed' and v['exit_code'] == 0 for k, v in status.items() if k != 'verifier39')
    try:
        w.require_full39(OUT / 'verifier39', OUT / 'reviewed-probe')
    except ValueError as exc:
        blocked = str(exc)
        assert blocked == 'Successful full39 is required before validation30'
    else:
        raise AssertionError('Failed full39 must block validation30')
    assert not (OUT / 'validation30').exists()
    failures = [{'example_id': c['example_id'], 'gold': c['label'],
                 'prediction': row['result']['assessed_label'], 'stop': row['result']['stop_reason'],
                 'validation_issues': [t['validation_issue'] for t in row['result']['trace'] if t.get('validation_issue')]}
                for c, row in zip(cases, outputs) if c['label'] != row['result']['assessed_label']]
    indexed = {row['example_id']: row['result'] for row in outputs}
    rules = importlib.import_module('04_factchecker.inference.assessment_rules')
    # Reproduce guard behavior on actual traces, without changing any prediction.
    north = indexed['scope:entity:support']['parts'][0]
    north_obs = north['observations'][0]
    assert not any(rules.contains(north_obs['member'], q) for q in north_obs['quotes'])
    assert r.atomic.other_named_target(north['part'], north_obs['quotes'][0]) is False
    assert rules.evidence_issue(north['part'], north_obs['member'], north_obs['quotes'], 'true') is None
    third = indexed['scope:universal:contradict']['trace'][1]
    request = json.loads(third['messages'][1]['content'])
    obs = third['output']['observations'][0]
    assert rules.evidence_issue(request['part'], obs['member'], obs['quotes'], obs['truth']) == 'observation_polarity_mismatch'
    own = [p for q in obs['quotes'] for p in rules.clauses(q) if rules.contains(obs['member'], p)]
    assert own == ['the third became worse at recalling relevant records']
    assert rules.evidence_issue(request['part'], obs['member'], own, obs['truth']) is None
    guard_diagnostics = {
        'north_support_accepted_with_only_south_quote': True,
        'other_named_target_returned_false_on_south_quote': True,
        'third_counterexample_rejected_with_mixed_quote': True,
        'third_counterexample_not_rejected_with_member_clause_only': True,
        'localized_clause_used_for_diagnostic_only_no_predictions_rewritten': True,
    }
    write_once(REPORT.with_name(REPORT.stem + '-guard-diagnostics.json'), json_bytes(guard_diagnostics))
    report = {'run_id': RUN, 'recovery_id': RECOVERY, 'candidate': release['candidate'],
              'zip_sha256': digest(raw), 'output_files': len(manifest['files']) + 1,
              'input_files': len(inputs), 'all_output_hashes_valid': True, 'all_input_bytes_match_release': True,
              'parent_original_files_preserved': preserved, 'parent_lineage_valid': True,
              'probe_human_admission': admission, 'smoke_replayed_without_new_inference': True,
              'model_revision_source_prompt_contract_budget_gate_unchanged': True,
              'all_predictions_and_calls_replayed': True, 'metrics_recomputed_exactly': True,
              'criteria_sha256': release['criteria_sha256'], 'payload_sha256': release['payload_sha256'],
              'predictions_sha256': r.sha256(OUT / folder / 'predictions.jsonl'),
              'metrics': metrics, 'validation_issues': dict(issues),
              'exact_citations_checked_in_accepted_assessment_attempts': citations,
              'numeric_records_checked_in_accepted_assessment_attempts': numeric_count,
              'derived_citation_additions': additions, 'failed_cases': failures,
              'validation30_admission_block': blocked, 'validation30_inference_present': False,
              'full39_human_review_completed': False, 'new_model_inference_during_audit': False,
              'limitations': ['Stored provenance establishes artifact consistency, not remote-host attestation.',
                              'Exact quotes and deterministic replay do not prove semantic entailment.',
                              '39 development cases do not establish zero false support on unseen data.',
                              'Full39 label-correct rows can still have unsupported citations or incorrect explanations.']}
    write_once(REPORT, json_bytes(report))
    print(json.dumps({k: v for k, v in report.items() if k not in ('metrics', 'failed_cases')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
