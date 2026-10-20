# Chạy candidate cellfix5 trên Colab T4

Candidate: `atomic-verifier-constrained-v8-cellfix5`.
Notebook: `scripts/colab_atomic_verifier_cellfix5_fresh.ipynb`.
Source độc lập: `research-runs/atomic-cellfix5-frozen/workspace`.

## Thay đổi và phạm vi

Cellfix4 cho phép metric như `improved recall`, `improved throughput`,
`gained yield` dù prompt yêu cầu tên đại lượng không kèm change verb.
User đã đánh dấu tiêu chí entity/metric không đạt ở 010/014/018. Nhận xét
này không có nghĩa ba câu mất chủ thể hoặc mất ý nghĩa; chúng vi phạm
quy tắc biểu diễn metric bắt buộc.

Cellfix5 sửa `source_metric_requirement()` trong candidate. Validator và
`decomposition_schema()` của decoder cùng dùng kết quả của helper này.
Với dạng active change verb + cụm đại lượng có measurement head được hỗ trợ,
metric phải đúng cụm đại lượng trong source, bỏ change verb và `the/its/their`
ở đầu, giữ mọi modifier và chữ hoa/thường. Ví dụ `reduced median batch latency`
yêu cầu metric `median batch latency`; `latency` đơn lẻ cũng bị chặn.

Output sai đi vào repair có giới hạn với `metric_property_not_canonical`
và `required_source`. Không sửa predictions sau khi model sinh. Hướng thay đổi,
số liệu và restriction giữ nguyên trong quote. Dạng count/duration vẫn giữ
predicate có quan hệ, ví dụ `took seven minutes`, không chỉ `seven minutes`.

Đây là grammar hữu hạn, không phải bộ phân tích ngữ nghĩa tổng quát. Named
property chưa biết, property đứng trước động từ, phrase bắt đầu bằng số,
attribution, relative clause, modal, negation hoặc passive không được quy tắc
mới tự suy diễn. Các kiểm tra hiện có và semantic review vẫn cần thiết.
`in May` trong population của 014 không bị chuyển thành thời gian cải thiện.

Regression có trace thật và câu mới về modifier, quantity, lượng từ, population,
scope từng vế và bounded repair. Đây là dữ liệu phát triển, không phải đánh giá
model trên bộ độc lập chưa dùng để sửa.

Source/prompt/contract/criteria/test/fixture/data được đóng băng cùng payload.
Original v8, cellfix4, ZIP và predictions cũ được giữ nguyên. Candidate chưa được
đưa vào serving; không thay source đang phục vụ pipeline chính.

## Cách chạy

1. Upload notebook cellfix5 vào Colab; dùng runtime mới và chọn GPU T4.
2. Chạy năm code cell từ đầu hoặc Run all. Không cần ZIP hoặc biến session cũ.
3. Ba cell đầu kiểm hash, dựng môi trường cô lập, chạy regression,
   CUDA preflight, ba validate-only và tải đúng model revision.
4. Cell 4 chạy smoke12, tải ZIP kể cả khi trượt. Smoke chỉ đạt khi đủ 12/12
   nhãn đúng, `false_support=0`, `runtime_failed_rows=0` và toàn bộ gate đạt.
5. Cell 5 chỉ chạy probe18 khi smoke đạt. Nếu smoke trượt, cell này bỏ qua.
   Giữ ZIP tải sau cùng, kể cả trình duyệt thêm `(1)` vào tên, rồi gửi để audit.

Notebook không có bước chạy inference full39. `verifier --validate-only`
chỉ kiểm cấu hình/hash của 39 ca, không đo nhãn hoặc false support.

Giữ nguyên Qwen/Qwen2.5-3B-Instruct revision
`aa8e72537993ba99e69dfaafa59ed015b17504d1`, NF4/float16, seed42,
8 call/ca, 2 attempt/stage, 1536 token/call, deadline 180 giây.
Prompt, dữ liệu, gold, budget và gate giữ nguyên.

## Đọc kết quả đúng phạm vi

Proof local: `docs/atomic-verifier-cellfix5-validation.json` và
`docs/atomic-verifier-cellfix5-offline-check.json`. Regression, stored-trace replay
và kiểm token filter với tokenizer Qwen không thay thế lần chạy model T4 mới.
Các phương án metric canonical trong regression là fixture viết tay, không phải
predictions đã được model mới sinh.

Kết quả cũ cellfix4: smoke 12/12, probe 18/18 hợp lệ về cấu trúc nhưng review
trượt tiêu chí entity/metric ở ba ca. Không chuyển những kết quả/chữ ký này
thành kết quả của cellfix5. Chưa xác nhận smoke/probe model mới đạt cho đến khi
có ZIP mới; human review mới cần gắn đúng run và hash của candidate mới.
Probe hợp lệ không đo độ chính xác nhãn hoặc false support. Zero false support
trên full39 của cellfix5 chưa được đo; full39 chưa chạy trong lượt này.
