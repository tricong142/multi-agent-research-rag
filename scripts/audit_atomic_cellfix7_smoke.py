"""Audit the received cf7 ZIP, preserving bytes and replaying calls without weights."""
import importlib.util
import io
import json
from pathlib import Path
import sys
import zipfile
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.audit_atomic_cellfix3 import extract
from scripts.atomic_validation_review import digest, json_bytes, write_once

RUN = '20261020T033551Z-c7337790'
BASE = ROOT/'research-runs'/('audit-cellfix7-fresh-'+RUN)


def main():
    raw = (ROOT.parent/('output-cellfix7-fresh-'+RUN+'.zip')).read_bytes()
    write_once(BASE/'original-output.zip', raw)
    out, source = BASE/'artifact', BASE/'workspace'
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        manifest = json.loads(archive.read('output-manifest.json'))
        assert manifest['run_id'] == RUN
        names = [item['path'] for item in manifest['files']]
        assert len(names) == len(set(names))
        assert set(archive.namelist()) == set(names)|{'output-manifest.json'}
        for item in manifest['files']:
            data = archive.read(item['path'])
            assert len(data) == item['size'] and digest(data) == item['sha256']
        extract(archive, out)
    read = lambda name: json.loads((out/name).read_bytes())
    rows = lambda name: [json.loads(s) for s in (out/name).read_bytes().splitlines()]
    release = json.loads((ROOT/'docs/atomic-verifier-cellfix7-release.json').read_bytes())
    inputs = read('input-manifest.json')
    assert inputs == release['payload_files']
    payload = (out/'frozen-inputs.zip').read_bytes()
    assert digest(payload) == release['payload_sha256']
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert set(archive.namelist()) == set(inputs)
        extract(archive, source)
    for name, item in inputs.items():
        data = (source/name).read_bytes()
        assert len(data) == item['size'] and digest(data) == item['sha256'], name
    sys.path.insert(0, str(source))
    spec = importlib.util.spec_from_file_location('audit_workflow', source/'atomic_workflow_cellfix7.py')
    workflow = importlib.util.module_from_spec(spec); spec.loader.exec_module(workflow)
    r = workflow.r
    frozen, all_cases, data, contract, _, baseline, baseline_metrics = r.load_frozen(r.CRITERIA)
    assert r.sha256(r.CRITERIA) == release['criteria_sha256']
    assert workflow.binding(source/'validation/cellfix7') == read('validation-lock.json')
    assert (out/'validation-annotation-review.json').read_bytes() == (source/'validation/cellfix7/annotation-review.json').read_bytes()
    assert (out/'validation-original-lock.json').read_bytes() == (source/'validation/cellfix7/original-lock.json').read_bytes()
    criteria, cases = r.smoke_configuration(frozen, all_cases)
    folder = 'assessment-smoke/'
    assert read(folder+'cases.json') == cases
    assert read(folder+'baseline.json') == baseline and read(folder+'baseline-metrics.json') == baseline_metrics
    assert (out/folder/'criteria.json').read_bytes() == r.CRITERIA.read_bytes()
    assert (out/folder/'contract.json').read_bytes() == contract.read_bytes()
    for name, path in data.items():
        assert (out/folder/(name+'.jsonl')).read_bytes() == path.read_bytes()
    predictions, events = rows(folder+'predictions.jsonl'), rows(folder+'calls.jsonl')
    score = workflow.measured_score(predictions, cases, criteria, events)
    assert score == read(folder+'metrics.json')
    provenance = read(folder+'provenance.json')
    assert provenance['source_sha256'] == frozen['source_sha256']
    assert provenance['prompt_sha256'] == frozen['prompt_sha256']
    assert provenance['criteria_sha256'] == release['criteria_sha256']
    model = provenance['model']
    for key in ('model_files','shared_tokenizer_files','repo_id','revision','dtype','quantization','seed','do_sample'):
        assert model[key] == baseline['model_metadata'][key], key
    assert model['structured_decoder'] == frozen['structured_decoder']
    assert model['max_new_tokens'] == frozen['max_new_tokens']
    issues = Counter(); invalid = []; incorrect = []; citations = 0
    for case, row in zip(cases, predictions):
        assert case['example_id'] == row['example_id']
        for trace in row['result']['trace']:
            issue = trace.get('validation_issue')
            issues[issue or 'valid'] += 1
            payload = json.loads(trace['messages'][1]['content'])
            if 'output' not in trace:
                assert issue == 'invalid_json'
                try: json.loads(trace['raw_output'])
                except ValueError: pass
                else: raise AssertionError('Invalid JSON trace is parseable')
                invalid.append({'example_id':case['example_id'], 'attempt':trace['attempt'], 'raw':trace['raw_output']})
                continue
            try:
                if trace['stage'] == 'decompose':
                    r.atomic.normalize_decomposition(trace['output'], payload['claim'])
                else:
                    checked = r.atomic.assess_part(trace['output'], payload['part'], payload['context'])
                    for observation in checked['observations']:
                        assert all(q in payload['context'] for q in observation['quotes'])
                        citations += len(observation['quotes'])
            except ValueError as exc:
                assert str(exc) == issue, (case['example_id'], str(exc), issue)
            else:
                assert trace.get('valid') is True and not issue
        if case['label'] != row['result']['assessed_label']:
            incorrect.append({'case':case, 'result':row['result']})
    assert len(predictions) == 12 and score['backend_calls'] == 29
    stages = read('status.json')
    assert stages['assessment-smoke']['exit_code'] == 1
    assert all(v['exit_code']==0 for k,v in stages.items() if k!='assessment-smoke')
    assert 'Ran 237 tests' in (out/'regression.stderr.log').read_text(encoding='utf-8')
    validations = {k:read(k+'-validate-only.stdout.log') for k in ('smoke','probe','verifier','validation30')}
    for name in ('decomposition-probe','verifier39','validation30'):
        assert not (out/name).exists()
    report = {'run_id':RUN, 'zip_sha256':digest(raw), 'output_files':len(manifest['files'])+1,
        'input_files':len(inputs), 'criteria_sha256':release['criteria_sha256'],
        'all_output_hashes_valid':True, 'all_inputs_match_release':True, 'all_predictions_replayed':True,
        'metrics_recomputed_exactly':True, 'call_events_reconciled':score['backend_calls'],
        'remote_regression_tests_passed':237, 'remote_validate_only':validations,
        'model_revision_budget_unchanged':True, 'validation_binding_replayed':True,
        'exact_citations_checked':citations, 'validation_issues':dict(issues), 'metrics':score,
        'incorrect_cases':[v['case']['example_id'] for v in incorrect],
        'invalid_json_generations':len(invalid), 'probe18_present':False, 'full39_present':False,
        'validation30_inference_present':False, 'new_model_inference_completed':False,
        'predictions_sha256':digest((out/folder/'predictions.jsonl').read_bytes()),
        'limitations':['Stored provenance consistency is not a cryptographic signature of remote execution.',
            'Historical baseline 37/39 is not a cellfix7 result. No model quality is measured by this audit.']}
    write_once(ROOT/'docs'/('atomic-verifier-cellfix7-smoke-audit-'+RUN+'.json'), json_bytes(report))
    write_once(ROOT/'docs'/('atomic-verifier-cellfix7-smoke-diagnostics-'+RUN+'.json'), json_bytes(incorrect))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
