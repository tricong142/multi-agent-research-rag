"""Package unchanged cellfix6 bytes; human annotation admission precedes GPU work."""
import io
import json
from pathlib import Path, PurePosixPath
import zipfile

from scripts import build_colab_cellfix3_fresh as previous
from scripts.atomic_validation_review import digest, json_bytes, packet, write_once

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT/'docs/validation/atomic-cellfix6-v1'
TARGET = ROOT/'scripts/colab_atomic_verifier_cellfix6_fresh.ipynb'
CATALOG = ROOT/'docs/atomic-verifier-cellfix6-notebook-draft.json'

ADMISSION = '''
def require_validation_review(upload=False):
    # Recheck actual bytes, not a stale Boolean left over from another cell.
    for name,item in manifest.items():
        data=(root/name).read_bytes()
        if len(data)!=item['size'] or hashlib.sha256(data).hexdigest()!=item['sha256']:
            raise ValueError('Frozen input changed: '+name)
    review_path=out/'validation-annotation-review.json'
    if upload and not review_path.exists():
        print('Upload annotation-review-cellfix6-v1.json exported after your direct annotation review.')
        uploaded=files.upload()
        if len(uploaded)!=1:
            raise ValueError('Upload exactly one review JSON; do not upload a ZIP or old probe review.')
        review_path.write_bytes(next(iter(uploaded.values())))
    if not review_path.exists():
        raise ValueError('Validation annotations are pending human review. Complete the review before GPU work.')
    import importlib.util
    folder=root/'validation/atomic-cellfix6-v1'
    spec=importlib.util.spec_from_file_location('validation_gate',folder/'review_gate.py')
    gate=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    raw=review_path.read_bytes()
    lock=gate.admit(folder,json.loads(raw))
    if lock['candidate_criteria_sha256']!=criteria_sha256:
        raise ValueError('Annotation lock is for a different candidate')
    lock['review_sha256']=hashlib.sha256(raw).hexdigest()
    gate.write_once(out/'validation-lock.json',gate.json_bytes(lock))
    return lock
'''


def build():
    candidate = json.loads((ROOT/'docs/atomic-verifier-cellfix6-candidate.json').read_text())
    checked = json.loads((ROOT/'docs/atomic-verifier-cellfix6-validation.json').read_text())
    if not checked['all_regression_passed'] or checked['criteria_sha256']!=candidate['criteria_sha256']:
        raise ValueError('Candidate validation mismatch')
    for name, expected in checked['delivery_sha256'].items():
        if digest((ROOT/name).read_bytes()) != expected:
            raise ValueError('Validated delivery changed: '+name)
    validation, _ = packet(DATA)
    if validation['candidate_criteria_sha256'] != candidate['criteria_sha256']:
        raise ValueError('Validation packet candidate mismatch')
    source = Path(candidate['source_root'])
    blobs = {}
    for name,item in candidate['input_manifest'].items():
        raw=(source/name).read_bytes()
        if len(raw)!=item['size'] or digest(raw)!=item['sha256']:
            raise ValueError('Candidate input changed: '+name)
        blobs[name]=raw
    names = set(validation['files']) | {'manifest.json','annotation-review.template.json','REVIEW.html'}
    for name in sorted(names):
        blobs['validation/atomic-cellfix6-v1/'+name]=(DATA/name).read_bytes()
    manifest={name:{'size':len(raw),'sha256':digest(raw)} for name,raw in sorted(blobs.items())}
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,raw in sorted(blobs.items()):
            rel=PurePosixPath(name)
            if rel.is_absolute() or '..' in rel.parts or '\\' in name or ':' in name:
                raise ValueError('Unsafe payload path')
            entry=zipfile.ZipInfo(name,date_time=(2026,10,18,0,0,0))
            archive.writestr(entry,raw,compress_type=zipfile.ZIP_DEFLATED)
    frozen=json.loads(blobs[previous.CRITERIA])
    previous.EXPECTED=candidate['criteria_sha256']
    sources=previous.code_cells(frozen,manifest,stream.getvalue())
    for old,new in [("'atomic-cellfix3-fresh-'","'atomic-cellfix6-fresh-'"),
                    ("'output-cellfix3-fresh-'","'output-cellfix6-fresh-'"),
                    ("'atomic-verifier-constrained-v8-cellfix3'",repr(candidate['candidate'])),
                    ('Frozen cellfix3 ready.','Frozen cellfix6 ready.')]:
        if sources[0].count(old)!=1:
            raise ValueError('Upstream notebook template changed')
        sources[0]=sources[0].replace(old,new)
    sources[0]+=ADMISSION
    for index in range(1,5):
        guard='try:\n    require_validation_review(upload='+str(index==1)+')\nexcept BaseException:\n    download_archive()\n    raise\n'
        sources[index]=guard+sources[index]
    intro='''# Cellfix6 — candidate đóng băng, chờ xác nhận annotation validation

Source/prompt/contract/criteria và 89 đầu vào cellfix6 giữ nguyên hash đã kiểm.
Đính kèm bản nháp validation 30 ca từ 10 paper QASPER khác bộ development.
Nhãn do AI đề xuất, **chưa phải gold đã được người review xác nhận**.

Trước khi chạy GPU: mở `docs/validation/atomic-cellfix6-v1/REVIEW.html`, đọc context,
xác nhận riêng từng tiêu chí, ghi chú và xuất `annotation-review-cellfix6-v1.json`.
Cell 2 yêu cầu upload file này, kiểm hash/candidate/đủ 30 ca và tạo validation-lock.
Nếu annotation sai, sửa thành phiên bản dữ liệu mới trước inference; không bỏ gate.
Các giới hạn provenance trong form vẫn áp dụng sau khi được xác nhận.

Chọn runtime mới, GPU T4, chạy 5 cell. Cell 1 giải nén; cell 2 nhận review rồi dựng
môi trường; cell 3 chạy regression, ba validate-only và tải model đúng revision;
cell 4 chạy smoke12; cell 5 chỉ chạy probe18 nếu smoke đạt. Lỗi vẫn tải ZIP chẩn đoán.

Giữ Qwen/Qwen2.5-3B-Instruct aa8e72537993ba99e69dfaafa59ed015b17504d1,
NF4/float16/seed42; 8 call/ca, 2 attempt/stage, 1536 token/call, 180s/ca.
Không dùng kết quả validation để tune rồi gọi lại cùng bộ là độc lập.

**Notebook này chỉ chạy smoke12 và probe18.** Full39 và validation30 không tự chạy.
Probe mới cần review mới; sau đó chạy full39 dưới strict-identity-v1, rồi mới đo
validation đã khóa trên cùng candidate. Nhãn gốc cellfix5 21/39, false support=0
giữ nguyên để đối chiếu. Cellfix6 chưa có kết quả model/full39/validation hay E2E.
'''
    labels=['1 — Nạp payload và kiểm hash', '2 — Nhận review annotation, khóa validation, dựng GPU',
            '3 — Regression, ba validate-only, model cache', '4 — Smoke12', '5 — Probe18 sau smoke']
    cells=[{'cell_type':'markdown','metadata':{},'source':intro}]
    for label,code in zip(labels,sources):
        compile(code,label,'exec')
        cells += [{'cell_type':'markdown','metadata':{},'source':'**'+label+'**'},
                  {'cell_type':'code','metadata':{},'execution_count':None,'outputs':[],'source':code}]
    book={'cells':cells,'metadata':{'kernelspec':{'display_name':'Python 3','name':'python3'},
          'language_info':{'name':'python'},'accelerator':'GPU','colab':{'name':TARGET.name}},'nbformat':4,'nbformat_minor':4}
    write_once(TARGET,json_bytes(book))
    record={'candidate':candidate['candidate'],'status':'packaged_pending_human_annotation_lock',
            'criteria_sha256':candidate['criteria_sha256'],'payload_sha256':digest(stream.getvalue()),
            'candidate_input_files':len(candidate['input_manifest']),'payload_files':manifest,
            'validation_manifest_sha256':digest((DATA/'manifest.json').read_bytes()),
            'files':{p.relative_to(ROOT).as_posix():digest(p.read_bytes()) for p in
                     (TARGET,Path(__file__),ROOT/'scripts/build_colab_cellfix3_fresh.py',
                      ROOT/'scripts/colab_atomic_verifier_v8_smoke_probe.ipynb',
                      ROOT/'scripts/atomic_validation_review.py',ROOT/'scripts/prepare_atomic_validation_v1.py')},
            'code_cells':5,'human_annotation_review':'pending','model_inference_completed':False,
            'full39_runs_automatically':False,'validation30_runs_automatically':False,'promoted_to_serving':False}
    write_once(CATALOG,json_bytes(record))
    print(json.dumps({'notebook':str(TARGET),'payload_files':len(manifest),'status':record['status']}))


if __name__=='__main__':
    build()
