"""Reproduce semantic member failures in saved cf12 outputs, without weights."""
import importlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RUN = '20261027T025350Z-c67b6d37'
BASE = ROOT/'research-runs'/('audit-cellfix12-full39-'+RUN)
SOURCE, OUT = BASE/'workspace', BASE/'artifact/verifier39'
DEST = ROOT/'docs/reviews'/('cellfix12-full39-'+RUN)


def main():
    sys.path.insert(0,str(SOURCE))
    a = importlib.import_module('04_factchecker.inference.atomic_verifier')
    f = importlib.import_module('04_factchecker.inference.assessment_focus')
    rules = importlib.import_module('04_factchecker.inference.assessment_rules')
    from research_rag.tests.test_atomic_assessment_v8 import AssessmentTokenFilterTests
    from research_rag.tests.test_atomic_smoke_cellfix3 import request
    spec = importlib.util.spec_from_file_location('cf12_full_review_check',SOURCE/'atomic_workflow_cellfix12.py')
    w = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w)
    review = json.loads((DEST/'AI_EVIDENCE_AUDIT.json').read_bytes())
    flagged = set(review['ai_flagged_semantic_cases'])
    rows = [json.loads(s) for s in (OUT/'predictions.jsonl').read_bytes().splitlines()]
    tester = AssessmentTokenFilterTests()
    tester.setUp()
    findings = []
    for row in rows:
        if row['example_id'] not in flagged:
            continue
        for trace in row['result']['trace']:
            if trace['stage']=='decompose':
                continue
            payload = json.loads(trace['messages'][1]['content'])
            p,ctx,raw = payload['part'],payload['context'],trace['output']
            checked = a.assess_part(raw,p,ctx)
            legal = tester.accepts(tester.ordered(raw),request(payload['claim'],p,ctx))
            assert legal
            for obs in checked['observations']:
                findings.append({'example_id':row['example_id'],'part':p['quote'],
                    'member':obs['member'],'truth':obs['truth'],'quotes':obs['quotes'],
                    'raw_output_accepted_by_validator':True,
                    'character_token_fixture_accepts_same_ledger':legal,
                    'complete_absence_regex_matches_member':bool(rules._MISSING.search(obs['member'])),
                    'observation_focus_issue':f.observation_focus_issue(p,obs['member'],obs['quotes'],obs['truth'],ctx)})
    assert len(findings)==9 and {v['example_id'] for v in findings}==flagged
    # Regenerate the original form from the frozen workflow, without signatures.
    with tempfile.TemporaryDirectory(dir=ROOT/'research-runs',prefix='cf12-full39-review-check-') as temp:
        folder=Path(temp)/'full39'
        shutil.copytree(OUT,folder)
        w.make_review(folder,'full39')
        # Colab writes LF; Windows write_text uses CRLF. The form text must match.
        original_form=(OUT/'HUMAN_REVIEW.html').read_bytes()
        regenerated_form=(folder/'HUMAN_REVIEW.html').read_bytes()
        assert regenerated_form.decode('utf-8').replace('\r\n','\n')==original_form.decode('utf-8').replace('\r\n','\n')
        (folder/'semantic-review.json').write_bytes((DEST/'AI_EVIDENCE_AUDIT.json').read_bytes())
        try:
            w.require_full39(folder,BASE/'artifact/reviewed-probe')
        except ValueError as exc:
            block=str(exc)
            assert 'human review' in block.lower()
        else:
            raise AssertionError('An AI evidence audit cannot satisfy the human gate')
    result={'run_id':RUN,'kind':'saved_ledger_semantic_reproducer','findings':findings,
        'human_form_text_matches_frozen_renderer':True,
        'form_comparison_normalization':'CRLF to LF only',
        'original_colab_html_preserved_bytes':True,'human_signature_created':False,
        'ai_review_does_not_admit_validation30':True,'admission_block':block,
        'new_model_inference':False,'predictions_modified':False}
    (DEST/'GUARD_DIAGNOSTICS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='findings'},ensure_ascii=False))


if __name__=='__main__':
    main()
