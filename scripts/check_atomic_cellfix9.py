"""Run the actual frozen cf9 regressions and three validate-only modes offline."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'research-runs/atomic-cellfix9-candidate/workspace'
sys.path.insert(0,str(SOURCE))


def main():
    temporary=ROOT/'research-runs/cellfix9-test-tmp';temporary.mkdir(exist_ok=True)
    tempfile.tempdir=str(temporary)
    from research_rag.evaluation import evaluate_atomic_verifier as r
    assert Path(r.__file__).resolve().is_relative_to(SOURCE)
    frozen,cases,*_=r.load_frozen(r.CRITERIA)
    modules=[n[:-3].replace('/','.') for n in frozen['source_sha256'] if n.startswith('research_rag/tests/') and n.endswith('.py')]
    if '--new-only' in sys.argv:modules=['research_rag.tests.test_atomic_assessment_cellfix9']
    if '--focused' in sys.argv:modules=['research_rag.tests.'+name for name in
        ('test_atomic_verifier','test_atomic_smoke_cellfix','test_atomic_smoke_cellfix3',
         'test_atomic_assessment_cellfix6','test_atomic_assessment_cellfix9')]
    suite=unittest.defaultTestLoader.loadTestsFromNames(modules)
    log=ROOT/'research-runs/cellfix9-regression.log'
    with log.open('w',encoding='utf-8') as stream:
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    validations={}
    for mode,flags in [('smoke',['--assessment-smoke']),('probe',['--decomposition-probe']),('verifier',[])]:
        stream=io.StringIO()
        with patch.object(sys,'argv',['check','--validate-only','--output-dir',str(ROOT/'research-runs/cellfix9-unused'),*flags]),redirect_stdout(stream):
            r.main()
        validations[mode]=json.loads(stream.getvalue())
    report={'candidate':frozen['policy'],'criteria_sha256':r.sha256(r.CRITERIA),'regression_tests':result.testsRun,
            'regression_scope':'new_only' if '--new-only' in sys.argv else 'focused' if '--focused' in sys.argv else 'all',
            'failures':len(result.failures),'errors':len(result.errors),'all_regression_passed':result.wasSuccessful(),
            'validate_only':validations,'model_inference_completed':False,'full39_quality_measured':False,
            'independent_validation_completed':False,'promoted_to_serving':False}
    (ROOT/'docs/atomic-verifier-cellfix9-validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))
    if not result.wasSuccessful():print(log.read_text(encoding='utf-8')[-20000:])
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__=='__main__':main()
