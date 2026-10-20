"""Build an immutable cellfix5 candidate from the audited cellfix4 input bytes."""
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT/'research-runs/audit-cellfix4-fresh-20261017T111605Z-9505cc47'
SOURCE = ROOT/'research-runs/atomic-cellfix5-frozen/workspace'
CRITERIA = 'research_rag/evaluation/atomic_verifier_criteria_v8.json'
TARGET = 'scripts/colab_atomic_verifier_cellfix5_fresh.ipynb'
RELEASE = ROOT/'docs/atomic-verifier-cellfix5-fresh-colab-release.json'
FREEZE = ROOT/'docs/atomic-verifier-cellfix5-freeze.json'
sha = lambda b: hashlib.sha256(b).hexdigest()


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def freeze():
    assert not RELEASE.exists(),'Released candidate is immutable; use a new name.'
    release=json.loads((ROOT/'docs/atomic-verifier-cellfix4-fresh-colab-release.json').read_text())
    manifest=json.loads((PARENT/'artifact/input-manifest.json').read_text())
    assert manifest==release['payload_files']
    for name,item in manifest.items():
        data=(PARENT/'workspace'/name).read_bytes()
        assert len(data)==item['size'] and sha(data)==item['sha256'],name
        path=SOURCE/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(data)
    patch=module('cellfix5_patch',ROOT/'scripts/atomic_cellfix5_patch.py')
    patch.apply_patch(SOURCE)
    test='research_rag/tests/test_atomic_metric_cellfix5.py'
    fixture='research_rag/tests/fixtures/atomic_cellfix4_metric_traces.json'
    (SOURCE/test).write_bytes(patch.TESTS.encode('utf-8'))
    cases={r['example_id']:r for r in json.loads((PARENT/'artifact/decomposition-probe/cases.json').read_text())}
    expected={'decompose:010':'recall','decompose:014':'throughput','decompose:018':'yield'}
    traces=[]
    for line in (PARENT/'artifact/decomposition-probe/predictions.jsonl').read_text().splitlines():
        row=json.loads(line)
        if row['example_id'] in expected:
            event=row['result']['trace'][0]
            assert event['valid'] is True
            traces.append({'example_id':row['example_id'],'claim':cases[row['example_id']]['claim'],
                'output':event['output'],'expected_metric':expected[row['example_id']]})
    assert len(traces)==3
    (SOURCE/fixture).write_bytes((json.dumps(traces,indent=2)+'\n').encode('utf-8'))
    code="import importlib,json;a=importlib.import_module('04_factchecker.inference.atomic_verifier');d=importlib.import_module('04_factchecker.inference.atomic_decoding');print(json.dumps({'policy':a.POLICY,'decoder':d.DECODER,'prompts':{'decompose':a.DECOMPOSE_PROMPT,'assess':a.ASSESS_PROMPT}}))"
    metadata=json.loads(subprocess.check_output([sys.executable,'-c',code],cwd=SOURCE,
        env={**os.environ,'PYTHONPATH':str(SOURCE)},text=True,timeout=180))
    parent=json.loads((PARENT/'workspace'/CRITERIA).read_text())
    assert sha((PARENT/'workspace'/CRITERIA).read_bytes())==release['criteria_sha256']
    contract=json.loads((SOURCE/'research_rag/evaluation'/parent['contract_file']).read_text())
    contract['version']='atomic-contract-constrained-v8-cellfix5'
    contract['decomposition']['named_property_metric']={
        'shared_rule':'source_metric_requirement is consumed by scope_issues and decomposition_schema. For a supported active change-verb + property noun phrase with a known engineering measurement head, require that exact property phrase without the change verb or leading the/its/their. Preserve every remaining modifier and exact capitalization. No generated output is rewritten.',
        'repair':'metric_property_not_canonical supplies the exact required_source property span and enters the existing bounded decomposition repair.',
        'preserved':'Count/duration predicates keep verb+quantity/object. Direction and every quantity/restriction stay in the original quote. Clause-local restrictions and explicit shared prefixes retain their existing semantics.',
        'limitations':'Finite head vocabulary and active object-property grammar, not a POS/semantic parser. Unknown heads, property-before-verb, numeric-leading property phrases, ambiguous attribution, relative clauses, modal/negated/passive forms are not canonicalized by this new rule; existing constraints and semantic review still apply. A population in May is not a modal may, and is not reinterpreted as event time.'}
    contract['decoding']['decomposition']+=' Supported named-property predicates use the same source-derived exact metric enum as the validator; change verbs and dropped modifiers are not accepted in that field.'
    name='atomic_verifier_contract_v8_cellfix5.json'
    path=SOURCE/'research_rag/evaluation'/name
    path.write_bytes((json.dumps(contract,indent=2)+'\n').encode('utf-8'))
    frozen=copy.deepcopy(parent)
    frozen.update(version=metadata['policy'],policy=metadata['policy'],structured_decoder=metadata['decoder'],
        contract_file=name,contract_sha256=sha(path.read_bytes()),
        source_sha256={n:sha((SOURCE/n).read_bytes()) for n in list(parent['source_sha256'])+[test,fixture]},
        prompt_sha256={k:sha(v.encode()) for k,v in metadata['prompts'].items()})
    assert frozen['prompt_sha256']==parent['prompt_sha256'],'Prompts must remain identical.'
    frozen['limitations']=parent['limitations']+['Cellfix5 enforces a finite active named-property grammar shared by validator and decoder. Unrecognized or ambiguous constructions still need review; regression is development evidence, not new model quality/full39 evidence.']
    changed={'version','policy','structured_decoder','contract_file','contract_sha256','source_sha256','limitations'}
    assert all(frozen[k]==parent[k] for k in parent.keys()-changed)
    (SOURCE/CRITERIA).write_bytes((json.dumps(frozen,indent=2)+'\n').encode('utf-8'))
    names=sorted(set(manifest)|{test,fixture,'research_rag/evaluation/'+name})
    inputs={n:{'size':(SOURCE/n).stat().st_size,'sha256':sha((SOURCE/n).read_bytes())} for n in names}
    record={'candidate':frozen['policy'],'parent_criteria_sha256':release['criteria_sha256'],
        'criteria_sha256':sha((SOURCE/CRITERIA).read_bytes()),'source_root':str(SOURCE),'input_manifest':inputs,
        'source_zip_sha256':'e8f12af4d25948f158ab2acd4fd48989d756b40721c0081943be345f09a08cac',
        'prompts_model_data_budgets_and_gates_unchanged':True,'new_model_inference_completed':False}
    FREEZE.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')


def package():
    record=json.loads(FREEZE.read_text())
    assert record['source_root']==str(SOURCE)
    frozen=json.loads((SOURCE/CRITERIA).read_text())
    assert sha((SOURCE/CRITERIA).read_bytes())==record['criteria_sha256']
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,item in record['input_manifest'].items():
            rel=PurePosixPath(name)
            assert not rel.is_absolute() and '..' not in rel.parts and '\\' not in name
            assert '.env' not in rel.parts and not name.endswith(('.safetensors','.bin','.pem','.key'))
            data=(SOURCE/name).read_bytes()
            assert len(data)==item['size'] and sha(data)==item['sha256'],name
            entry=zipfile.ZipInfo(name,date_time=(2026,10,17,0,0,0))
            archive.writestr(entry,data,compress_type=zipfile.ZIP_DEFLATED)
    return frozen,record['input_manifest'],stream.getvalue(),record['criteria_sha256']


def build(release=False):
    frozen,manifest,payload,digest=package()
    previous=module('cellfix3_builder',ROOT/'scripts/build_colab_cellfix3_fresh.py')
    previous.EXPECTED=digest
    sources=previous.code_cells(frozen,manifest,payload)
    for old,new in [("'atomic-cellfix3-fresh-'","'atomic-cellfix5-fresh-'"),
            ("'output-cellfix3-fresh-'","'output-cellfix5-fresh-'"),
            ("'atomic-verifier-constrained-v8-cellfix3'","'atomic-verifier-constrained-v8-cellfix5'"),
            ('Frozen cellfix3 ready.','Frozen cellfix5 ready.')]:
        assert sources[0].count(old)==1,old
        sources[0]=sources[0].replace(old,new)
    intro='''# Atomic verifier cellfix5 — Colab T4 từ runtime mới

Candidate mới từ cellfix4 đã audit (smoke 12/12, probe 18/18 structural;
review của người dùng trượt TC4 ở 010/014/018). Không chuyển kết quả hay chữ ký cũ
thành kết quả của candidate này.

Validator và decoder dùng chung quy tắc source-derived cho dạng active change
verb + cụm đại lượng có measurement head được hỗ trợ. Metric bỏ change verb,
giữ modifier/case; hướng thay đổi và mọi quantity vẫn nằm nguyên trong quote.
Đây là grammar hữu hạn, không phải semantic parser. Count/duration, scope và
numeric-evidence ledger giữ nguyên. Source/prompt/contract/criteria/test/data đóng băng.

Chọn **runtime mới, GPU T4**, chạy lần lượt năm code cell hoặc Run all:
1. Nạp payload và kiểm hash; không cần ZIP/biến session cũ.
2. Dựng venv và cài dependency/CUDA pins đã dùng ở cellfix4.
3. Regression, CUDA, ba validate-only và model cache đúng revision.
4. Smoke12; tự tải ZIP kể cả khi gate trượt.
5. Probe18 chỉ khi smoke đạt; tải ZIP cập nhật sau probe.

Giữ Qwen/Qwen2.5-3B-Instruct revision aa8e72537993ba99e69dfaafa59ed015b17504d1,
NF4/float16/seed42, 8 call/ca, 2 attempt/stage, 1536 token/call, 180s/ca.
Không thay prompt, dữ liệu, budget hoặc gate. Không tự sửa predictions sau generation.

**Full39 không chạy trong notebook này.** Probe mới cần review mới đúng candidate.
Regression/replay/tokenizer feasibility là kiểm offline; không thay kết quả model.
Giữ ZIP tải sau cùng, kể cả khi trình duyệt thêm (1) vào tên.
'''
    labels=['1 — Nạp candidate đã đóng băng','2 — GPU và môi trường cô lập',
        '3 — Regression, validate-only và model cache','4 — Assessment-smoke',
        '5 — Probe18, tự bỏ qua nếu smoke trượt']
    cells=[dict(cell_type='markdown',metadata={},source=intro)]
    for label,source in zip(labels,sources):
        compile(source,label,'exec')
        cells += [dict(cell_type='markdown',metadata={},source='**'+label+'**'),
            dict(cell_type='code',metadata={},execution_count=None,outputs=[],source=source)]
    book={'cells':cells,'metadata':{'kernelspec':{'display_name':'Python 3','name':'python3'},
        'language_info':{'name':'python'},'accelerator':'GPU','colab':{'name':Path(TARGET).name}},
        'nbformat':4,'nbformat_minor':4}
    raw=(json.dumps(book,ensure_ascii=False,indent=1)+'\n').encode('utf-8')
    if RELEASE.exists(): assert (ROOT/TARGET).read_bytes()==raw,'Released notebook is immutable.'
    (ROOT/TARGET).write_bytes(raw)
    record={'candidate':frozen['policy'],'criteria_sha256':digest,'payload_sha256':sha(payload),
        'payload_files':manifest,'source_fixture_files':len(frozen['source_sha256']),
        'files':{n:sha((ROOT/n).read_bytes()) for n in (TARGET,'scripts/build_colab_cellfix5_fresh.py',
            'scripts/atomic_cellfix5_patch.py','scripts/build_colab_cellfix3_fresh.py',
            'scripts/colab_atomic_verifier_v8_smoke_probe.ipynb')},
        'code_cells':5,'previous_session_required':False,'full39_runs_automatically':False,
        'fresh_gpu_inference_completed':False,'human_review':'pending','promoted_to_serving':False}
    if RELEASE.exists(): assert json.loads(RELEASE.read_text())==record
    destination=RELEASE if release else ROOT/'research-runs/atomic-cellfix5-fresh-draft-release.json'
    destination.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'notebook':str(ROOT/TARGET),'bytes':len(raw),'input_files':len(manifest),
        'criteria_sha256':digest,'source_fixture_files':len(frozen['source_sha256'])}))


if __name__=='__main__':
    if '--freeze' in sys.argv: freeze()
    build(release='--release' in sys.argv)
