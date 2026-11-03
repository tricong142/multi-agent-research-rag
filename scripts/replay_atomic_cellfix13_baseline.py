"""Preserve the human-rejected cf12 run and replay saved ledgers, never scores."""
from collections import Counter
import difflib
import importlib
import json
from pathlib import Path
import sys
from scripts.atomic_validation_review import digest,json_bytes

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'research-runs/audit-cellfix12-admission-20261027T092904Z-e02b51ab'
SOURCE=ROOT/'research-runs/atomic-cellfix13-candidate/workspace'
sys.path.insert(0,str(SOURCE))


def main():
    a=importlib.import_module('04_factchecker.inference.atomic_verifier')
    candidate=json.loads((ROOT/'docs/atomic-verifier-cellfix13-candidate.json').read_bytes())
    preserved=json.loads((ROOT/'docs/atomic-verifier-cellfix12-preserved-before-cellfix13.json').read_bytes())
    assert digest((BASE/'original-output.zip').read_bytes())==preserved['zip_sha256']
    assert digest((BASE/'uploaded-semantic-review.json').read_bytes())==preserved['human_review_sha256']
    assert digest((BASE/'artifact/verifier39/predictions.jsonl').read_bytes())==preserved['predictions_sha256']
    for name,expected in preserved['parent_release_files'].items():
        assert digest((ROOT/name).read_bytes())==expected,name
    for name,expected in preserved['baseline_outputs_sha256'].items():
        assert digest((BASE/'artifact'/name).read_bytes())==expected,name
    for name,expected in preserved['validation30_files_sha256'].items():
        assert digest((ROOT/'docs/validation/atomic-cellfix6-v1'/name).read_bytes())==expected,name
    entries=[]
    for line in (BASE/'artifact/verifier39/predictions.jsonl').read_bytes().splitlines():
        row=json.loads(line)
        for trace in row['result']['trace']:
            if trace['stage']=='decompose':continue
            p=json.loads(trace['messages'][1]['content'])
            try:
                result=a.assess_part(trace['output'],p['part'],p['context'])
                entry={'accepted':True,'replayed_label':result['assessed_label']}
            except ValueError as exc:
                entry={'accepted':False,'rejection':str(exc)}
            entries.append({'example_id':row['example_id'],'part':p['part']['quote'],**entry})
    rejected=[e for e in entries if not e['accepted']]
    expected={r['example_id'] for r in preserved['human_failed_cases']}
    assert expected <= {r['example_id'] for r in rejected},rejected
    report={'candidate':candidate['candidate'],'criteria_sha256':candidate['criteria_sha256'],
        'parent_run':preserved['run_id'],'saved_assessments':len(entries),
        'outcomes':dict(Counter('accepted' if e['accepted'] else 'rejected' for e in entries)),
        'entries':entries,'additional_rejections':[e for e in rejected if e['example_id'] not in expected],
        'baseline_release_and_human_review_preserved':True,'validation30_used_for_tuning':False,
        'new_model_inference':False,'new_predictions_created':False}
    folder=ROOT/'docs/reviews/cellfix13-development';folder.mkdir(parents=True,exist_ok=True)
    (folder/'BASELINE_TRACE_REPLAY.json').write_bytes(json_bytes(report))
    parent=ROOT/'research-runs/atomic-cellfix12-candidate/workspace';diffs=[]
    for name in candidate['input_manifest']:
        if not name.startswith('04_factchecker/inference/') or not name.endswith('.py'):continue
        old=(parent/name).read_text(encoding='utf-8') if (parent/name).exists() else ''
        new=(SOURCE/name).read_text(encoding='utf-8')
        if old!=new:diffs.extend(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='cellfix12/'+name,tofile='cellfix13/'+name))
    (folder/'CODE_DIFF.patch').write_text(''.join(diffs),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='entries'}))


if __name__=='__main__':main()
