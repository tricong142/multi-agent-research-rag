"""Verify received cellfix6 artifacts and replay stored outputs without loading weights."""
from collections import Counter
import hashlib
import importlib
import io
import json
from pathlib import Path
import sys
import zipfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts.audit_atomic_cellfix3 import extract
from scripts.atomic_validation_review import admit, digest, json_bytes, write_once

RUN = '20261019T171503Z-bfe32d16'
ARCHIVE = REPO.parent / ('output-cellfix6-fresh-' + RUN + '.zip')
BASE = REPO / 'research-runs' / ('audit-cellfix6-fresh-' + RUN)
ROOT, OUT = BASE / 'workspace', BASE / 'artifact'


def main():
    original = ARCHIVE.read_bytes()
    write_once(BASE/'original-output.zip', original)
    with zipfile.ZipFile(io.BytesIO(original)) as archive:
        manifest = json.loads(archive.read('output-manifest.json'))
        assert manifest['run_id'] == RUN
        names = [r['path'] for r in manifest['files']]
        assert len(names) == len(set(names))
        assert set(archive.namelist()) == set(names) | {'output-manifest.json'}
        for item in manifest['files']:
            raw = archive.read(item['path'])
            assert len(raw) == item['size'] and digest(raw) == item['sha256'], item['path']
        extract(archive, OUT)
    read = lambda n: json.loads((OUT/n).read_text(encoding='utf-8'))
    lines = lambda n: [json.loads(s) for s in (OUT/n).read_text(encoding='utf-8').splitlines()]
    release = json.loads((REPO/'docs/atomic-verifier-cellfix6-notebook-draft.json').read_text())
    for name, expected in release['files'].items():
        assert digest((REPO/name).read_bytes()) == expected, name
    payload = (OUT/'frozen-inputs.zip').read_bytes()
    inputs = read('input-manifest.json')
    assert inputs == release['payload_files'] and digest(payload) == release['payload_sha256']
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert set(archive.namelist()) == set(inputs)
        extract(archive, ROOT)
    for name, item in inputs.items():
        raw = (ROOT/name).read_bytes()
        assert len(raw) == item['size'] and digest(raw) == item['sha256'], name
    review_raw = (OUT/'validation-annotation-review.json').read_bytes()
    admitted = admit(ROOT/'validation/atomic-cellfix6-v1', json.loads(review_raw))
    admitted['review_sha256'] = digest(review_raw)
    assert admitted == read('validation-lock.json')
    # Do not replace the local human review with a byte-different upload.
    local_review = REPO/'docs/validation/atomic-cellfix6-v1/annotation-review-cellfix6-v1.json'
    remote_review = json.loads(review_raw)
    local = json.loads(local_review.read_bytes())
    review_differences = []
    for uploaded, saved in zip(remote_review['decisions'], local['decisions']):
        assert uploaded['id'] == saved['id']
        assert uploaded['accepted_label'] == saved['accepted_label'] and uploaded['checks'] == saved['checks']
        if uploaded != saved:
            review_differences.append({'id':uploaded['id'], 'different_fields':[
                k for k in uploaded if uploaded[k] != saved[k]]})
    for key in set(remote_review)-{'decisions'}:
        assert remote_review[key] == local[key], key
    sys.path.insert(0, str(ROOT))
    e = importlib.import_module('research_rag.evaluation.evaluate_atomic_verifier')
    assert Path(e.__file__).resolve().is_relative_to(ROOT)
    criteria_path = ROOT/'research_rag/evaluation/atomic_verifier_criteria_v8.json'
    frozen, all_cases, data_inputs, contract, _, baseline, baseline_metrics = e.load_frozen(criteria_path)
    assert digest(criteria_path.read_bytes()) == release['criteria_sha256']
    effective, cases = e.smoke_configuration(frozen, all_cases)
    folder = 'assessment-smoke'
    assert cases == read(folder+'/cases.json')
    assert read(folder+'/baseline.json') == baseline
    assert read(folder+'/baseline-metrics.json') == baseline_metrics
    for name, path in data_inputs.items():
        assert (OUT/folder/(name+'.jsonl')).read_bytes() == path.read_bytes(), name
    assert (OUT/folder/'criteria.json').read_bytes() == criteria_path.read_bytes()
    assert (OUT/folder/'contract.json').read_bytes() == contract.read_bytes()
    provenance = read(folder+'/provenance.json')
    assert provenance['criteria_sha256'] == release['criteria_sha256']
    assert provenance['source_sha256'] == frozen['source_sha256']
    assert provenance['prompt_sha256'] == frozen['prompt_sha256']
    assert provenance['serving_modified'] is False
    model = provenance['model']
    keys = ('model_files','shared_tokenizer_files','repo_id','revision','dtype','quantization','seed','do_sample')
    pairing = {key:model[key] == baseline['model_metadata'][key] for key in keys}
    assert all(pairing.values()) and pairing == provenance['historical_model_pairing']
    assert model['repo_id'] == frozen['base_model'] and model['revision'] == frozen['base_revision']
    assert model['structured_decoder'] == frozen['structured_decoder']
    assert model['max_new_tokens'] == frozen['max_new_tokens'] and model['seed'] == frozen['seed']
    rows = lines(folder+'/predictions.jsonl')
    assert [r['example_id'] for r in rows] == [c['example_id'] for c in cases]
    metrics = e.score(rows, cases, effective)  # Replays every aggregate, not just reported labels.
    events = lines(folder+'/calls.jsonl')
    starts = [r for r in events if r['event']=='call_started']
    generations = [r for r in events if r['event']=='generation']
    finishes = [r for r in events if r['event']=='call_finished']
    traces = [(r['example_id'],t) for r in rows for t in r['result']['trace']]
    assert len(starts) == len(generations) == len(finishes) == len(traces) == metrics['backend_calls']
    issues = Counter()
    citations = numeric_count = additions = 0
    for index, ((cid,t), start, gen, finish) in enumerate(zip(traces,starts,generations,finishes),1):
        assert start['call_id'] == gen['call_id'] == finish['call_id'] == index
        assert start['example_id'] == gen['example_id'] == finish['example_id'] == cid
        assert start['messages'] == finish['messages'] == t['messages']
        assert gen['json_valid'] is True and gen['parse_error_type'] is None
        assert json.loads(gen['raw_output']) == finish['parsed_output'] == t['output']
        assert start['max_new_tokens'] == gen['max_new_tokens'] == finish['max_new_tokens'] == t['max_new_tokens'] == frozen['max_new_tokens']
        data = json.loads(t['messages'][1]['content'])
        before = json.dumps(t['output'], sort_keys=True)
        try:
            if t['stage']=='decompose':
                e.atomic.normalize_decomposition(t['output'],data['claim'])
            else:
                checked = e.atomic.assess_part(t['output'],data['part'],data['context'])
                for obs in checked['observations']:
                    assert all(q in data['context'] for q in obs['quotes'])
                    additions += len(obs['citation_additions'])
        except ValueError as exc:
            assert str(exc) == t['validation_issue'], (cid,str(exc))
        else:
            assert t.get('valid') is True and not t.get('validation_issue')
        assert json.dumps(t['output'],sort_keys=True) == before
        issues[t.get('validation_issue') or 'valid'] += 1
        if t['stage']!='decompose':
            for obs in t['output']['observations']:
                assert obs['member'] in data['context']
                for quote in obs['quotes']:
                    assert quote in data['context']; citations += 1
                records = obs['numeric'] if isinstance(obs['numeric'],list) else [obs['numeric']] if obs['numeric'] else []
                for record in records:
                    assert record['source_quote'] in data['context']
                    assert record['right']['quote'] in record['source_quote']
                    assert record['left']['quote'] in data['part']['quote'] or record['kind']=='change'
                    numeric_count += 1
    metrics['generated_tokens'] = sum(g['generated_tokens'] for g in generations)
    metrics['prompt_tokens'] = sum(g['prompt_tokens'] for g in generations)
    metrics['checks']['within_measured_token_budget'] = (metrics['generated_tokens'] <= effective['maximum_generated_tokens']
        and all(g['generated_tokens'] <= frozen['max_new_tokens'] for g in generations))
    metrics['checks']['structured_decoding_trace_complete'] = e.decoding_trace_complete(generations,[t['messages'] for _,t in traces],frozen)
    metrics['checks']['cooperative_deadline_trace_complete'] = all(t['cooperative_deadline'] for _,t in traces)
    metrics['automated_gate_pass'] = all(metrics['checks'].values())
    assert metrics == read(folder+'/metrics.json')
    summary = read(folder+'/summary.json')
    assert summary['experiment_completed'] is True and summary['prediction_count'] == len(rows)
    assert summary['automated_gate_pass'] == metrics['automated_gate_pass'] is False
    assert summary['backend_calls'] == len(traces) and summary['overall_pass'] is False
    assert summary['promoted_to_serving'] is False and summary['human_review']=='pending'
    reviews = lines(folder+'/evidence-review.jsonl')
    assert len(reviews) == len(rows)
    for case,row,review in zip(cases,rows,reviews):
        assert case['example_id'] == row['example_id'] == review['example_id']
        assert row['result'] == review['result']
        assert review['review_status']=='pending' and review['reviewer']==''
        assert all(value is None for value in review['judgments'].values())
    stages = read('status.json')
    assert stages['assessment-smoke']['exit_code']==1 and stages['assessment-smoke']['state']=='failed'
    assert all(r['exit_code']==0 and r['state']=='completed' for n,r in stages.items() if n!='assessment-smoke')
    assert not (OUT/'decomposition-probe').exists() and not (OUT/'verifier39').exists()
    log = (OUT/'regression.stderr.log').read_text(encoding='utf-8')
    assert 'Ran 211 tests' in log and log.rstrip().endswith('OK')
    validations = {}
    for name,n,calls in [('probe',18,36),('smoke',12,96),('verifier',39,312)]:
        validations[name] = read(name+'-validate-only.stdout.log')
        assert validations[name] == {'freeze_valid':True,'cases':n,'maximum_calls':calls}
    notebook = read('notebook-provenance.json')
    assert notebook['criteria_sha256']==release['criteria_sha256'] and notebook['payload_sha256']==release['payload_sha256']
    assert notebook['candidate']==release['candidate'] and notebook['model_data_budgets_and_gates_unchanged'] is True
    incorrect = []
    for case,row in zip(cases,rows):
        result = row['result']
        if case['label'] != result['assessed_label']:
            incorrect.append({'example_id':case['example_id'],'claim':case['claim'],'context':case['context'],
                'gold':case['label'],'prediction':result['assessed_label'],
                'parts':result['parts'], 'assessment_trace':[
                    {k:t[k] for k in ('stage','attempt','output','validation_issue') if k in t}
                    for t in result['trace'] if t['stage']!='decompose']})
    previous = REPO/'research-runs/audit-cellfix5-full39-20261018T153854Z-2c3e0bd6/artifact/verifier39'
    previous_rows = {r['example_id']:r for r in [json.loads(s) for s in (previous/'predictions.jsonl').read_text().splitlines()]}
    previous_cases = {r['example_id']:r for r in json.loads((previous/'cases.json').read_text())}
    same = all((case['claim'],case['context'],case['label']) == tuple(previous_cases[case['example_id']][k]
               for k in ('claim','context','label')) for case in cases)
    assert same
    previous_correct = sum(previous_rows[c['example_id']]['result']['assessed_label']==c['label'] for c in cases)
    support = sum(r['result']['assessed_label']=='support' for r in rows)
    correct_support = sum(c['label']=='support' and r['result']['assessed_label']=='support' for c,r in zip(cases,rows))
    report = {'run_id':RUN,'zip_sha256':digest(original),'output_files':len(manifest['files'])+1,
        'all_output_hashes_valid':True,'all_inputs_match_packaged_payload':True,'input_files':len(inputs),
        'criteria_sha256':release['criteria_sha256'],'payload_sha256':release['payload_sha256'],
        'candidate':release['candidate'],'load_frozen_passed':True,'model_pairing':pairing,
        'validation_admission_replayed':admitted,'review_diff_from_local':review_differences,
        'local_human_review_preserved':True,'remote_regression_tests_passed':211,'remote_validate_only':validations,
        'remote_cuda_preflight':read('cuda-preflight.stdout.log'),'stages':stages,
        'all_12_predictions_replayed':True,'metrics_recomputed_exactly':True,'call_triplets_reconciled':len(traces),
        'validation_issues':dict(issues),'exact_raw_citations_checked':citations,'exact_numeric_sources_checked':numeric_count,
        'derived_citation_additions':additions,'metrics':metrics,'summary':summary,
        'support_predictions':support,'support_precision':correct_support/support if support else None,
        'support_recall':correct_support/metrics['gold_support_count'],'contradict_recall':0.0,
        'paired_development_comparison':{'source':'stored cellfix5 full39 original-contract subset',
            'same_claim_context_gold':same,'n':len(cases),'cellfix5_correct':previous_correct,
            'cellfix6_correct':metrics['correct_labels'],'single_runtime_per_candidate':True,
            'causal_attribution_established':False},
        'incorrect_cases':[r['example_id'] for r in incorrect],
        'probe18_present':False,'full39_present':False,'validation30_inference_present':False,
        'new_gpu_inference_during_audit':False,'promoted_to_serving':False,
        'limitations':['Hash and log consistency is not a cryptographic signature of remote execution.',
            'The 12 cases are development diagnostics; no generalization guarantee.',
            'Validation gold review is not approval of new decomposition predictions.',
            'Historical baseline 37/39 is not cellfix6 full39 inference.']}
    write_once(REPO/'docs'/('atomic-verifier-cellfix6-smoke-audit-'+RUN+'.json'),json_bytes(report))
    write_once(REPO/'docs'/('atomic-verifier-cellfix6-smoke-diagnostics-'+RUN+'.json'),json_bytes(incorrect))
    print(json.dumps({k:report[k] for k in ('run_id','all_12_predictions_replayed','metrics','incorrect_cases','paired_development_comparison')},indent=2))


if __name__=='__main__':
    main()
