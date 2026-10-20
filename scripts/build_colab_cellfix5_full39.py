"""Admit the supplied human review, then package the unchanged candidate for full39."""
import base64
import hashlib
import importlib
import io
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
RUN='20261017T173345Z-905edcb5'
BASE=ROOT/'research-runs'/('audit-cellfix5-fresh-'+RUN)
SOURCE=BASE/'workspace'
ORIGINAL=ROOT.parent/('output-cellfix5-fresh-'+RUN+'.zip')
REVIEW=ROOT/'docs'/('semantic-review-cellfix5-'+RUN+'-human.json')
REVIEWED=ROOT/'research-runs/cellfix5-reviewed-probe'/RUN
ADMISSION=ROOT/'docs'/('atomic-verifier-cellfix5-human-admission-'+RUN+'.json')
TARGET=ROOT/'scripts/colab_atomic_verifier39_cellfix5.ipynb'
RELEASE=ROOT/'docs/atomic-verifier-cellfix5-full39-colab-release.json'
CRITERIA='research_rag/evaluation/atomic_verifier_criteria_v8.json'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()


def admit():
    received=ROOT.parent/'semantic-review.json'
    release=json.loads((ROOT/'docs/atomic-verifier-cellfix5-fresh-colab-release.json').read_text())
    audit=json.loads((ROOT/'docs'/('atomic-verifier-cellfix5-smoke-probe-audit-'+RUN+'.json')).read_text(encoding='utf-8'))
    assert sha(ORIGINAL)==audit['zip_sha256']
    assert sha(SOURCE/CRITERIA)==release['criteria_sha256']
    for name,item in release['payload_files'].items():
        assert sha(SOURCE/name)==item['sha256'],name
    data=received.read_bytes();review=json.loads(data.decode('utf-8-sig'))
    cases=json.loads((BASE/'artifact/decomposition-probe/cases.json').read_text())
    assert len(review['cases'])==18
    assert [(r['example_id'],r['claim']) for r in review['cases']]==[(r['example_id'],r['claim']) for r in cases]
    if REVIEW.exists():assert REVIEW.read_bytes()==data,'Saved human review differs; preserve it and inspect.'
    else:REVIEW.write_bytes(data)
    REVIEWED.mkdir(parents=True,exist_ok=True)
    for p in (BASE/'artifact/decomposition-probe').iterdir():
        target=REVIEWED/p.name
        if p.name=='semantic-review.json':
            if target.exists():assert target.read_bytes()==data
            else:target.write_bytes(data)
        elif target.exists():assert target.read_bytes()==p.read_bytes()
        else:shutil.copyfile(p,target)
    sys.path.insert(0,str(SOURCE))
    driver=importlib.import_module('research_rag.evaluation.evaluate_atomic_verifier')
    assert Path(driver.__file__).resolve().is_relative_to(SOURCE)
    record=driver.require_probe_review(REVIEWED,SOURCE/CRITERIA)
    assert record['semantic_review_sha256']==sha(REVIEW)
    assert json.loads((BASE/'artifact/decomposition-probe/semantic-review.json').read_text())['review_completed'] is False
    result={'candidate':release['candidate'],'probe_run':RUN,'criteria_sha256':release['criteria_sha256'],
        'human_review_completed':True,'admission_verified':True,**record,
        'review_file':REVIEW.relative_to(ROOT).as_posix(),'reviewed_probe_directory':str(REVIEWED),
        'received_review_file':str(received),'received_review_sha256':sha(received),
        'original_probe_zip_sha256':sha(ORIGINAL),'all_claim_texts_match_probe':True,
        'original_zip_and_unsigned_review_preserved':True,'model_inference_completed':False,
        'full39_inference_completed':False,'promoted_to_serving':False}
    ADMISSION.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'admission_verified':True,'reviewer':record['reviewer']},ensure_ascii=False),flush=True)


def build(release=False):
    admitted=json.loads(ADMISSION.read_text(encoding='utf-8'))
    assert admitted['admission_verified'] is True and admitted['human_review_completed'] is True
    assert sha(REVIEW)==admitted['semantic_review_sha256'] and sha(ORIGINAL)==admitted['original_probe_zip_sha256']
    previous=ROOT/'scripts/colab_atomic_verifier_cellfix5_fresh.ipynb'
    catalog=json.loads((ROOT/'docs/atomic-verifier-cellfix5-fresh-colab-release.json').read_text())
    for name,digest in catalog['files'].items():assert sha(ROOT/name)==digest,name
    assert admitted['criteria_sha256']==catalog['criteria_sha256']
    old=json.loads(previous.read_text(encoding='utf-8'))
    code=[c['source'] for c in old['cells'] if c['cell_type']=='code']
    assert len(code)==5
    setup=code[0]
    for before,after in (("'atomic-cellfix5-fresh-'","'atomic-cellfix5-full39-'"),
            ("'output-cellfix5-fresh-'","'output-cellfix5-full39-'")):
        assert setup.count(before)==1;setup=setup.replace(before,after)
    setup+='\nimport shutil\n'
    setup+='probe_zip_b64 = '+repr(base64.b64encode(ORIGINAL.read_bytes()).decode())+'\n'
    setup+='probe_zip_sha256 = '+repr(sha(ORIGINAL))+'\n'
    setup+='review_b64 = '+repr(base64.b64encode(REVIEW.read_bytes()).decode())+'\n'
    setup+='review_sha256 = '+repr(sha(REVIEW))+'\n'
    setup+='''try:
    probe_data=base64.b64decode(probe_zip_b64,validate=True)
    assert hashlib.sha256(probe_data).hexdigest()==probe_zip_sha256
    (out/'probe-original.zip').write_bytes(probe_data)
    original_probe=run_root/'probe-original'
    original_probe.mkdir(exist_ok=False)
    with zipfile.ZipFile(io.BytesIO(probe_data)) as archive:
        assert archive.testzip() is None
        records=json.loads(archive.read('output-manifest.json'))['files']
        names=[r['path'] for r in records]
        assert len(names)==len(set(names)) and set(archive.namelist())==set(names)|{'output-manifest.json'}
        for item in records:
            relative=PurePosixPath(item['path'])
            assert not relative.is_absolute() and '..' not in relative.parts and '\\\\' not in item['path'] and ':' not in item['path']
            data=archive.read(item['path'])
            assert len(data)==item['size'] and hashlib.sha256(data).hexdigest()==item['sha256']
            target=original_probe/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(data)
    reviewed_probe=out/'reviewed-probe'
    shutil.copytree(original_probe/'decomposition-probe',reviewed_probe)
    review_data=base64.b64decode(review_b64,validate=True)
    assert hashlib.sha256(review_data).hexdigest()==review_sha256
    (reviewed_probe/'semantic-review.json').write_bytes(review_data)
    provenance=json.loads((out/'notebook-provenance.json').read_text())
    provenance.update(purpose='probe-admitted full39',original_probe_run='''+repr(RUN)+''',
        original_probe_zip_sha256=probe_zip_sha256,semantic_review_sha256=review_sha256)
    (out/'notebook-provenance.json').write_text(json.dumps(provenance,indent=2))
    bundle()
except BaseException:
    download_archive()
    raise
print('Original probe preserved. Human review is installed only in a separate reviewed copy.')
'''
    admission='''try:
    admission_code="import json; from pathlib import Path; from research_rag.evaluation.evaluate_atomic_verifier import require_probe_review; print(json.dumps(require_probe_review(Path("+repr(str(reviewed_probe))+")),ensure_ascii=False))"
    run('probe-admission',[python,'-c',admission_code],timeout=300)
except BaseException:
    download_archive()
    raise
print('Human admission passed before model-cache downloads or inference.')
'''+code[2]
    run39='''full39_passed=False
try:
    required=('gpu-host','venv','bootstrap','torch','runtime','pip-check','pip-freeze','regression',
        'cuda-preflight','probe-validate-only','smoke-validate-only','verifier-validate-only','pinned-model-cache','probe-admission')
    assert all(statuses.get(n,{}).get('exit_code')==0 for n in required),'Complete cells 1-3 including human admission.'
    assert not (out/'verifier39').exists(),'Run already has verifier39 output; preserve it and use a fresh runtime for another run.'
    code=run('verifier39',[python,'-u','-m','research_rag.evaluation.evaluate_atomic_verifier',
        '--output-dir',str(out/'verifier39'),'--probe-dir',str(reviewed_probe),'--online-model-downloads'],
        timeout=5520,required=False)
    for name in ('summary.json','metrics.json'):
        path=out/'verifier39'/name
        print(name,path.read_text() if path.exists() else 'Incomplete; inspect saved logs.')
    path=out/'verifier39/metrics.json'
    metrics=json.loads(path.read_text()) if path.exists() else {}
    full39_passed=(code==0 and metrics.get('automated_gate_pass') is True and metrics.get('n')==39
        and metrics.get('correct_labels')==39 and metrics.get('false_support')==0 and metrics.get('runtime_failed_rows')==0)
finally:
    download_archive()
print('FULL39 AUTOMATED GATE:',full39_passed)
print('Keep the ZIP including failures. Evidence review and E2E are still required; this does not promote serving.')
'''
    intro=f'''# Cellfix5 — full39 sau human admission

Probe đã audit: {RUN}. Human reviewer: {admitted['reviewer']}.
Review mới đủ 18 ca/90 tiêu chí đã qua require_probe_review local.
Notebook nhúng source cellfix5, ZIP probe gốc và JSON review đúng hash.
Không cần chạy lại smoke/probe hoặc upload thêm file.

Dùng runtime mới, GPU T4, Run all bốn code cell:
1. Kiểm payload/hash; giữ ZIP gốc và tạo reviewed-probe riêng.
2. Dựng môi trường cô lập theo dependency/CUDA pins đã chạy thành công.
3. Admission lại bằng runner trước model-cache; 181 regression, CUDA và ba validate-only.
4. Chạy full39; tải ZIP kể cả khi trượt gate hoặc timeout.

Giữ nguyên Qwen/Qwen2.5-3B-Instruct revision aa8e72537993ba99e69dfaafa59ed015b17504d1,
NF4/float16/seed42, 8 calls/ca, 2 attempts/stage, 1536 tokens/call, 180s/ca;
tối đa 312 calls, 479232 generated tokens, worker 5400s, notebook watchdog 5520s.
Đạt tự động cần 39/39 nhãn đúng, false_support=0, runtime_failed_rows=0 và mọi check đạt.

Full39 của candidate chưa chạy tại thời điểm đóng gói. Sau khi gửi ZIP còn phải audit/replay
và review evidence, population/coverage, numeric binding, missing information từng ca.
18/39 là development data; chưa chứng minh generalization hoặc E2E Reader/Summarizer.
Giữ ZIP tải cuối cùng, kể cả có thêm (1) trong tên, rồi dừng GPU.
'''
    cells=[{'cell_type':'markdown','metadata':{},'source':intro}]
    for title,source in zip(('1 — Candidate và review','2 — Môi trường T4','3 — Admission và validation','4 — Full39'),(setup,code[1],admission,run39)):
        compile(source,title,'exec')
        cells += [{'cell_type':'markdown','metadata':{},'source':'**'+title+'**'},
            {'cell_type':'code','metadata':{},'execution_count':None,'outputs':[],'source':source}]
    book={**old,'cells':cells,'metadata':{**old['metadata'],'colab':{'name':TARGET.name}}}
    raw=(json.dumps(book,ensure_ascii=False,indent=1)+'\n').encode('utf-8')
    if RELEASE.exists():assert TARGET.read_bytes()==raw,'Released notebook is immutable.'
    TARGET.write_bytes(raw)
    record={'candidate':catalog['candidate'],'criteria_sha256':catalog['criteria_sha256'],
        'payload_sha256':catalog['payload_sha256'],'original_probe_run':RUN,'original_probe_zip_sha256':sha(ORIGINAL),
        'human_review':{k:admitted[k] for k in ('reviewer','probe_predictions_sha256','semantic_review_sha256')},
        'human_admission_verified_locally':True,'human_admission_rechecked_before_model_cache':True,
        'code_cells':4,'new_probe_inference_required':False,'full39_inference_completed':False,
        'files':{p.relative_to(ROOT).as_posix():sha(p) for p in (TARGET,Path(__file__),previous,REVIEW,ADMISSION)}}
    if RELEASE.exists():assert json.loads(RELEASE.read_text(encoding='utf-8'))==record
    destination=RELEASE if release else ROOT/'research-runs/cellfix5-full39-draft-release.json'
    destination.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'notebook':str(TARGET),'bytes':len(raw),'criteria_sha256':catalog['criteria_sha256']}))


if __name__=='__main__':
    if '--admit' in sys.argv:admit()
    build(release='--release' in sys.argv)
