# Kết quả audit cellfix4 và bước tiếp theo

ZIP: `output-cellfix4-fresh-20261017T111605Z-9505cc47.zip`.
SHA256: `e8f12af4d25948f158ab2acd4fd48989d756b40721c0081943be345f09a08cac`.

**Smoke12 đã đạt; probe18 đã đạt cấu trúc. Human review của run này vẫn pending;
full39 chưa chạy. Chưa có cơ sở tuyên bố Ready hoặc zero false support trên full39.**

| Kiểm tra | Kết quả thực trong ZIP, đã đối chiếu/replay |
| --- | --- |
| Provenance | 62 file đầu ra, 81 file đầu vào khớp release; 34 source/fixture khớp hash |
| Model | Qwen/Qwen2.5-3B-Instruct, revision `aa8e72537993ba99e69dfaafa59ed015b17504d1`, NF4/float16/seed42; provenance khớp baseline |
| Môi trường | CUDA preflight và toàn bộ stage exit 0; regression 166 test đạt trên Colab |
| Validate-only | Cả probe18, smoke12, full39 đều freeze_valid; đây là kiểm cấu hình, không phải inference full39 |
| Smoke | 12/12 đúng nhãn: 4 support, 4 contradict, 4 NEI; false_support=0, runtime_failed_rows=0 |
| Smoke calls | 28; không repair, không deadline/truncation failure; 3577 generated tokens |
| Probe | 18/18 decomposition hợp lệ, 20 parts, không incomplete; label_accuracy=null |
| Probe calls | 18; mỗi claim một call; 976 generated tokens |
| Replay | Đối chiếu 46 bộ call_started/generation/call_finished; raw JSON, schema hash, prompt và deadline metadata khớp |
| Human/serving | Human chưa ký run này; overall_pass=false, promoted_to_serving=false |

Hash kiểm tính nhất quán với candidate đã biết, không phải chữ ký xác thực máy
Colab; weights từ máy GPU không nằm trong ZIP để tự rehash ở local.

## Điều đã xác nhận từ bằng chứng

`contract:cross_sentence` đã hoàn tất với nhãn support. Hai check độc lập là
four/models và two/datasets; cả hai cho true. Câu `Evaluation used two datasets.`
đã có trong raw numeric.source_quote, được xác minh rồi thêm vào ledger và ghi
`citation_additions`. Không tự tạo bằng chứng hoặc bỏ quantity thứ hai.

Trong `contract:accuracy_conflict`, part memory có model_truth=false nhưng code
tính true cho giảm 25% memory; part accuracy bị refute bởi 81%, not 94% nên nhãn
tổng contradict đúng. Raw explanation của part memory lại nói về accuracy.
Đây là lệch giải thích của model, không phải false support theo nhãn của run.
Khi review/hiển thị cần đọc code_truth, numeric_result và citation; không dùng
riêng raw model_explanation để giải thích part này. Explanation cross_sentence
cũng chỉ nhắc four models; ledger/checks mới thể hiện đủ hai quantity.

## Review probe18

Đã đọc toàn bộ 20 parts, kiểm predicate, coverage/quantity, lượng từ, entity/metric
và restriction. Cả 18 canonical plan của run mới trùng nội dung plan v7 đã review.
Điều này giúp đối chiếu semantic; không chuyển chữ ký human cũ sang candidate mới.

Không thấy predicate/quantity bị rơi trong phần review AI. Vẫn có ba vi phạm
format literal của prompt, giữ nguyên trong artifact:

| Claim | Metric thực tế | Dạng named property prompt yêu cầu |
| --- | --- | --- |
| 010 | improved recall | recall |
| 014 | improved throughput | throughput |
| 018 | gained yield | yield |

Những metric này vẫn chứa đúng property; hướng thay đổi còn trong quote.
Không kết luận prompt-format compliance 100%. Human cần đọc lưu ý trước khi đánh
giá binding. Nếu tiêu chuẩn là format literal tuyệt đối, không ký qua: sửa quy tắc
chung validator/decoder trong candidate mới, regression bằng câu mới rồi chạy lại.
Không sửa predictions sau run để đổi kết quả.

Ca 014: `in May` trong condition được diễn giải là lọc population **trial conducted
in May**, không khẳng định improvement diễn ra trong May. Không tự chuyển restriction
này sang thời gian của improvement. Đây là điểm cần kiểm attachment khi review;
schema chưa có trường riêng cho thời gian của population. Không đủ căn cứ coi
`time=""` tự thân là bằng chứng sai nghĩa, cũng không coi schema pass là chứng minh
mọi cách gắn temporal restriction đều đúng.

## Thứ tự làm tiếp

1. Giữ ZIP, predictions và candidate hiện tại. Mở form
   [HUMAN_REVIEW_CELLFIX4_20261017T111605Z-9505cc47.html](HUMAN_REVIEW_CELLFIX4_20261017T111605Z-9505cc47.html).
   Đọc đủ 18 claim/20 parts, đặc biệt 010/014/018, đánh dấu riêng năm tiêu chí,
   nhập tên và kiểm/chỉnh ghi chú. Chỉ khi thực sự đạt mới xuất `semantic-review.json`.
   Form bắt đầu với 90 ô trống, không có nút ký tất cả; chạy offline.
2. Gửi JSON đã review. Kiểm lại admission gắn đúng predictions SHA
   `ae6fcb5d6b7a129afa00896a6a8a684a1dc9cd64570d53f134a796dca65f137f`
   và criteria SHA
   `2e49e7c2b09d6b4379d43c09e267e228c7ae1ed4f74236aae444dc0f918e07fb`.
   Gate `require_probe_review()` của source đóng băng đã được chạy thử: hiện chặn
   full39 trước model loader với `Completed human review bound to this probe is required`.
3. Khi admission qua, chạy full39 với **đúng cellfix4**, giữ model/revision/data/
   budget/gate. Không dùng notebook full39 v7 cho candidate này. Điều kiện tiếp tục:
   39/39 đúng nhãn, false_support=0, runtime_failed_rows=0, đủ bằng chứng/numeric
   checks và audit/review. ZIP hiện không chứa kết quả full39 này; baseline 37/39
   là lịch sử, không được tính cho candidate.
4. Sau full39 ổn định, đánh giá trên dữ liệu chưa dùng sửa lỗi. Sau đó tích hợp
   Reader OCR local có tự đánh giá accept/retry/fallback và Summarizer; chạy E2E,
   đối chiếu trước/sau trên 39 ca và một tập riêng. Không suy ra khả năng tổng quát
   hoặc readiness của toàn pipeline từ smoke12/probe18.

Không thay source/prompt/criteria trong lượt audit này. Review AI và test form
không phải human review. File `semantic-review.json` gốc trong ZIP vẫn nguyên trạng.

Audit máy đọc:
[atomic-verifier-cellfix4-smoke-probe-audit-20261017T111605Z-9505cc47.json](atomic-verifier-cellfix4-smoke-probe-audit-20261017T111605Z-9505cc47.json).
