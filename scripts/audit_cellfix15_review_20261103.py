"""Verify the received runtime and reproduce both admission blockers offline."""
from collections import Counter
import hashlib
import importlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import zipfile

from scripts.audit_atomic_cellfix3 import extract
from scripts.atomic_cellfix15_replay_compat import patch_workflow
from scripts.atomic_validation_review import write_once, json_bytes

ROOT=Path(__file__).resolve().parents[1]
RUN='20261103T070810Z-84730c0f'
BASE=ROOT/'research-runs'/('audit-cellfix15-review-'+RUN)
sha=lambda b:hashlib.sha256(b).hexdigest()


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result


def main():
    raw=(ROOT.parent/('output-cellfix15-kaggle-'+RUN+'.zip')).read_bytes()
    review_raw=(ROOT.parent/'semantic-review (8).json').read_bytes()
    write_once(BASE/'original-output.zip',raw)
    write_once(BASE/'submitted-review.json',review_raw)
    release=json.loads((ROOT/'docs/atomic-verifier-cellfix15-release.json').read_bytes())
    for n,h in release['files'].items():assert sha((ROOT/n).read_bytes())==h,n
    out,source=BASE/'artifact',BASE/'workspace'
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        assert len(z.infolist())<1000 and sum(i.file_size for i in z.infolist())<256*1024**2
        manifest=json.loads(z.read('output-manifest.json'));assert manifest['run_id']==RUN
        names=[v['path'] for v in manifest['files']]
        assert len(names)==len(set(names)) and set(z.namelist())==set(names)|{'output-manifest.json'}
        for item in manifest['files']:
            b=z.read(item['path']);assert len(b)==item['size'] and sha(b)==item['sha256'],item['path']
        payload=z.read('frozen-inputs.zip');inputs=json.loads(z.read('input-manifest.json'))
        assert sha(payload)==release['payload_sha256'] and inputs==release['payload_files']
        extract(z,out)
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        assert set(z.namelist())==set(inputs)
        for n,item in inputs.items():
            b=z.read(n);assert len(b)==item['size'] and sha(b)==item['sha256'],n
        extract(z,source)
    read=lambda p:json.loads(p.read_bytes())
    rows=lambda p:[json.loads(v) for v in p.read_bytes().splitlines()]
    provenance=read(out/'notebook-provenance.json')
    for k in ('candidate','criteria_sha256','payload_sha256'):assert provenance[k]==release[k]
    sys.path.insert(0,str(source))
    original=module('received_cf15_workflow',source/'atomic_workflow_cellfix15.py')
    r=original.r
    assert Path(r.__file__).resolve().is_relative_to(source)
    frozen,cases,*_=r.load_frozen(r.CRITERIA)
    predictions=rows(out/'verifier39/predictions.jsonl')
    events=rows(out/'verifier39/calls.jsonl')
    assert read(out/'verifier39/cases.json')==cases
    cache=importlib.import_module('04_factchecker.inference.cellfix14_runtime').decode_request
    with cache(None):score=original.measured_score(predictions,cases,frozen,events)
    stored=read(out/'verifier39/metrics.json')
    difference={k:dict(replayed=score.get(k),stored=stored.get(k),stored_present=k in stored)
                for k in score.keys()|stored.keys() if score.get(k)!=stored.get(k) or (k in score)!=(k in stored)}
    assert set(difference)=={'usage_complete'} and score['usage_complete'] is True
    assert score['automated_gate_pass'] is True and score['correct_labels']==39
    review=json.loads(review_raw)
    assert review['criteria_sha256']==release['criteria_sha256']
    assert review['predictions_sha256']==sha((out/'verifier39/predictions.jsonl').read_bytes())
    assert any(p.read_bytes()==review_raw for p in (out/'review-attempts').glob('*.json'))
    failed=[]
    by_id={v['example_id']:v['result'] for v in predictions}
    for c in review['cases']:
        rejected={k:v for k,v in c['judgments'].items() if v is not True}
        if rejected:failed.append(dict(example_id=c['example_id'],rejected=rejected,notes=c['notes'],actual_parts=by_id[c['example_id']]['parts']))
    compatible=BASE/'compatibility/atomic_workflow_cellfix15.py'
    write_once(compatible,patch_workflow((source/'atomic_workflow_cellfix15.py').read_bytes()))
    patched=module('compatible_cf15_workflow',compatible)
    errors={}
    with tempfile.TemporaryDirectory(dir=BASE,prefix='review-preflight-') as tmp:
        full=Path(tmp)/'full39';shutil.copytree(out/'verifier39',full)
        (full/'semantic-review.json').write_bytes(review_raw)
        for label,worker in [('original',original),('compatible',patched)]:
            with cache(None):
                try:worker.require_full39(full,out/'reviewed-probe')
                except ValueError as exc:errors[label]=str(exc)
                else:raise AssertionError('Review with negative judgments was admitted')
    assert errors['original']=='Full39 gate failed on replay'
    assert 'contract:causality_missing' in errors['compatible'] and 'missing_information_specific' in errors['compatible']
    assert not (out/'validation30').exists()
    for item in manifest['files']:assert sha((out/item['path']).read_bytes())==item['sha256']
    actual16=read(ROOT/'docs/atomic-verifier-cellfix16-release.json')
    notebook=ROOT/'scripts/kaggle_atomic_verifier_cellfix16.ipynb'
    notebook_check=read(ROOT/'docs/atomic-verifier-cellfix16-kaggle-validation.json')
    assert sha(notebook.read_bytes())==notebook_check['sha256']
    report=dict(run_id=RUN,archive_sha256=sha(raw),verified_outputs=len(manifest['files']),verified_inputs=len(inputs),
                actual_candidate=provenance['candidate'],actual_criteria_sha256=release['criteria_sha256'],
                intended_cellfix16_criteria_sha256=actual16['criteria_sha256'],review_sha256=sha(review_raw),
                review_bound_to_received_predictions=True,review_negative_cases=failed,metrics_difference=difference,
                replayed_metrics=score,admission_errors=errors,validation30_started=False,
                cellfix16_notebook_sha256=sha(notebook.read_bytes()),new_model_inference=False,
                original_outputs_and_review_unchanged=True)
    target=ROOT/'docs'/('atomic-verifier-cellfix15-review-audit-'+RUN+'.json')
    target.write_bytes(json_bytes(report))
    print(json.dumps({k:v for k,v in report.items() if k not in ('review_negative_cases','replayed_metrics')},indent=2),flush=True)


if __name__=='__main__':main()
