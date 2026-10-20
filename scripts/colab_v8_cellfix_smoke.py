# Replace the OLD assessment-smoke cell with this cell, after the preparation cell.
import json
from google.colab import files

smoke_passed = False
assert all(statuses.get(n,{}).get('exit_code') == 0 for n in
           ('regression-cellfix','smoke-validate-only-cellfix')), 'Finish the cellfix preparation first.'
try:
    code = run('assessment-smoke',[python,'-u','-m','research_rag.evaluation.evaluate_atomic_verifier',
        '--output-dir',str(out/'assessment-smoke'),'--assessment-smoke','--online-model-downloads'],
        timeout=2520,required=False)
    path = out/'assessment-smoke/metrics.json'
    metrics = json.loads(path.read_text()) if path.exists() else {}
    print(json.dumps(metrics,indent=2) if metrics else 'No final metrics: inspect saved logs and summary.')
    case_path, prediction_path = out/'assessment-smoke/cases.json', out/'assessment-smoke/predictions.jsonl'
    if case_path.exists() and prediction_path.exists():
        gold = {c['example_id']:c['label'] for c in json.loads(case_path.read_text())}
        for line in prediction_path.read_text().splitlines():
            row=json.loads(line); r=row['result']
            issues=[e.get('validation_issue') for e in r['trace'] if e.get('validation_issue')]
            print(row['example_id'],'gold=',gold[row['example_id']],'prediction=',r['assessed_label'],
                  'stop=',r['stop_reason'],'issues=',issues)
    smoke_passed = code == 0 and metrics.get('automated_gate_pass') is True
finally:
    bundle()
    files.download(str(out.with_suffix('.zip')))
assert smoke_passed, 'Smoke still failed: preserve this NEW ZIP and stop before probe/full39.'
print('Smoke passed. The original probe cell now uses this candidate workspace; human review must be new.')
