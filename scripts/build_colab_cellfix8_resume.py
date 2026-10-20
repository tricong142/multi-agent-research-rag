"""Build a single Colab cell restoring audited artifacts before full39."""
import ast
import json
from pathlib import Path

REPO=Path(__file__).resolve().parents[1]
RUN='20261020T061934Z-c87bce57'
DEST=REPO/'docs/reviews'/('cellfix8-'+RUN)/'human'

RUNTIME=r'''
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
import hashlib, io, json, os, signal, subprocess, sys, time, uuid, zipfile, shutil

AUDITED_RUN = __RUN__
EXPECTED_ZIP = __ZIP__
EXPECTED_REVIEW = __REVIEW__
EXPECTED_PAYLOAD = __PAYLOAD__
EXPECTED_CRITERIA = __CRITERIA__
EXPECTED_PROBE = __PROBE__


def checked_zip(raw, expected_names=None):
    archive = zipfile.ZipFile(io.BytesIO(raw))
    names = archive.namelist()
    if len(names) != len(set(names)) or archive.testzip() is not None:
        raise ValueError('ZIP duplicate paths or corrupt entries')
    for info in archive.infolist():
        name = info.orig_filename
        rel = PurePosixPath(name)
        if rel.is_absolute() or '..' in rel.parts or chr(92) in name or ':' in name or chr(0) in name:
            raise ValueError('Unsafe ZIP path: '+name)
    if expected_names is not None and set(names) != set(expected_names):
        raise ValueError('ZIP inventory differs from audited manifest')
    return archive


def verify_uploads(uploaded):
    blobs = {}
    for raw in uploaded.values():
        digest = hashlib.sha256(raw).hexdigest()
        if digest in blobs:
            raise ValueError('Duplicate upload; choose the original ZIP and human JSON once each')
        blobs[digest] = raw
    if set(blobs) != {EXPECTED_ZIP, EXPECTED_REVIEW}:
        raise ValueError('Upload TWO files together: output-cellfix8-fresh-20261020T061934Z-c87bce57 (2).zip and semantic-review (1).json. Contents must match the audited files; filename suffixes do not matter.')
    zip_raw, review_raw = blobs[EXPECTED_ZIP], blobs[EXPECTED_REVIEW]
    archive = checked_zip(zip_raw)
    saved = json.loads(archive.read('output-manifest.json'))
    if saved['run_id'] != AUDITED_RUN:
        raise ValueError('Wrong archived run')
    names = [row['path'] for row in saved['files']]
    if len(names) != len(set(names)):
        raise ValueError('Duplicate output manifest rows')
    if set(archive.namelist()) != set(names)|{'output-manifest.json'}:
        raise ValueError('Output manifest inventory differs')
    for item in saved['files']:
        raw = archive.read(item['path'])
        if len(raw) != item['size'] or hashlib.sha256(raw).hexdigest() != item['sha256']:
            raise ValueError('Output hash mismatch: '+item['path'])
    payload = archive.read('frozen-inputs.zip')
    manifest = json.loads(archive.read('input-manifest.json'))
    if hashlib.sha256(payload).hexdigest() != EXPECTED_PAYLOAD:
        raise ValueError('Frozen payload differs from released cf8')
    frozen = checked_zip(payload, manifest)
    for name,item in manifest.items():
        raw = frozen.read(name)
        if len(raw) != item['size'] or hashlib.sha256(raw).hexdigest() != item['sha256']:
            raise ValueError('Frozen input hash mismatch: '+name)
    if hashlib.sha256(frozen.read('research_rag/evaluation/atomic_verifier_criteria_v8.json')).hexdigest() != EXPECTED_CRITERIA:
        raise ValueError('Candidate criteria mismatch')
    if hashlib.sha256(archive.read('decomposition-probe/predictions.jsonl')).hexdigest() != EXPECTED_PROBE:
        raise ValueError('Reviewed probe predictions changed')
    review = json.loads(review_raw)
    if (review.get('reviewer_kind') != 'human' or review.get('review_completed') is not True
            or review.get('criteria_sha256') != EXPECTED_CRITERIA
            or review.get('predictions_sha256') != EXPECTED_PROBE):
        raise ValueError('Human review does not bind this probe')
    return archive, frozen, manifest, review_raw


def restore_uploads(uploaded, base):
    # Validate every upload before creating a workspace or replacing globals.
    archive, frozen, restored_manifest, review_raw = verify_uploads(uploaded)
    recovery_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
    target = Path(base)/('atomic-cellfix8-resume-'+recovery_id)
    target.mkdir(parents=True,exist_ok=False)
    source = target/'workspace'
    output = target/('output-cellfix8-resume-full39-'+AUDITED_RUN+'-'+recovery_id)
    source.mkdir();output.mkdir()
    for source_zip,directory in ((frozen,source),(archive,output)):
        for name in source_zip.namelist():
            path = (directory/name).resolve()
            if not path.is_relative_to(directory.resolve()):
                raise ValueError('Unsafe resolved archive path')
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(source_zip.read(name))
    # Preserve the historical stage/manifest before adding this recovery's logs.
    (output/'resume-parent-status.json').write_bytes((output/'status.json').read_bytes())
    (output/'resume-parent-output-manifest.json').write_bytes((output/'output-manifest.json').read_bytes())
    (output/'probe-human-review.json').write_bytes(review_raw)
    reviewed = output/'reviewed-probe'
    shutil.copytree(output/'decomposition-probe',reviewed)
    (reviewed/'semantic-review.json').write_bytes(review_raw)
    metadata={'original_run_id':AUDITED_RUN,'recovery_id':recovery_id,
        'parent_zip_sha256':EXPECTED_ZIP,'human_review_sha256':EXPECTED_REVIEW,
        'criteria_sha256':EXPECTED_CRITERIA,'payload_sha256':EXPECTED_PAYLOAD,
        'probe_predictions_sha256':EXPECTED_PROBE,'startup':'restore audited artifacts; no new smoke/probe generation',
        'source_model_budget_gate_unchanged':True,'original_artifacts_preserved':True}
    (output/'resume-provenance.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+chr(10),encoding='utf-8')
    return target,source,output,restored_manifest


__HELPERS__


def main():
    global run_root,root,out,run_id,env,venv,python,statuses,manifest,criteria_sha256,payload_sha256
    global smoke_passed,full39_passed,RUN_FULL39
    from google.colab import files as colab_files
    globals()['files'] = colab_files
    print('Chon GPU T4. Upload CUNG LUC 2 file: ZIP probe da audit va semantic-review (1).json human.')
    uploaded = files.upload()
    run_root,root,out,manifest = restore_uploads(uploaded,Path('/content'))
    run_id = AUDITED_RUN
    criteria_sha256,payload_sha256 = EXPECTED_CRITERIA,EXPECTED_PAYLOAD
    statuses = {}  # This recovery's checks; original checks remain in resume-parent-status.json.
    env = os.environ.copy()
    env.update(PYTHONPATH=str(root),HF_HOME=str(run_root/'hf'),
        HF_HUB_DISABLE_PROGRESS_BARS='1',TOKENIZERS_PARALLELISM='false')
    env.pop('HF_HUB_OFFLINE',None);env.pop('TRANSFORMERS_OFFLINE',None)
    venv = run_root/'venv'
    python = str(venv/'bin/python')
    smoke_passed = False;full39_passed = False;RUN_FULL39 = True
    print('Verified archived run:',run_id,'New recovery directory:',run_root)
    try:
        require_validation_binding()
__INSTALL__
__PREFLIGHT__
        run('resume-audited-replay',[python,'-c',REPLAY,str(out)],timeout=600)
        smoke_passed = True  # Set only after current replay/admission, without regenerating probe.
        code = run('verifier39',[python,'-u','-m','research_rag.evaluation.evaluate_atomic_verifier',
            '--output-dir',str(out/'verifier39'),'--probe-dir',str(out/'reviewed-probe'),
            '--online-model-downloads'],timeout=5520,required=False)
        path = out/'verifier39/metrics.json'
        metrics = json.loads(path.read_text()) if path.exists() else {}
        print(json.dumps(metrics,indent=2))
        full39_passed = (code==0 and metrics.get('automated_gate_pass') is True
            and metrics.get('n')==39 and metrics.get('correct_labels')==39
            and metrics.get('false_support')==0 and metrics.get('runtime_failed_rows')==0)
        if full39_passed:
            run('full39-review-form',[python,str(root/'atomic_workflow_cellfix8.py'),
                '--make-review',str(out/'verifier39'),'--review-mode','full39'],timeout=300)
            files.download(str(out/'verifier39/HUMAN_REVIEW.html'))
            print('FULL39 GATE DAT. Review prediction/evidence39 truoc validation30. Chua promote serving.')
        else:
            print('FULL39 CHUA DAT. Giu ZIP chan doan, dung truoc validation30.')
    finally:
        download_archive()


REPLAY = __REPLAY__

if __name__ == '__main__':
    main()
'''

REPLAY=r'''
from pathlib import Path
import json,sys
import atomic_workflow_cellfix8 as w
r=w.r
out=Path(sys.argv[1])
read=lambda name:json.loads((out/name).read_bytes())
rows=lambda name:[json.loads(s) for s in (out/name).read_bytes().splitlines()]
criteria,all_cases,*_=r.load_frozen(r.CRITERIA)
effective,cases=r.smoke_configuration(criteria,all_cases)
assert cases==read('assessment-smoke/cases.json')
score=w.measured_score(rows('assessment-smoke/predictions.jsonl'),cases,effective,rows('assessment-smoke/calls.jsonl'))
assert score==read('assessment-smoke/metrics.json') and score['automated_gate_pass']
assert (score['n'],score['correct_labels'],score['false_support'],score['runtime_failed_rows'])==(12,12,0,0)
binding=w.binding(Path.cwd()/'validation/cellfix8')
assert binding==read('validation-lock.json')
probe=r.require_probe_review(out/'reviewed-probe')
result={'original_run_id':'20261020T061934Z-c87bce57','smoke_replayed':True,'probe_human_admission':probe,
    'smoke_generated_again':False,'probe_generated_again':False,'new_model_calls_during_replay':0}
(out/'resume-admission.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+chr(10),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
'''


def build():
    audit=json.loads((REPO/'docs'/('atomic-verifier-cellfix8-smoke-probe-audit-'+RUN+'.json')).read_bytes())
    admitted=json.loads((DEST/'admission.json').read_bytes())
    assert admitted['admission_passed'] and admitted['criteria_sha256']==audit['criteria_sha256']
    book=json.loads((REPO/'scripts/colab_atomic_verifier_cellfix8.ipynb').read_bytes())
    cells=[c['source'] for c in book['cells'] if c['cell_type']=='code']
    wanted=('bundle','run','download_archive','require_validation_binding')
    helpers={n.name:ast.get_source_segment(cells[0],n) for n in ast.parse(cells[0]).body
        if isinstance(n,ast.FunctionDef) and n.name in wanted}
    assert set(helpers)==set(wanted)
    install=[]
    for node in ast.walk(ast.parse(cells[1])):
        if (isinstance(node,ast.Expr) and isinstance(node.value,ast.Call)
                and isinstance(node.value.func,ast.Name) and node.value.func.id=='run'):
            command=ast.get_source_segment(cells[1],node)
            name=ast.literal_eval(node.value.args[0])
            install.append(command.replace(repr(name),repr('resume-'+name),1))
    assert len(install)==7
    preflight=[]
    for node in ast.walk(ast.parse(cells[2])):
        if (isinstance(node,ast.Expr) and isinstance(node.value,ast.Call)
                and isinstance(node.value.func,ast.Name) and node.value.func.id=='run'
                and isinstance(node.value.args[0],ast.Constant)
                and node.value.args[0].value in ('cuda-preflight','pinned-model-cache')):
            command=ast.get_source_segment(cells[2],node);name=node.value.args[0].value
            preflight.append(command.replace(repr(name),repr('resume-'+name),1))
    assert len(preflight)==2
    replacements={'__RUN__':repr(RUN),'__ZIP__':repr(audit['zip_sha256']),
        '__REVIEW__':repr(admitted['input_sha256']),'__PAYLOAD__':repr(audit['payload_sha256']),
        '__CRITERIA__':repr(audit['criteria_sha256']),'__PROBE__':repr(admitted['predictions_sha256']),
        '__HELPERS__':'\n\n'.join(helpers[n] for n in wanted),
        '__INSTALL__':'\n'.join('        '+s for s in install),
        '__PREFLIGHT__':'\n'.join('        '+s for s in preflight), '__REPLAY__':repr(REPLAY)}
    code=RUNTIME.lstrip()
    for key,value in replacements.items():
        assert code.count(key)==1,key
        code=code.replace(key,value,1)
    compile(code,'RESTORE_AND_RUN_FULL39','exec')
    target=DEST/'RESTORE_AND_RUN_FULL39.py'
    target.write_text(code,encoding='utf-8')
    print(target)
    return target


if __name__=='__main__':build()
