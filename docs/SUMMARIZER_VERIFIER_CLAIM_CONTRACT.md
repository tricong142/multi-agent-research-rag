# Hợp đồng claim Agent 3 → Agent 4

Audit E2E `docs/E2E_AUDIT_20261007.md` ghi nhận ca sufficient gửi chuỗi `42`
sang FactChecker và nhận NEI. Runtime sau audit đã chặn số trơ, nhưng regex cũ
không chặn `42 participants`, `92% accuracy`, `Improved accuracy to 92%.` hoặc
một câu đầy đủ đi kèm fragment ở câu tiếp theo. Graph chưa có cùng guard này.

## Contract và triển khai

Mỗi claim gửi để kiểm chứng phải có chủ thể rõ và chỉ số/hành động/quan hệ.
Claim định lượng giữ giá trị, đơn vị, comparator, thời gian và điều kiện do nguồn
hỗ trợ. Không bắt claim định tính thêm số. Ví dụ `Model A reduced latency.` là
câu có thể kiểm chứng; `92% accuracy` cần rewrite để chỉ ra chủ thể và quan hệ.

`train_agent3_summarizer/claim_contract.py` cung cấp chung `split_claims` và
`claim_contract_issues`. Nó kiểm từng câu/bullet, số kèm đơn vị, noun fragments,
predicate không có chủ ngữ và một số pronoun không có referent. Decimal không
bị tách giữa các chữ số; bảo vệ một số abbreviation thông dụng. Guard dùng
standard library, không nạp model và không thay đổi text evidence.

`SummarizerNode.run` yêu cầu câu đầy đủ ngay từ instruction đầu. Nếu fragment
vẫn được Critic chấp thuận, local guard vẫn buộc `rewrite`; Generator nhận
feedback cấu trúc trước lượt sau. Giữ nguyên tối đa 3 lượt nội bộ. Nếu Critic
yêu cầu `request_more_context`, node yield ngay để Retrieval tìm nguồn; không
ép rewrite trên nguồn thiếu thông tin hoặc tự nối entity lấy từ câu hỏi vào số.
Hết retry thì `is_supported=False`, `confidence=low` và không có claim được duyệt.

Critic có thêm tiêu chí kiểm cả cấu trúc và binding của mỗi claim với evidence.
JSON wire schema vẫn là `answer/evidence_spans`; không đổi checkpoint weights
hoặc bắt model sinh một schema entity/relation/quantity mới.

Graph kiểm lại output kể cả khi Summarizer là service/injected implementation
báo high confidence. `summary_diagnostics.claim_contract_issues` lưu index/code
của các câu chưa đủ cấu trúc. Trước lời gọi FactChecker, mọi proposed/prior/audit
claim đều được kiểm; fragment trong evidence có thể tồn tại như span trích dẫn,
nhưng không được dùng làm standalone claim để gửi Verifier. Việc audit những
câu nguồn hoàn chỉnh vẫn giữ nguyên cơ chế không publish unaccepted summaries.
Source IDs, matching span và kiểm mâu thuẫn qua toàn bộ nguồn vẫn được giữ.

## Giới hạn và vận hành

Đây là **grammar guard hữu hạn**, không phải parser đầy đủ hoặc chứng minh
ngữ nghĩa. Câu đúng ngoài các mẫu English/Vietnamese hiện nhận diện có thể bị
yêu cầu rewrite; một câu đúng grammar vẫn có thể gắn sai entity/metric/value.
Critic và Verifier phải kiểm phần binding đó, cùng evidence verbatim của graph.
Chưa thể bảo đảm mọi câu tự nhiên đều được phân tích chính xác bằng heuristic.

Policy graph tăng `runtime_schema` lên 4 và khóa `claim_contract` để không
resume lẫn checkpoint trước/sau thay đổi. Dùng thread mới cho lượt thử mới;
không sửa hoặc reset checkpoint cũ để bỏ kiểm tra này.

Builder E2E `scripts/build_validation_notebook.py` đã liệt kê helper mới và
adapter atomic trong runtime patch. Các notebook đã sinh trước đây và release
Cellfix16 được giữ nguyên; không tự coi notebook cũ đã chứa code serving mới.
Thay đổi này tác động lớp Summarizer/graph E2E, không chỉnh rules/decoder/gold
của verifier frozen hay packet holdout30-v2.

## Kiểm chứng

Test mới `research_rag/tests/test_claim_contract.py` dùng ví dụ synthetic:
fragment → rewrite → Verifier nhận câu hoàn chỉnh; giữ citation; missing context
yield; retry exhaustion; câu định tính, passive, Vietnamese; các fragment từ
service/audit không chạm Verifier. Không dùng holdout để viết hoặc chọn guard.

Các báo cáo/log kiểm tra hiện hành:

- `docs/summarizer-verifier-claim-contract-validation.json`.
- `research-runs/claim-contract-light-tests.log`.
- `research-runs/claim-contract-regression.log`.

Tests dùng backend giả lập. Chưa chạy lại sufficient hoặc E2E bằng các model
thật trên GPU; không dùng kết quả unit test thay cho gate E2E.
