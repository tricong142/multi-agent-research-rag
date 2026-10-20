"""Build a standalone Colab notebook from the exact validated cellfix3 inputs."""
import ast
import base64
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
TARGET='scripts/colab_atomic_verifier_cellfix3_fresh.ipynb'
RELEASE='docs/atomic-verifier-cellfix3-fresh-colab-release.json'
CRITERIA='research_rag/evaluation/atomic_verifier_criteria_v8.json'
EXPECTED='c38cf4cad12ce7ddcf257c1b80dff5467dc1d499a22f295d2824b0ca5c5a558f'


def package():
    verified=json.loads((ROOT/'docs/atomic-verifier-cellfix3-validation.json').read_text())
    local=verified['local_validation']['run']
    source=Path(local['candidate_root'])
    manifest=json.loads((Path(local['candidate_out'])/'input-manifest.json').read_text())
    frozen=json.loads((source/CRITERIA).read_text())
    assert hashlib.sha256((source/CRITERIA).read_bytes()).hexdigest()==EXPECTED
    assert set(frozen['source_sha256']) <= set(manifest)
    assert all(manifest[n]['sha256']==h for n,h in frozen['source_sha256'].items())
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,item in sorted(manifest.items()):
            path=PurePosixPath(name)
            assert not path.is_absolute() and '..' not in path.parts and '\\' not in name
            assert '.env' not in path.parts and not name.endswith(('.safetensors','.bin','.pem','.key'))
            data=(source/name).read_bytes()
            assert len(data)==item['size'] and hashlib.sha256(data).hexdigest()==item['sha256'],name
            entry=zipfile.ZipInfo(name,date_time=(2026,10,17,0,0,0))
            archive.writestr(entry,data,compress_type=zipfile.ZIP_DEFLATED)
    return frozen,manifest,stream.getvalue()


def code_cells(frozen,manifest,payload):
    previous=json.loads((ROOT/'scripts/colab_atomic_verifier_v8_smoke_probe.ipynb').read_text(encoding='utf-8'))
    original=[''.join(c['source']) if isinstance(c['source'],list) else c['source']
        for c in previous['cells'] if c['cell_type']=='code']
    helpers=[ast.get_source_segment(original[0],n) for n in ast.parse(original[0]).body
        if isinstance(n,ast.FunctionDef) and n.name in ('bundle','run')]
    assert len(helpers)==2
    setup='''from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
import base64, hashlib, io, json, os, signal, subprocess, sys, time, uuid, zipfile
from google.colab import files

smoke_passed = False
run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
run_root = Path('/content')/('atomic-cellfix3-fresh-'+run_id)
root = run_root/'workspace'
out = run_root/('output-cellfix3-fresh-'+run_id)
root.mkdir(parents=True,exist_ok=False)
out.mkdir(exist_ok=False)
statuses = {}
env = os.environ.copy()
env.update(PYTHONPATH=str(root),HF_HOME=str(run_root/'hf'),
    HF_HUB_DISABLE_PROGRESS_BARS='1',TOKENIZERS_PARALLELISM='false')
env.pop('HF_HUB_OFFLINE',None)
env.pop('TRANSFORMERS_OFFLINE',None)
venv = run_root/'venv'
python = str(venv/'bin/python')
'''
    setup+='payload = '+repr(base64.b64encode(payload).decode())+'\n'
    setup+='payload_sha256 = '+repr(hashlib.sha256(payload).hexdigest())+'\n'
    setup+='manifest = '+repr(manifest)+'\n'
    setup+='criteria_sha256 = '+repr(EXPECTED)+'\n'
    setup+='\n\n'.join(helpers)+'\n'
    setup+='''
def download_archive():
    bundle()
    files.download(str(out.with_suffix('.zip')))

try:
    raw=base64.b64decode(payload,validate=True)
    assert hashlib.sha256(raw).hexdigest()==payload_sha256
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist())==len(manifest) and set(archive.namelist())==set(manifest)
        for name,item in manifest.items():
            relative=PurePosixPath(name)
            assert not relative.is_absolute() and '..' not in relative.parts and '\\\\' not in name
            data=archive.read(name)
            assert len(data)==item['size'] and hashlib.sha256(data).hexdigest()==item['sha256'],name
            target=root/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(data)
    assert hashlib.sha256((root/'research_rag/evaluation/atomic_verifier_criteria_v8.json').read_bytes()).hexdigest()==criteria_sha256
    (out/'input-manifest.json').write_text(json.dumps(manifest,indent=2))
    (out/'frozen-inputs.zip').write_bytes(raw)
    (out/'notebook-provenance.json').write_text(json.dumps({
        'candidate':'atomic-verifier-constrained-v8-cellfix3',
        'criteria_sha256':criteria_sha256,'payload_sha256':payload_sha256,
        'startup':'fresh embedded inputs; no previous session required',
        'model_data_budgets_and_gates_unchanged':True},indent=2))
    bundle()
except BaseException:
    download_archive()
    raise
print('Frozen cellfix3 ready. Run directory:',run_root)
'''
    # Preserve the previously exercised CUDA/dependency pins verbatim.
    install="try:\n    run('gpu-host',['nvidia-smi'])\n"+'\n'.join('    '+line for line in original[1].splitlines())
    install+='\nexcept BaseException:\n    download_archive()\n    raise\n'
    modules=[p[:-3].replace('/','.') for p in frozen['source_sha256']
        if p.startswith('research_rag/tests/') and p.endswith('.py')]
    validate='try:\n    run(\'regression\',[python,\'-m\',\'unittest\','+','.join(repr(m) for m in modules)+",'-v'],timeout=900)\n"
    validate+='''    run('cuda-preflight',[python,'-c',"import json,torch; assert torch.cuda.is_available(); print(json.dumps({'torch':torch.__version__,'cuda':torch.version.cuda,'gpu':torch.cuda.get_device_name(0)}))"])
    for name,flag in (('probe-validate-only','--decomposition-probe'),('smoke-validate-only','--assessment-smoke'),('verifier-validate-only',None)):
        command=[python,'-m','research_rag.evaluation.evaluate_atomic_verifier','--output-dir',str(out/'unused'),'--validate-only']
        if flag: command.append(flag)
        run(name,command)
    run('pinned-model-cache',[python,'-c',"from huggingface_hub import snapshot_download; print(snapshot_download('Qwen/Qwen2.5-3B-Instruct',revision='aa8e72537993ba99e69dfaafa59ed015b17504d1',ignore_patterns=['*.bin','*.gguf','original/*']))"],timeout=1800)
except BaseException:
    download_archive()
    raise
print('Regression, CUDA, freeze and pinned model-cache checks passed.')
'''
    smoke='''smoke_passed = False
try:
    assert all(statuses.get(n,{}).get('exit_code')==0 for n in ('gpu-host','venv','bootstrap','torch','runtime','pip-check','pip-freeze','regression','cuda-preflight','probe-validate-only','smoke-validate-only','verifier-validate-only','pinned-model-cache')), 'Complete cells 1-3 first.'
    code=run('assessment-smoke',[python,'-u','-m','research_rag.evaluation.evaluate_atomic_verifier',
        '--output-dir',str(out/'assessment-smoke'),'--assessment-smoke','--online-model-downloads'],
        timeout=2520,required=False)
    path=out/'assessment-smoke/metrics.json'
    metrics=json.loads(path.read_text()) if path.exists() else {}
    print(json.dumps(metrics,indent=2))
    smoke_passed=code==0 and metrics.get('automated_gate_pass') is True
finally:
    download_archive()
if smoke_passed:
    print('SMOKE DAT: co the chay probe18 o cell tiep theo. Full39 van can human review moi.')
else:
    print('SMOKE CHUA DAT: da luu ZIP; probe18/full39 bi chan. Cell ket thuc khong co nghia la gate da dat.')
'''
    probe='''if not globals().get('smoke_passed',False):
    print('BO QUA PROBE18: assessment-smoke chua dat. Giu ZIP chan doan va dung tai day.')
else:
    path=out/'assessment-smoke/metrics.json'
    confirmed=(statuses.get('assessment-smoke',{}).get('exit_code')==0 and path.exists()
        and json.loads(path.read_text()).get('automated_gate_pass') is True)
    if not confirmed:
        smoke_passed=False
        print('BO QUA PROBE18: khong co ket qua smoke dat cho run hien tai.')
    else:
        try:
            code=run('decomposition-probe',[python,'-u','-m','research_rag.evaluation.evaluate_atomic_verifier',
                '--output-dir',str(out/'decomposition-probe'),'--decomposition-probe','--online-model-downloads'],
                timeout=2520,required=False)
            for name in ('summary.json','metrics.json'):
                path=out/'decomposition-probe'/name
                print(name,path.read_text() if path.exists() else 'Incomplete; inspect saved logs.')
        finally:
            download_archive()
        print('Gui ZIP moi de audit va review 18 claim. Human review van pending; chua chay full39 hoac serving.')
'''
    return [setup,install,validate,smoke,probe]


def build(*,release=False):
    frozen,manifest,payload=package()
    sources=code_cells(frozen,manifest,payload)
    intro='''# Atomic verifier cellfix3 — chạy từ đầu trên Colab T4

Notebook này tự chứa source, prompt, contract, criteria, dữ liệu và tokenizer của
candidate cellfix3 đã đóng băng. Không cần ZIP cũ, Drive, cell vá hoặc biến của
session trước. Weights Qwen được tải từ đúng revision đã chốt.

Chọn GPU **T4**, dùng runtime mới, rồi chạy lần lượt **5 code cell** hoặc Run all.
1. Giải nén và kiểm hash đầu vào.
2. Tạo venv, cài đúng dependency/CUDA pins của notebook trước.
3. Regression, CUDA, ba validate-only và tải model đúng revision.
4. Assessment-smoke 12 ca; tự tải ZIP kể cả khi gate trượt.
5. Probe18 chỉ chạy nếu smoke đạt; smoke trượt thì cell này tự bỏ qua.

Giữ nguyên Qwen/Qwen2.5-3B-Instruct, revision
`aa8e72537993ba99e69dfaafa59ed015b17504d1`, NF4/float16/seed42.
Mỗi ca vẫn tối đa 8 call, 2 attempt/stage, 1536 token/call, deadline 180 giây.
Đây là bộ development đã được dùng sửa lỗi; chưa phải đánh giá độc lập.

Notebook **không tự chạy full39**. Probe18 cần human review mới gắn đúng candidate
trước gate full39. ZIP có frozen-inputs.zip để replay, log và metrics của run này.
Giữ ZIP mới ngay cả khi smoke trượt; cell chạy xong không đồng nghĩa gate đạt.
Mỗi lần chạy lại từ đầu tạo thư mục mới, không ghi đè kết quả trước.
'''
    labels=['1 — Nạp candidate đã đóng băng','2 — GPU và môi trường cô lập',
        '3 — Regression, validate-only và model cache','4 — Assessment-smoke',
        '5 — Probe18, tự bỏ qua nếu smoke trượt']
    cells=[dict(cell_type='markdown',metadata={},source=intro)]
    for i,(label,source) in enumerate(zip(labels,sources),1):
        compile(source,f'cellfix3-fresh-cell-{i}','exec')
        cells.append(dict(cell_type='markdown',metadata={},source='**'+label+'**'))
        cells.append(dict(cell_type='code',metadata={},execution_count=None,outputs=[],source=source))
    notebook={'cells':cells,'metadata':{'kernelspec':{'display_name':'Python 3','name':'python3'},
        'language_info':{'name':'python'},'accelerator':'GPU','colab':{'name':Path(TARGET).name}},
        'nbformat':4,'nbformat_minor':4}
    raw=(json.dumps(notebook,ensure_ascii=False,indent=1)+'\n').encode('utf-8')
    target=ROOT/TARGET
    release_path=ROOT/RELEASE
    if release_path.exists():
        assert target.read_bytes()==raw,'Released notebook is immutable; use a new candidate name.'
    target.write_bytes(raw)
    record={'candidate':frozen['version'],'criteria_sha256':EXPECTED,
        'payload_sha256':hashlib.sha256(payload).hexdigest(),'payload_files':manifest,
        'files':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
            (TARGET,'scripts/build_colab_cellfix3_fresh.py')},
        'code_cells':5,'source_fixture_files':len(frozen['source_sha256']),
        'previous_session_required':False,'full39_runs_automatically':False,
        'fresh_gpu_inference_completed':False,'human_review':'pending','promoted_to_serving':False}
    if release_path.exists():
        assert json.loads(release_path.read_text())==record,'Released metadata is immutable.'
    destination=release_path if release else ROOT/'research-runs/atomic-cellfix3-fresh-draft-release.json'
    destination.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'notebook':str(target),'bytes':len(raw),'payload_files':len(manifest),
        'criteria_sha256':EXPECTED}))
    return target


if __name__=='__main__':
    build(release='--release' in sys.argv)
