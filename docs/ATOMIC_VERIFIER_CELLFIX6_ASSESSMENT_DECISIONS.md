# Cellfix6 — binding, annotation và assessment

## Quyết định annotation

Người dùng chọn: **“Giữ context, đánh nhãn lại theo evidence nghiêm ngặt.”**
Quyết định này áp dụng trong bản annotation `strict-identity-v1` của candidate
cellfix6; không thay dữ liệu, ZIP, prediction hoặc báo cáo lịch sử cellfix5.

| Ca gốc | Gold gốc | Gold mới | Lý do |
| --- | --- | --- | --- |
| scope:conjunction:support | support | not_enough_info | Context có memory/recall của workload, không định danh extractor trong claim. |
| scope:conjunction:contradict | contradict | not_enough_info | Recall giảm cũng chưa phản bác được extractor khi identity chưa được chứng minh. |
| scope:conjunction:not_enough_info | not_enough_info | not_enough_info | Thiếu identity và thiếu recall; không coi memory part đã được support. |

Ba rationale được sửa, hai label đổi. Mỗi bản sửa gắn SHA256 claim/context và
nhãn gốc; runner từ chối nếu input không khớp. Claim/context giữ nguyên byte.
Các fixture gốc vẫn có annotation ban đầu; runner áp bản sửa riêng sau khi đã
kiểm baseline lịch sử. Gold/rationale không được đưa vào payload cho model.
Đây là điều chỉnh annotation development theo quyết định của người dùng,
không phải một vòng human review độc lập cho mọi evidence/prediction.

Vì label đổi, điểm mới không được so trực tiếp với 21/39 như một cải thiện
model. Runner giữ `original_gold`, `gold`, `annotation_version` trong comparisons;
baseline 37/39 tiếp tục mang nhãn `historical_original`. Chấm lại prediction
lịch sử trên nhãn mới được ghi riêng là rescore, không phải inference mới.

## Quy tắc dùng chung

- **Identity:** từ gần nghĩa `extraction`/`extractor` hoặc cùng workload không
  đủ làm alias. Target không được xác định thì NEI ở cả hướng support/refute.
- **Metric:** bảo toàn median/mean và mọi modifier. Chỉ hỗ trợ lược một object
  modifier khi nguồn có cấu trúc rõ `for the same <objects>` cùng statistic/head.
  Ví dụ `mean packet latency` có thể gắn với `mean latency` trong phạm vi
  `for the same packets`; `median latency` hoặc `different packets` không thay thế.
- **Truth:** đánh positive predicate cho từng member trước lượng từ.
  `NONE leaked` với một member thực sự leaked có truth=true và refute NONE.
- **Thiếu thông tin:** “not reported/measured”, thiếu baseline hoặc thiếu
  population closure không phải một kết quả âm. Counterexample cần evidence
  trái với predicate, đúng subject/metric/time/condition.
- **Population:** giữ nguyên toán học ALL/SOME/NONE. Một positive witness đủ
  cho SOME; ALL-support và NONE-support cần closure thích hợp. Prompt yêu cầu
  chọn witness và điền coverage từ toàn context, không suy closure từ danh từ tập hợp.
- **Số liệu:** `afterward` và các temporal adverb được hỗ trợ không phải unit.
  Cặp before/after phải cùng metric, đúng thứ tự. Chỉ tách clause khi không làm
  mất modality/negation/retraction. Không chuyển đổi hoặc đoán unit thiếu.

## Thay đổi implementation

Candidate riêng ở `research-runs/atomic-cellfix6-candidate/workspace`.
Builder `scripts/build_atomic_cellfix6_candidate.py` lấy đúng 84 input đã audit
của cellfix5, xác minh release/ZIP và tạo manifest mới. Serving source đang làm
dở trong repository và các notebook đã release không được ghi đè.

- `assessment_rules.py`: finite evidence guards; phát hiện lỗi thì đưa vào repair
  có giới hạn. Không tự gán nhãn đúng thay model. Quy tắc scope dùng month và cặp
  hyphenated condition được liệt kê; không phải semantic parser tổng quát.
- `atomic_verifier.py`: gọi evidence guards; prompt assessment mới cho positive
  predicate/witness/closure, absence, scope và numeric role. Decomposition giữ nguyên.
- `numeric_verifier.py`: vocabulary non-unit dùng chung; chọn cặp số theo metric
  và clause; giữ các guard nguồn, chronology, modality/negation và đơn vị.
- `atomic_decoding.py`: lọc passage thiếu thông tin/sai scope rõ ràng và cặp số
  không bind được. Output unknown vẫn có đường hợp lệ. Guard phụ thuộc member
  chạy ở validator sau generation, không tuyên bố schema chứng minh entailment.
- Runner: áp bản annotation đã kiểm hash; bảo toàn baseline lịch sử và báo rescore riêng.

Giữ Qwen2.5-3B-Instruct/revision, NF4/float16, seed42, 8 calls/case,
2 attempts/stage, 1536 tokens/call, 180s/case và gate 39/39, zero false support,
zero runtime failures. Không giảm gate vì sửa annotation.

## Phạm vi kiểm chứng

Kết quả offline ghi ở `atomic-verifier-cellfix6-validation.json` và log
`research-runs/cellfix6-regression.log`; manifest ở
`atomic-verifier-cellfix6-candidate.json`. Regression gồm trace thật cellfix5
và câu development mới. Câu mới dùng để test code không được gọi là held-out.

Đã chạy: **211/211 regression đạt**, gồm 181 test hiện có và 30 test mới.
Hai fixture aggregation cũ từng cố tình gán truth trái evidence đã được chỉnh
câu evidence cho nhất quán, giữ nguyên kết quả phép tổng hợp cần kiểm.
Test số lượng label được cập nhật theo bản annotation mới (12 S / 12 C / 15 NEI).
Không bỏ test nào. Các kiểm tra checkpoint chạy trong thư mục temp thuộc
workspace để tránh lỗi quyền rename của temp Windows sandbox.

Ba entrypoint CLI `--validate-only` đạt: smoke12/96 calls, probe18/36 calls,
full39/312 calls. `load_frozen` kiểm source, prompt, contract, decoder, annotation,
model/budget/gate; claim/context không thay đổi. Manifest candidate có criteria
SHA256 `b9d77823b5c8d6d2a56d4053667b8b53f6e059a1f5edb9e7e3a7578a50f34071`.

Token filter thật với tokenizer Qwen đã kiểm hash đạt **7/7 đường thử**:
4 output thủ công hợp lệ được chấp nhận, 3 output sai bị từ chối (đảo cặp số,
thiếu numeric bắt buộc, thiếu evidence nhưng gán false). Có đường hợp lệ cho
dimensionless `afterward`, metric modifier được bind từ nguồn, unknown và
closed ALL coverage. Tất cả đường hợp lệ nằm trong 1536 tokens; không nạp
weights, không tạo prediction mới. Báo cáo: `atomic-verifier-cellfix6-tokenizer-check.json`.

Chưa chạy inference T4 cho cellfix6, chưa có điểm smoke/probe/full39 mới,
chưa có validation độc lập hoặc E2E. Prompt tốt hơn không chứng minh model sẽ
chọn đúng witness/coverage. Guard hữu hạn có thể bỏ sót paraphrase hoặc tạo thêm
repair; cần đo trên model thật với nguyên budget trước khi chấp nhận candidate.

Bước sau: kiểm local đạt, đóng gói notebook candidate đúng manifest; chạy
smoke rồi probe và review/admission đúng candidate, sau đó full39 trên annotation
đã chốt. Đánh giá độc lập riêng vẫn cần trước khi tích hợp Reader/Summarizer.
