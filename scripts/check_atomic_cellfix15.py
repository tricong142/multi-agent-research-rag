"""CPU regressions from the actual candidate; no inference or accuracy claim."""
import io
import json
from pathlib import Path
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'research-runs/atomic-cellfix15-candidate/workspace'
sys.path.insert(0,str(SOURCE))


def main():
    from research_rag.evaluation import evaluate_atomic_verifier as r
    criteria,*_=r.load_frozen(r.CRITERIA)
    modules=[n[:-3].replace('/','.') for n in criteria['source_sha256'] if n.startswith('research_rag/tests/') and n.endswith('.py')]
    if '--new-only' in sys.argv:modules=['research_rag.tests.test_atomic_cellfix15']
    log=ROOT/'research-runs/cellfix15-regression.log'
    with log.open('w',encoding='utf-8') as stream:
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(modules))
    checks={}
    if result.wasSuccessful():
        for mode,flags in [('smoke',['--assessment-smoke']),('probe',['--decomposition-probe']),('full39',[])]:
            stream=io.StringIO()
            with patch.object(sys,'argv',['check','--validate-only','--output-dir',str(ROOT/'research-runs/cellfix15-unused'),*flags]),redirect_stdout(stream):r.main()
            checks[mode]=json.loads(stream.getvalue())
    report=dict(candidate=criteria['policy'],criteria_sha256=r.sha256(r.CRITERIA),regression_tests=result.testsRun,
        regression_scope='new_only' if '--new-only' in sys.argv else 'all',failures=len(result.failures),errors=len(result.errors),
        all_regression_passed=result.wasSuccessful(),validate_only=checks,model_inference_completed=False,
        validation30_used_for_tuning=True,independent_validation_completed=False,promoted_to_serving=False)
    (ROOT/'docs/atomic-verifier-cellfix15-validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))
    if not result.wasSuccessful():print(log.read_text(encoding='utf-8')[-14000:])
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__=='__main__':main()
