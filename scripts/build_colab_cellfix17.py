"""Freeze cf13 workflow: smoke, reviewed probe, full39, reviewed evidence, validation30."""
import argparse
import io
import json
from pathlib import Path
import zipfile

from scripts import build_colab_cellfix3_fresh as previous
from scripts.atomic_cellfix17_binding import build as build_binding
from scripts.atomic_validation_review import digest, json_bytes, write_once

ROOT=Path(__file__).resolve().parents[1]
TARGET=ROOT/'scripts/colab_atomic_verifier_cellfix17.ipynb'
RELEASE=ROOT/'docs/atomic-verifier-cellfix17-release.json'

GUARD='''
def require_validation_binding():
    for name,item in manifest.items():
        raw=(root/name).read_bytes()
        if len(raw)!=item['size'] or hashlib.sha256(raw).hexdigest()!=item['sha256']:
            raise ValueError('Frozen input changed: '+name)
    import importlib.util
    folder=root/'validation/cellfix17'
    spec=importlib.util.spec_from_file_location('cf13_binding',folder/'binding_gate.py')
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
print('Exposed dev30 gold unchanged; development binding verified. No review upload is needed in cell 2.')
'''

FULL39=(ROOT/'scripts/colab_cellfix17_cell6.py').read_text(encoding='utf-8')

VALIDATION='''RUN_VALIDATION30 = False  # Change to True only after reviewing the full39 evidence.
if not RUN_VALIDATION30:
    print('VALIDATION30 CHUA CHAY. Full39 phai dat va duoc review evidence truoc.')
else:
    try:
        require_validation_binding()
        if ((out/'validation30').exists() or 'validation30' in statuses
                or any((out/('validation30'+suffix)).exists() for suffix in ('.stdout.log','.stderr.log'))):
            raise ValueError('Preserve the existing validation30 attempt; do not rerun exposed outcomes.')
        path=out/'verifier39/metrics.json'
        assert statuses.get('verifier39',{}).get('exit_code')==0 and path.exists() and json.loads(path.read_text()).get('automated_gate_pass') is True,'Successful full39 required.'
        uploaded=files.upload();assert len(uploaded)==1,'Upload full39 semantic-review.json, not the probe review.'
        import shutil
        import tempfile
        reviewed_full39=out/'reviewed-verifier39'
        worker=str(root/'atomic_workflow_cellfix17.py')
        raw_review=next(iter(uploaded.values()))
        preserve_review(raw_review)
        if reviewed_full39.exists() and probe_files(reviewed_full39)!=probe_files(out/'verifier39'):
            raise ValueError('Existing reviewed full39 differs from the current full39; preserve diagnostics.')
        with tempfile.TemporaryDirectory(prefix='full39-review-preflight-',dir=str(out)) as temp:
            staged=Path(temp)/'full39'
            shutil.copytree(out/'verifier39',staged)
            (staged/'semantic-review.json').write_bytes(raw_review)
            run(unused_stage('full39-admission-preflight'),[python,worker,'--admit-full39','--full39-dir',str(staged),'--probe-dir',str(out/'reviewed-probe')],timeout=300)
        if not reviewed_full39.exists():shutil.copytree(out/'verifier39',reviewed_full39)
        review_path=reviewed_full39/'semantic-review.json'
        if review_path.exists() and review_path.read_bytes()!=raw_review:preserve_review(review_path.read_bytes())
        if not review_path.exists() or review_path.read_bytes()!=raw_review:review_path.write_bytes(raw_review)
        run(unused_stage('full39-admission'),[python,worker,'--admit-full39','--full39-dir',str(reviewed_full39),'--probe-dir',str(out/'reviewed-probe')],timeout=300)
        code=run('validation30',[python,'-u',worker,'--output-dir',str(out/'validation30'),
            '--probe-dir',str(out/'reviewed-probe'),'--full39-dir',str(reviewed_full39),
            '--binding-dir',str(root/'validation/cellfix17'),'--online-model-downloads'],timeout=5520,required=False)
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
    candidate=json.loads((ROOT/'docs/atomic-verifier-cellfix17-candidate.json').read_bytes())
    checked=json.loads((ROOT/'docs/atomic-verifier-cellfix17-validation.json').read_bytes())
    if (not checked['all_regression_passed'] or checked.get('regression_scope')!='all'
            or checked['criteria_sha256']!=candidate['criteria_sha256']):
        raise ValueError('Validate the final candidate first')
    tokenizer=json.loads((ROOT/'docs/atomic-verifier-cellfix17-tokenizer-check.json').read_bytes())
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
            blobs['validation/cellfix17/'+path.relative_to(binding).as_posix()]=path.read_bytes()
    blobs['atomic_workflow_cellfix17.py']=(ROOT/'scripts/atomic_cellfix17_workflow.py').read_bytes()
    manifest={name:{'size':len(raw),'sha256':digest(raw)} for name,raw in sorted(blobs.items())}
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,raw in sorted(blobs.items()):
            entry=zipfile.ZipInfo(name,date_time=(2026,10,26,0,0,0));archive.writestr(entry,raw,compress_type=zipfile.ZIP_DEFLATED)
    frozen=json.loads(blobs[previous.CRITERIA]);previous.EXPECTED=candidate['criteria_sha256']
    sources=previous.code_cells(frozen,manifest,stream.getvalue())
    for before,after in [("'atomic-cellfix3-fresh-'","'atomic-cellfix17-fresh-'"),("'output-cellfix3-fresh-'","'output-cellfix17-fresh-'"),
                         ("'atomic-verifier-constrained-v8-cellfix3'",repr(candidate['candidate'])),('Frozen cellfix3 ready.','Frozen cellfix17 ready.')]:
        if sources[0].count(before)!=1:raise ValueError('Upstream notebook changed')
        sources[0]=sources[0].replace(before,after)
    sources[0]+=GUARD
    for index in range(1,5):
        sources[index]='try:\n    require_validation_binding()\nexcept BaseException:\n    download_archive()\n    raise\n'+sources[index]
    marker="    run('pinned-model-cache'"
    extra="    run('validation30-validate-only',[python,str(root/'atomic_workflow_cellfix17.py'),'--binding-dir',str(root/'validation/cellfix17'),'--validate-only'],timeout=300)\n"
    sources[2]=sources[2].replace(marker,extra+marker,1)
    sources[4]+='''
if statuses.get('decomposition-probe',{}).get('exit_code')==0:
    path=out/'decomposition-probe/metrics.json'
    if path.exists() and json.loads(path.read_text()).get('automated_gate_pass') is True:
        try:
            run('probe-review-form',[python,str(root/'atomic_workflow_cellfix17.py'),'--make-review',str(out/'decomposition-probe'),'--review-mode','probe'],timeout=300)
            files.download(str(out/'decomposition-probe/HUMAN_REVIEW.html'))
        finally:
            download_archive()
'''
    sources += [FULL39,VALIDATION]
    intro='# Cellfix17 — candidate mới, dev30-v1 đã lộ kết quả\n\nSửa coverage member enum rỗng do lọc mất dấu câu; giữ source span và validator.\nGiữ model/revision, gold, ngân sách call/token/thời gian và gate full39.\nBộ30 đã dùng để sửa là DEVELOPMENT, không phải holdout độc lập. Kết quả model\nchưa được đo cho candidate này. Cần holdout mới disjoint theo paper trước nghiệm thu.\nChạy cells1–5; review probe mới trước cell6; review full39 mới trước cell7 dev30.\nKhông tự ký review hoặc đổi gold. Cells6/7 mặc định tắt. Lưu ZIP kể cả thất bại.\n'
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
    files=[TARGET,Path(__file__)]+[ROOT/'scripts'/n for n in ['build_atomic_cellfix17_candidate.py', 'check_atomic_cellfix17.py', 'check_atomic_cellfix17_tokenizer.py', 'atomic_cellfix17_binding.py', 'atomic_cellfix17_workflow.py', 'colab_cellfix17_cell6.py', 'test_atomic_cellfix17.py', 'fixtures/atomic_cellfix14_member_absence.json', 'fixtures/cellfix15_validation30.json', 'atomic_cellfix17_coverage.py', 'fixtures/cellfix16_full39_failure.json', 'prepare_cellfix17_packaging.py', 'atomic_offline_memory.py', 'test_cellfix17_packaging.py', 'test_colab_cellfix17.py', 'test_atomic_cellfix17_workflow.py', 'test_cellfix17_cell6.py', 'test_cellfix17_cell7.py', 'check_cellfix17_packaging.py', 'check_kaggle_cellfix17.py', 'build_kaggle_cellfix17.py', 'build_atomic_cellfix14_candidate.py', 'build_colab_cellfix3_fresh.py']]
    record={'candidate':candidate['candidate'],'criteria_sha256':candidate['criteria_sha256'],'payload_sha256':digest(stream.getvalue()),
        'payload_files':manifest,'files':{p.relative_to(ROOT).as_posix():digest(p.read_bytes()) for p in files},
        'code_cells':7,'candidate_input_files':len(candidate['input_manifest']),
        'validation_binding_sha256':digest((binding/'binding.json').read_bytes()),
        'model_inference_completed':False,'full39_quality_measured':False,'independent_validation_completed':False,'validation30_used_for_tuning':True,'evaluation_role':'development',
        'probe_human_review':'pending_new_predictions','full39_human_review':'pending_new_predictions',
        'full39_automatically_enabled':False,'validation30_automatically_enabled':False,'promoted_to_serving':False}
    path=RELEASE if release else ROOT/'research-runs/cellfix17-notebook-draft.json'
    if release or RELEASE.exists():write_once(path,json_bytes(record))
    else:path.write_bytes(json_bytes(record))
    print(json.dumps({'notebook':str(TARGET),'payload_files':len(manifest),'criteria_sha256':candidate['criteria_sha256']}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--release',action='store_true')
    build(parser.parse_args().release)
