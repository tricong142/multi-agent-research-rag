"""Freeze cf9 workflow: smoke, reviewed probe, full39, reviewed evidence, validation30."""
import argparse
import io
import json
from pathlib import Path
import zipfile

from scripts import build_colab_cellfix3_fresh as previous
from scripts.atomic_cellfix9_binding import build as build_binding
from scripts.atomic_validation_review import digest, json_bytes, write_once

ROOT=Path(__file__).resolve().parents[1]
TARGET=ROOT/'scripts/colab_atomic_verifier_cellfix9.ipynb'
RELEASE=ROOT/'docs/atomic-verifier-cellfix9-release.json'

GUARD='''
def require_validation_binding():
    for name,item in manifest.items():
        raw=(root/name).read_bytes()
        if len(raw)!=item['size'] or hashlib.sha256(raw).hexdigest()!=item['sha256']:
            raise ValueError('Frozen input changed: '+name)
    import importlib.util
    folder=root/'validation/cellfix9'
    spec=importlib.util.spec_from_file_location('cf9_binding',folder/'binding_gate.py')
    gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
    binding=gate.verify(folder,criteria_sha256)
    path=out/'validation-lock.json'
    raw=(json.dumps(binding,ensure_ascii=False,indent=2)+'\\n').encode('utf-8')
    if path.exists() and path.read_bytes()!=raw:
        raise ValueError('Existing validation lock changed; preserve this run')
    path.write_bytes(raw)
    (out/'validation-annotation-review.json').write_bytes((folder/'annotation-review.json').read_bytes())
    (out/'validation-original-lock.json').write_bytes((folder/'original-lock.json').read_bytes())
    return binding
require_validation_binding()
bundle()
print('Validation gold reused unchanged; new candidate binding verified. No review upload is needed in cell 2.')
'''

FULL39='''RUN_FULL39 = False  # Change to True only after directly reviewing the new 18-claim probe.
full39_passed=False
if not RUN_FULL39:
    print('FULL39 CHUA CHAY. Review HUMAN_REVIEW.html cua probe moi, xuat semantic-review.json, roi bat RUN_FULL39.')
else:
    try:
        require_validation_binding()
        probe=out/'decomposition-probe'
        assert statuses.get('decomposition-probe',{}).get('exit_code')==0 and json.loads((probe/'metrics.json').read_text())['automated_gate_pass'] is True,'Probe18 must pass first.'
        uploaded=files.upload()
        assert len(uploaded)==1,'Upload exactly the new probe semantic-review.json.'
        import shutil
        reviewed_probe=out/'reviewed-probe'
        assert not reviewed_probe.exists(),'Reviewed probe already exists; preserve it and use a new run.'
        shutil.copytree(probe,reviewed_probe)
        (reviewed_probe/'semantic-review.json').write_bytes(next(iter(uploaded.values())))
        command="import json; from pathlib import Path; from research_rag.evaluation.evaluate_atomic_verifier import require_probe_review; print(json.dumps(require_probe_review(Path("+repr(str(reviewed_probe))+"))))"
        run('probe-admission',[python,'-c',command],timeout=300)
        code=run('verifier39',[python,'-u','-m','research_rag.evaluation.evaluate_atomic_verifier',
            '--output-dir',str(out/'verifier39'),'--probe-dir',str(reviewed_probe),'--online-model-downloads'],timeout=5520,required=False)
        path=out/'verifier39/metrics.json'
        metrics=json.loads(path.read_text()) if path.exists() else {}
        print(json.dumps(metrics,indent=2))
        full39_passed=(code==0 and metrics.get('automated_gate_pass') is True and metrics.get('n')==39 and metrics.get('correct_labels')==39 and metrics.get('false_support')==0 and metrics.get('runtime_failed_rows')==0)
        if full39_passed:
            run('full39-review-form',[python,str(root/'atomic_workflow_cellfix9.py'),'--make-review',str(out/'verifier39'),'--review-mode','full39'],timeout=300)
            files.download(str(out/'verifier39/HUMAN_REVIEW.html'))
            print('Review the 39 predictions and evidence before validation30. No serving promotion.')
    finally:
        download_archive()
'''

VALIDATION='''RUN_VALIDATION30 = False  # Change to True only after reviewing the full39 evidence.
if not RUN_VALIDATION30:
    print('VALIDATION30 CHUA CHAY. Full39 phai dat va duoc review evidence truoc.')
else:
    try:
        require_validation_binding()
        path=out/'verifier39/metrics.json'
        assert statuses.get('verifier39',{}).get('exit_code')==0 and path.exists() and json.loads(path.read_text()).get('automated_gate_pass') is True,'Successful full39 required.'
        uploaded=files.upload();assert len(uploaded)==1,'Upload full39 semantic-review.json, not the probe review.'
        import shutil
        reviewed_full39=out/'reviewed-verifier39'
        assert not reviewed_full39.exists(),'Preserve existing reviewed full39; use a new run.'
        shutil.copytree(out/'verifier39',reviewed_full39)
        (reviewed_full39/'semantic-review.json').write_bytes(next(iter(uploaded.values())))
        worker=str(root/'atomic_workflow_cellfix9.py')
        run('full39-admission',[python,worker,'--admit-full39','--full39-dir',str(reviewed_full39),'--probe-dir',str(out/'reviewed-probe')],timeout=300)
        code=run('validation30',[python,'-u',worker,'--output-dir',str(out/'validation30'),
            '--probe-dir',str(out/'reviewed-probe'),'--full39-dir',str(reviewed_full39),
            '--binding-dir',str(root/'validation/cellfix9'),'--online-model-downloads'],timeout=5520,required=False)
        for name in ('metrics.json','classification.json','summary.json'):
            path=out/'validation30'/name
            print(name,path.read_text() if path.exists() else 'Incomplete; keep diagnostics.')
        if code==0 and (out/'validation30/HUMAN_REVIEW.html').exists():
            files.download(str(out/'validation30/HUMAN_REVIEW.html'))
        print('Keep every validation outcome. If used to tune, retire this set to development.')
    finally:
        download_archive()
'''


def build(release=False):
    candidate=json.loads((ROOT/'docs/atomic-verifier-cellfix9-candidate.json').read_bytes())
    checked=json.loads((ROOT/'docs/atomic-verifier-cellfix9-validation.json').read_bytes())
    if (not checked['all_regression_passed'] or checked.get('regression_scope')!='all'
            or checked['criteria_sha256']!=candidate['criteria_sha256']):
        raise ValueError('Validate the final candidate first')
    tokenizer=json.loads((ROOT/'docs/atomic-verifier-cellfix9-tokenizer-check.json').read_bytes())
    if tokenizer['criteria_sha256']!=candidate['criteria_sha256'] or any(v['accepted']!=v['expected'] for v in tokenizer['checks']):
        raise ValueError('Token-filter feasibility check missing or stale')
    binding=build_binding(ROOT)
    source=Path(candidate['source_root']);blobs={}
    for name,item in candidate['input_manifest'].items():
        raw=(source/name).read_bytes()
        if len(raw)!=item['size'] or digest(raw)!=item['sha256']:raise ValueError('Candidate input changed: '+name)
        blobs[name]=raw
    for path in binding.rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts:
            blobs['validation/cellfix9/'+path.relative_to(binding).as_posix()]=path.read_bytes()
    blobs['atomic_workflow_cellfix9.py']=(ROOT/'scripts/atomic_cellfix9_workflow.py').read_bytes()
    manifest={name:{'size':len(raw),'sha256':digest(raw)} for name,raw in sorted(blobs.items())}
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,raw in sorted(blobs.items()):
            entry=zipfile.ZipInfo(name,date_time=(2026,10,20,0,0,0));archive.writestr(entry,raw,compress_type=zipfile.ZIP_DEFLATED)
    frozen=json.loads(blobs[previous.CRITERIA]);previous.EXPECTED=candidate['criteria_sha256']
    sources=previous.code_cells(frozen,manifest,stream.getvalue())
    for before,after in [("'atomic-cellfix3-fresh-'","'atomic-cellfix9-fresh-'"),("'output-cellfix3-fresh-'","'output-cellfix9-fresh-'"),
                         ("'atomic-verifier-constrained-v8-cellfix3'",repr(candidate['candidate'])),('Frozen cellfix3 ready.','Frozen cellfix9 ready.')]:
        if sources[0].count(before)!=1:raise ValueError('Upstream notebook changed')
        sources[0]=sources[0].replace(before,after)
    sources[0]+=GUARD
    for index in range(1,5):
        sources[index]='try:\n    require_validation_binding()\nexcept BaseException:\n    download_archive()\n    raise\n'+sources[index]
    marker="    run('pinned-model-cache'"
    extra="    run('validation30-validate-only',[python,str(root/'atomic_workflow_cellfix9.py'),'--binding-dir',str(root/'validation/cellfix9'),'--validate-only'],timeout=300)\n"
    sources[2]=sources[2].replace(marker,extra+marker,1)
    sources[4]+='''
if statuses.get('decomposition-probe',{}).get('exit_code')==0:
    path=out/'decomposition-probe/metrics.json'
    if path.exists() and json.loads(path.read_text()).get('automated_gate_pass') is True:
        try:
            run('probe-review-form',[python,str(root/'atomic_workflow_cellfix9.py'),'--make-review',str(out/'decomposition-probe'),'--review-mode','probe'],timeout=300)
            files.download(str(out/'decomposition-probe/HUMAN_REVIEW.html'))
        finally:
            download_archive()
'''
    sources += [FULL39,VALIDATION]
    intro='''# Cellfix9 — workflow Colab T4 với các gate giữ nguyên

Source verifier là candidate mới từ cellfix8 full39 29/39 đã bảo toàn. Model,
revision, NF4/float16/seed42, 8 call/ca, 2 attempt/stage, 1536 token/call,
180s/ca và gate development giữ nguyên. Sửa binding member/predicate/citation,
polarity, collective coverage và missing-information; decomposition prompt không đổi.

Bộ validation30 và gold/review cũ giữ nguyên bytes. Binding mới dẫn chiếu chữ
ký annotation cũ theo yêu cầu đổi candidate; không tạo chữ ký human mới.
Không cần upload review30 ở cell 2. Mỗi stage kiểm lại toàn bộ hash.

1. Runtime mới, GPU T4; chạy cells 1–5: payload → môi trường → regression và
validate-only → smoke12 → probe18 nếu smoke đạt. Giữ ZIP kể cả thất bại.
2. Probe đạt: tải HUMAN_REVIEW.html, trực tiếp review 18 claim, ghi từng tiêu
chí và xuất semantic-review.json. Sửa RUN_FULL39=True ở cell 6 rồi upload file.
Runner replay admission đúng candidate trước khi chạy full39.
3. Full39 đạt: review 39 prediction/evidence bằng form mới, xuất review mới.
Sửa RUN_VALIDATION30=True ở cell 7; upload review full39. Admission và replay
full39 phải đạt trước khi chạy validation30 đã khóa. Chưa dùng bộ này để tune.

Run all mặc định chỉ tới probe; cell 6/7 mặc định tắt. Không tự ký review,
không đổi gold sau khi xem prediction, không tự promote serving. Nếu validation
được dùng để chỉnh candidate, chuyển bộ này thành development và tạo bộ khác.
Regression/tokenizer/validate-only là kiểm offline; chưa có kết quả GPU cellfix9.
'''
    labels=['1 — Nạp source và binding đã khóa','2 — Dựng môi trường GPU','3 — Regression, validate-only, model cache',
            '4 — Smoke12','5 — Probe18 và form review mới','6 — Sau human review probe: full39','7 — Sau human review full39: validation30']
    cells=[{'cell_type':'markdown','metadata':{},'source':intro}]
    for label,code in zip(labels,sources):
        compile(code,label,'exec')
        cells += [{'cell_type':'markdown','metadata':{},'source':'**'+label+'**'},
                  {'cell_type':'code','metadata':{},'execution_count':None,'outputs':[],'source':code}]
    book={'cells':cells,'metadata':{'kernelspec':{'display_name':'Python 3','name':'python3'},'language_info':{'name':'python'},
        'accelerator':'GPU','colab':{'name':TARGET.name}},'nbformat':4,'nbformat_minor':4}
    raw=json_bytes(book)
    if RELEASE.exists():write_once(TARGET,raw)
    else:TARGET.write_bytes(raw)
    files=[TARGET,Path(__file__),ROOT/'scripts/atomic_cellfix9_workflow.py',ROOT/'scripts/atomic_cellfix9_binding.py',
           ROOT/'scripts/atomic_cellfix9_patch.py',ROOT/'scripts/atomic_cellfix9_evidence.py',ROOT/'scripts/atomic_cellfix8_parser.py',ROOT/'scripts/build_atomic_cellfix9_candidate.py',
           ROOT/'scripts/check_atomic_cellfix9.py',ROOT/'scripts/check_atomic_cellfix9_tokenizer.py',
           ROOT/'scripts/check_cellfix9_validation_overlap.py',
           ROOT/'scripts/test_colab_cellfix9.py',ROOT/'scripts/test_atomic_cellfix9_workflow.py',
           ROOT/'scripts/test_atomic_cellfix9_assessment.py',ROOT/'scripts/build_colab_cellfix3_fresh.py',
           ROOT/'scripts/colab_atomic_verifier_v8_smoke_probe.ipynb']
    record={'candidate':candidate['candidate'],'criteria_sha256':candidate['criteria_sha256'],'payload_sha256':digest(stream.getvalue()),
        'payload_files':manifest,'files':{p.relative_to(ROOT).as_posix():digest(p.read_bytes()) for p in files},
        'code_cells':7,'candidate_input_files':len(candidate['input_manifest']),
        'validation_binding_sha256':digest((binding/'binding.json').read_bytes()),
        'model_inference_completed':False,'full39_quality_measured':False,'independent_validation_completed':False,
        'probe_human_review':'pending_new_predictions','full39_human_review':'pending_new_predictions',
        'full39_automatically_enabled':False,'validation30_automatically_enabled':False,'promoted_to_serving':False}
    path=RELEASE if release else ROOT/'research-runs/cellfix9-notebook-draft.json'
    if release or RELEASE.exists():write_once(path,json_bytes(record))
    else:path.write_bytes(json_bytes(record))
    print(json.dumps({'notebook':str(TARGET),'payload_files':len(manifest),'criteria_sha256':candidate['criteria_sha256']}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--release',action='store_true')
    build(parser.parse_args().release)
