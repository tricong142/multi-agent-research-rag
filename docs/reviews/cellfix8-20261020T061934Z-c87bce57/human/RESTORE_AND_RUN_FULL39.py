from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
import hashlib, io, json, os, signal, subprocess, sys, time, uuid, zipfile, shutil

AUDITED_RUN = '20261020T061934Z-c87bce57'
EXPECTED_ZIP = '9604fc031e34aa40dee5d64831430662fa4d88960cead0b4b2c1fa337c91f6ac'
EXPECTED_REVIEW = '06ce2e455f3c5da3273197ecd0dedf34b6f043f6df14bcdd76a8ee7dc88fee79'
EXPECTED_PAYLOAD = '9c783b696e69abfc84f0e0c36273fb11cbb4173e90843642b071a6387bf69bc4'
EXPECTED_CRITERIA = 'fbf969ebea81aba03961767b9ee53960f89cc3e3cb2d370da3a4adba4007def8'
EXPECTED_PROBE = '16da0c50c5c62e22caba50749e50c3cb4f3f1dde83cdba18356c54e85dc01260'


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


def bundle():
    # This dedicated directory contains only diagnostics produced by these cells.
    entries = [{'path':str(p.relative_to(out)), 'size':p.stat().st_size,
                'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
               for p in sorted(out.rglob('*')) if p.is_file() and p.name != 'output-manifest.json']
    (out/'output-manifest.json').write_text(json.dumps({'run_id':run_id,'files':entries},indent=2))
    archive = out.with_suffix('.zip')
    pending = archive.with_suffix('.zip.partial')
    with zipfile.ZipFile(pending, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob('*')):
            if p.is_file(): z.write(p, str(p.relative_to(out)))
    pending.replace(archive)
    print('Diagnostic archive:', archive.name, flush=True)

def run(name, command, *, timeout=1800, child_env=None, required=True):
    assert name not in statuses, 'Preserve the previous stage; start a fresh run for retries'
    started = time.perf_counter()
    status = {'state':'running'}
    statuses[name] = status
    (out/'status.json').write_text(json.dumps(statuses,indent=2))
    try:
        with (out/(name+'.stdout.log')).open('x') as stdout, (out/(name+'.stderr.log')).open('x') as stderr:
            process = subprocess.Popen(command, cwd=root, env=child_env or env,
                                       stdout=stdout, stderr=stderr, start_new_session=True)
            try:
                while True:
                    try:
                        code = process.wait(timeout=15)
                        break
                    except subprocess.TimeoutExpired:
                        elapsed = time.perf_counter()-started
                        print(name, 'running', round(elapsed), 'seconds', flush=True)
                        if elapsed > timeout: raise TimeoutError(name)
            except BaseException:
                os.killpg(process.pid, signal.SIGTERM)
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                raise
        status.update(state='completed' if code == 0 else 'failed', exit_code=code)
    except BaseException as exc:
        status.update(state='interrupted', error_type=type(exc).__name__)
        raise
    finally:
        status['elapsed_ms'] = round((time.perf_counter()-started)*1000,2)
        (out/'status.json').write_text(json.dumps(statuses,indent=2))
        bundle()
    print(name, status, flush=True)
    if required and code:
        print((out / (name + '.stderr.log')).read_text()[-12000:], flush=True)
        raise RuntimeError(name + ' failed; inspect its saved stderr')
    return code

def download_archive():
    bundle()
    files.download(str(out.with_suffix('.zip')))

def require_validation_binding():
    for name,item in manifest.items():
        raw=(root/name).read_bytes()
        if len(raw)!=item['size'] or hashlib.sha256(raw).hexdigest()!=item['sha256']:
            raise ValueError('Frozen input changed: '+name)
    import importlib.util
    folder=root/'validation/cellfix8'
    spec=importlib.util.spec_from_file_location('cf8_binding',folder/'binding_gate.py')
    gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
    binding=gate.verify(folder,criteria_sha256)
    path=out/'validation-lock.json'
    raw=(json.dumps(binding,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    if path.exists() and path.read_bytes()!=raw:
        raise ValueError('Existing validation lock changed; preserve this run')
    path.write_bytes(raw)
    (out/'validation-annotation-review.json').write_bytes((folder/'annotation-review.json').read_bytes())
    (out/'validation-original-lock.json').write_bytes((folder/'original-lock.json').read_bytes())
    return binding


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
        run('resume-gpu-host',['nvidia-smi'])
        run('resume-venv', [sys.executable, '-m', 'venv', '--without-pip', str(venv)])
        run('resume-bootstrap', [sys.executable, '-m', 'pip', '--python', python, 'install', '--no-cache-dir', 'pip==26.2.1', 'wrapt==2.1.2'])
        run('resume-torch', [python, '-m', 'pip', 'install', '--no-cache-dir', 'torch==2.10.0', 'torchvision==0.25.0', '--index-url', 'https://download.pytorch.org/whl/cu128'])
        run('resume-runtime', [python, '-m', 'pip', 'install', '--no-cache-dir', '-r', 'requirements-orchestrator.txt', '-r', 'requirements-atomic-verifier.txt'])
        run('resume-pip-check', [python, '-m', 'pip', 'check'])
        run('resume-pip-freeze', [python, '-m', 'pip', 'freeze'])
        run('resume-cuda-preflight',[python,'-c',"import json,torch; assert torch.cuda.is_available(); print(json.dumps({'torch':torch.__version__,'cuda':torch.version.cuda,'gpu':torch.cuda.get_device_name(0)}))"])
        run('resume-pinned-model-cache',[python,'-c',"from huggingface_hub import snapshot_download; print(snapshot_download('Qwen/Qwen2.5-3B-Instruct',revision='aa8e72537993ba99e69dfaafa59ed015b17504d1',ignore_patterns=['*.bin','*.gguf','original/*']))"],timeout=1800)
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


REPLAY = "\nfrom pathlib import Path\nimport json,sys\nimport atomic_workflow_cellfix8 as w\nr=w.r\nout=Path(sys.argv[1])\nread=lambda name:json.loads((out/name).read_bytes())\nrows=lambda name:[json.loads(s) for s in (out/name).read_bytes().splitlines()]\ncriteria,all_cases,*_=r.load_frozen(r.CRITERIA)\neffective,cases=r.smoke_configuration(criteria,all_cases)\nassert cases==read('assessment-smoke/cases.json')\nscore=w.measured_score(rows('assessment-smoke/predictions.jsonl'),cases,effective,rows('assessment-smoke/calls.jsonl'))\nassert score==read('assessment-smoke/metrics.json') and score['automated_gate_pass']\nassert (score['n'],score['correct_labels'],score['false_support'],score['runtime_failed_rows'])==(12,12,0,0)\nbinding=w.binding(Path.cwd()/'validation/cellfix8')\nassert binding==read('validation-lock.json')\nprobe=r.require_probe_review(out/'reviewed-probe')\nresult={'original_run_id':'20261020T061934Z-c87bce57','smoke_replayed':True,'probe_human_admission':probe,\n    'smoke_generated_again':False,'probe_generated_again':False,'new_model_calls_during_replay':0}\n(out/'resume-admission.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+chr(10),encoding='utf-8')\nprint(json.dumps(result,ensure_ascii=False))\n"

if __name__ == '__main__':
    main()
