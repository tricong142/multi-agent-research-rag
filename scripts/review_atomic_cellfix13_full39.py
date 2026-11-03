"""Review the received full39 evidence; keep AI notes separate from human approval."""
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RUN = '20261027T113721Z-18c80dae'
BASE = ROOT / 'research-runs' / ('audit-cellfix13-full39-' + RUN)
OUT = BASE / 'artifact/verifier39'
DEST = ROOT / 'docs/reviews' / ('cellfix13-full39-' + RUN)

# These judgments concern this archive only; they are never model inputs.
NOTES = {
    'contract:partial_accuracy': 'Memory 25% có bằng chứng và numeric check đúng. Accuracy 94% chưa được báo cáo; part accuracy unknown và missing đúng target/metric, nên AND là NEI. Không dùng memory để support accuracy.',
    'contract:partial_memory': 'Accuracy 94% được xác nhận, memory 25% chưa có bằng chứng. Cả hai part được kiểm; missing chỉ memory của Model Juniper, nên NEI đúng.',
    'contract:both_supported': 'Câu nguồn xác nhận cả memory giảm 25% và accuracy 94%. Hai numeric records gắn đúng metric/value; cả hai part support và AND support.',
    'contract:accuracy_conflict': 'Memory 25% support; accuracy thực tế 81%, nguồn phủ định trực tiếp 94%. Numeric record chọn 81% làm giá trị nguồn, không chọn 94% trong phủ định. Một part contradict đủ refute AND.',
    'contract:irrelevant': 'NEI đúng: nguồn không xác định Model Juniper. Run mới có observations rỗng, coverage rỗng/incomplete và scope unknown; missing yêu cầu bind đúng target. Không còn dùng No model accuracy is reported làm member giả.',
    'contract:negation': 'Nguồn phủ định trực tiếp việc study dùng human labels. Member study, truth false và quote cùng scope; đây là kết quả phủ định, không phải chưa đo. Contradict đúng.',
    'contract:causality_missing': 'Chỉ có co-occurrence, nguồn nói chưa xác lập causal relationship. Quote đúng câu này; unknown và missing nêu quan hệ caused của claim, nên NEI. Dấu chấm lặp ở cuối missing là lỗi trình bày nhỏ, không đổi nghĩa.',
    'contract:scope': 'ALL bị refute bởi a fourth task became less accurate sau compression. Một phản ví dụ cùng scope đủ contradict; không cần giả định đã biết toàn bộ population.',
    'contract:cross_sentence': 'Hai yêu cầu độc lập được kiểm: four models=4 models và two datasets=2 datasets. Hai numeric records dùng đúng hai câu nguồn; citation_additions đưa câu datasets vào quotes. Support có đủ cả hai yêu cầu.',
    'contract:wrong_units': 'Claim 12 seconds khác nguồn 12 hours, nguồn còn phủ định 12 seconds trực tiếp. Record giữ đúng unit của mỗi bên và explicit_quantity_denial, nên contradict; không so hai số 12 rồi support.',
    'contract:atomic_support': 'Sample và nguồn final sample bind được; 240 documents được kiểm đúng value/unit/object. Metric contained 240 documents đầy đủ và support đúng.',
    'contract:bounded_scope': 'Quote xác nhận method tăng recall trên tested dataset. Kết quả chưa biết ở dataset khác không phủ định claim có phạm vi giới hạn này. Condition đúng, support đúng.',
    'scope:universal:support': 'Population đóng gồm đúng Cedar, Maple, Pine; nguồn nói each of these three shards cải thiện recall sau revision. Group member three shards đại diện đúng toàn bộ tập có nguồn, coverage complete nên ALL support.',
    'scope:universal:contradict': 'Nguồn xác định ba shard, shard thứ ba giảm khả năng recall sau revision. Member the third là tham chiếu về shard trong cùng quote; truth false refute ALL, không cần closure để tìm phản ví dụ.',
    'scope:universal:not_enough_info': 'Hai shard cải thiện chưa chứng minh EVERY khi complete set và kết quả còn lại chưa biết. Unknown member là nominal the complete set of validation shards có trong nguồn; coverage incomplete và missing đúng population/results. Quotes rỗng không được dùng làm bằng chứng cho true/false.',
    'scope:existential:support': 'Birch thuộc audited cache nodes và nhanh hơn sau patch. Một witness cùng scope đủ SOME support; Elm/Fir chậm hơn không xóa witness này.',
    'scope:existential:contradict': 'Dùng cách hiểu annotation đã được người dùng chốt: complete audited set là toàn bộ audited cache nodes của claim. Birch/Elm tăng response time, Fir không đổi; complete population không có true member, nên SOME contradict. Group member và closure quote cùng xác định ba node.',
    'scope:existential:not_enough_info': 'Elm tăng response time nhưng kết quả các audited nodes khác chưa báo cáo. Một false witness không refute SOME khi population chưa đóng. Unknown nominal the other audited nodes đúng nguồn; missing đòi population/results, NEI đúng.',
    'scope:none:support': 'Nguồn đóng tập đúng ba pumps và xác nhận không pump nào leak trong overnight test. Truth false áp lên positive predicate leaked trước NONE; complete coverage làm NONE support, không đảo polarity hai lần.',
    'scope:none:contradict': 'Silver thuộc monitored pumps và leaked trong overnight test. Truth true của leaked là witness refute NONE; quote giữ đúng Silver/time, contradict đúng.',
    'scope:none:not_enough_info': 'Đã sửa identity: member Silver, không còn fragment leak status was not. Quote có câu Silver chưa được báo cáo; truth unknown, không biến unreported thành no leak. Blue/Green không leak chưa đủ support NONE; missing đúng kết quả còn thiếu, NEI đúng.',
    'scope:entity:support': 'Member North gateway, quote chính North error rate decreased sau calibration. Không dùng South; positive evidence support đúng.',
    'scope:entity:contradict': 'Member North gateway, quote chính North error rate increased sau calibration. Truth false refute reduced; không bỏ bằng chứng quyết định bằng unknown. Contradict đúng.',
    'scope:entity:not_enough_info': 'Nguồn chỉ có outcome South và nói không có calibration results North. North unknown, quotes rỗng và missing đúng North/error rate/after calibration; NEI đúng. scope_match=mismatched mô tả thiếu outcome phù hợp, không phải bằng chứng North tăng error rate.',
    'scope:time:support': 'Nguồn đóng tập bốn trials conducted in May và nói each cải thiện throughput. May là điều kiện chọn population trial, không ép thời điểm improvement. Quote loại April; coverage complete, ALL support.',
    'scope:time:contradict': 'Bốn trials May gồm một trial reduced throughput. Member one là tham chiếu trực tiếp trong cùng quote về May trials; phản ví dụ đúng condition refute ALL.',
    'scope:time:not_enough_info': 'Member the weekly trials conducted in May và quote đúng câu không có throughput results May. Không lấy April support May. Unknown/coverage incomplete, missing giữ population/metric/May, NEI đúng.',
    'scope:direction:support': 'Cùng requests/conditions: latency 42 ms trước patch, 31 ms sau patch. Numeric change giữ đúng thứ tự và unit, delta -11/decrease khớp reduced nên support.',
    'scope:direction:contradict': 'Cùng requests/conditions: latency 42 ms trước, 55 ms sau patch. Numeric change delta +13/increase trái reduced nên contradict, không đổi chiều baseline/final.',
    'scope:direction:not_enough_info': 'Chỉ biết latency sau patch 31 ms; nguồn nói không có baseline/comparative change. Unknown và missing yêu cầu baseline đúng metric/target; không suy giảm từ một số đo nên NEI.',
    'scope:metric:support': 'Numeric record precision 0.81 trước -> 0.86 sau configuration change, delta +0.05. Quote cùng điều kiện, đúng metric precision nên support.',
    'scope:metric:contradict': 'Numeric record chọn precision 0.81 -> 0.74, delta -0.07, không lấy recall 0.64 -> 0.79. Precision giảm refute increased, contradict đúng.',
    'scope:metric:not_enough_info': 'Quote đúng Precision was not measured. và truth unknown; missing yêu cầu measurement precision. Recall tăng không support precision và không đo không đồng nghĩa kết quả giảm. NEI đúng.',
    'scope:conjunction:support': 'ID lịch sử chứa support nhưng frozen gold đã chốt NEI theo strict identity: workload không xác định extractor. Cả memory và token recall có empty unknown ledger; missing đúng extractor/metric/After tuning. Không còn lấy 5.4 to 4.6 gigabytes làm member hoặc gán nó cho recall.',
    'scope:conjunction:contradict': 'Frozen gold NEI vì chưa bind workload với extractor. Cả hai part được kiểm, empty ledger/scope unknown, missing identity đúng từng metric/time. Không dùng memory clause hay 4.6 gigabytes làm entity; không suy contradict cho extractor từ workload chưa bind.',
    'scope:conjunction:not_enough_info': 'Context thiếu extractor; recall còn chưa evaluated. Hai part NEI, observations rỗng, missing ưu tiên identity đúng từng metric/time. Không dùng extraction workload hoặc memory quantity thay extractor; không khẳng định outcome recall.',
    'scope:condition:support': 'Nguồn đóng low-temperature group đúng ba batches và each gained yield sau update. Quote chỉ low group; high-temperature lost yield ngoài scope không refute claim. Coverage complete và ALL support đúng.',
    'scope:condition:contradict': 'Nguồn low-temperature group ba batches có một batch lost yield sau update. Member one được bind bằng cùng quote về low group, truth false là phản ví dụ refute ALL.',
    'scope:condition:not_enough_info': 'Đã sửa member thành low-temperature group có nguồn, không còn fragment no yield changes were. Quote chỉ câu chưa đo yield changes low group; truth unknown và missing giữ batch/yield/after update/low condition. Không đưa high-temperature vào ledger; NEI đúng.'
}


def main():
    audit = json.loads((ROOT / 'docs' / ('atomic-verifier-cellfix13-full39-audit-' + RUN + '.json')).read_bytes())
    assert audit['all_predictions_and_calls_replayed'] and audit['metrics_recomputed_exactly']
    cases = json.loads((OUT / 'cases.json').read_bytes())
    rows = [json.loads(v) for v in (OUT / 'predictions.jsonl').read_bytes().splitlines()]
    rubric = json.loads((OUT / 'criteria.json').read_bytes())['human_review_rubric']
    assert len(cases) == len(rows) == len(NOTES) == 39
    assert set(NOTES) == {c['example_id'] for c in cases} and len(rubric) == 5
    reviewed = []
    for case, row in zip(cases, rows):
        cid = case['example_id']
        assert cid == row['example_id'] and case['label'] == row['result']['assessed_label']
        reviewed.append({'example_id': cid, 'claim': case['claim'], 'context': case['context'],
                         'frozen_gold': case['label'], 'prediction': row['result']['assessed_label'],
                         'judgments': dict.fromkeys(rubric, True), 'notes': NOTES[cid],
                         'parts': row['result']['parts'], 'claim_explanation': row['result']['explanation']})
    review = {'run_id': RUN, 'candidate': audit['candidate'], 'criteria_sha256': audit['criteria_sha256'],
              'predictions_sha256': hashlib.sha256((OUT / 'predictions.jsonl').read_bytes()).hexdigest(),
              'reviewer_kind': 'assistant', 'reviewer': 'Codex (AI evidence audit)',
              'ai_review_completed': True, 'human_review_completed': False,
              'all_semantic_criteria_passed': True, 'ai_flagged_semantic_cases': {}, 'cases': reviewed,
              'limitations': ['AI judgments are review assistance, not human approval.',
                              'No validation30 inference or independent accuracy is measured here.']}
    DEST.mkdir(parents=True, exist_ok=True)
    (DEST / 'AI_EVIDENCE_AUDIT.json').write_text(json.dumps(review, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (DEST / 'HUMAN_REVIEW.html').write_bytes((OUT / 'HUMAN_REVIEW.html').read_bytes())
    page = (OUT / 'HUMAN_REVIEW.html').read_text(encoding='utf-8')
    for row in reviewed:
        marker = '<article data-id="' + row['example_id'] + '">'
        assert page.count(marker) == 1
        note = ('<aside style="border-left:4px solid #667;padding:12px;background:#f6f6f6">'
                '<b>Ghi chú AI — chưa phải human review</b><p>' + html.escape(row['notes']) + '</p></aside>')
        page = page.replace(marker, marker + note, 1)

    class Form(HTMLParser):
        def __init__(self):
            super().__init__()
            self.criteria = self.boxes = self.notes = self.cards = 0

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == 'article':
                self.cards += 1
            if tag == 'textarea':
                self.notes += 1
            if tag == 'input' and attrs.get('type') == 'checkbox':
                self.boxes += 1
                assert 'checked' not in attrs
                self.criteria += int('data-key' in attrs)

    form = Form()
    form.feed(page)
    assert (form.cards, form.criteria, form.notes, form.boxes) == (39, 195, 39, 196)
    # Preserve the original export code and its hashes; negative judgments can still be exported.
    original_script = (OUT / 'HUMAN_REVIEW.html').read_text(encoding='utf-8').split('<script>', 1)[1]
    assert page.split('<script>', 1)[1] == original_script
    (DEST / 'HUMAN_REVIEW_WITH_AI_NOTES.html').write_text(page, encoding='utf-8')

    # Test the real frozen admission gate with assistant metadata, never human metadata.
    with tempfile.TemporaryDirectory(prefix='ai-review-gate-', dir=str(BASE)) as temp:
        staged = Path(temp) / 'full39'
        shutil.copytree(OUT, staged)
        (staged / 'semantic-review.json').write_text(json.dumps(review), encoding='utf-8')
        result = subprocess.run([sys.executable, str(BASE / 'workspace/atomic_workflow_cellfix13.py'),
                                 '--admit-full39', '--full39-dir', str(staged),
                                 '--probe-dir', str(BASE / 'artifact/reviewed-probe')],
                                cwd=BASE / 'workspace', capture_output=True, text=True, timeout=300)
        assert result.returncode != 0 and 'Completed human review bound' in result.stderr, result.stderr
        block = 'Completed human review bound to this candidate and predictions is required'
    validation = {'run_id': RUN, 'form_cards': form.cards, 'form_criteria': form.criteria,
                  'form_notes_fields': form.notes, 'prechecked_boxes': 0, 'original_export_script_unchanged': True,
                  'original_html_bytes_preserved': (DEST / 'HUMAN_REVIEW.html').read_bytes() == (OUT / 'HUMAN_REVIEW.html').read_bytes(),
                  'ai_true_judgments': 195, 'ai_false_judgments': 0, 'human_review_completed': False,
                  'ai_review_admission_blocked': True, 'gate_message': block}
    (DEST / 'review-validation.json').write_text(json.dumps(validation, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    table = ['# AI evidence audit full39 Cellfix13',
             'Run `' + RUN + '`. AI review: 39 ca / 195 tiêu chí chưa thấy lỗi semantic. Human review còn pending.',
             'Các phán xét dưới đây là của AI; người review tự đọc evidence và xác nhận từng tiêu chí trong form mới.',
             '| Case | Gold = prediction | Ghi chú AI |', '|---|---|---|']
    for row in reviewed:
        table.append('| ' + row['example_id'] + ' | ' + row['prediction'] + ' | ' + row['notes'] + ' |')
    (DEST / 'EVIDENCE_REVIEW_39.md').write_text('\n\n'.join(table[:3]) + '\n\n' + '\n'.join(table[3:]) + '\n', encoding='utf-8')
    print(json.dumps(validation, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
