"""Offline candidate checks. No model loading, no new predictions."""
import hashlib
import importlib
import json
from pathlib import Path
import sys
import time
import tempfile
import unittest
from contextlib import redirect_stdout
import io
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'research-runs/atomic-cellfix6-candidate/workspace'
sys.path.insert(0,str(SOURCE))


def main():
    # Keep test-created checkpoints inside the writable workspace on Windows.
    temp=ROOT/'research-runs/cellfix6-test-tmp'
    temp.mkdir(exist_ok=True)
    tempfile.tempdir=str(temp)
    from research_rag.evaluation import evaluate_atomic_verifier as runner
    assert Path(runner.__file__).resolve().is_relative_to(SOURCE)
    criteria,cases,*_=runner.load_frozen(runner.CRITERIA)
    modules=[n[:-3].replace('/','.') for n in criteria['source_sha256']
        if n.startswith('research_rag/tests/') and n.endswith('.py')]
    if '--new-only' in sys.argv:
        modules=['research_rag.tests.test_atomic_assessment_cellfix6']
    suite=unittest.defaultTestLoader.loadTestsFromNames(modules)
    started=time.perf_counter()
    log=ROOT/'research-runs/cellfix6-regression.log'
    with log.open('w',encoding='utf-8') as stream:
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    validation={
        'candidate':criteria['policy'],'criteria_sha256':runner.sha256(runner.CRITERIA),
        'kind':'offline_regression_and_validate_only','regression_tests':result.testsRun,
        'failures':len(result.failures),'errors':len(result.errors),
        'all_regression_passed':result.wasSuccessful(),'new_tests_only':'--new-only' in sys.argv,
        'elapsed_seconds':round(time.perf_counter()-started,3),
        'log':'research-runs/cellfix6-regression.log',
        'validate_only':{'verifier':{'freeze_valid':True,'cases':len(cases),'maximum_calls':criteria['maximum_total_backend_calls']}},
        'new_model_inference_completed':False,'full39_quality_measured':False,
        'independent_validation_completed':False,'serving_modified':False}
    probe,claims,_=runner.probe_configuration(criteria,cases,runner.CRITERIA)
    smoke,selected=runner.smoke_configuration(criteria,cases)
    for key,spec,rows in [('probe',probe,claims),('smoke',smoke,selected)]:
        validation['validate_only'][key]={'freeze_valid':True,'cases':len(rows),'maximum_calls':spec['maximum_total_backend_calls']}
    for mode,flags in [('verifier',[]),('probe',['--decomposition-probe']),('smoke',['--assessment-smoke'])]:
        stream=io.StringIO()
        with patch.object(sys,'argv',['evaluate_atomic_verifier','--validate-only',
                '--output-dir',str(ROOT/'research-runs/cellfix6-validate-only-unused'),*flags]),redirect_stdout(stream):
            runner.main()
        assert json.loads(stream.getvalue())==validation['validate_only'][mode]
    validation['validate_only_cli_checked']=True
    # Confirm every recorded parent input/output byte still exists unchanged.
    parent=ROOT/'research-runs/audit-cellfix5-full39-20261018T153854Z-2c3e0bd6'
    preserved=json.loads((ROOT/'docs/atomic-verifier-cellfix5-preserved-before-cellfix6.json').read_text())
    assert runner.sha256(parent/'original-output.zip')==preserved['zip_sha256']
    assert runner.sha256(parent/'artifact/verifier39/predictions.jsonl')==preserved['original_predictions_sha256']
    for name,item in preserved['parent_inputs'].items():
        assert runner.sha256(parent/'workspace'/name)==item['sha256']
    validation['parent_preserved']=True
    path=ROOT/'docs/atomic-verifier-cellfix6-validation.json'
    path.write_text(json.dumps(validation,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(validation),flush=True)
    if not result.wasSuccessful():
        print(log.read_text(encoding='utf-8')[-22000:])
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__=='__main__':
    main()
