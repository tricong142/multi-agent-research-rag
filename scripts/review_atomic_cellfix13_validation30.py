"""Per-case AI diagnostic notes for failed validation, with no human signature."""
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = '20261027T151114Z-20ea1926'
BASE = ROOT / 'research-runs' / ('audit-cellfix13-validation30-' + RUN)
OUT = BASE / 'artifact/validation30'
DEST = ROOT / 'docs/reviews' / ('cellfix13-validation30-' + RUN)

NOTES = {
    1: ('quantity_identifier,unknown_despite_measurement', 'Nguồn nêu Model E-4 + LibriSpeech LM đạt 88.26% WER. Numeric requirements lại có quantity giả 4 achieved từ model ID; ledger unknown dù có measurement. Gold support giữ nguyên; NEI sai.'),
    2: ('quantity_identifier,condition_binding', 'LibriSpeech LM gắn 88.26%, còn 80.40% thuộc Lyrics LM. Claim 80.40% với LibriSpeech bị refute; model trả unknown. Numeric requirements còn có 4 achieved giả từ E-4. Cần bind target/LM/value, không lấy số cùng paragraph tùy ý.'),
    3: ('quantity_identifier', 'NEI đúng vì không có memory comparison. Tuy nhiên numeric requirements có 4 used giả từ E-4 ngoài quantity 25%; nhãn đúng chưa chứng minh quantity contract đúng.'),
    4: ('target_alias_or_shared_head', 'Nguồn liệt kê For WMT De-En, En-De and Zh-En we measure detokenized BLEU. Exact target WMT En-De bị coi vắng mặt do shared WMT head/list. Empty ledger làm bỏ support; cần quy chiếu có chứng cứ, không nới lỏng mọi alias.'),
    5: ('target_alias_or_shared_head', 'Cùng nguồn WMT detokenized BLEU refute tokenized BLEU của claim. Empty ledger/missing identity bỏ bằng chứng quyết định; NEI sai. IWSLT tokenized BLEU thuộc setup khác.'),
    6: ('missing_reason_target_vs_measurement', 'NEI đúng: paragraph không cho BLEU score 30. Missing hiện đòi target identity trong khi WMT En-De được quy chiếu qua danh sách; cần nêu thiếu score thay vì nhầm thiếu target.'),
    7: ('citation_quality_warning', 'Support 41.87 SARI/WikiLarge khớp nguồn và numeric record cuối đúng. Quotes chứa các đoạn dài cắt giữa mệnh đề, hai đoạn trùng nhau; citation bổ sung đầy đủ giữ được bằng chứng. Cần review quote selection, không coi mọi literal substring là quote tốt.'),
    8: ('predicate_condition_binding', 'Nguồn nói without requiring any external resource or modified training objective. Claim required modified objective phải contradict. Plan lại đưa modified training objective vào condition và metric achieve its WikiLarge score; unknown bỏ phủ định trực tiếp của requirement.'),
    9: ('deadline,quantifier_population', 'Không có latency 20 ms nên gold NEI; run không có final label. Assessment mất 2716.593455 giây dù còn 174.427156 giây deadline. Plan gán ALL cho subject parametrization thay vì từng sentence; cần kiểm population của object quantifier.'),
    10: ('decomposition_fragment,numeric_object_binding,repair_exhausted', 'Plan chấp nhận fragment and 14,769 actions và entity 4,340 cho part visible. Unit bị lấy video/are. Assessment quantity 14,769 actions lại chọn right=4,340 of hai lần; guard từ chối và hết repair. Nguồn có đủ 1,268 clips, 14,769 actions, 4,340 visible.'),
    11: ('deadline,count_subset_reasoning', 'Gold contradict vì chỉ 4,340 trong 14,769 actions visible, không phải all. Assessment quá deadline, không có final label/generation event. Cần kiểm count/subset logic và deadline thực tế.'),
    12: ('decomposition_metric,repair_control', 'NEI đúng vì không có duration 10 seconds. Attempt đầu invent complete coverage từ fragment về paper contributions; validator reject và repair thành incomplete. Metric lasts vẫn chỉ động từ, missing không nêu duration cụ thể; nhãn đúng chưa làm decomposition đầy đủ.'),
    13: ('unknown_despite_numeric_evidence,compound_quantity_object', 'Nguồn We achieve 0.548 prediction accuracy và câu sau quy về model. Numeric result cùng 0.548 nhưng ledger vẫn unknown. Unit prediction chỉ là phần đầu của prediction accuracy; missing nói thiếu measurement đang có trong nguồn.'),
    14: ('unknown_despite_measurement,compound_quantity_object', 'Nguồn chỉ rõ accuracy 0.548, refute claim 0.748 trong cùng report. Model trả unknown không quote; numeric object chỉ prediction. Gold contradict giữ nguyên; cần kiểm binding qua câu, không thay gold thành NEI để tăng điểm.'),
    15: ('quantifier_attachment,decoder_validator_conflict,repair_exhausted', 'Cả hai attempts gán ALL cho accuracy và each prediction; normalize từ chối quantifier_not_preserved. Đã kiểm hàm frozen: decoder ép enum all cho cả hai alternatives, nhưng validator chấp nhận accuracy=atomic, latency=all. Đây là đường schema loại output hợp lệ; repair không thể sửa qua decoder hiện tại. Counterfactual dùng để kiểm contract, không phải prediction mới.'),
    16: ('compound_count_duration_contract', 'Nhãn support đúng; source xác nhận 120 half-hour conversations. Numeric requirement/record lại là 120 half, chưa biểu diễn độc lập count 120 và duration half-hour. Cần kiểm contrast với ca 017, không dùng nhãn đúng để kết luận duration contract đã được kiểm đầy đủ.'),
    17: ('compound_count_duration_contract', 'Nguồn half-hour refute two-hour. Requirements tạo 120 two và two=2 rời rạc; model unknown thay vì refute. Phải tách count conversations và duration conversation, giữ quan hệ của chúng.'),
    18: ('target_apposition,missing_reason_target_vs_measurement', 'NEI đúng vì không có WER 5%. CALLHOME BIBREF11, transcriptions... đã có apposition trong nguồn; missing target identity phản ánh exact-match guard quá hẹp thay vì nêu thiếu WER.'),
    19: ('known_member_identity,closure_member_binding', 'Nhãn support đúng theo nguồn 80 events, each paired with news. Tuy nhiên ledger/coverage member Dataset BIBREF15 is a small data set consisting là clause fragment, không phải plane-crash event/group. Known truth=true vẫn lọt guard identity; đây là lỗi semantic dù nhãn đúng.'),
    20: ('quantifier_population,subset_counterevidence', 'Nguồn 40 training và 40 testing refute all 80 training. Plan đặt ALL lên Stanford Plane Crash Dataset thay vì event population và đẩy all 80 events for training thành condition. Unknown/missing closure bỏ counterevidence có sẵn.'),
    21: ('false_refutation,missing_property_is_unknown', 'Nguồn không nói language của news articles. Ledger gán news articles=false cho written in French chỉ từ câu paired with related news articles; không có bằng chứng non-French. Đây là false refutation: phải NEI, không phải contradict.'),
    22: ('multi_quantity_object_binding', 'Nguồn xác nhận 980 annotations trong 670 Turkish tweets, gold support. Requirements chỉ lấy 980 name và 670 Turkish làm unit/object; ledger unknown, không quote. Cần binding đủ count + object + language restriction cho từng quantity.'),
    23: ('quantifier_population,subset_counterevidence', 'Nguồn eight categories nhưng study chỉ first three. Claim all eight phải contradict. Plan dùng entity study cho ALL thay vì categories; requirement eight named thiếu full object. Unknown bỏ explicit subset counterevidence.'),
    24: ('compound_quantity_object', 'NEI đúng vì context không nêu số annotators. Requirement Three human lấy human làm unit thay vì human annotators; giữ nhận xét contract này tách khỏi nhãn đúng. Missing phải hướng vào annotator count/binding chưa được báo cáo.'),
    25: ('subject_comparator_reversal', 'Nguồn our model tốt hơn wav2letter Transformer trên test-other. Claim nói proposed model nhưng decomposition chọn entity the wav2letter Transformer (đối chứng), truth false và contradict. Gold support đúng; phải giữ hướng subject/comparator và dataset.'),
    26: ('target_coreference,unknown_despite_counterevidence', 'Nguồn our model vẫn worse than best hybrid model trên test-other, refute better. Proposed model không exact-match our model nên empty ledger. Cần coreference có căn cứ của paper, không áp alias tùy tiện cho workload chưa xác định.'),
    27: ('epistemic_causal_specificity', 'NEI đúng: source chỉ The reason might be, không nói experimentally established. Missing renderer hiện ghi generic scoped evidence và condition chứa because; cần người review kiểm việc nêu rõ thiếu experimental/causal certainty.'),
    28: ('section_identifier,decomposition_fragment,target_coreference', 'Nguồn PDTB hereafter -> sections 0-1 là development for hyperparameter optimization. Range section IDs bị coi quantities 0 và 1 were. AND nối hai mục đích nhưng split thành part hyperparameter optimization với entity chính nó; cả hai part NEI vì binding/fragment.'),
    29: ('section_identifier,target_coreference', 'Nguồn sections 21-22 là test, sections 0-1 là development nên claim test set phải contradict. Exact PDTB sections 0-1 vắng nguyên chuỗi làm empty ledger; section IDs còn bị coi quantities với unit were.'),
    30: ('missing_reason_review', 'NEI đúng: nguồn không cho số epochs. Missing hiện đòi study identity thay vì training-epoch evidence; source dùng we/our corpus. Cần kiểm quy chiếu paper và nêu thông tin training còn thiếu, không suy 10 epochs từ section IDs.')
}


def main():
    audit = json.loads((ROOT / 'docs' / ('atomic-verifier-cellfix13-validation30-audit-' + RUN + '.json')).read_bytes())
    assert audit['all_stored_outputs_replayed'] and audit['all_metrics_and_classification_recomputed']
    cases = json.loads((OUT / 'cases.json').read_bytes())
    rows = [json.loads(v) for v in (OUT / 'predictions.jsonl').read_bytes().splitlines()]
    assert len(cases) == len(rows) == len(NOTES) == 30
    reviewed = []
    for index, (case, row) in enumerate(zip(cases, rows), 1):
        assert case['example_id'] == row['example_id'] == 'validation-v1:' + str(index).zfill(3)
        categories, note = NOTES[index]
        reviewed.append({**case, 'prediction': row['result']['assessed_label'],
                         'label_matches_frozen_gold': case['label'] == row['result']['assessed_label'],
                         'stop_reason': row['result']['stop_reason'], 'elapsed_ms': row['result']['elapsed_ms'],
                         'diagnostic_categories': categories.split(','), 'notes': note,
                         'decomposition': row['result']['decomposition'], 'parts': row['result']['parts']})
    report = {'run_id': RUN, 'candidate': audit['candidate'], 'criteria_sha256': audit['criteria_sha256'],
              'predictions_sha256': hashlib.sha256((OUT / 'predictions.jsonl').read_bytes()).hexdigest(),
              'reviewer_kind': 'assistant', 'reviewer': 'Codex (AI diagnostic audit)',
              'ai_diagnostic_review_completed': True, 'human_review_completed': False,
              'automated_gate_pass': False, 'ready_for_next_pipeline_stage': False,
              'gold_changed': False, 'cases': reviewed}
    DEST.mkdir(parents=True, exist_ok=True)
    (DEST / 'AI_DIAGNOSTIC_REVIEW.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    original = (OUT / 'HUMAN_REVIEW.html').read_bytes()
    (DEST / 'HUMAN_REVIEW.html').write_bytes(original)
    page = original.decode('utf-8')
    for row in reviewed:
        marker = '<article data-id="' + row['example_id'] + '">'
        assert page.count(marker) == 1
        note = ('<aside style="padding:12px;border-left:4px solid #b60;background:#fff4df">'
                '<b>AI diagnostic — validation gate đã trượt; không phải chữ ký human</b><p>'
                + html.escape(row['notes']) + '</p></aside>')
        page = page.replace(marker, marker + note, 1)

    class Form(HTMLParser):
        def __init__(self):
            super().__init__()
            self.cards = self.criteria = self.notes = 0

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            self.cards += int(tag == 'article')
            self.notes += int(tag == 'textarea')
            if tag == 'input' and attrs.get('type') == 'checkbox':
                assert 'checked' not in attrs
                self.criteria += int('data-key' in attrs)

    form = Form()
    form.feed(page)
    assert (form.cards, form.criteria, form.notes) == (30, 150, 30)
    assert page.split('<script>', 1)[1] == original.decode('utf-8').split('<script>', 1)[1]
    (DEST / 'HUMAN_REVIEW_WITH_AI_NOTES.html').write_text(page, encoding='utf-8')
    table = ['# Diagnostic Validation30 Cellfix13',
             'Run `' + RUN + '`: 10/30 nhãn đúng, 4 incomplete, gate failed. AI notes không phải human acceptance.',
             '| Case | Frozen gold | Prediction | Nhận xét |', '|---|---|---|---|']
    for row in reviewed:
        table.append('| ' + row['example_id'] + ' | ' + row['label'] + ' | ' + (row['prediction'] or '__incomplete__') + ' | ' + row['notes'] + ' |')
    (DEST / 'EVIDENCE_REVIEW_30.md').write_text('\n\n'.join(table[:2]) + '\n\n' + '\n'.join(table[2:]) + '\n', encoding='utf-8')
    print(json.dumps({'cases_reviewed': 30, 'human_criteria_blank': 150, 'human_notes_blank': 30,
                      'gold_changed': False, 'human_review_completed': False,
                      'original_export_script_unchanged': True, 'form': str(DEST / 'HUMAN_REVIEW_WITH_AI_NOTES.html')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
