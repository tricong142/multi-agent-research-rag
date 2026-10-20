"""Freeze a citation-ledger delta and package a fresh notebook from audited inputs."""
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / 'research-runs/audit-cellfix3-fresh-20261017T101839Z-a9590fe1'
SOURCE = ROOT / 'research-runs/atomic-cellfix4-frozen/workspace'
CRITERIA = 'research_rag/evaluation/atomic_verifier_criteria_v8.json'
TARGET = 'scripts/colab_atomic_verifier_cellfix4_fresh.ipynb'
RELEASE = ROOT / 'docs/atomic-verifier-cellfix4-fresh-colab-release.json'
sha = lambda b: hashlib.sha256(b).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def freeze():
    # Rebuild deterministically only before release. Never modify any parent input.
    assert not RELEASE.exists(), 'Candidate is released; use another candidate name.'
    manifest = json.loads((PARENT / 'artifact/input-manifest.json').read_text())
    released = json.loads((ROOT / 'docs/atomic-verifier-cellfix3-fresh-colab-release.json').read_text())
    assert manifest == released['payload_files']
    for name, item in manifest.items():
        data = (PARENT / 'workspace' / name).read_bytes()
        assert len(data) == item['size'] and sha(data) == item['sha256'], name
        path = SOURCE / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    patch = module('cellfix4_patch', ROOT / 'scripts/atomic_cellfix4_patch.py')
    patch.apply_patch(SOURCE)
    test_name = 'research_rag/tests/test_atomic_smoke_cellfix4.py'
    fixture_name = 'research_rag/tests/fixtures/atomic_cellfix3_citation_traces.json'
    (SOURCE / test_name).write_bytes(patch.TESTS.encode('utf-8'))
    rows = [json.loads(s) for s in (PARENT / 'artifact/assessment-smoke/predictions.jsonl').read_text().splitlines()]
    row = next(r for r in rows if r['example_id'] == 'contract:cross_sentence')
    fixture = [{**json.loads(t['messages'][1]['content']), 'output': t['output'],
                'parent_validation_issue': t['validation_issue'], 'attempt': t['attempt']}
               for t in row['result']['trace'] if t['stage'] != 'decompose']
    (SOURCE / fixture_name).write_bytes((json.dumps(fixture, indent=2) + '\n').encode('utf-8'))
    meta_code = "import importlib,json;a=importlib.import_module('04_factchecker.inference.atomic_verifier');d=importlib.import_module('04_factchecker.inference.atomic_decoding');print(json.dumps({'policy':a.POLICY,'decoder':d.DECODER,'prompts':{'decompose':a.DECOMPOSE_PROMPT,'assess':a.ASSESS_PROMPT}}))"
    env = {**os.environ, 'PYTHONPATH': str(SOURCE)}
    meta = json.loads(subprocess.check_output([sys.executable, '-c', meta_code], cwd=SOURCE, env=env, text=True, timeout=180))
    old = json.loads((PARENT / 'workspace' / CRITERIA).read_text())
    assert sha((PARENT / 'workspace' / CRITERIA).read_bytes()) == released['criteria_sha256']
    contract = json.loads((SOURCE / 'research_rag/evaluation' / old['contract_file']).read_text())
    contract['version'] = 'atomic-contract-constrained-v8-cellfix4'
    contract['assessment']['citation_ledger'] = 'A numeric source_quote is an explicit model citation. After its exact source membership and operand validation, code adds it to a copied observation quotes ledger when not already contained. Raw trace stays unchanged; derived citation_additions is recorded for replay/review. No measurement check, target association, arithmetic, qualitative evidence or missing quantity is invented. Existing count/length limits apply to the union.'
    contract['assessment']['target_binding'] += ' Explicit another/other/different/second/third target mentions are conservatively rejected into bounded repair, including fully cited passages.'
    contract['numeric']['requirements'] = contract['numeric']['requirements'].replace('each source_quote must be cited in that observation', 'each source_quote must be exact source text and is included in that observation evidence ledger after verification')
    contract['result']['derived_observation_fields'] = {'citation_additions': 'Exact model-supplied numeric source citations added to the derived ledger; empty if already cited. Never changes raw model output.'}
    contract_name = 'atomic_verifier_contract_v8_cellfix4.json'
    contract_path = SOURCE / 'research_rag/evaluation' / contract_name
    contract_path.write_bytes((json.dumps(contract, indent=2) + '\n').encode('utf-8'))
    frozen = copy.deepcopy(old)
    frozen.update(version=meta['policy'], policy=meta['policy'], structured_decoder=meta['decoder'],
                  contract_file=contract_name, contract_sha256=sha(contract_path.read_bytes()),
                  source_sha256={n:sha((SOURCE / n).read_bytes()) for n in list(old['source_sha256']) + [test_name, fixture_name]},
                  prompt_sha256={k:sha(v.encode()) for k,v in meta['prompts'].items()})
    frozen['limitations'] = old['limitations'] + ['Cellfix4 removes duplicate numeric-citation serialization, not semantic uncertainty. Finite target/binding guards do not establish entailment; all model quality, independent evaluation and full39 results remain unmeasured for this candidate.']
    changed = {'version','policy','structured_decoder','contract_file','contract_sha256','source_sha256','prompt_sha256','limitations'}
    assert all(frozen[k] == old[k] for k in old.keys() - changed)
    assert frozen['prompt_sha256']['decompose'] == old['prompt_sha256']['decompose']
    (SOURCE / CRITERIA).write_bytes((json.dumps(frozen, indent=2) + '\n').encode('utf-8'))
    names = sorted(set(manifest) | {test_name, fixture_name, 'research_rag/evaluation/' + contract_name})
    inputs = {n:{'size':(SOURCE/n).stat().st_size,'sha256':sha((SOURCE/n).read_bytes())} for n in names}
    record = {'candidate': frozen['policy'], 'parent_criteria_sha256': released['criteria_sha256'],
              'criteria_sha256': sha((SOURCE/CRITERIA).read_bytes()), 'source_root': str(SOURCE),
              'input_manifest': inputs, 'model_data_budgets_and_gates_unchanged': True,
              'source_zip_sha256': '37fa91b236c15078ebaf2fb571a3fdf91dd76f96ad88dae6ee1fd6adf759eec2',
              'new_model_inference_completed': False}
    (ROOT/'docs/atomic-verifier-cellfix4-freeze.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    return frozen, inputs


def package():
    record = json.loads((ROOT/'docs/atomic-verifier-cellfix4-freeze.json').read_text())
    assert record['source_root'] == str(SOURCE)
    frozen = json.loads((SOURCE/CRITERIA).read_text())
    assert sha((SOURCE/CRITERIA).read_bytes()) == record['criteria_sha256']
    stream = io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,item in record['input_manifest'].items():
            data=(SOURCE/name).read_bytes()
            assert len(data)==item['size'] and sha(data)==item['sha256'],name
            entry=zipfile.ZipInfo(name,date_time=(2026,10,17,0,0,0))
            archive.writestr(entry,data,compress_type=zipfile.ZIP_DEFLATED)
    return frozen,record['input_manifest'],stream.getvalue(),record['criteria_sha256']


def build(release=False):
    frozen,manifest,payload,digest = package()
    previous=module('cellfix3_fresh_builder',ROOT/'scripts/build_colab_cellfix3_fresh.py')
    previous.EXPECTED=digest
    sources=previous.code_cells(frozen,manifest,payload)
    # Retain all tested stage guards and dependency pins. Preserve payload and
    # manifest assignments byte-for-byte, including historical filenames.
    for old,new in [("'atomic-cellfix3-fresh-'","'atomic-cellfix4-fresh-'"),
                    ("'output-cellfix3-fresh-'","'output-cellfix4-fresh-'"),
                    ("'atomic-verifier-constrained-v8-cellfix3'","'atomic-verifier-constrained-v8-cellfix4'"),
                    ('Frozen cellfix3 ready.','Frozen cellfix4 ready.')]:
        assert sources[0].count(old)==1,old
        sources[0]=sources[0].replace(old,new)
    intro='''# Atomic verifier cellfix4 — chạy từ đầu trên Colab T4

Sửa lỗi citation trong ZIP cellfix3 (11/12, zero false support trên smoke12).
Numeric source_quote đã được model chọn được kiểm nguyên văn và toán hạng rồi
hợp nhất vào ledger; raw output và citation_additions được giữ để replay/review.
Không thêm check còn thiếu, không bỏ counterevidence, không suy ra bằng chứng.
Target khác được chặn kể cả khi đã trích dẫn. Gate và ngân sách giữ nguyên.

Notebook tự chứa đúng source/prompt/contract/criteria/data/tokenizer đã đóng băng.
Không cần notebook/ZIP/biến session cũ. Model tải từ revision đã chốt.
Chọn runtime mới **GPU T4**, chạy lần lượt **5 code cell** hoặc Run all:
1. Nạp và kiểm hash.
2. Cài môi trường cô lập với dependency/CUDA pins cũ.
3. Regression, CUDA, ba validate-only, cache model đúng revision.
4. Smoke12 và tải ZIP; gate trượt thì dừng.
5. Probe18 chỉ khi smoke đạt, rồi tải ZIP cập nhật.

Qwen/Qwen2.5-3B-Instruct revision aa8e72537993ba99e69dfaafa59ed015b17504d1,
NF4/float16/seed42. Mỗi ca tối đa 8 call, 2 attempt/stage, 1536 token/call, 180s.
Không tăng budget hoặc nới gate. Đây là development, không phải held-out.
**Chưa đo smoke/probe/full39 bằng model của candidate mới tại thời điểm build.**
Full39 không chạy tự động; probe18 vẫn cần human review mới cho candidate này.
Giữ ZIP MỚI được tải sau cùng. Trong ZIP có frozen-inputs.zip để audit/replay.
'''
    labels=['1 — Nạp candidate đã đóng băng','2 — GPU và môi trường cô lập',
            '3 — Regression, validate-only và model cache','4 — Assessment-smoke',
            '5 — Probe18, tự bỏ qua nếu smoke trượt']
    cells=[dict(cell_type='markdown',metadata={},source=intro)]
    for label,source in zip(labels,sources):
        compile(source,label,'exec')
        cells.append(dict(cell_type='markdown',metadata={},source='**'+label+'**'))
        cells.append(dict(cell_type='code',metadata={},execution_count=None,outputs=[],source=source))
    book={'cells':cells,'metadata':{'kernelspec':{'display_name':'Python 3','name':'python3'},
          'language_info':{'name':'python'},'accelerator':'GPU','colab':{'name':Path(TARGET).name}},
          'nbformat':4,'nbformat_minor':4}
    raw=(json.dumps(book,ensure_ascii=False,indent=1)+'\n').encode('utf-8')
    if RELEASE.exists(): assert (ROOT/TARGET).read_bytes()==raw,'Released notebook is immutable.'
    (ROOT/TARGET).write_bytes(raw)
    record={'candidate':frozen['policy'],'criteria_sha256':digest,'payload_sha256':sha(payload),
            'payload_files':manifest,'source_fixture_files':len(frozen['source_sha256']),
            'files':{n:sha((ROOT/n).read_bytes()) for n in (TARGET,
                'scripts/build_colab_cellfix4_fresh.py','scripts/atomic_cellfix4_patch.py',
                'scripts/build_colab_cellfix3_fresh.py','scripts/colab_atomic_verifier_v8_smoke_probe.ipynb')},
            'code_cells':5,'previous_session_required':False,'full39_runs_automatically':False,
            'fresh_gpu_inference_completed':False,'human_review':'pending','promoted_to_serving':False}
    if RELEASE.exists(): assert json.loads(RELEASE.read_text())==record
    destination=RELEASE if release else ROOT/'research-runs/atomic-cellfix4-fresh-draft-release.json'
    destination.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'notebook':str(ROOT/TARGET),'bytes':len(raw),'inputs':len(manifest),
                      'criteria_sha256':digest,'source_fixture_files':len(frozen['source_sha256'])}))


if __name__=='__main__':
    if '--freeze' in sys.argv: freeze()
    build(release='--release' in sys.argv)
