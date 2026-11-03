# Cellfix12 full39 — automated gate đạt, bắt đầu human review; chưa mở Validation30

Run: `20261027T025350Z-c67b6d37`.
ZIP: `output-cellfix12-fresh-20261027T025350Z-c67b6d37 (3).zip`.
ZIP SHA256: `c40478f7d1bc42c4cac932fb05eee5f5c1ae1a0e1818ca15836801ea183df009`.
Criteria SHA256: `e147868fc5826a1f10e5a5132e1ea0fb0517e16b66b229c2ad163e71f64146f7`.
Full39 predictions SHA256: `6a577853874ba11b282a954c366f17ba0b45aa44267ea3fce5f75d79dae6ae5e`.

## Kết luận

**Được chuyển sang human review full39 để đánh giá và ghi nhận kết quả.**
Chưa đủ căn cứ ký review sạch hoặc bật `RUN_VALIDATION30=True`: AI audit
đánh dấu sáu ca ở tiêu chí `explanation_follows_evidence` vì observation dùng
fragment, quantity hoặc workload làm member thay đối tượng cần kiểm.
Nhãn đúng không tự làm ledger/explanation đúng. Không chuyển ca chưa đạt thành
đạt để qua admission; hãy xuất review trung thực kể cả có tiêu chí false.

## Đã xác minh

| Phép kiểm | Kết quả |
|---|---|
| Manifest ZIP | 113 output files khớp size/hash, không có extra/duplicate paths |
| Payload/source | 127 input khớp frozen release; source/prompt/contract/criteria đúng hash |
| Lineage | Giữ nguyên ZIP smoke/probe `(2)` và bytes các artifact cũ; reviewed-probe là đúng copy |
| Regression Colab | 363/363 đạt |
| Validate-only | smoke, probe, full39, validation30 đều đạt cấu hình; không phải inference validation30 |
| Smoke | 12/12 nhãn đúng; false support=0, runtime=0 |
| Probe | 18/18 decomposition hợp lệ; human admission Trí Công đúng predictions hash và 90 judgments |
| Full39 | **39/39 nhãn đúng, false support=0, runtime=0** |
| Groups | original_contracts 12/12, scope_regression 27/27 |
| Calls/tokens | 85 calls; 9.361 generated, 113.156 prompt, trong budget |
| Stop/gate | 39 completed; automated_gate_pass=true; human_review=pending; overall_pass=false |
| Validation30 | Chưa inference; admission hiện chặn vì chưa có human review full39 |

Đã replay 69 prediction rows/131 call triplets smoke/probe/full39: raw JSON,
parsed output, normalization, assessment, citations/numeric records, aggregate
label và metrics đều khớp. Model/revision/quantization/seed/budget/gate giữ nguyên.
Lượt audit không gọi model mới hoặc thay predictions/source/gold.

Hai lỗi North gateway của Cellfix11 đã đúng trên output mới: support dùng đúng
North decreased; contradict dùng đúng North increased. Condition NEI đã giữ
unknown, quote đúng low-temperature, không còn absence=false. Causal missing
và Precision was not measured cũng đúng. Điểm này không xóa các lỗi identity
còn lại bên dưới.

## Sáu ca AI đánh dấu chưa đạt ở explanation/observation

| Case | Member trong output mới | Vấn đề |
|---|---|---|
| `contract:irrelevant` | `No model accuracy is reported` | Một mệnh đề thiếu báo cáo được gọi là member; không phải Model Juniper. Missing target đúng, nhưng observation explanation sai loại đối tượng. |
| `scope:none:not_enough_info` | `Silver's leak status was not` | Fragment cắt trước reported; đối tượng cần kiểm là pump Silver. Quote chứa đúng absence, nhưng member/explanation không đúng. |
| `scope:conjunction:support` | `5.4 to 4.6 gigabytes`; `4.6 gigabytes` | Quantities không phải extractor; memory quantity còn làm member của token recall. Gold NEI là annotation strict identity hiện hành, dù ID lịch sử chứa support. |
| `scope:conjunction:contradict` | `For the same workload, tuning reduced memory use`; `4.6 gigabytes` | Clause và quantity thay entity extractor. Gold/prediction NEI đúng nhưng prose về pseudo-member chưa đạt. |
| `scope:conjunction:not_enough_info` | `the extraction workload`; `4.6 gigabytes` | Chưa bind workload với extractor; quantity memory không phải member cho token recall. Missing identity đúng nhưng observation explanation chưa đạt. |
| `scope:condition:not_enough_info` | `no yield changes were` | Fragment cắt trước measured, không phải batch/group. Truth unknown và quote low-temperature đúng, nhưng lời giải thích gọi fragment là member. |

Đây là đánh giá AI, không phải chữ ký human. Toàn bộ 39 ca và 195 judgments
được ghi riêng trong `AI_EVIDENCE_AUDIT.json`/`EVIDENCE_REVIEW_39.md`.
Các ca khác cũng phải được người review trực tiếp đọc, không tích theo mặc định.

## Cơ chế từ code/trace

`source_members()` trong decoder tạo mọi span liên tiếp tối đa tám từ từ
context, chưa phân biệt entity với clause/quantity. Trong các ca atomic target
vắng mặt nêu trên, decoder chỉ giữ truth=unknown nhưng vẫn cho arbitrary source
spans; minItems của observations vẫn yêu cầu một record.

Guard `observation_member_is_not_entity` hiện dựa vào `_MISSING.search(member)`
và auxiliary verb. Hai fragment cắt trước reported/measured không còn chứa
pattern absence hoàn chỉnh, nên không bị guard loại. Các đoạn source đúng
substring vẫn không tự trở thành member có nghĩa. Renderer ghép tên member đã
được chấp nhận vào explanation nên mang lỗi identity sang prose.

Không sửa runtime rule theo sáu case ID hoặc thay member thủ công trong
predictions. Nếu review xác nhận trượt, candidate tiếp cần quy tắc member
semantics/target binding chung, dùng chung validator/decoder; phải có đường
unknown trung thực khi target vắng mặt, tránh bắt buộc bịa source-span member.
Thêm regression từ fragment thật và câu mới, giữ model/budget/gate và không
tune bằng Validation30. Đây mới là hướng sửa, chưa triển khai candidate mới.

## Thực hiện human review

1. Mở `HUMAN_REVIEW_WITH_AI_NOTES.html` trong thư mục này. Đây là bản form
   đúng run, có ghi chú AI cho từng ca; **195 checkbox vẫn chưa được tích**.
   `HUMAN_REVIEW.html` bên cạnh là bản nguyên văn từ ZIP.
2. Đọc đủ 39 claim/context/decomposition/ledger. Xác nhận từng tiêu chí và ghi
   chú; với sáu ca trên, đối chiếu trực tiếp member và explanation. Chỉ tích
   tiêu chí thật sự đạt; xuất semantic-review.json kể cả có tiêu chí trượt.
3. Giữ `RUN_VALIDATION30=False`. Nếu còn judgment false, không chạy cell7
   để cố vượt gate; giữ review thất bại làm bằng chứng cho candidate tiếp.
4. Chỉ sau khi cả automated gate và human evidence review sạch của **cùng
   candidate/predictions hash** đạt mới bật cell7/upload review full39 riêng.
   Review probe hoặc review của Cellfix10/11 không thay thế review full39 này.

Zero false support đã được đo trên 39 ca development hiện hành. Nó không
chứng minh ledger sạch hoặc khả năng khái quát trên bộ30 độc lập. Lượt này
chưa chạy Validation30, chưa promote serving, chưa kiểm Reader/Summarizer E2E.
