"""Audit cellfix4 smoke/probe artifacts, preserving the ZIP and unsigned human review."""
from collections import Counter
import hashlib
import importlib
import io
import json
from pathlib import Path
import sys
from unittest.mock import patch
import zipfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts.audit_atomic_cellfix3 import extract

RUN = '20261017T111605Z-9505cc47'
ARCHIVE = Path.home()/'Downloads'/('output-cellfix4-fresh-'+RUN+'.zip')
BASE = REPO/'research-runs'/('audit-cellfix4-fresh-'+RUN)
ROOT, OUT = BASE/'workspace', BASE/'artifact'
sha = lambda b: hashlib.sha256(b).hexdigest()


def main():
    with zipfile.ZipFile(ARCHIVE) as archive:
        manifest = json.loads(archive.read('output-manifest.json'))
        assert manifest['run_id'] == RUN
        names = [r['path'] for r in manifest['files']]
        assert len(names) == len(set(names))
        assert set(archive.namelist()) == set(names) | {'output-manifest.json'}
        for r in manifest['files']:
            data = archive.read(r['path'])
            assert len(data) == r['size'] and sha(data) == r['sha256'], r['path']
        extract(archive, OUT)
        payload = archive.read('frozen-inputs.zip')
        inputs = json.loads(archive.read('input-manifest.json'))
    release = json.loads((REPO/'docs/atomic-verifier-cellfix4-fresh-colab-release.json').read_text())
    assert inputs == release['payload_files'] and sha(payload) == release['payload_sha256']
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert set(archive.namelist()) == set(inputs)
        extract(archive, ROOT)
    for name, item in inputs.items():
        data = (ROOT/name).read_bytes()
        assert len(data) == item['size'] and sha(data) == item['sha256'], name
    sys.path.insert(0, str(ROOT))
    e = importlib.import_module('research_rag.evaluation.evaluate_atomic_verifier')
    assert Path(e.__file__).resolve().is_relative_to(ROOT)
    criteria_path = ROOT/'research_rag/evaluation/atomic_verifier_criteria_v8.json'
    frozen, all_cases, data_inputs, contract, _, baseline, baseline_metrics = e.load_frozen(criteria_path)
    assert sha(criteria_path.read_bytes()) == release['criteria_sha256']
    read = lambda n: json.loads((OUT/n).read_text(encoding='utf-8'))
    lines = lambda n: [json.loads(s) for s in (OUT/n).read_text(encoding='utf-8').splitlines()]
    results = {}
    for folder in ('assessment-smoke', 'decomposition-probe'):
        probe = folder == 'decomposition-probe'
        if probe:
            effective, cases, data_path = e.probe_configuration(frozen, all_cases, criteria_path)
            sources = {'probe-claims': data_path}
        else:
            effective, cases = e.smoke_configuration(frozen, all_cases)
            sources = data_inputs
        assert cases == read(folder+'/cases.json')
        assert read(folder+'/baseline.json') == baseline
        assert read(folder+'/baseline-metrics.json') == baseline_metrics
        for name, path in sources.items():
            assert (OUT/folder/(name+'.jsonl')).read_bytes() == path.read_bytes()
        assert (OUT/folder/'criteria.json').read_bytes() == criteria_path.read_bytes()
        assert (OUT/folder/'contract.json').read_bytes() == contract.read_bytes()
        provenance = read(folder+'/provenance.json')
        assert provenance['criteria_sha256'] == release['criteria_sha256']
        assert provenance['source_sha256'] == frozen['source_sha256']
        assert provenance['prompt_sha256'] == frozen['prompt_sha256']
        assert provenance['serving_modified'] is False
        model = provenance['model']
        keys = ('model_files','shared_tokenizer_files','repo_id','revision','dtype','quantization','seed','do_sample')
        pairing = {k:model[k] == baseline['model_metadata'][k] for k in keys}
        assert all(pairing.values()) and pairing == provenance['historical_model_pairing']
        assert model['repo_id'] == frozen['base_model'] and model['revision'] == frozen['base_revision']
        assert model['structured_decoder'] == frozen['structured_decoder']
        assert model['max_new_tokens'] == frozen['max_new_tokens'] and model['seed'] == frozen['seed']
        rows = lines(folder+'/predictions.jsonl')
        assert [r['example_id'] for r in rows] == [c['example_id'] for c in cases]
        metrics = e.score_probe(rows, cases, effective) if probe else e.score(rows, cases, effective)
        events = lines(folder+'/calls.jsonl')
        starts = [r for r in events if r['event'] == 'call_started']
        gens = [r for r in events if r['event'] == 'generation']
        finishes = [r for r in events if r['event'] == 'call_finished']
        traces = [(r['example_id'], t) for r in rows for t in r['result']['trace']]
        expected_calls = 18 if probe else 28
        assert len(starts) == len(gens) == len(finishes) == len(traces) == expected_calls
        issues = Counter()
        citations = records = additions = 0
        for i, ((cid,t), start, gen, finish) in enumerate(zip(traces, starts, gens, finishes),1):
            assert start['call_id'] == gen['call_id'] == finish['call_id'] == i
            assert start['example_id'] == gen['example_id'] == finish['example_id'] == cid
            assert start['messages'] == finish['messages'] == t['messages']
            assert gen['json_valid'] is True and gen['parse_error_type'] is None
            assert json.loads(gen['raw_output']) == finish['parsed_output'] == t['output']
            assert start['max_new_tokens'] == gen['max_new_tokens'] == finish['max_new_tokens'] == t['max_new_tokens'] == frozen['max_new_tokens']
            p = json.loads(t['messages'][1]['content'])
            before = json.dumps(t['output'],sort_keys=True)
            try:
                if t['stage'] == 'decompose':
                    e.atomic.normalize_decomposition(t['output'],p['claim'])
                else:
                    checked = e.atomic.assess_part(t['output'],p['part'],p['context'])
                    for obs in checked['observations']:
                        assert all(q in p['context'] for q in obs['quotes'])
                        additions += len(obs['citation_additions'])
                        for q in obs['citation_additions']:
                            numeric = obs['numeric'] if isinstance(obs['numeric'],list) else [obs['numeric']]
                            assert q in [r['source_quote'] for r in numeric]
            except ValueError as exc:
                assert str(exc) == t['validation_issue'], (cid,str(exc))
            else:
                assert t.get('valid') is True and not t.get('validation_issue')
            assert json.dumps(t['output'],sort_keys=True) == before
            issues[t.get('validation_issue','valid')] += 1
            if t['stage'] != 'decompose':
                for obs in t['output']['observations']:
                    assert obs['member'] in p['context']
                    for quote in obs['quotes']:
                        assert quote in p['context']
                        citations += 1
                    checks = obs['numeric'] if isinstance(obs['numeric'],list) else [obs['numeric']] if obs['numeric'] else []
                    for record in checks:
                        assert record['source_quote'] in p['context']
                        assert record['right']['quote'] in record['source_quote']
                        assert record['left']['quote'] in p['part']['quote'] or record['kind'] == 'change'
                        records += 1
        metrics['generated_tokens'] = sum(g['generated_tokens'] for g in gens)
        metrics['prompt_tokens'] = sum(g['prompt_tokens'] for g in gens)
        metrics['checks']['within_measured_token_budget'] = metrics['generated_tokens'] <= effective['maximum_generated_tokens'] and all(g['generated_tokens'] <= frozen['max_new_tokens'] for g in gens)
        metrics['checks']['structured_decoding_trace_complete'] = e.decoding_trace_complete(gens,[t['messages'] for _,t in traces],frozen)
        metrics['checks']['cooperative_deadline_trace_complete'] = all(t['cooperative_deadline'] for _,t in traces)
        metrics['automated_gate_pass'] = all(metrics['checks'].values())
        assert metrics == read(folder+'/metrics.json')
        summary = read(folder+'/summary.json')
        assert summary['experiment_completed'] is True and summary['automated_gate_pass'] is True
        assert summary['prediction_count'] == len(rows) and summary['backend_calls'] == expected_calls
        assert summary['human_review'] == 'pending' and summary['overall_pass'] is False
        assert summary['promoted_to_serving'] is False
        reviews = lines(folder+'/evidence-review.jsonl')
        assert len(reviews) == len(rows)
        for case,row,review in zip(cases,rows,reviews):
            assert row['example_id'] == review['example_id'] == case['example_id']
            assert row['result'] == review['result']
            assert review['review_status'] == 'pending' and review['reviewer'] == ''
            assert all(v is None for v in review['judgments'].values())
        results[folder] = {'all_predictions_replayed':True,'metrics_recomputed_exactly':True,
            'model_pairing':pairing,'call_triplets_reconciled':expected_calls,
            'validation_issues':dict(issues),'exact_raw_citations_checked':citations,
            'exact_numeric_sources_checked':records,'derived_numeric_citations_checked':additions,
            'metrics':metrics,'summary':summary,'predictions_sha256':sha((OUT/folder/'predictions.jsonl').read_bytes())}
    review_path = OUT/'decomposition-probe/semantic-review.json'
    original_review = review_path.read_bytes()
    try:
        e.require_probe_review(OUT/'decomposition-probe',criteria_path)
    except ValueError as exc:
        admission_error = str(exc)
        assert admission_error == 'Completed human review bound to this probe is required'
    else:
        raise AssertionError('Unsigned human review admitted full39')
    unused = BASE/'must-not-run-full39'
    assert not unused.exists()
    with patch.object(e,'model_loader') as loader, patch.object(sys,'argv',[
            'audit','--output-dir',str(unused),'--criteria',str(criteria_path),'--probe-dir',str(OUT/'decomposition-probe')]):
        try:
            e.main()
        except ValueError as exc:
            assert str(exc) == admission_error
        else:
            raise AssertionError('Full39 CLI bypassed unsigned review')
        loader.assert_not_called()
    assert review_path.read_bytes() == original_review and not unused.exists()
    stages = read('status.json')
    assert all(s['exit_code'] == 0 and s['state'] == 'completed' for s in stages.values())
    log = (OUT/'regression.stderr.log').read_text(encoding='utf-8')
    assert 'Ran 166 tests' in log and log.rstrip().endswith('OK')
    validations = {}
    for name,count,calls in (('probe',18,36),('smoke',12,96),('verifier',39,312)):
        validations[name] = read(name+'-validate-only.stdout.log')
        assert validations[name] == {'freeze_valid':True,'cases':count,'maximum_calls':calls}
    report = {'run_id':RUN,'zip_sha256':sha(ARCHIVE.read_bytes()),'output_files':len(manifest['files'])+1,
        'all_output_hashes_valid':True,'all_input_bytes_match_released_payload':True,
        'input_files':len(inputs),'source_fixture_files':len(frozen['source_sha256']),
        'criteria_sha256':release['criteria_sha256'],'payload_sha256':release['payload_sha256'],
        'load_frozen_passed':True,'remote_regression_tests_passed':166,
        'remote_validate_only':validations,'remote_cuda_preflight':read('cuda-preflight.stdout.log'),
        'results':results,'human_review':'pending','full39_admission_error':admission_error,
        'full39_blocked_before_model_loader':True,'original_human_review_preserved':True,
        'new_gpu_inference_during_audit':False,'full39_current_candidate':None,'promoted_to_serving':False,
        'limitations':['Hashes show consistency with the frozen local release, not a signature of remote execution.',
            'Smoke12 measures labels only on development data; probe18 measures decomposition structure, not label accuracy.',
            'Human review must be newly bound to current criteria and predictions. Historical v7 approval is not copied.']}
    target = REPO/'docs'/('atomic-verifier-cellfix4-smoke-probe-audit-'+RUN+'.json')
    target.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'report':str(target),'smoke':results['assessment-smoke']['metrics'],
        'probe':results['decomposition-probe']['metrics'],'full39_admission_error':admission_error},indent=2))


if __name__ == '__main__':
    main()
