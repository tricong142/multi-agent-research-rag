"""Audit supplied output as data; replay only locally released, hash-verified source."""
from collections import Counter
from copy import deepcopy
import hashlib
import importlib
import importlib.util
import io
import json
from pathlib import Path
import sys
from unittest.mock import patch
import zipfile

from scripts.audit_atomic_cellfix3 import extract
from scripts.atomic_validation_review import write_once,json_bytes

ROOT=Path(__file__).resolve().parents[1]
RUN='20261102T120149Z-ca882061'
ARCHIVE=ROOT.parent/('output-cellfix14-kaggle-'+RUN+'.zip')
BASE=ROOT/'research-runs'/('audit-cellfix14-full39-'+RUN)
OUT=BASE/'artifact'
sha=lambda raw:hashlib.sha256(raw).hexdigest()


def main():
    release=json.loads((ROOT/'docs/atomic-verifier-cellfix14-release.json').read_bytes())
    candidate=json.loads((ROOT/'docs/atomic-verifier-cellfix14-candidate.json').read_bytes())
    source=Path(candidate['source_root'])
    for name,expected in release['files'].items():assert sha((ROOT/name).read_bytes())==expected,name
    for name,item in candidate['input_manifest'].items():
        raw=(source/name).read_bytes();assert len(raw)==item['size'] and sha(raw)==item['sha256'],name
    raw=ARCHIVE.read_bytes();write_once(BASE/'original-output.zip',raw)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        assert len(z.infolist())<1000 and sum(i.file_size for i in z.infolist())<256*1024*1024
        manifest=json.loads(z.read('output-manifest.json'));assert manifest['run_id']==RUN
        names=[v['path'] for v in manifest['files']]
        assert len(names)==len(set(names))
        assert set(z.namelist())==set(names)|{'output-manifest.json'}
        for item in manifest['files']:
            data=z.read(item['path']);assert len(data)==item['size'] and sha(data)==item['sha256'],item['path']
        inputs=json.loads(z.read('input-manifest.json'));payload=z.read('frozen-inputs.zip')
        assert inputs==release['payload_files'] and sha(payload)==release['payload_sha256']
        extract(z,OUT)
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        assert z.testzip() is None and len(z.namelist())==len(set(z.namelist()))
        assert set(z.namelist())==set(inputs)
        for name,item in inputs.items():
            data=z.read(name);assert len(data)==item['size'] and sha(data)==item['sha256'],name
        source=BASE/'workspace'
        extract(z,source)
    read=lambda name:json.loads((OUT/name).read_bytes())
    lines=lambda name:[json.loads(v) for v in (OUT/name).read_bytes().splitlines()]
    for key in ('candidate','criteria_sha256','payload_sha256'):
        assert read('notebook-provenance.json')[key]==release[key]
    sys.path.insert(0,str(source))
    spec=importlib.util.spec_from_file_location('cf14_audit_workflow',source/'atomic_workflow_cellfix14.py')
    w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w);r=w.r
    assert Path(r.__file__).resolve().is_relative_to(source)
    frozen,all_cases,data,contract,_,baseline,baseline_metrics=r.load_frozen(r.CRITERIA)
    assert r.sha256(r.CRITERIA)==release['criteria_sha256']
    admission=r.require_probe_review(OUT/'reviewed-probe')
    assert admission==read('verifier39/probe-admission.json')
    reports={};failed=[]
    for folder in ('assessment-smoke','decomposition-probe','verifier39'):
        if folder=='decomposition-probe':effective,cases,_=r.probe_configuration(frozen,all_cases,r.CRITERIA)
        elif folder=='assessment-smoke':effective,cases=r.smoke_configuration(frozen,all_cases)
        else:effective,cases=frozen,all_cases
        assert read(folder+'/cases.json')==cases
        assert (OUT/folder/'criteria.json').read_bytes()==r.CRITERIA.read_bytes()
        assert read(folder+'/baseline.json')==baseline and read(folder+'/baseline-metrics.json')==baseline_metrics
        provenance=read(folder+'/provenance.json')
        assert provenance['criteria_sha256']==release['criteria_sha256']
        assert provenance['source_sha256']==frozen['source_sha256'] and provenance['prompt_sha256']==frozen['prompt_sha256']
        for key in ('model_files','shared_tokenizer_files','repo_id','revision','dtype','quantization','seed','do_sample'):
            assert provenance['model'][key]==baseline['model_metadata'][key],key
        assert provenance['model']['structured_decoder']==frozen['structured_decoder']
        assert provenance['model']['max_new_tokens']==frozen['max_new_tokens']
        outputs,events=lines(folder+'/predictions.jsonl'),lines(folder+'/calls.jsonl')
        assert [v['example_id'] for v in outputs]==[v['example_id'] for v in cases]
        for case,row in zip(cases,outputs):r.replay_result(row['result'],case['claim'],case.get('context',''),effective)
        if folder=='decomposition-probe':
            metrics=r.score_probe(outputs,cases,effective)
            generations=[e for e in events if e['event']=='generation']
            metrics['generated_tokens']=sum(e['generated_tokens'] for e in generations)
            metrics['prompt_tokens']=sum(e['prompt_tokens'] for e in generations)
            traces=[t for row in outputs for t in row['result']['trace']]
            metrics['checks']['within_measured_token_budget']=(len(generations)==len(traces) and metrics['generated_tokens']<=effective['maximum_generated_tokens'] and all(g['generated_tokens']<=effective['max_new_tokens'] for g in generations))
            metrics['checks']['structured_decoding_trace_complete']=r.decoding_trace_complete(generations,[t['messages'] for t in traces],effective)
            metrics['checks']['cooperative_deadline_trace_complete']=all(t.get('cooperative_deadline') is True for t in traces)
            metrics['automated_gate_pass']=all(metrics['checks'].values())
        else:
            metrics=w.measured_score(outputs,cases,effective,events)
            # The shared workflow adds this diagnostic field; the frozen main
            # runner stores the same usage checks without this additional key.
            assert metrics.pop('usage_complete') is True
        assert metrics==read(folder+'/metrics.json'),folder
        for row in outputs:
            if row['result']['status']!='completed':
                case=next(c for c in cases if c['example_id']==row['example_id'])
                failed.append({'stage':folder,'case':case,'result':row['result']})
        reports[folder]={'metrics':metrics,'event_counts':dict(Counter(e['event'] for e in events)),
                         'max_case_elapsed_ms':max(row['result']['elapsed_ms'] for row in outputs)}
        print('Replayed '+folder,flush=True)
    assert len(failed)==1
    failure=failed[0];result=failure['result']
    assessments=[t for t in result['trace'] if t['stage']!='decompose']
    request=json.loads(assessments[0]['messages'][1]['content'])
    # Actual LMFE token filtering with the released tiny tokenizer. No weights.
    h=importlib.import_module('research_rag.tests.test_atomic_assessment_v8')
    token_tests=importlib.import_module('research_rag.tests.test_atomic_decoding')
    messages=[{'role':'system','content':r.atomic.ASSESS_PROMPT},
              {'role':'user','content':json.dumps(request)}]
    backend=token_tests.token_backend()
    def accepts(value):
        callback=backend.generation_options(messages)['prefix_allowed_tokens_fn']
        ids=token_tests.Sequence([ord('P')])
        for char in h.AssessmentTokenFilterTests().ordered(value):
            if ord(char) not in callback(0,ids):return False
            ids.append(ord(char))
        return 0 in callback(0,ids)
    bad=deepcopy(assessments[0]['output'])
    bad_allowed=accepts(bad)
    try:r.atomic.assess_part(bad,request['part'],request['context'])
    except ValueError as exc:bad_issue=str(exc)
    else:raise AssertionError('Received invalid record was accepted')
    good=deepcopy(bad);good['observations'][0].update(member='Silver',truth='unknown')
    corrected=r.atomic.assess_part(good,request['part'],request['context'])
    assert corrected['assessed_label']=='not_enough_info'
    good_allowed=accepts(good)
    focus=importlib.import_module('04_factchecker.inference.assessment_focus')
    members=importlib.import_module('04_factchecker.inference.assessment_members')
    previous=focus.observation_focus_issue
    def local_absence_guard(part,member,quotes,truth,context):
        if truth!='unknown' and members.member_absence_quotes(part,member,context):
            return 'missing_evidence_is_not_false'
        return previous(part,member,quotes,truth,context)
    # Counterfactual in memory only: do not change source, prompts, gold or predictions.
    with patch.object(focus,'observation_focus_issue',local_absence_guard):
        guarded_bad_allowed=accepts(bad);guarded_good_allowed=accepts(good)
        assert r.atomic.assess_part(good,request['part'],request['context'])['assessed_label']=='not_enough_info'
    assert bad_allowed and good_allowed and not guarded_bad_allowed and guarded_good_allowed
    proof={'received_output_allowed_by_frozen_filter':bad_allowed,'received_output_rejected_by_validator':bad_issue,
           'corrected_unknown_allowed_by_frozen_filter':good_allowed,'corrected_unknown_label':corrected['assessed_label'],
           'counterfactual_guard_rejects_bad_tokens':not guarded_bad_allowed,'counterfactual_guard_keeps_unknown_tokens':guarded_good_allowed,
           'kind':'tiny_tokenizer_actual_LMFE_and_validator_counterfactual_not_model_prediction',
           'source_modified':False,'new_inference':False}
    assert not (OUT/'validation30').exists()
    report={'run_id':RUN,'candidate':release['candidate'],'zip_sha256':sha(raw),
        'output_files':len(manifest['files']),'input_files':len(inputs),'all_output_hashes_valid':True,
        'all_input_bytes_match_release':True,'all_stages_replayed_and_metrics_recomputed':True,
        'criteria_sha256':release['criteria_sha256'],'probe_admission':admission,'results':reports,
        'failed_case':failure['case'],'failed_case_stop_reason':result['stop_reason'],
        'failed_case_elapsed_ms':result['elapsed_ms'],'failed_case_budget':result['budget'],
        'assessment_attempts':[{'attempt':t['attempt'],'output':t['output'],'validation_issue':t.get('validation_issue'),'elapsed_ms':t['elapsed_ms']} for t in assessments],
        'decoder_validator_proof':proof,'validation30_run':False,'new_inference_during_audit':False,'promoted_to_serving':False,
        'limitations':['No new model inference. Counterfactual is not a prediction or a released candidate.',
                      'Human review admission validates submitted metadata/content; it does not attest reviewer identity.',
                      'Archive payload hashes establish internal consistency, not notebook or hardware attestation.']}
    target=ROOT/'docs'/('atomic-verifier-cellfix14-full39-audit-'+RUN+'.json')
    target.write_bytes(json_bytes(report))
    write_once(BASE/'failed-case.json',json_bytes(failure))
    print(json.dumps({'report':str(target),'failed_case':failure['case']['example_id'],'proof':proof},ensure_ascii=False))


if __name__=='__main__':main()
