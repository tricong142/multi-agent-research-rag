# Tiếp tục Reader — 2026-10-11

## Kết luận hiện tại

Đã hoàn thiện và kiểm tra notebook local. **Chưa có kết quả Gemini/Reader mới.**
Lượt `20261010T105802Z` vẫn là bằng chứng Reader gần nhất: router gặp HTTP 503
qua ba attempts, `reader-failed-page` thất bại, chưa được chạy full PDF.
Không dùng kết quả kiểm thử giả lập để thay cho kết quả model thật.

Notebook hiện hành: [`scripts/kaggle_reader_diagnostics.ipynb`](../scripts/kaggle_reader_diagnostics.ipynb).
Tiêu đề trong notebook phải là **Reader availability + text export — 2026-10-11**.
Notebook vẫn có **4 code cell**. Dataset/runtime payload không thay đổi; không
cần upload lại weights hoặc nhập API key vào code.

## Đã sửa và kiểm tra

- Cell 1 lấy Secret `GEMINI_API_KEY`, kiểm tra model đang cấu hình rồi gọi một
  yêu cầu sinh JSON nhỏ. Tối đa một GET metadata và một POST generateContent;
  không tự retry. Giới hạn đọc phản hồi 64 KiB, timeout kết nối/socket 30 giây.
  Đây không phải cam kết tổng thời gian toàn cell là 30 giây.
- Luôn lưu kết quả probe dưới `/kaggle/working/gemini-availability-<id>.json`
  trước khi kiểm tra điều kiện tiếp tục. Lưu mã HTTP, trạng thái được cho phép,
  thời gian, kết quả kiểm tra JSON và token usage nếu có. Không lưu key, raw
  response, raw exception message hoặc thông tin tài khoản.
- Probe thất bại sẽ dừng cell 1 trước khi mount dữ liệu. Khi chạy lại thủ công,
  mỗi probe tạo file mới; không ghi đè bằng chứng cũ.
- Cell 3 xác nhận model chưa đổi, đưa JSON probe vào ZIP của run mới và giữ
  khoảng cách tối thiểu 61 giây từ probe đến lần gọi Reader tiếp theo.
- Cell 4 kiểm tra đủ trạng thái `completed`, exit code `0` và gate boolean
  `true` của kết quả trang thử, trước khi gọi Reader toàn PDF.
- 10/10 notebook tests đạt. Có ca 429, 503, lỗi quyền, timeout, sai model,
  phản hồi HTML/JSON không dùng được và kiểm tra không lộ secret. Các test
  API đều giả lập; không có inference thật trong lượt kiểm tra local này.
- Test tạo ZIP bị sandbox Windows chặn `Path.replace`; chạy lại cùng bộ test
  ngoài sandbox đạt. Giữ nguyên test và cơ chế ghi ZIP, không bỏ kiểm tra.

Bằng chứng: [reader-resume-validation-20261011.json](reader-resume-validation-20261011.json).

## Chạy trên Kaggle

1. Giữ ZIP cũ. Import notebook hiện hành vào một notebook riêng tư mới để
   không nhầm với bản ngày 10/10. Dùng GPU/Internet và hai dataset workspace,
   diagnostics v2 như lượt trước; bật quyền sử dụng Secret `GEMINI_API_KEY`
   cho notebook. Không dán key vào cell.
2. Chạy **cell 1**. Chỉ sang cell 2 khi `endpoint_available` là `true` và cell
   kết thúc thành công. Nếu lỗi, giữ file `gemini-availability-*.json`; không
   chạy các cell còn lại. Không lặp tự động để cố vượt quota.
3. Chạy **cell 2** để tạo run/workspace mới, cài môi trường, chạy contract tests
   và preflight. Không dùng thư mục `rag-validation-20261010T105802Z` cũ.
4. Chạy **cell 3**, chỉ thử `page_no=3` (trang thứ tư). Helper xuất text/blocks,
   log đã lọc, ZIP và replay offline. Một cell hoàn tất không có nghĩa Reader
   đạt: helper có thể giữ failure để xuất bằng chứng.
5. Chỉ chạy **cell 4** khi đồng thời đạt:

   ```text
   statuses['reader-failed-page']['state'] == 'completed'
   statuses['reader-failed-page']['exit_code'] == 0
   reader-failed-page/summary.json: automated_gate_pass == true
   ```

   Guard đã có trong cell; không sửa/bỏ guard để tiếp tục. Full PDF và replay
   được chạy trong cell 4. Probe API thành công không bảo đảm toàn bộ Reader
   sẽ thành công ở các lần gọi tiếp theo.
6. Lưu Version kèm Output, tải ZIP mới và dừng session GPU. Đối chiếu
   `page_blocks.jsonl`/`extractions.jsonl` với PDF để review chất lượng.
   `human_review=pending` chưa phải nghiệm thu đạt.

## Phân biệt lỗi

| Dấu hiệu | Kết luận có thể đưa ra | Việc tiếp theo |
|---|---|---|
| Worker không khởi động / công cụ browser timeout | Chưa có request Gemini được xác nhận | Khôi phục phiên Kaggle/Browser trước |
| HTTP 429 | Request bị giới hạn tài nguyên/rate/quota | Kiểm tra quota đúng project/model; lưu JSON |
| HTTP 503 | Request gặp lỗi dịch vụ tạm thời | Kiểm tra status và thử lại có kiểm soát khi dịch vụ phục hồi |
| HTTP 403/404 | Quyền truy cập hoặc model/endpoint không hợp lệ cho request | Kiểm tra Secret/quyền/model; không tăng retry |
| HTTP 200 nhưng JSON không đạt | Request đã nhận response, probe chưa đạt contract | Xem `error_type`, `finish_reason`; chưa chạy Reader |

Tài liệu chính thức được kiểm tra ngày 11/10/2026 xác nhận ID
[`gemini-3.6-flash`](https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flash).
Điều này không chứng minh khả dụng cho tài khoản tại thời điểm chạy.
[Hướng dẫn lỗi/retry của Google](https://ai.google.dev/gemini-api/docs/troubleshooting)
và [trang status](https://aistudio.google.com/status) là nguồn tham khảo;
JSON request thực tế mới là bằng chứng cho lượt probe của tài khoản.

## Điểm đang bị chặn và công việc tiếp theo

Đã mở tab Reader cũ trong Codex. Điều khiển click qua browser bị timeout cả
hai cách; chưa import notebook mới lên Kaggle và chưa chạy cell 1–4 trong
lượt này. Vì vậy chưa kết luận dịch vụ đã phục hồi, chưa có ZIP Reader mới.

Sau Reader: đối chiếu ZIP/review PDF, xử lý confidence bằng thí nghiệm verifier
nhãn có evidence (chưa triển khai; giữ phục vụ `repair`), xử lý Summarizer rồi
mới chạy full E2E và review nghiệm thu. Toàn dự án hiện chưa đạt gate phát hành.
