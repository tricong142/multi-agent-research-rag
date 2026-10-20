"""Audit the received full39 ZIP against the release; replay without model inference."""
from collections import Counter
import hashlib
import importlib
import io
import json
from pathlib import Path
import sys
import zipfile

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from scripts.audit_atomic_cellfix3 import extract

RUN='20261018T153854Z-2c3e0bd6'
ARCHIVE=REPO.parent/('output-cellfix5-full39-'+RUN+'.zip')
BASE=REPO/'research-runs'/('audit-cellfix5-full39-'+RUN)
ROOT,OUT=BASE/'workspace',BASE/'artifact'
sha=lambda b:hashlib.sha256(b).hexdigest()


def main():
    with zipfile.ZipFile(ARCHIVE) as z:
        manifest=json.loads(z.read('output-manifest.json'))
        assert manifest['run_id']==RUN
        names=[r['path'] for r in manifest['files']]
        assert len(names)==len(set(names)) and set(z.namelist())==set(names)|{'output-manifest.json'}
        for item in manifest['files']:
            raw=z.read(item['path'])
            assert len(raw)==item['size'] and sha(raw)==item['sha256'],item['path']
        extract(z,OUT)
    read=lambda n:json.loads((OUT/n).read_text(encoding='utf-8'))
    lines=lambda n:[json.loads(s) for s in (OUT/n).read_text(encoding='utf-8').splitlines()]
    release=json.loads((REPO/'docs/atomic-verifier-cellfix5-full39-colab-release.json').read_text(encoding='utf-8'))
    fresh=json.loads((REPO/'docs/atomic-verifier-cellfix5-fresh-colab-release.json').read_text())
    for catalog in (release,fresh):
        for name,digest in catalog['files'].items():assert sha((REPO/name).read_bytes())==digest,name
    inputs=read('input-manifest.json');payload=(OUT/'frozen-inputs.zip').read_bytes()
    assert inputs==fresh['payload_files'] and sha(payload)==fresh['payload_sha256']==release['payload_sha256']
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        assert set(z.namelist())==set(inputs)
        extract(z,ROOT)
    for name,item in inputs.items():assert sha((ROOT/name).read_bytes())==item['sha256'],name
    original=(OUT/'probe-original.zip').read_bytes()
    assert sha(original)==release['original_probe_zip_sha256']
    with zipfile.ZipFile(io.BytesIO(original)) as z:
        original_manifest=json.loads(z.read('output-manifest.json'))
        assert original_manifest['run_id']==release['original_probe_run']
        assert set(z.namelist())=={r['path'] for r in original_manifest['files']}|{'output-manifest.json'}
        for item in original_manifest['files']:
            raw=z.read(item['path']);assert len(raw)==item['size'] and sha(raw)==item['sha256']
            if item['path'].startswith('decomposition-probe/'):
                relative=item['path'].split('/',1)[1]
                if relative=='semantic-review.json':
                    assert json.loads(raw)['review_completed'] is False
                else:assert (OUT/'reviewed-probe'/relative).read_bytes()==raw,relative
    sys.path.insert(0,str(ROOT))
    e=importlib.import_module('research_rag.evaluation.evaluate_atomic_verifier')
    assert Path(e.__file__).resolve().is_relative_to(ROOT)
    criteria_path=ROOT/'research_rag/evaluation/atomic_verifier_criteria_v8.json'
    frozen,cases,data_inputs,contract,_,baseline,baseline_metrics=e.load_frozen(criteria_path)
    assert sha(criteria_path.read_bytes())==release['criteria_sha256']
    admitted=e.require_probe_review(OUT/'reviewed-probe',criteria_path)
    assert admitted==read('probe-admission.stdout.log')==read('verifier39/probe-admission.json')==release['human_review']
    assert cases==read('verifier39/cases.json')
    for name,path in data_inputs.items():assert (OUT/'verifier39'/(name+'.jsonl')).read_bytes()==path.read_bytes()
    assert read('verifier39/baseline.json')==baseline and read('verifier39/baseline-metrics.json')==baseline_metrics
    assert (OUT/'verifier39/criteria.json').read_bytes()==criteria_path.read_bytes()
    assert (OUT/'verifier39/contract.json').read_bytes()==contract.read_bytes()
    provenance=read('verifier39/provenance.json');model=provenance['model']
    assert provenance['criteria_sha256']==release['criteria_sha256']
    assert provenance['source_sha256']==frozen['source_sha256'] and provenance['prompt_sha256']==frozen['prompt_sha256']
    keys=('model_files','shared_tokenizer_files','repo_id','revision','dtype','quantization','seed','do_sample')
    pairing={k:model[k]==baseline['model_metadata'][k] for k in keys}
    assert all(pairing.values()) and pairing==provenance['historical_model_pairing']
    assert model['structured_decoder']==frozen['structured_decoder'] and model['max_new_tokens']==frozen['max_new_tokens']
    assert provenance['serving_modified'] is False
    notebook=read('notebook-provenance.json')
    assert notebook['candidate']==release['candidate'] and notebook['criteria_sha256']==release['criteria_sha256']
    assert notebook['payload_sha256']==release['payload_sha256']
    assert notebook['original_probe_zip_sha256']==release['original_probe_zip_sha256']
    assert notebook['semantic_review_sha256']==admitted['semantic_review_sha256']
    rows=lines('verifier39/predictions.jsonl')
    assert [r['example_id'] for r in rows]==[c['example_id'] for c in cases]
    metrics=e.score(rows,cases,frozen)
    events=lines('verifier39/calls.jsonl')
    starts=[r for r in events if r['event']=='call_started']
    gens=[r for r in events if r['event']=='generation']
    finishes=[r for r in events if r['event']=='call_finished']
    traces=[(r['example_id'],t) for r in rows for t in r['result']['trace']]
    assert len(starts)==len(gens)==len(finishes)==len(traces)==metrics['backend_calls']
    issues=Counter();citations=numeric=additions=0
    for index,((cid,t),start,gen,finish) in enumerate(zip(traces,starts,gens,finishes),1):
        assert start['call_id']==gen['call_id']==finish['call_id']==index
        assert start['example_id']==gen['example_id']==finish['example_id']==cid
        assert start['messages']==finish['messages']==t['messages']
        assert gen['json_valid'] is True and gen['parse_error_type'] is None
        assert json.loads(gen['raw_output'])==finish['parsed_output']==t['output']
        assert start['max_new_tokens']==gen['max_new_tokens']==finish['max_new_tokens']==t['max_new_tokens']==frozen['max_new_tokens']
        p=json.loads(t['messages'][1]['content']);before=json.dumps(t['output'],sort_keys=True)
        try:
            if t['stage']=='decompose':e.atomic.normalize_decomposition(t['output'],p['claim'])
            else:
                checked=e.atomic.assess_part(t['output'],p['part'],p['context'])
                for obs in checked['observations']:
                    assert all(q in p['context'] for q in obs['quotes'])
                    additions+=len(obs['citation_additions'])
        except ValueError as exc:
            assert str(exc)==t['validation_issue'],(cid,str(exc))
        else:assert t.get('valid') is True and not t.get('validation_issue')
        assert json.dumps(t['output'],sort_keys=True)==before
        issues[t.get('validation_issue') or 'valid']+=1
        if t['stage']!='decompose':
            for obs in t['output']['observations']:
                assert obs['member'] in p['context']
                for q in obs['quotes']:assert q in p['context'];citations+=1
                checks=obs['numeric'] if isinstance(obs['numeric'],list) else [obs['numeric']] if obs['numeric'] else []
                for record in checks:
                    assert record['source_quote'] in p['context']
                    assert record['right']['quote'] in record['source_quote']
                    assert record['left']['quote'] in p['part']['quote'] or record['kind']=='change'
                    numeric+=1
    metrics['generated_tokens']=sum(g['generated_tokens'] for g in gens)
    metrics['prompt_tokens']=sum(g['prompt_tokens'] for g in gens)
    metrics['checks']['within_measured_token_budget']=(metrics['generated_tokens']<=frozen['maximum_generated_tokens']
        and all(g['generated_tokens']<=frozen['max_new_tokens'] for g in gens))
    metrics['checks']['structured_decoding_trace_complete']=e.decoding_trace_complete(gens,[t['messages'] for _,t in traces],frozen)
    metrics['checks']['cooperative_deadline_trace_complete']=all(t['cooperative_deadline'] for _,t in traces)
    metrics['automated_gate_pass']=all(metrics['checks'].values())
    assert metrics==read('verifier39/metrics.json')
    summary=read('verifier39/summary.json')
    assert summary['experiment_completed'] is True and summary['prediction_count']==len(rows)
    assert summary['automated_gate_pass']==metrics['automated_gate_pass']
    assert summary['backend_calls']==len(traces) and summary['overall_pass'] is False
    assert summary['promoted_to_serving'] is False and summary['human_review']=='pending'
    reviews=lines('verifier39/evidence-review.jsonl')
    assert len(reviews)==len(rows)
    for case,row,review in zip(cases,rows,reviews):
        assert case['example_id']==row['example_id']==review['example_id']
        assert review['result']==row['result']
        assert review['review_status']=='pending' and review['reviewer']==''
        assert all(v is None for v in review['judgments'].values())
    statuses=read('status.json')
    assert statuses['verifier39']['exit_code']==(0 if metrics['automated_gate_pass'] else 1)
    assert all(s['exit_code']==0 and s['state']=='completed' for n,s in statuses.items() if n!='verifier39')
    assert 'Ran 181 tests' in (OUT/'regression.stderr.log').read_text() and (OUT/'regression.stderr.log').read_text().rstrip().endswith('OK')
    validations={}
    for name,count,calls in (('probe',18,36),('smoke',12,96),('verifier',39,312)):
        validations[name]=read(name+'-validate-only.stdout.log')
        assert validations[name]=={'freeze_valid':True,'cases':count,'maximum_calls':calls}
    support=sum(r['result']['assessed_label']=='support' for r in rows)
    support_correct=sum(r['result']['assessed_label']=='support' and c['label']=='support' for r,c in zip(rows,cases))
    report={'run_id':RUN,'zip_sha256':sha(ARCHIVE.read_bytes()),'output_files':len(manifest['files'])+1,
        'all_output_hashes_valid':True,'all_input_bytes_match_released_payload':True,
        'input_files':len(inputs),'source_fixture_files':len(frozen['source_sha256']),
        'criteria_sha256':release['criteria_sha256'],'payload_sha256':release['payload_sha256'],
        'original_probe_zip_preserved':True,'human_probe_admission_replayed':admitted,
        'remote_regression_tests_passed':181,'remote_validate_only':validations,
        'remote_cuda_preflight':read('cuda-preflight.stdout.log'),'notebook_provenance':notebook,
        'model_pairing':pairing,'all_39_predictions_replayed':True,'metrics_recomputed_exactly':True,
        'call_triplets_reconciled':len(traces),'validation_issues':dict(issues),
        'exact_raw_citations_checked':citations,'exact_numeric_sources_checked':numeric,'derived_citation_additions':additions,
        'metrics':metrics,'summary':summary,'stages':statuses,
        'label_accuracy':metrics['correct_labels']/39,'support_predictions':support,
        'support_precision':support_correct/support if support else None,
        'support_recall':support_correct/metrics['gold_support_count'],
        'wrong_case_ids':[c['example_id'] for c,r in zip(cases,rows) if c['label']!=r['result']['assessed_label']],
        'case_elapsed_ms':{r['example_id']:r['result'].get('elapsed_ms') for r in rows},
        'evidence_review_status':'pending','new_gpu_inference_during_audit':False,'promoted_to_serving':False,
        'limitations':['Hash consistency is not independent attestation of remote execution.',
            '39 cases are inspected development data, not held-out evaluation.',
            'Zero false support does not imply correct labels or adequate support recall.'],
        'audit_script_sha256':sha(Path(__file__).read_bytes())}
    target=REPO/'docs'/('atomic-verifier-cellfix5-full39-audit-'+RUN+'.json')
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'report':str(target),'metrics':metrics,'wrong_case_ids':report['wrong_case_ids']},ensure_ascii=False))


if __name__=='__main__':main()
