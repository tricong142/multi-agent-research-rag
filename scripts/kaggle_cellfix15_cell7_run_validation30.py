
def _cell7_replay_worker():
    import hashlib
    import json
    from pathlib import Path
    original=root/'atomic_workflow_cellfix15.py'
    raw=original.read_bytes()
    original_sha=hashlib.sha256(raw).hexdigest()
    if original_sha != '64a838b28d187c795a16edfa525786680539e729e6255f5d45c74546f450f9ee':
        raise ValueError('Expected the original frozen Cellfix15 workflow')
    if manifest['atomic_workflow_cellfix15.py']['sha256'] != original_sha:
        raise ValueError('Workflow differs from the frozen input manifest')
    newline='\r\n' if b'\r\n' in raw else '\n'
    before="    if score!=read(directory/'metrics.json') or not score['automated_gate_pass']:\n".replace('\n',newline)
    after="    stored=read(directory/'metrics.json')\n    # Full39 producer omits this diagnostic; only verified complete usage may omit it.\n    if 'usage_complete' not in stored and score.get('usage_complete') is True:\n        score={k:v for k,v in score.items() if k!='usage_complete'}\n    if score!=stored or not score['automated_gate_pass']:\n".replace('\n',newline)
    text=raw.decode('utf-8')
    if text.count(before)!=1:
        raise ValueError('Replay comparison anchor changed')
    patched=text.replace(before,after,1).encode('utf-8')
    patched_sha=hashlib.sha256(patched).hexdigest()
    if patched_sha != '5b250930ea9ee249ef71c5fae0135628cc664b174244ce88d45ae894bbef4eb8':
        raise ValueError('Unexpected compatibility worker bytes')
    folder=out/'compatibility/cellfix15-full39-replay-v1'
    worker=folder/'atomic_workflow_cellfix15.py'
    compile(patched,str(worker),'exec')
    record={'version':'cellfix15-full39-replay-compat-v1',
            'criteria_sha256':criteria_sha256,'original_workflow_sha256':original_sha,
            'compatibility_workflow_sha256':patched_sha,
            'change':'omit replay-only usage_complete only when recomputed True and absent from producer metrics',
            'producer_metrics_modified':False,'frozen_inputs_modified':False}
    metadata=(json.dumps(record,indent=2)+'\n').encode('utf-8')
    # Preserve previous attempts and the original frozen workflow.
    for path,data in ((worker,patched),(folder/'compatibility.json',metadata)):
        if path.exists() and path.read_bytes()!=data:
            raise ValueError('Preserve existing compatibility artifact: '+str(path))
    folder.mkdir(parents=True,exist_ok=True)
    for path,data in ((worker,patched),(folder/'compatibility.json',metadata)):
        if not path.exists():path.write_bytes(data)
    print('Using recorded full39 replay compatibility:',patched_sha)
    return str(worker)

FULL39_REVIEW_PATH = globals().get("FULL39_REVIEW_PATH", "")  # Reuse the full39 review path from this runtime.
RUN_VALIDATION30 = True
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
        uploaded=read_review(FULL39_REVIEW_PATH);assert len(uploaded)==1,'Upload full39 semantic-review.json, not the probe review.'
        import shutil
        import tempfile
        reviewed_full39=out/'reviewed-verifier39'
        worker=_cell7_replay_worker()
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
            '--binding-dir',str(root/'validation/cellfix15'),'--online-model-downloads'],timeout=5520,required=False)
        for name in ('metrics.json','classification.json','summary.json'):
            path=out/'validation30'/name
            print(name,path.read_text() if path.exists() else 'Incomplete; keep diagnostics.')
        if code==0 and (out/'validation30/HUMAN_REVIEW.html').exists():
            show_file(str(out/'validation30/HUMAN_REVIEW.html'))
        print('Keep every validation outcome. If used to tune, retire this set to development.')
    finally:
        download_archive()
