"""AI evidence notes for the received run; no human signature or changed prediction."""
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RUN='20261026T102553Z-54409fed'
BASE=ROOT/'research-runs'/('audit-cellfix10-full39-'+RUN)
OUT=BASE/'artifact/verifier39'
DEST=ROOT/'docs/reviews'/('cellfix10-full39-'+RUN)

# Findings are review artifacts, never inference inputs or model instructions.
NOTES={
 'contract:partial_accuracy':'Memory 25% có numeric proof; accuracy chưa báo cáo, AND thành NEI đúng. Missing ghi accuracy nhưng nên chỉ rõ yêu cầu 94%; không coi memory hỗ trợ accuracy.',
 'contract:partial_memory':'Accuracy 94% có proof; memory chưa có, AND thành NEI đúng. Missing nên nêu rõ mức giảm 25% so baseline thay vì chỉ tên memory.',
 'contract:both_supported':'Cả 25% less memory và 94% accuracy đúng Model Juniper, có source/requirement/check riêng; support đúng.',
 'contract:accuracy_conflict':'Memory 25% true, accuracy 81% phủ định 94% false; aggregate contradict đúng. Không dùng 94% bị phủ định làm observed value.',
 'contract:irrelevant':'NEI và missing target đúng. Observation member lại là đoạn The benchmark was conducted on a Tuesday. No, không phải Model Juniper hay entity có nghĩa; scope_match=matched chưa biểu đạt target thiếu. Cần review chất lượng identity/observation riêng.',
 'contract:negation':'Study did not use human labels là same-scope false; contradict đúng, không nhầm thiếu evidence.',
 'contract:causality_missing':'NEI đúng: index và latency cùng deployment chưa chứng minh caused. Missing chỉ ghi new index/latency, bỏ quan hệ nhân quả cần chứng minh; chưa đạt độ cụ thể của missing-information.',
 'contract:scope':'Fourth task less accurate là một false witness, refute ALL đúng; không cần đủ roster và không mượn polarity của ba task improved.',
 'contract:cross_sentence':'q0 kiểm 4 models, q1 kiểm 2 datasets từ hai câu, cùng report/event. Cả hai source_quote nguyên văn; q1 được bổ sung citation theo contract. Support có đủ hai requirement.',
 'contract:wrong_units':'Observed 12 hours, explicitly not 12 seconds. Numeric giữ đúng claimed/observed units; contradict đúng, không tự đổi đơn vị.',
 'contract:atomic_support':'Contained exactly 240 documents có đúng entity/sample, quantity/object và numeric check; support đúng.',
 'contract:bounded_scope':'Quote riêng tested dataset chứng minh recall improved; không đòi dataset khác; support đúng scope.',
 'scope:universal:support':'Closed three-shard population và each improved recall after revision có trong full quote, coverage=true; support ALL đúng.',
 'scope:universal:contradict':'The third worsened recalling là false member trong validation population sau revision; contradict ALL đúng.',
 'scope:universal:not_enough_info':'Hai shard positive không phủ hết population; complete set/results others chưa biết nên NEI đúng. Ledger chỉ giữ unknown collective, chưa lưu hai fact positive; missing remaining population đúng.',
 'scope:existential:support':'Birch faster là một true member sau patch; support SOME đúng. Không cần complete=true và không mượn outcome Elm/Fir.',
 'scope:existential:contradict':'Full audited roster Birch/Elm/Fir có outcomes increased/increased/unchanged, đều false cho reduced response time; complete=true nên contradict SOME đúng theo binding đã được người dùng chốt. population_binding_basis=unique_complete_selection_set được giữ.',
 'scope:existential:not_enough_info':'Elm tăng response time chỉ là một false member; other node results chưa báo cáo, chưa refute SOME. NEI và missing remaining population đúng.',
 'scope:none:support':'Whole monitored population no leaks, positive leaked=false trước NONE, complete=true; support đúng. Renderer không còn prose đảo thành có leak như cf9.',
 'scope:none:contradict':'Silver leaked=true trước NONE, cùng overnight test; một true witness refute NONE đúng.',
 'scope:none:not_enough_info':'Silver leak status chưa báo cáo, Blue/Green no leak không đủ để support NONE. NEI đúng; missing nên gọi rõ Silver để cụ thể hơn.',
 'scope:entity:support':'Quote North error rate decreased after calibration, không còn South-only citation; support đúng.',
 'scope:entity:contradict':'North error rate increased là same-scope false cho reduced; contradict đúng, không dùng South decreased.',
 'scope:entity:not_enough_info':'North calibration results không được ghi, không dùng South decreased để support. NEI đúng và missing giữ North/error rate/after calibration.',
 'scope:time:support':'Exactly four weekly trials conducted in May và each improved có coverage đầy đủ; bỏ April. May lọc population trial, không tự gán thời gian improvement.',
 'scope:time:contradict':'One reduced throughput thuộc bốn May trials là false witness, refute ALL đúng.',
 'scope:time:not_enough_info':'April improved không chứng minh May; May không có throughput results. NEI đúng; missing giữ in May, có thể nêu rõ không có kết quả May thay vì generic remaining population.',
 'scope:direction:support':'42 -> 31 milliseconds cùng requests/conditions, ordered change giảm -11; support đúng.',
 'scope:direction:contradict':'42 -> 55 milliseconds tăng +13, refute reduced; contradict đúng.',
 'scope:direction:not_enough_info':'31 milliseconds after-only không chứng minh giảm; missing baseline/comparison đúng. Đã hoàn tất, không còn invented author/year hoặc repair exhaustion.',
 'scope:metric:support':'Precision 0.81 -> 0.86 được check đúng metric/order, support đúng.',
 'scope:metric:contradict':'Precision 0.81 -> 0.74 false cho increased; không dùng recall 0.64 -> 0.79, contradict đúng.',
 'scope:metric:not_enough_info':'NEI/missing precision chưa đo đúng, nhưng quote duy nhất là Recall rose..., không trích Precision was not measured. Citation này không chứng minh lý do NEI về precision; quote_relevant chưa đạt.',
 'scope:conjunction:support':'ID lịch sử support nhưng gold hiện tại NEI theo strict-identity-v1: context thiếu extractor. Hai part đều NEI và missing identity đúng. Member là 5.4 to 4.6 gigabytes / 4.6 gigabytes, là measurement thay vì entity; observation prose cần review.',
 'scope:conjunction:contradict':'ID lịch sử contradict nhưng gold NEI vì workload chưa xác định extractor. Không bỏ qua binding để suy contradict từ recall 0.72 -> 0.68. Missing identity đúng; member workload/4.6 gigabytes chưa đúng entity.',
 'scope:conjunction:not_enough_info':'Đã assess đủ hai part, đều NEI vì extractor chưa bind; memory part không còn nhầm missing token recall. Member workload/4.6 gigabytes vẫn là identity chất lượng thấp. Token recall cũng chưa evaluated, renderer mới nêu missing identity trước.',
 'scope:condition:support':'Đúng three batches low-temperature và each gained yield after update; không mượn high-temperature. Coverage và support ALL đúng.',
 'scope:condition:contradict':'One lost yield thuộc low-temperature sau update là false witness refute ALL; đúng scope.',
 'scope:condition:not_enough_info':'NEI đúng vì low-temperature yield chưa measured. Observation lại dùng All measured high-temperature batches truth=unknown dù nhóm này có reported gained yield, trong scope_match=matched. Ledger/explanation lệch nhóm cần kiểm; missing giữ đúng low-temperature nhưng diễn đạt còn generic.'
}
FAILURES={
 'contract:causality_missing': ['missing_information_specific'],
 'scope:metric:not_enough_info': ['quote_relevant'],
 'scope:condition:not_enough_info': ['explanation_follows_evidence'],
}
IDENTITY_WARNINGS={
 'contract:irrelevant','scope:conjunction:support','scope:conjunction:contradict',
 'scope:conjunction:not_enough_info','scope:condition:not_enough_info'}


def main():
    audit=json.loads((ROOT/'docs'/('atomic-verifier-cellfix10-full39-audit-'+RUN+'.json')).read_bytes())
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
    table=['# AI evidence audit full39 cellfix10',
        'Run `'+RUN+'`. Nhãn 39/39 khớp frozen gold; AI còn đánh dấu tiêu chí semantic. Human review chưa hoàn tất.',
        '| Case | Gold/prediction | Tiêu chí AI chưa đạt | Ghi chú |',
        '|---|---|---|---|']
    for row in reviewed:
        table.append('| '+row['example_id']+' | '+row['prediction']+' | '+(', '.join(FAILURES.get(row['example_id'],[])) or 'Không đánh dấu trượt; vẫn cần human review')+' | '+row['notes']+' |')
    (DEST/'EVIDENCE_REVIEW_39.md').write_text('\n\n'.join(table[:2])+'\n\n'+'\n'.join(table[2:])+'\n',encoding='utf-8')
    print(json.dumps({'cases':39,'label_matches':39,'ai_semantic_flagged_cases':list(FAILURES),
        'human_review_completed':False,'form_checked_boxes':0,'form_criteria':195}))


if __name__=='__main__':main()
