"""AI evidence notes for the received run; no human signature or changed prediction."""
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RUN='20261027T025350Z-c67b6d37'
BASE=ROOT/'research-runs'/('audit-cellfix12-full39-'+RUN)
OUT=BASE/'artifact/verifier39'
DEST=ROOT/'docs/reviews'/('cellfix12-full39-'+RUN)

# Findings are review artifacts, never inference inputs or model instructions.
from scripts.review_atomic_cellfix10_full39 import NOTES as BASE_NOTES

NOTES={**BASE_NOTES,
 'contract:irrelevant':'NEI và missing target đúng, nhưng member=No model accuracy is reported là mệnh đề về việc báo cáo số liệu, không phải entity Model Juniper. Quotes rỗng; observation explanation dựng trên pseudo-member. AI đánh dấu explanation_follows_evidence chưa đạt, không dùng nhãn NEI đúng để bỏ lỗi identity.',
 'contract:causality_missing':'NEI đúng, cite The study did not establish a causal relationship. Missing causal_relationship nêu đầy đủ caused trong part quote; không suy cause từ co-occurrence. Dấu chấm lặp chỉ là formatting.',
 'scope:universal:not_enough_info':'Hai validation shard positive chưa phủ hết population. Member tập còn thiếu và unknown/incomplete giữ NEI; missing remaining members đúng. Có thể cite câu không xác định complete set để người đọc dễ đối chiếu.',
 'scope:existential:not_enough_info':'Other audited nodes chưa báo cáo nên SOME vẫn NEI; Elm increased không refute SOME nếu population chưa đóng. Member là nhóm còn thiếu, unknown; missing target/response time/after patch đúng. Quotes rỗng là điểm cần reviewer xem, không tự biến thành false evidence.',
 'scope:none:not_enough_info':"Nhãn NEI đúng, nhưng member=Silver's leak status was not là fragment cắt trước reported, không phải pump Silver. Renderer gọi fragment này là Member. Quote có đúng absence của Silver nhưng identity/observation explanation chưa đạt; không được coi trạng thái chưa báo cáo là false outcome.",
 'scope:entity:support':'Đã sửa trên run này: truth=true cho North gateway, quote đúng North error rate decreased after calibration; không cite South thay North. Support đúng.',
 'scope:entity:contradict':'Đã sửa trên run này: truth=false cho North gateway, quote đúng North error rate increased after calibration; không bỏ decisive witness bằng unknown. Contradict đúng.',
 'scope:entity:not_enough_info':'NEI đúng: context chỉ có outcome South và nói không có calibration results North. Member North gateway đúng; không dùng South để support. Missing đúng North/error rate/after calibration; quote rỗng có thể cải thiện nhưng không là citation sai.',
 'scope:time:not_enough_info':'May trials không có throughput results; April positive không áp lên May. Member đúng population May, unknown, không có quote. Missing giữ weekly trial/throughput/in May; reviewer cần phân biệt population filter May với event time improvement.',
 'scope:metric:not_enough_info':'Quote đúng Precision was not measured.; truth unknown và missing precision measurement đúng. Không mượn recall rose làm proof của precision.',
 'scope:conjunction:support':'Frozen gold NEI theo strict identity: workload không xác định extractor, không phải support dù ID lịch sử chứa support. Cả hai part đã được assess nhưng member=5.4 to 4.6 gigabytes và 4.6 gigabytes là quantities; quantity memory còn bị gọi là member của token recall. Missing identity đúng, observation explanation sai loại đối tượng.',
 'scope:conjunction:contradict':'Frozen gold NEI vì context thiếu extractor. Hai part NEI đúng nhưng member=For the same workload, tuning reduced memory use và 4.6 gigabytes là clause/quantity thay entity. Explanation dựng trên pseudo-member; không suy contradict cho extractor từ workload chưa bind.',
 'scope:conjunction:not_enough_info':'Cả hai part NEI vì thiếu extractor; token recall cũng chưa evaluated. Member=the extraction workload và 4.6 gigabytes không phải extractor; memory quantity bị gọi là member của token recall. Missing ưu tiên identity là đúng; observation explanation chưa đạt.',
 'scope:condition:not_enough_info':'Đã sửa nhãn về NEI, quote chỉ low-temperature absence và truth=unknown, không mượn high-temperature. Tuy nhiên member=no yield changes were là fragment cắt trước measured, không phải batch/group. Renderer gọi fragment là member; explanation_follows_evidence chưa đạt.'
}
FAILURES={cid:['explanation_follows_evidence'] for cid in (
 'contract:irrelevant','scope:none:not_enough_info','scope:conjunction:support',
 'scope:conjunction:contradict','scope:conjunction:not_enough_info','scope:condition:not_enough_info')}
IDENTITY_WARNINGS=set(FAILURES)



def main():
    audit=json.loads((ROOT/'docs'/('atomic-verifier-cellfix12-full39-audit-'+RUN+'.json')).read_bytes())
    assert audit['all_predictions_and_calls_replayed'] and audit['metrics_recomputed_exactly']
    cases=json.loads((OUT/'cases.json').read_bytes())
    rows=[json.loads(v) for v in (OUT/'predictions.jsonl').read_bytes().splitlines()]
    rubric=json.loads((OUT/'criteria.json').read_bytes())['human_review_rubric']
    assert len(cases)==len(rows)==len(NOTES)==39 and set(NOTES)=={c['example_id'] for c in cases}
    reviewed=[]
    for case,row in zip(cases,rows):
        cid=case['example_id']
        assert cid==row['example_id'] and case['label']==row['result']['assessed_label']
        judgments={k:k not in FAILURES.get(cid,[]) for k in rubric}
        reviewed.append({'example_id':cid,'claim':case['claim'],'context':case['context'],
            'frozen_gold':case['label'],'prediction':row['result']['assessed_label'],
            'judgments':judgments,'notes':NOTES[cid],
            'observation_identity_warning':cid in IDENTITY_WARNINGS})
    DEST.mkdir(parents=True,exist_ok=True)
    review={'run_id':RUN,'candidate':audit['candidate'],
        'criteria_sha256':audit['criteria_sha256'],
        'predictions_sha256':hashlib.sha256((OUT/'predictions.jsonl').read_bytes()).hexdigest(),
        'reviewer_kind':'assistant','reviewer':'Codex (AI evidence audit)',
        'ai_review_completed':True,'human_review_completed':False,
        'all_semantic_criteria_passed':False,'ai_flagged_semantic_cases':FAILURES,
        'cases':reviewed}
    (DEST/'AI_EVIDENCE_AUDIT.json').write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (DEST/'HUMAN_REVIEW.html').write_bytes((OUT/'HUMAN_REVIEW.html').read_bytes())
    page=(OUT/'HUMAN_REVIEW.html').read_text(encoding='utf-8')
    for row in reviewed:
        cid=row['example_id'];marker='<article data-id="'+cid+'">'
        assert page.count(marker)==1
        flags=FAILURES.get(cid,[])
        note='<aside style="border-left:4px solid '+('#b22' if flags else '#667')+';padding:12px;background:#f6f6f6"><b>Ghi chú AI — chưa phải human review</b><p>'+html.escape(row['notes'])+'</p>'
        if flags:note+='<p><b>AI đánh dấu chưa đạt:</b> '+html.escape(', '.join(flags))+'. Hãy đối chiếu nguồn; lưu review kể cả tiêu chí trượt.</p>'
        note+='</aside>'
        page=page.replace(marker,marker+note,1)
    assert page.count('<article ')==39 and page.count('data-key=')==195
    class Checkboxes(HTMLParser):
        def handle_starttag(self,tag,attrs):
            attrs=dict(attrs)
            if tag=='input' and attrs.get('type')=='checkbox':
                assert 'checked' not in attrs
    Checkboxes().feed(page)
    (DEST/'HUMAN_REVIEW_WITH_AI_NOTES.html').write_text(page,encoding='utf-8')
    table=['# AI evidence audit full39 cellfix12',
        'Run `'+RUN+'`. Nhãn 39/39 khớp frozen gold; AI còn đánh dấu tiêu chí semantic. Human review chưa hoàn tất.',
        '| Case | Gold/prediction | Tiêu chí AI chưa đạt | Ghi chú |',
        '|---|---|---|---|']
    for row in reviewed:
        table.append('| '+row['example_id']+' | '+row['prediction']+' | '+(', '.join(FAILURES.get(row['example_id'],[])) or 'Không đánh dấu trượt; vẫn cần human review')+' | '+row['notes']+' |')
    (DEST/'EVIDENCE_REVIEW_39.md').write_text('\n\n'.join(table[:2])+'\n\n'+'\n'.join(table[2:])+'\n',encoding='utf-8')
    print(json.dumps({'cases':39,'label_matches':39,'ai_semantic_flagged_cases':list(FAILURES),
        'human_review_completed':False,'form_checked_boxes':0,'form_criteria':195}))


if __name__=='__main__':main()
