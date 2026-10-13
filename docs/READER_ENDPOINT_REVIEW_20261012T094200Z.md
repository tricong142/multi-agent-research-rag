# Reader endpoint — đối chiếu ZIP 20261012T094200Z

**Chưa đạt Reader gate.** Bốn request đã chạy; router qua SDK/REST đều bị 503.
Google trả thông báo model đang có nhu cầu cao. Critique qua SDK trả cấu trúc hợp
lệ. Chưa có căn cứ đổi sang REST, thay key, hạ quality gate hoặc kết luận Reader
đã đọc được toàn PDF.

## Bằng chứng đã kiểm

ZIP `reader-endpoint-20261012T094200Z-8bf24d19.zip`, 48.409 bytes, SHA256
`339e5bcd1d1abd04091c6f011f0ecb7cb34fce8311b1bfc8f06b83aa42f4a27e`.
CRC hợp lệ; không trùng/thừa entry; 23/23 file đúng hash/kích thước; 5/5 file
manifest code đúng hash. Ba file source chính khớp repo hiện hành. Summary khớp
requests.jsonl; request body của mỗi role đúng hash và giống nhau qua SDK/REST.
Khoảng cách bắt đầu request lần lượt 61.000160, 61.000143, 61.000155 giây.
Hash xác nhận tính nhất quán của ZIP nhận được, không phải chữ ký nhà cung cấp.

| Role / đường gọi | Kết quả | Diễn giải |
| --- | --- | --- |
| Router / SDK | 503 UNAVAILABLE | Provider báo model có nhu cầu cao. |
| Router / REST | 503 UNAVAILABLE | Cùng payload; chuyển sang REST chưa giải quyết được. |
| Critique / SDK | contract_pass=true | JSON/schema hợp lệ, accept; HTTP status không được SDK ghi, không suy diễn thành mã HTTP đã đo. |
| Critique / REST | 503 UNAVAILABLE | Provider báo model có nhu cầu cao. |

Mỗi case một attempt, đúng giới hạn bốn request, không có retry ẩn được ghi
nhận bởi guard. Stage failed/exit 1, 184.847 giây. Hai backend đều chưa đạt cả
hai vai trò; quality_gate_pass=null, backend_promotion=false. Critique SDK ghi
1.030 total tokens; không có usage cho ba request lỗi và không có chi phí USD.
Không dùng 1.030 làm tổng token/billing của cả run.

Thông báo provider: “This model is currently experiencing high demand.” Điều
này phù hợp nhóm lỗi tạm thời 503 trong [tài liệu Gemini](https://ai.google.dev/gemini-api/docs/troubleshooting).
Đây là thông báo cho các request trong run; không xác định thời điểm dịch vụ
phục hồi hoặc nguyên nhân nội bộ chi tiết. Không có 403/429 trong run này.

ZIP không chứa setup-before-wrapt.json hoặc log repair wrapt. Freeze chưa có
wrapt và probe.stderr.log vẫn ghi cảnh báo thiếu wrapt. Tuy vậy cả bốn request
đã được thực hiện và có một kết quả hợp lệ. Lượt này không chứng minh bản sửa
wrapt đã chạy; cũng không chứng minh cảnh báo đó gây các HTTP 503 từ provider.

## Bước tiếp theo

1. Giữ ZIP này; dừng session CPU sau khi đã lưu Output. Không chạy lặp lại
   phép so SDK/REST cùng cấu hình để tiếp tục thu cùng loại bằng chứng.
2. Chuyển sang [ứng viên verifier riêng](BLIND_VERIFIER_VALIDATION.md), dùng
   GPU Qwen đã có đường chạy; không gọi Gemini. Baseline repair lấy từ run
   confidence đã audit, không chạy lại bốn profile cũ.
3. Reader vẫn pending. Khi có lý do kiểm tra lại dịch vụ, dùng notebook endpoint
   bản hiện hành trong run mới; chỉ sau contract router/critique đạt và xác nhận
   quota đủ mới quay lại Reader trang 4/full PDF. Không có lịch retry tự động.
4. Sau khi Reader và verifier có bằng chứng đạt: xử lý Summarizer heldout_3,
   regression tám ca E2E, review câu trả lời/trích dẫn và đánh giá độc lập.

Không đổi model Reader hoặc backend serving trong lượt này. Checkpoint/resume
Reader theo trang vẫn là việc còn thiếu nếu cần trải lượt đọc qua nhiều kỳ quota.

Audit có máy đọc được: [reader-endpoint-audit-20261012T094200Z.json](reader-endpoint-audit-20261012T094200Z.json).
Bằng chứng được giữ ở `research-runs/reader-endpoint-20261012T094200Z-8bf24d19`.
