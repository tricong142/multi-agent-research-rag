# Chạy candidate logic_v3 trên Kaggle — ba cell

Scope_v2 run 20261012T153832Z đạt 33/39, có một false support và một quote
validation failure. Candidate mới sửa quy trình kiểm tra logic và phản hồi lỗi
quote, chưa được kiểm chứng bằng model thật. Không dùng notebook scope_v2 cũ
để chạy bước này.

## Các bước chạy

1. Tạo notebook Kaggle **mới, Private**, import
   `scripts/kaggle_blind_verifier_logic_v3.ipynb`.
2. Bật **GPU T4/T4 x2 và Internet**. Thêm hai datasets workspace và runtime
   diagnostics **v2** hiện có như lượt verifier vừa chạy. Notebook đã đóng gói
   source, criteria, cases và snapshot v2; không cần upload lại datasets.
   Không cần Gemini Secret; không dùng quota Reader.
3. **Cell 1** mount datasets.
4. **Cell 2** cài môi trường, kiểm hashes, tests và preflight. Chờ
   `SETUP COMPLETE`. Nếu lỗi, giữ ZIP setup và dừng tại đây.
5. **Cell 3** chạy một lần. Dùng model base đã pin revision, cùng 39 cases,
   tối đa 78 calls. Có thể tải khoảng 6,2 GB weights nếu cache chưa có.
6. **Save Version with Output**, tải `rag-validation-…zip` được in cuối cell
   kể cả exit 1, rồi dừng GPU. Gửi ZIP để kiểm/replay trước khi tích hợp.

Không chạy lại cùng stage vào output cũ. Không chạy thêm Reader/confidence/
baseline hoặc toàn hệ trong phiên này.

## Đọc kết quả

- `summary.json`: `experiment_completed=true`, `prediction_count=39`,
  `backend_calls<=78`, `automated_gate_pass=true` mới đạt automation.
- `metrics.json`: ca cũ 12/12, ca mới 27/27; false support, wrong-label
  agreements và runtime failures phải zero. Macro-F1 không thay gate.
- `historical-verifier-metrics.json`: mốc **scope_v2 33/39**, có một false
  support và một failure. Không nhầm mốc này với base v1 11/12.
- `provenance.json`: `verifier_prompt_profile=logic_v3`,
  `repair_feedback_policy=quote_membership_v1`, model pairing đều true.
- `base_instruct-calls.jsonl`: messages/output; `base_instruct.jsonl` ghi
  attempts và validation_issue. Quote sai vẫn bị validator chặn, không tự sửa
  hoặc nhận nhãn gold từ scorer.
- `evidence-review.jsonl`: 39 rows còn pending để người đánh giá kiểm nhãn,
  quote, explanation, độ phủ từng factual part và missing information.

`experiment_completed=true` nhưng gate false có nghĩa candidate đã chấm xong
và trượt. Exit 1 lúc đó là chủ ý, không phải yêu cầu chạy lại setup. Summary
không tồn tại nghĩa là cần đọc status/stderr để xác định failure trước khi chấm.

## Giới hạn và việc cần làm sau đó

Đây là regression trên dữ liệu synthetic đã được inspect để sửa policy.
Automation pass chưa chứng minh generalization, chưa thay semantic review
bằng người hoặc đánh giá độc lập và chưa cho phép gọi toàn hệ đã hoàn thành.
Policy thay prompt và repair feedback cùng lúc; không kết luận riêng hiệu quả
prompt hoặc feedback. Snapshot v2 được chấm offline, không tốn calls model để
chạy lại baseline. Serving chưa đổi.

Sau khi verifier đủ bằng chứng chất lượng mới tích hợp và chạy các gate Reader,
Summarizer heldout_3, tám ca E2E, review câu trả lời/trích dẫn và tài liệu bảo vệ.
Nếu v3 trượt, giữ output để quyết định theo lỗi thực đo; không hạ gate.

## Implementation

- `04_factchecker/inference/verifier.py`: profile logic_v3, fixed quote feedback;
  baseline_v1 và scope_v2 prompt giữ nguyên.
- `research_rag/evaluation/compare_blind_verifier.py`: ghi validation issue;
  full-case historical comparison và input pairing; old criteria giữ behavior.
- `research_rag/evaluation/blind_verifier_logic_v3_criteria.json`,
  `blind_verifier_scope_v2_baseline.json`: policy/input/budget đóng băng.
- `research_rag/tests/test_blind_verifier_logic.py`: feedback, blinding,
  validation, gate, baseline đủ cases và tamper checks dùng model giả lập.
- `scripts/build_blind_verifier_notebook.py --logic-v3`: notebook riêng;
  các notebook cũ sinh lại để source hashes khớp code chung.

[Báo cáo ZIP scope_v2](BLIND_VERIFIER_REVIEW_20261012T153832Z.md).

26 focused tests local đạt: 9 verifier tests cũ, 7 regression tests, 6 logic/repair
tests và 4 tests notebook/source. Model dùng trong test là giả lập, không chứng
minh chất lượng logic_v3. [Bản ghi validation](blind-verifier-logic-v3-local-validation.json).
