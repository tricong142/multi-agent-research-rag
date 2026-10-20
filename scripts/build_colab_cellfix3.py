"""Emit one self-contained replacement smoke cell; do not rebuild the v8 notebook."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT/'research-runs/audit-cellfix2-20261017T085227Z-e0a1ba82/artifact'

SETUP = '''# Thay cell assessment-smoke hien tai bang TOAN BO noi dung file nay.
# Dung trong session cellfix2 cu; khong doi model, budget, gold hay gate.
# Regression local khong phai ket qua inference Qwen/T4.
import copy, hashlib, json, shutil, subprocess, uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from google.colab import files

smoke_passed = False
assert all(k in globals() for k in ('root','out','env','python','manifest','run','bundle')), 'Can session cellfix2 cu.'
criteria_rel = 'research_rag/evaluation/atomic_verifier_criteria_v8.json'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()

def _find_cellfix3_parent():
    expected='a31549bda8776f6a566689c59378e5c47092faf6000d4597ef7ab82fdafa197b'
    manifest_hash='01d110cddae3bbdb4a41569429c255359c14a87c2f30f8c633817900bf269533'
    current=dict(root=Path(root),out=Path(out),env=env.copy())
    states=[current]+[s for k in ('_cellfix3_parent','_cellfix2_parent','_v8_before_cellfix')
        if isinstance((s:=globals().get(k)),dict) and 'root' in s and 'out' in s]
    roots=[]
    def add_root(path):
        path=Path(path).resolve()
        if path not in roots: roots.append(path)
    for state in states: add_root(state['root'])
    anchors={Path(s['root']).resolve().parent for s in states}
    anchors.update(Path(s['out']).resolve().parent for s in states)
    if 'run_root' in globals(): anchors.add(Path(run_root).resolve())
    if Path('/content').is_dir(): anchors.update(Path('/content').glob('atomic-v8-*'))
    for base in sorted(anchors):
        if base.is_dir():
            for path in sorted(base.glob('workspace-cellfix2-*'),reverse=True): add_root(path)
    diagnostics=[]
    for candidate in roots:
        path=candidate/criteria_rel
        detail={'root':str(candidate)}
        diagnostics.append(detail)
        if not path.is_file():
            detail['error']='criteria file missing'
            continue
        try:
            digest=sha(path)
            detail['criteria_sha256']=digest
            if digest!=expected: continue
            outputs=[]
            if candidate.name.startswith('workspace-cellfix2-'):
                outputs.append(candidate.with_name(candidate.name.replace('workspace-cellfix2-','output-cellfix2-',1)))
            matching=[s for s in states if Path(s['root']).resolve()==candidate]
            outputs.extend(Path(s['out']) for s in matching)
            outputs.extend(sorted(candidate.parent.glob('output-cellfix2-*'),reverse=True))
            for output in dict.fromkeys(outputs):
                manifest_path=output/'input-manifest.json'
                if not manifest_path.is_file(): continue
                try:
                    data=json.loads(manifest_path.read_text())
                except (OSError,ValueError):
                    continue
                fingerprint=hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()
                if fingerprint!=manifest_hash: continue
                for name,item in data.items():
                    relative=PurePosixPath(name)
                    assert not relative.is_absolute() and '..' not in relative.parts and '\\\\' not in name
                    source=candidate/relative
                    if not source.is_file() or source.stat().st_size!=item['size'] or sha(source)!=item['sha256']:
                        raise ValueError('Input integrity mismatch: '+name)
                chosen_env=next((s['env'] for s in matching if isinstance(s.get('env'),dict)),env)
                return dict(root=candidate,out=output,env=chosen_env.copy(),manifest=data)
            detail['error']='No matching audited input-manifest.json'
        except (OSError,ValueError,KeyError,TypeError) as exc:
            detail['error']=str(exc)
    raise RuntimeError('Khong tim thay source cellfix2 da audit; chua chay smoke. '
        'Khong bo kiem hash. Root/hash tim thay: '+json.dumps(diagnostics,ensure_ascii=False))

# Cache only after criteria, manifest and all input bytes have been verified.
parent=_find_cellfix3_parent()
_cellfix3_parent=parent
print('Verified cellfix2 parent:',parent['root'])
old = json.loads((parent['root']/criteria_rel).read_text())
for name,digest in old['source_sha256'].items():
    assert sha(parent['root']/name)==digest, 'Source thay doi: '+name
run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
new_root = parent['root'].parent/('workspace-cellfix3-'+run_id)
new_out = parent['out'].parent/('output-cellfix3-'+run_id)
new_root.mkdir(exist_ok=False)
new_out.mkdir(exist_ok=False)
for name,item in parent['manifest'].items():
    relative=PurePosixPath(name)
    assert not relative.is_absolute() and '..' not in relative.parts and '\\\\' not in name
    source,target=parent['root']/name,new_root/name
    assert sha(source)==item['sha256'] and source.stat().st_size==item['size'],name
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,target)
'''

FINISH = '''
apply_patch(new_root)
test_rel='research_rag/tests/test_atomic_smoke_cellfix3.py'
fixture_rel='research_rag/tests/fixtures/atomic_cellfix2_binding_traces.json'
(new_root/test_rel).write_bytes(TESTS.encode('utf-8'))
(new_root/fixture_rel).write_bytes((json.dumps(TRACE_FIXTURE,indent=2)+'\\n').encode('utf-8'))
new_env=parent['env'].copy()
new_env['PYTHONPATH']=str(new_root)
metadata_code="import importlib,json;a=importlib.import_module('04_factchecker.inference.atomic_verifier');d=importlib.import_module('04_factchecker.inference.atomic_decoding');print(json.dumps({'policy':a.POLICY,'decoder':d.DECODER,'prompts':{'decompose':a.DECOMPOSE_PROMPT,'assess':a.ASSESS_PROMPT}}))"
metadata=json.loads(subprocess.check_output([python,'-c',metadata_code],cwd=new_root,env=new_env,text=True))
criteria=copy.deepcopy(old)
contract=json.loads((new_root/'research_rag/evaluation'/old['contract_file']).read_text())
contract.update(version='atomic-contract-constrained-v8-cellfix3')
contract['assessment']['target_binding']='One observation for an exactly source-matched atomic target, carrying all its evidence/checks. Out-of-target observations enter bounded repair; absent exact target cannot establish a decisive atomic label. Alias/coreference entailment is not inferred.'
contract['numeric']['measurement_binding']='Shared finite entity/metric/object binding for decoder and validator. Correct alternative measurement in context makes malformed binding repairable; an absent measurement remains unknown. Scope a value check to an exact independent measurement clause, retaining shared modality/broad negation. Explicit quantity denial allows a short claim-grounded metric noun bridge.'
contract_name='atomic_verifier_contract_v8_cellfix3.json'
contract_path=new_root/'research_rag/evaluation'/contract_name
contract_path.write_bytes((json.dumps(contract,indent=2)+'\\n').encode('utf-8'))
criteria.update(version='atomic-verifier-constrained-v8-cellfix3',policy=metadata['policy'],
    structured_decoder=metadata['decoder'],contract_file=contract_name,contract_sha256=sha(contract_path),
    prompt_sha256={k:hashlib.sha256(v.encode()).hexdigest() for k,v in metadata['prompts'].items()})
criteria['source_sha256']={name:sha(new_root/name) for name in list(old['source_sha256'])+[test_rel,fixture_rel]}
criteria['limitations']=old['limitations']+['Cellfix3 exact-span target and finite English measurement-clause grammar are conservative. Aliases, semantic coreference, evidence completeness and unsupported syntax still require independent evaluation and review. No new model quality or full39 result is established by regression.']
changed={'version','policy','structured_decoder','contract_file','contract_sha256','prompt_sha256','source_sha256','limitations'}
assert all(criteria[k]==old[k] for k in old.keys()-changed), 'Model/data/budget/gate changed unexpectedly.'
assert criteria['prompt_sha256']['decompose']==old['prompt_sha256']['decompose']
(new_root/criteria_rel).write_bytes((json.dumps(criteria,indent=2)+'\\n').encode('utf-8'))
root,out,env,statuses=new_root,new_out,new_env,{}
manifest={p.relative_to(root).as_posix():{'size':p.stat().st_size,'sha256':sha(p)}
    for p in sorted(root.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
(out/'input-manifest.json').write_text(json.dumps(manifest,indent=2))
(out/'cellfix3-provenance.json').write_text(json.dumps({'candidate':criteria['version'],
    'parent_criteria_sha256':sha(parent['root']/criteria_rel),'candidate_criteria_sha256':sha(root/criteria_rel),
    'previous_output':str(parent['out']),'model_data_budgets_and_gates_unchanged':True,
    'intentional_legacy_fixture_updates':['Two different members are no longer a valid atomic target decoder example; add a single-target positive assertion.','Wrong object binding with available correct evidence must reject into bounded repair rather than silently finalize NEI.']},indent=2))
(out/'cellfix3-patch-contents.json').write_text(json.dumps({'numeric_patch':NUMERIC_PATCH,
    'atomic_patch':ATOMIC_PATCH,'decoder_patch':DECODER_PATCH,'regression_tests':TESTS,
    'development_trace_fixture':TRACE_FIXTURE},indent=2))
try:
    modules=[p[:-3].replace('/','.').replace('\\\\','.') for p in criteria['source_sha256']
        if p.startswith('research_rag/tests/') and p.endswith('.py')]
    run('regression-cellfix3',[python,'-m','unittest',*modules,'-v'],timeout=900)
    for name,flag in (('probe-validate-only-cellfix3','--decomposition-probe'),
            ('smoke-validate-only-cellfix3','--assessment-smoke'),('verifier-validate-only-cellfix3',None)):
        command=[python,'-m','research_rag.evaluation.evaluate_atomic_verifier',
            '--output-dir',str(out/'unused'),'--validate-only']
        if flag: command.append(flag)
        run(name,command)
    run('cuda-preflight-cellfix3',[python,'-c',"import json,torch; assert torch.cuda.is_available(); print(json.dumps({'gpu':torch.cuda.get_device_name(0),'torch':torch.__version__}))"])
    code=run('assessment-smoke',[python,'-u','-m','research_rag.evaluation.evaluate_atomic_verifier',
        '--output-dir',str(out/'assessment-smoke'),'--assessment-smoke','--online-model-downloads'],
        timeout=2520,required=False)
    path=out/'assessment-smoke/metrics.json'
    metrics=json.loads(path.read_text()) if path.exists() else {}
    print(json.dumps(metrics,indent=2))
    smoke_passed=code==0 and metrics.get('automated_gate_pass') is True
finally:
    bundle()
    files.download(str(out.with_suffix('.zip')))
if smoke_passed:
    print('SMOKE DAT. Gui ZIP moi de audit; probe18/human review/full39 van la cac gate tiep theo.')
else:
    print('SMOKE CHUA DAT. Da luu ZIP moi. Dung tai day; khong chay probe/full39.')
'''


def build():
    cases={c['example_id']:c for c in json.loads((ARTIFACT/'assessment-smoke/cases.json').read_text())}
    fixture=[]
    for line in (ARTIFACT/'assessment-smoke/predictions.jsonl').read_text().splitlines():
        row=json.loads(line)
        if row['example_id'] not in {'contract:partial_memory','contract:accuracy_conflict','contract:both_supported','contract:cross_sentence'}:
            continue
        for t in row['result']['trace']:
            if t['stage']=='decompose':continue
            payload=json.loads(t['messages'][1]['content'])
            fixture.append({'example_id':row['example_id'],'stage':t['stage'],
                'claim':payload['claim'],'part':payload['part'],'context':payload['context'],'output':t['output']})
    module=(ROOT/'scripts/atomic_cellfix3_patch.py').read_text(encoding='utf-8')
    source=SETUP+'\n'+module+'\nTRACE_FIXTURE = '+repr(fixture)+'\n'+FINISH
    compile(source,'<cellfix3>','exec')
    target=ROOT/'scripts/colab_v8_assessment_smoke_cellfix3.py'
    target.write_bytes(source.encode('utf-8'))
    print(target)


if __name__=='__main__':
    build()
