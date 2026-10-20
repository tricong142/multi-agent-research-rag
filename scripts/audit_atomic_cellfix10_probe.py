"""Audit all cf10 smoke/probe artifacts and the attached HTML without new inference."""
from collections import Counter
import importlib.util
import io
import json
from pathlib import Path
import sys
import zipfile

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from scripts.audit_atomic_cellfix3 import extract
from scripts.atomic_validation_review import digest,json_bytes,write_once

RUN='20261020T145035Z-d525a354'
BASE=REPO/'research-runs'/('audit-cellfix10-fresh-'+RUN)
SOURCE,OUT=BASE/'workspace',BASE/'artifact'


def main():
    raw=(REPO.parent/('output-cellfix10-fresh-'+RUN+' (2).zip')).read_bytes()
    write_once(BASE/'original-output.zip',raw)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        manifest=json.loads(archive.read('output-manifest.json'))
        assert manifest['run_id']==RUN
        names=[i['path'] for i in manifest['files']]
        assert len(names)==len(set(names))
        assert len(archive.namelist())==len(set(archive.namelist()))
        assert set(archive.namelist())==set(names)|{'output-manifest.json'}
        for item in manifest['files']:
            blob=archive.read(item['path'])
            assert len(blob)==item['size'] and digest(blob)==item['sha256'],item['path']
        extract(archive,OUT)
    html=(OUT/'decomposition-probe/HUMAN_REVIEW.html').read_bytes()
    write_once(BASE/'attached-HUMAN_REVIEW.html',html)
    read=lambda name:json.loads((OUT/name).read_bytes())
    lines=lambda name:[json.loads(s) for s in (OUT/name).read_bytes().splitlines()]
    release=json.loads((REPO/'docs/atomic-verifier-cellfix10-release.json').read_bytes())
    for name,expected in release['files'].items():assert digest((REPO/name).read_bytes())==expected,name
    payload=(OUT/'frozen-inputs.zip').read_bytes();inputs=read('input-manifest.json')
    assert inputs==release['payload_files'] and digest(payload)==release['payload_sha256']
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert len(archive.namelist())==len(set(archive.namelist()))
        assert set(archive.namelist())==set(inputs)
        extract(archive,SOURCE)
    for name,item in inputs.items():
        blob=(SOURCE/name).read_bytes()
        assert len(blob)==item['size'] and digest(blob)==item['sha256'],name
    sys.path.insert(0,str(SOURCE))
    spec=importlib.util.spec_from_file_location('audit_workflow',SOURCE/'atomic_workflow_cellfix10.py')
    w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
    r=w.r
    assert Path(r.__file__).resolve().is_relative_to(SOURCE)
    frozen,all_cases,data,contract,_,baseline,baseline_metrics=r.load_frozen(r.CRITERIA)
    assert r.sha256(r.CRITERIA)==release['criteria_sha256']
    binding=w.binding(SOURCE/'validation/cellfix10')
    assert binding==read('validation-lock.json')
    for remote,local in [('validation-annotation-review.json','annotation-review.json'),('validation-original-lock.json','original-lock.json')]:
        assert (OUT/remote).read_bytes()==(SOURCE/'validation/cellfix10'/local).read_bytes()
    results={}
    for folder in ('assessment-smoke','decomposition-probe'):
        probe=folder=='decomposition-probe'
        if probe:
            effective,cases,path=r.probe_configuration(frozen,all_cases,r.CRITERIA)
            sources={'probe-claims':path}
        else:
            effective,cases=r.smoke_configuration(frozen,all_cases);sources=data
        assert read(folder+'/cases.json')==cases
        assert read(folder+'/baseline.json')==baseline and read(folder+'/baseline-metrics.json')==baseline_metrics
        assert (OUT/folder/'criteria.json').read_bytes()==r.CRITERIA.read_bytes()
        assert (OUT/folder/'contract.json').read_bytes()==contract.read_bytes()
        for name,path in sources.items():assert (OUT/folder/(name+'.jsonl')).read_bytes()==path.read_bytes()
        provenance=read(folder+'/provenance.json');model=provenance['model']
        assert provenance['criteria_sha256']==release['criteria_sha256']
        assert provenance['source_sha256']==frozen['source_sha256'] and provenance['prompt_sha256']==frozen['prompt_sha256']
        assert provenance['serving_modified'] is False
        for key in ('model_files','shared_tokenizer_files','repo_id','revision','dtype','quantization','seed','do_sample'):
            assert model[key]==baseline['model_metadata'][key],key
        assert model['structured_decoder']==frozen['structured_decoder'] and model['max_new_tokens']==frozen['max_new_tokens']
        rows,events=lines(folder+'/predictions.jsonl'),lines(folder+'/calls.jsonl')
        assert [v['example_id'] for v in rows]==[v['example_id'] for v in cases]
        score=r.score_probe(rows,cases,effective) if probe else r.score(rows,cases,effective)
        starts=[v for v in events if v['event']=='call_started']
        gens=[v for v in events if v['event']=='generation']
        finishes=[v for v in events if v['event']=='call_finished']
        traces=[(row['example_id'],t) for row in rows for t in row['result']['trace']]
        assert len(starts)==len(gens)==len(finishes)==len(traces)==score['backend_calls']
        issues=Counter();citations=numeric_count=additions=0
        from importlib import import_module
        numeric_records=import_module('04_factchecker.inference.assessment_decisions').numeric_records
        reporting=import_module('04_factchecker.inference.assessment_reporting')
        replayed={v['example_id']:{'parts':[]} for v in rows}
        for index,((cid,t),start,gen,finish) in enumerate(zip(traces,starts,gens,finishes),1):
            assert start['call_id']==gen['call_id']==finish['call_id']==index
            assert start['example_id']==gen['example_id']==finish['example_id']==cid
            assert start['messages']==finish['messages']==t['messages']
            assert gen['json_valid'] is True and gen['parse_error_type'] is None
            assert json.loads(gen['raw_output'])==finish['parsed_output']==t['output']
            assert start['max_new_tokens']==gen['max_new_tokens']==finish['max_new_tokens']==t['max_new_tokens']==frozen['max_new_tokens']
            request=json.loads(t['messages'][1]['content']);before=json.dumps(t['output'],sort_keys=True)
            try:
                if t['stage']=='decompose':
                    normalized=r.atomic.normalize_decomposition(t['output'],request['claim'])
                else:
                    assert t['output']['explanation']==reporting.ASSESSMENT_NOTE
                    assert all(o['explanation']==reporting.OBSERVATION_NOTE for o in t['output']['observations'])
                    assert all(v==reporting.missing_reason(request['part'],request['context']) for v in t['output']['missing_information'])
                    checked=r.atomic.assess_part(t['output'],request['part'],request['context'])
                    for observation in checked['observations']:
                        assert all(q in request['context'] for q in observation['quotes'])
                        citations+=len(observation['quotes']);additions+=len(observation['citation_additions'])
                        for record in numeric_records(observation['numeric'],checked['numeric_requirements']):
                            assert record['source_quote'] in request['context']
                            assert record['right']['quote'] in record['source_quote']
                            assert record['left']['quote'] in request['part']['quote'] or record['kind']=='change'
                            numeric_count+=1
            except ValueError as exc:assert str(exc)==t.get('validation_issue'),(cid,str(exc))
            else:
                assert t.get('valid') is True and not t.get('validation_issue')
                if t['stage']=='decompose':replayed[cid]['decomposition']=normalized
                else:replayed[cid]['parts'].append(checked)
            assert json.dumps(t['output'],sort_keys=True)==before
            issues[t.get('validation_issue') or 'valid']+=1
        for row in rows:
            stored=row['result'];actual=replayed[row['example_id']]
            assert stored['decomposition']==actual['decomposition']
            assert stored['parts']==actual['parts']
            assert stored['policy']==frozen['policy']
            assert stored['stop_reason']=='completed' and stored['status']=='completed'
            if not probe:
                labels=[p['assessed_label'] for p in actual['parts']]
                label='contradict' if 'contradict' in labels else 'support' if all(v=='support' for v in labels) else 'not_enough_info'
                assert stored['assessed_label']==label
                assert len(actual['parts'])==len(actual['decomposition']['parts'])
        score['generated_tokens']=sum(g['generated_tokens'] for g in gens)
        score['prompt_tokens']=sum(g['prompt_tokens'] for g in gens)
        score['checks']['within_measured_token_budget']=(score['generated_tokens']<=effective['maximum_generated_tokens']
            and all(g['generated_tokens']<=frozen['max_new_tokens'] for g in gens))
        score['checks']['structured_decoding_trace_complete']=r.decoding_trace_complete(gens,[t['messages'] for _,t in traces],frozen)
        score['checks']['cooperative_deadline_trace_complete']=all(t.get('cooperative_deadline') is True for _,t in traces)
        score['automated_gate_pass']=all(score['checks'].values())
        assert score==read(folder+'/metrics.json') and score['automated_gate_pass'] is True
        summary=read(folder+'/summary.json')
        assert summary['experiment_completed'] and summary['prediction_count']==len(cases)
        assert summary['backend_calls']==len(traces) and summary['overall_pass'] is False
        assert summary['human_review']=='pending' and summary['promoted_to_serving'] is False
        reviews=lines(folder+'/evidence-review.jsonl');assert len(reviews)==len(rows)
        for row,review in zip(rows,reviews):
            assert row['example_id']==review['example_id'] and row['result']==review['result']
            assert review['review_status']=='pending' and review['reviewer']==''
            assert all(v is None for v in review['judgments'].values())
        results[folder]={'metrics':score,'call_triplets_reconciled':len(traces),'validation_issues':dict(issues),
            'exact_citations_checked':citations,'numeric_records_checked':numeric_count,
            'derived_citation_additions':additions,'predictions_sha256':r.sha256(OUT/folder/'predictions.jsonl')}
    review=read('decomposition-probe/semantic-review.json')
    assert review['review_completed'] is False and not review['reviewer']
    assert review['predictions_sha256']==results['decomposition-probe']['predictions_sha256']
    assert review['criteria_sha256']==release['criteria_sha256']
    try:r.require_probe_review(OUT/'decomposition-probe')
    except ValueError as exc:
        assert 'Completed human review bound to this probe is required' in str(exc);admission=str(exc)
    else:raise AssertionError('Unsigned probe must not admit full39')
    statuses=read('status.json');assert all(v['exit_code']==0 and v['state']=='completed' for v in statuses.values())
    regression=(OUT/'regression.stderr.log').read_text(encoding='utf-8')
    assert 'Ran 314 tests' in regression and regression.rstrip().endswith('OK')
    notebook=read('notebook-provenance.json')
    assert notebook['candidate']==release['candidate'] and notebook['criteria_sha256']==release['criteria_sha256'] and notebook['payload_sha256']==release['payload_sha256']
    assert not (OUT/'verifier39').exists() and not (OUT/'validation30').exists()
    report={'run_id':RUN,'candidate':release['candidate'],'zip_sha256':digest(raw),
        'output_files':len(manifest['files'])+1,'input_files':len(inputs),'criteria_sha256':release['criteria_sha256'],
        'payload_sha256':release['payload_sha256'],'all_output_hashes_valid':True,'all_input_bytes_match_release':True,
        'all_predictions_replayed':True,'metrics_recomputed_exactly':True,'model_revision_budget_gate_unchanged':True,
        'remote_regression_tests_passed':314,'remote_validate_only':{k:read(k+'-validate-only.stdout.log') for k in ('smoke','probe','verifier','validation30')},
        'html_matches_probe_exactly':True,'html_sha256':digest(html),'validation_binding_replayed':True,
        'results':results,'original_human_review_completed':False,'unsigned_review_admission_block':admission,
        'full39_present':False,'validation30_inference_present':False,'new_inference_during_audit':False,
        'limitations':['Stored provenance is consistency evidence, not a cryptographic signature of the Colab host.',
            'Probe decomposition validity is not label accuracy or false-support measurement.',
            'Smoke label correctness does not certify every model explanation.',
            'Full39 has not run for this cellfix10 run; historical baseline metrics are not new outcomes.']}
    write_once(REPO/'docs'/('atomic-verifier-cellfix10-smoke-probe-audit-'+RUN+'.json'),json_bytes(report))
    print(json.dumps({k:v for k,v in report.items() if k!='results'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
