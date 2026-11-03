"""Reproduce accepted bad full39 ledgers without model weights or changed outputs."""
import importlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
RUN='20261026T150123Z-615bf4eb'
BASE=ROOT/'research-runs'/('audit-cellfix11-full39-'+RUN)
SOURCE=BASE/'workspace'
sys.path.insert(0,str(SOURCE))


def main():
    a=importlib.import_module('04_factchecker.inference.atomic_verifier')
    f=importlib.import_module('04_factchecker.inference.assessment_focus')
    decisions=importlib.import_module('04_factchecker.inference.assessment_decisions')
    rules=importlib.import_module('04_factchecker.inference.assessment_rules')
    from research_rag.tests.test_atomic_smoke_cellfix3 import request
    from research_rag.tests.test_atomic_assessment_v8 import AssessmentTokenFilterTests
    tester=AssessmentTokenFilterTests();tester.setUp()
    folder=BASE/'artifact/verifier39'
    cases=json.loads((folder/'cases.json').read_bytes())
    outputs=[json.loads(v) for v in (folder/'predictions.jsonl').read_bytes().splitlines()]
    findings=[]
    for case,row in zip(cases,outputs):
        if case['label']==row['result']['assessed_label']:continue
        trace=next(t for t in reversed(row['result']['trace']) if t['stage']!='decompose')
        payload=json.loads(trace['messages'][1]['content'])
        p,ctx,raw=payload['part'],payload['context'],trace['output']
        checked=a.assess_part(raw,p,ctx)
        legal=tester.accepts(tester.ordered(raw),request(payload['claim'],p,ctx))
        assert legal and checked['assessed_label']==row['result']['assessed_label']
        obs=checked['observations'][0]
        entry={'example_id':case['example_id'],'gold':case['label'],
            'prediction':checked['assessed_label'],'raw_assessment_accepted_on_replay':True,
            'character_token_filter_accepts_stored_wrong_ledger':legal,
            'decoder_test_kind':'LMFE character-token fixture, not Qwen inference',
            'member':obs['member'],'truth':obs['truth'],'quotes':obs['quotes'],
            'finite_decision_evidence':decisions.decision_evidence(p,ctx),
            'member_scope_issue':f.member_scope_issue(p,obs['member'],obs['quotes'],ctx),
            'focus_issue':f.focus_issue(checked,p,ctx),'preferred_absence_quotes':f.absence_quotes(p,ctx),
            'source_quote_contains_member':[rules.contains(obs['member'],q) for q in obs['quotes']]}
        if case['example_id'].startswith('scope:entity'):
            entry['code_mechanism']='No atomic decisive witness because the multiword modifier guard also covers North gateway; unknown quoted clauses can fall back to the full-context member clause, leaving another entity quote or no quote accepted.'
        else:
            own=[c for c in rules.clauses(ctx) if rules.contains(obs['member'],c)]
            entry['old_missing_regex_matches_owned_clauses']=[bool(rules._MISSING.search(c)) for c in own]
            entry['code_mechanism']='Direct absence recognizer finds no yield changes were measured, but focus only requires the quote for unknown. The false branch survives because the older absence regex lacks this construction; an absence clause is accepted as a false member.'
        findings.append(entry)
    assert len(findings)==3
    dest=ROOT/'docs/reviews'/('cellfix11-full39-'+RUN);dest.mkdir(parents=True,exist_ok=True)
    report={'run_id':RUN,'kind':'read_only_bad_ledger_reproducer','findings':findings,
        'new_model_inference':False,'predictions_modified':False,'source_modified':False,
        'validation30_used':False}
    (dest/'GUARD_DIAGNOSTICS.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
