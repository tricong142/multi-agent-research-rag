assert globals().get('run_id') == '20261020T061934Z-c87bce57', 'Runtime does not contain the audited run; restore audited artifacts first.'
RUN_FULL39 = True  # Change to True only after directly reviewing the new 18-claim probe.
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
        assert hashlib.sha256(next(iter(uploaded.values()))).hexdigest()=='06ce2e455f3c5da3273197ecd0dedf34b6f043f6df14bcdd76a8ee7dc88fee79', 'Upload the exact human review already audited; filename suffix (1) is allowed.'
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
            run('full39-review-form',[python,str(root/'atomic_workflow_cellfix8.py'),'--make-review',str(out/'verifier39'),'--review-mode','full39'],timeout=300)
            files.download(str(out/'verifier39/HUMAN_REVIEW.html'))
            print('Review the 39 predictions and evidence before validation30. No serving promotion.')
    finally:
        download_archive()
