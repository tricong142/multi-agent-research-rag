"""Review received plans and prepare a new, unsigned human form for this exact run."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
RUN = '20261017T111605Z-9505cc47'
OUT = ROOT/'research-runs'/('audit-cellfix4-fresh-'+RUN)/'artifact'
DOCS = ROOT/'docs'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
read = lambda p: json.loads(p.read_text(encoding='utf-8'))
lines = lambda p: [json.loads(s) for s in p.read_text(encoding='utf-8').splitlines()]


def main():
    audit_path = DOCS/('atomic-verifier-cellfix4-smoke-probe-audit-'+RUN+'.json')
    audit = read(audit_path)
    assert audit['all_output_hashes_valid'] and audit['all_input_bytes_match_released_payload']
    probe = OUT/'decomposition-probe'
    original_review = (probe/'semantic-review.json').read_bytes()
    template = read(probe/'semantic-review.json')
    assert template['reviewer'] == '' and template['reviewer_kind'] == '' and template['review_completed'] is False
    assert template['criteria_sha256'] == audit['criteria_sha256']
    assert template['predictions_sha256'] == sha(probe/'predictions.jsonl')
    rows = lines(probe/'predictions.jsonl')
    prior = lines(DOCS/'decomposition-semantic-review-20261016T024708Z-a57ee72a.jsonl')
    cases = read(probe/'cases.json')
    rubric = read(probe/'criteria.json')['decomposition_probe']['human_review_rubric']
    reviews = []
    for case, row, old in zip(cases,rows,prior):
        assert case['example_id'] == row['example_id'] == old['example_id']
        assert case['claim'] == old['claim']
        plan = row['result']['decomposition']
        # Check all actual current plans; this compares semantic content, not
        # an old review signature, timing, source or model assessment results.
        assert plan == old['decomposition'] and not plan['unresolved']
        review = deepcopy(old)
        review.update(run_id=RUN, reviewer='Codex', reviewer_kind='assistant',
            independent_human_review=False, human_review_completed=False,
            predictions_sha256=template['predictions_sha256'], criteria_sha256=template['criteria_sha256'],
            review_basis='Actual current plan inspected and verified identical to the previously reviewed v7 canonical plan. Current reviewer checked predicates, coverage, numeric requirements, quantifiers, entity/metric and restriction attachment. No historical human signature is transferred.')
        assert set(review['judgments']) == set(rubric)
        if case['example_id'] == 'decompose:014':
            review['notes'] += (' Diễn giải condition in May là bộ lọc population các trial conducted in May; '
                'không suy ra cải thiện throughput diễn ra trong May. Schema chưa có trường riêng cho thời gian của population; '
                'người review phải kiểm tra cách gắn restriction này. Không tự chuyển May sang thời gian của predicate.')
        review['review_status'] = 'semantic_pass_with_prompt_format_caveat' if review['prompt_format_deviations'] else 'semantic_pass'
        reviews.append(review)
    assert len(reviews) == 18 and sum(len(r['decomposition']['parts']) for r in reviews) == 20
    assert {r['example_id'] for r in reviews if r['prompt_format_deviations']} == {'decompose:010','decompose:014','decompose:018'}
    review_file = DOCS/('decomposition-semantic-review-cellfix4-'+RUN+'.jsonl')
    review_file.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in reviews),encoding='utf-8')

    # Reuse the existing offline form and its tested per-case controls. All
    # canonical plans match exactly; replace the unsigned template and run hashes.
    old_run = '20261016T024708Z-a57ee72a'
    page = (DOCS/('HUMAN_REVIEW_V7_'+old_run+'.html')).read_text(encoding='utf-8')
    marker = r'(<script id="template" type="application/json">)(.*?)(</script>)'
    match = re.search(marker,page,re.S)
    assert match is not None
    old_template = json.loads(match[2])
    for key in ('predictions_sha256','criteria_sha256'):
        page = page.replace(old_template[key],template[key])
    page = page.replace(old_run,RUN).replace('probe v7','probe cellfix4').replace('claim — v7','claim — cellfix4')
    intro_old = 'Provenance/replay và automated gate đạt. Review AI: 18/18 đạt năm rubric semantic;'
    intro_new = ('Provenance/replay và automated gate đạt. Smoke12 đúng 12/12; probe18 chỉ đo cấu trúc. '
        'Review AI đã đọc 20 parts, kiểm đủ năm tiêu chí và xác nhận các plan trùng với v7; '
        'human review cho candidate/hash mới vẫn chưa hoàn tất. Chữ ký v7 không được chuyển sang run này;')
    assert page.count(intro_old) == 1
    page = page.replace(intro_old,intro_new)
    # Update the case-014 note without altering its actual model output.
    old_note = next(r for r in prior if r['example_id']=='decompose:014')['notes']
    new_note = next(r for r in reviews if r['example_id']=='decompose:014')['notes']
    import html
    assert page.count(html.escape(old_note)) == 1
    page = page.replace(html.escape(old_note),html.escape(new_note))
    data = json.dumps(template,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    page = re.sub(marker,lambda m:m[1]+data+m[3],page,flags=re.S)
    assert page.count('type="checkbox"') == 90 and page.count('class="case"') == 18
    assert ' checked' not in page and 'https://' not in page and 'http://' not in page
    assert json.loads(re.search(marker,page,re.S)[2]) == template
    form = DOCS/('HUMAN_REVIEW_CELLFIX4_'+RUN+'.html')
    form.write_text(page,encoding='utf-8')

    smoke = []
    cases12 = read(OUT/'assessment-smoke/cases.json')
    for case,row in zip(cases12,lines(OUT/'assessment-smoke/predictions.jsonl')):
        result = row['result']
        assert result['assessed_label'] == case['label'] and result['status'] == 'completed'
        item = {'example_id':case['example_id'],'claim':case['claim'],'context':case['context'],
            'gold':case['label'],'code_label':result['assessed_label'],
            'reviewer_kind':'assistant','label_matches_gold':True,'notes':[],
            'part_evidence':[{'quote':p['part']['quote'],'label':p['assessed_label'],
                'observations':[{'member':o['member'],'model_truth':o['model_truth'],'code_truth':o['truth'],
                    'quotes':o['quotes'],'citation_additions':o['citation_additions'],
                    'numeric_result':o['numeric_result'],'model_explanation':o['explanation']}
                    for o in p['observations']]} for p in result['parts']]}
        if row['example_id'] == 'contract:accuracy_conflict':
            obs = result['parts'][0]['observations'][0]
            assert obs['model_truth'] == 'false' and obs['truth'] == 'true'
            item['notes'].append('Memory part: code correctly computes true for 25% reduction; model_truth=false and its accuracy-related explanation do not explain this memory decision. Keep raw versus derived truth visible. Aggregate contradict is correct because 94% accuracy is explicitly denied.')
        if row['example_id'] == 'contract:cross_sentence':
            obs = result['parts'][0]['observations'][0]
            assert obs['citation_additions'] == ['Evaluation used two datasets.']
            assert len(obs['numeric_result']) == 2
            item['notes'].append('Both separate quantity checks are grounded, true and cited in derived ledger; second citation came from the explicit raw numeric source_quote. Model explanation mentions four models only; use both code checks/quotes for the complete decision.')
        smoke.append(item)
    smoke_file = DOCS/('atomic-verifier-cellfix4-evidence-review-'+RUN+'.jsonl')
    smoke_file.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in smoke),encoding='utf-8')
    audit['assistant_review'] = {'probe_claims_inspected':18,'parts_inspected':20,
        'canonical_plans_equal_previous_v7':18,'all_five_semantic_rubrics_rechecked':True,
        'prompt_literal_compliance':False,'metric_format_caveats':['decompose:010','decompose:014','decompose:018'],
        'may_scope_note':'Population filter for trials conducted in May; not proof of improvement occurring in May.',
        'smoke_labels_and_evidence_inspected':12,'explanation_alignment_caveat':'contract:accuracy_conflict memory part',
        'human_review_completed':False,'human_approval_transferred':False,
        'files':{p.relative_to(ROOT).as_posix():sha(p) for p in (review_file,smoke_file,form)}}
    assert (probe/'semantic-review.json').read_bytes() == original_review
    audit_path.write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'form':str(form),'semantic_review':str(review_file),
        'evidence_review':str(smoke_file),'human_review_completed':False},ensure_ascii=False))


if __name__ == '__main__':
    main()
