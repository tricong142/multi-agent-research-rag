"""Audit received bytes, reproduce admission failure and verify the compatibility fix."""
from collections import Counter
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import zipfile

from scripts.audit_atomic_cellfix3 import extract
from scripts.atomic_validation_review import write_once,json_bytes
from scripts.atomic_cellfix15_replay_compat import patch_workflow

ROOT = Path(__file__).resolve().parents[1]
RUN = '20261102T163553Z-ed00dfbc'
BASE = ROOT/'research-runs'/('audit-cellfix15-full39-'+RUN)
ARCHIVE = ROOT.parent/('output-cellfix15-kaggle-'+RUN+'.zip')
sha = lambda raw:hashlib.sha256(raw).hexdigest()


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result


def main():
    release=json.loads((ROOT/'docs/atomic-verifier-cellfix15-release.json').read_bytes())
    for name,expected in release['files'].items():
        assert sha((ROOT/name).read_bytes())==expected,name
    raw=ARCHIVE.read_bytes();write_once(BASE/'original-output.zip',raw)
    out=BASE/'artifact';source=BASE/'workspace'
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        assert len(z.infolist())<1000 and sum(i.file_size for i in z.infolist())<256*1024*1024
        manifest=json.loads(z.read('output-manifest.json'));assert manifest['run_id']==RUN
        assert set(z.namelist())=={v['path'] for v in manifest['files']}|{'output-manifest.json'}
        for item in manifest['files']:
            data=z.read(item['path']);assert len(data)==item['size'] and sha(data)==item['sha256'],item['path']
        inputs=json.loads(z.read('input-manifest.json'));payload=z.read('frozen-inputs.zip')
        assert inputs==release['payload_files'] and sha(payload)==release['payload_sha256']
        extract(z,out)
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        assert set(z.namelist())==set(inputs)
        for name,item in inputs.items():
            data=z.read(name);assert len(data)==item['size'] and sha(data)==item['sha256'],name
        extract(z,source)
    read=lambda name:json.loads((out/name).read_bytes())
    rows=lambda name:[json.loads(v) for v in (out/name).read_bytes().splitlines()]
    for key in ('candidate','criteria_sha256','payload_sha256'):
        assert read('notebook-provenance.json')[key]==release[key]
    sys.path.insert(0,str(source))
    w=module('cellfix15_original_audit',source/'atomic_workflow_cellfix15.py');r=w.r
    assert Path(r.__file__).resolve().is_relative_to(source)
    frozen,all_cases,_,_,_,baseline,baseline_metrics=r.load_frozen(r.CRITERIA)
    assert r.sha256(r.CRITERIA)==release['criteria_sha256']
    admission=r.require_probe_review(out/'reviewed-probe')
    assert admission==read('verifier39/probe-admission.json')
    reports={}
    for folder in ('assessment-smoke','decomposition-probe','verifier39'):
        if folder=='decomposition-probe':effective,cases,_=r.probe_configuration(frozen,all_cases,r.CRITERIA)
        elif folder=='assessment-smoke':effective,cases=r.smoke_configuration(frozen,all_cases)
        else:effective,cases=frozen,all_cases
        assert read(folder+'/cases.json')==cases
        assert (out/folder/'criteria.json').read_bytes()==r.CRITERIA.read_bytes()
        assert read(folder+'/baseline.json')==baseline and read(folder+'/baseline-metrics.json')==baseline_metrics
        provenance=read(folder+'/provenance.json')
        assert provenance['criteria_sha256']==release['criteria_sha256']
        assert provenance['source_sha256']==frozen['source_sha256'] and provenance['prompt_sha256']==frozen['prompt_sha256']
        for key in ('model_files','shared_tokenizer_files','repo_id','revision','dtype','quantization','seed','do_sample'):
            assert provenance['model'][key]==baseline['model_metadata'][key],key
        assert provenance['model']['structured_decoder']==frozen['structured_decoder']
        assert provenance['model']['max_new_tokens']==frozen['max_new_tokens']
        predictions,events=rows(folder+'/predictions.jsonl'),rows(folder+'/calls.jsonl')
        assert [v['example_id'] for v in predictions]==[c['example_id'] for c in cases]
        for case,row in zip(cases,predictions):
            r.replay_result(row['result'],case['claim'],case.get('context',''),effective)
        if folder=='decomposition-probe':
            score=r.score_probe(predictions,cases,effective)
            generations=[e for e in events if e['event']=='generation']
            traces=[t for row in predictions for t in row['result']['trace']]
            assert len(generations)==len(traces) and all(g.get('usage_complete',True) for g in generations)
            score['generated_tokens']=sum(g['generated_tokens'] for g in generations)
            score['prompt_tokens']=sum(g['prompt_tokens'] for g in generations)
            score['checks']['within_measured_token_budget']=(score['generated_tokens']<=effective['maximum_generated_tokens'] and all(g['generated_tokens']<=effective['max_new_tokens'] for g in generations))
            score['checks']['structured_decoding_trace_complete']=r.decoding_trace_complete(generations,[t['messages'] for t in traces],effective)
            score['checks']['cooperative_deadline_trace_complete']=all(t.get('cooperative_deadline') is True for t in traces)
            score['automated_gate_pass']=all(score['checks'].values())
        else:
            score=w.measured_score(predictions,cases,effective,events)
            assert score.pop('usage_complete') is True
        assert score==read(folder+'/metrics.json'),folder
        reports[folder]={'metrics':score,'event_counts':dict(Counter(v['event'] for v in events))}
        print('Verified '+folder,flush=True)
    full=out/'verifier39';predictions=rows('verifier39/predictions.jsonl')
    received=w.measured_score(predictions,all_cases,frozen,rows('verifier39/calls.jsonl'))
    stored=read('verifier39/metrics.json')
    difference={k:{'replay':received.get(k),'stored':stored.get(k),'stored_present':k in stored}
                for k in received.keys()|stored.keys() if received.get(k)!=stored.get(k) or (k in received)!=(k in stored)}
    assert set(difference)=={'usage_complete'} and received['usage_complete'] is True
    review_paths=[p for p in (out/'review-attempts').glob('*.json')
        if json.loads(p.read_bytes()).get('predictions_sha256')==r.sha256(full/'predictions.jsonl')]
    assert len(review_paths)==1
    compatibility=BASE/'compatibility/atomic_workflow_cellfix15.py'
    write_once(compatibility,patch_workflow((source/'atomic_workflow_cellfix15.py').read_bytes()))
    patched=module('cellfix15_compatible_audit',compatibility)
    with tempfile.TemporaryDirectory(dir=BASE,prefix='full39-admission-audit-') as tmp:
        staged=Path(tmp)/'full39';shutil.copytree(full,staged)
        (staged/'semantic-review.json').write_bytes(review_paths[0].read_bytes())
        try:w.require_full39(staged,out/'reviewed-probe')
        except ValueError as exc:original_error=str(exc)
        else:raise AssertionError('Original admission unexpectedly passed')
        assert original_error=='Full39 gate failed on replay'
        accepted=patched.require_full39(staged,out/'reviewed-probe')
    assert not (out/'validation30').exists()
    none=next(row for row in predictions if row['example_id']=='scope:none:not_enough_info')
    assert none['result']['status']=='completed' and none['result']['assessed_label']=='not_enough_info'
    # The immutable extracted output remains byte-identical after all replay checks.
    for item in manifest['files']:
        assert sha((out/item['path']).read_bytes())==item['sha256'],item['path']
    report=dict(run_id=RUN,archive_sha256=sha(raw),verified_outputs=len(manifest['files']),
        verified_payload_inputs=len(inputs),criteria_sha256=release['criteria_sha256'],stages=reports,
        original_admission_error=original_error,metrics_difference=difference,
        compatible_admission=accepted,review_json_sha256=sha(review_paths[0].read_bytes()),
        member_local_absence_case=none,new_model_inference_completed=False,
        validation30_started=False,original_outputs_unchanged=True,frozen_release_unchanged=True,
        compatibility_worker_sha256=sha(compatibility.read_bytes()))
    target=ROOT/'docs'/('atomic-verifier-cellfix15-full39-audit-'+RUN+'.json')
    target.write_bytes(json_bytes(report))
    print(json.dumps({'report':str(target),'correct_labels':stored['correct_labels'],
        'difference':difference,'compatibility_admission_passed':True,'validation30_started':False}))


if __name__=='__main__':main()
