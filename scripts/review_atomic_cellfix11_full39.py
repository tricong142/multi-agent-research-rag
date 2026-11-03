"""AI review of failed cf11 full39; no human review export or prediction edits."""
import hashlib
import json
from pathlib import Path

from scripts.review_atomic_cellfix10_full39 import NOTES as BASE_NOTES

ROOT=Path(__file__).resolve().parents[1]
RUN='20261026T150123Z-615bf4eb'
BASE=ROOT/'research-runs'/('audit-cellfix11-full39-'+RUN)
OUT=BASE/'artifact/verifier39'
DEST=ROOT/'docs/reviews'/('cellfix11-full39-'+RUN)

NOTES={**BASE_NOTES,
 'contract:irrelevant':'NEI và missing target đúng. Member No model accuracy is reported là một câu absence, chưa phải entity. Không tạo false support nhưng identity/observation còn chưa tốt.',
 'contract:causality_missing':'Đã sửa trên output mới: NEI, quote The study did not establish a causal relationship., missing causal_relationship giữ causal predicate. Không coi index và lower latency cùng deployment là chứng minh cause. Dấu chấm cuối lặp là formatting.',
 'scope:existential:not_enough_info':'Elm increased chỉ là một false member, không bác SOME khi others chưa báo cáo. NEI đúng; quote Results for the other audited nodes were not reported. và missing population liên quan.',
 'scope:none:not_enough_info':'Silver status chưa báo cáo; Blue/Green no leaks không đủ support NONE. NEI đúng, cite câu chứa leak status Silver chưa báo cáo; missing nên gọi rõ Silver.',
 'scope:entity:support':'SAI NHÃN: gold support, prediction NEI. Member North gateway nhưng quote duy nhất nói South error rate increased; nguồn đã nói North decreased after calibration. Unknown không được miễn binding quote/member hoặc tự bỏ evidence North.',
 'scope:entity:contradict':'SAI NHÃN: gold contradict, prediction NEI. Source nói North error rate increased after calibration, là counterevidence của reduced; model dùng unknown và quotes=[] nhưng validator chấp nhận, không repair.',
 'scope:time:not_enough_info':'NEI đúng do May không có throughput results. Quote gồm April positive và May no-results; không dùng April làm outcome May, missing giữ in May. Có thể rút quote về câu May để rõ hơn.',
 'scope:metric:not_enough_info':'Đã sửa đúng quote: Precision was not measured.; label NEI, missing precision measurement_unreported. Không còn cite Recall rose... thay cho bằng chứng thiếu precision.',
 'scope:conjunction:not_enough_info':'Đã kiểm đủ hai part; thiếu identity extractor nên NEI theo strict-identity-v1. Cả hai observation dùng the extraction workload thay entity extractor, identity còn yếu nhưng không suy support từ số workload. Recall cũng chưa evaluated; missing ưu tiên identity.',
 'scope:condition:not_enough_info':'SAI NHÃN: gold NEI, prediction contradict. Model dùng no yield changes were measured for that group làm member=false, cite đúng câu low-temperature nhưng biến thiếu phép đo thành false witness refute ALL. Đây không phải counterevidence của gained yield.'}
FAILURES={
 'scope:entity:support':['label_correct','quote_relevant','explanation_follows_evidence','missing_information_specific'],
 'scope:entity:contradict':['label_correct','explanation_follows_evidence','missing_information_specific'],
 'scope:condition:not_enough_info':['label_correct','explanation_follows_evidence','missing_information_specific'],
}


def main():
    audit=json.loads((ROOT/'docs'/('atomic-verifier-cellfix11-full39-audit-'+RUN+'.json')).read_bytes())
    assert audit['all_predictions_and_calls_replayed'] and audit['metrics_recomputed_exactly']
    cases=json.loads((OUT/'cases.json').read_bytes())
    rows=[json.loads(v) for v in (OUT/'predictions.jsonl').read_bytes().splitlines()]
    rubric=json.loads((OUT/'criteria.json').read_bytes())['human_review_rubric']
    assert len(cases)==len(rows)==len(NOTES)==39 and set(NOTES)=={c['example_id'] for c in cases}
    reviews=[]
    for c,row in zip(cases,rows):
        cid=c['example_id'];assert cid==row['example_id']
        correct=c['label']==row['result']['assessed_label']
        assert correct==(cid not in FAILURES)
        reviews.append({'example_id':cid,'claim':c['claim'],'context':c['context'],
            'frozen_gold':c['label'],'prediction':row['result']['assessed_label'],
            'judgments':{k:k not in FAILURES.get(cid,[]) for k in rubric},'notes':NOTES[cid]})
    assert sum(v['judgments']['label_correct'] for v in reviews)==36
    DEST.mkdir(parents=True,exist_ok=True)
    result={'run_id':RUN,'candidate':audit['candidate'],'criteria_sha256':audit['criteria_sha256'],
        'predictions_sha256':hashlib.sha256((OUT/'predictions.jsonl').read_bytes()).hexdigest(),
        'reviewer_kind':'assistant','reviewer':'Codex (AI evidence audit)',
        'ai_review_completed':True,'human_review_completed':False,
        'automated_gate_pass':False,'all_semantic_criteria_passed':False,'cases':reviews,
        'validation30_authorized_by_this_audit':False,'new_model_inference_during_audit':False}
    (DEST/'AI_EVIDENCE_AUDIT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    table=['# AI review full39 Cellfix11',
        'Run `'+RUN+'`: 36/39 nhãn đúng; false support=0, runtime=0. Gate chưa đạt; human review không thể thay gate 39/39.',
        '| Case | Gold | Prediction | Tiêu chí AI chưa đạt | Ghi chú |',
        '|---|---|---|---|---|']
    for v in reviews:
        table.append('| '+v['example_id']+' | '+v['frozen_gold']+' | '+v['prediction']+' | '
            +(', '.join(FAILURES.get(v['example_id'],[])) or 'Không đánh dấu trượt; vẫn cần review nếu phát hành')+' | '+v['notes']+' |')
    (DEST/'EVIDENCE_REVIEW_39.md').write_text('\n\n'.join(table[:2])+'\n\n'+'\n'.join(table[2:])+'\n',encoding='utf-8')
    print(json.dumps({'cases_reviewed':39,'correct_labels':36,'failed_cases':list(FAILURES),
        'human_signature_created':False,'validation30_ready':False}))


if __name__=='__main__':main()
