# Chạy kiểm tra Reader API thực tế trên CPU

ZIP 082718Z xác nhận router gặp 503 trong cả probe và retry. Probe JSON nhỏ
trả 200 không đủ chứng minh yêu cầu router/critique hoạt động. Notebook này
kiểm bốn requests theo hai vai trò, cùng payload qua SDK và REST, có message
đã lọc; không cần chạy lại model extraction để lấy thông tin đó.

1. Giữ ZIP Reader hiện có; dừng phiên GPU cũ nếu không còn công việc đang chạy.
2. Import `scripts/kaggle_reader_endpoint_comparison.ipynb` vào một notebook
   Kaggle **mới, Private**, đặt Accelerator **None**, Internet **On**.
3. Bật quyền Secret **GEMINI_API_KEY** hiện có cho notebook mới. Không cần
   attach dataset, upload repo, tải trọng số hoặc đổi key/model.
4. Chạy cell 1. Nó tạo môi trường Python riêng với các SDK đã pin, kiểm source
   và Secret; chưa gọi Gemini. Chỉ chạy cell 2 khi cuối cell 1 có `SETUP_OK`.
5. Chạy cell 2 **một lần**. Tối đa bốn request: router SDK, router REST,
   critique SDK, critique REST; mỗi request chỉ một attempt, cách nhau ít nhất
   61 giây. Thời gian thuận lợi khoảng 3–4 phút; process giới hạn 600 giây.
6. Lưu Version với Output, tải ZIP **reader-endpoint-…zip** được in ở dòng
   `ZIP:` sau cell 2, kể cả khi state failed. Gửi ZIP đó để kiểm tra.

Nếu cell 1 lỗi cài package/Secret, giữ ZIP setup và xử lý lỗi đó trước.
Không chạy cell 2 lại hoặc mở nhiều notebook để gọi thử song song.

## Phiên hiện tại có SETUP_OK nhưng thiếu wrapt

Output run `reader-endpoint-20261012T094200Z-8bf24d19` đạt `SETUP_OK` nhưng
Python báo `Error in sitecustomize` / `No module named 'wrapt'`. Setup cũ kiểm
exit code và import SDK, chưa kiểm lỗi khởi động này. Chưa có bằng chứng API
Gemini ở lượt này.

Không cần chạy lại cell 1. Trong cùng phiên, chèn một cell trước cell 2 và
dán toàn bộ [cell sửa wrapt](../scripts/kaggle_reader_wrapt_fix.cell.py).
Cell cài `wrapt==2.1.2` vào venv hiện có, kiểm import SDK và stderr khi khởi
động, lưu setup trước sửa cùng log/freeze sau sửa và đóng ZIP. Nó chưa gọi
Gemini. Chỉ chạy cell 2 gốc một lần sau `ENV_OK`. Khi repair lỗi, trạng thái
setup chuyển failed để cell 2 bị chặn.

Bản notebook CPU cũng đã thêm wrapt và chặn `SETUP_OK` nếu SDK smoke test
còn lỗi sitecustomize. Pin wrapt dùng cùng version với runner chính của repo.
Không thay đổi key/model hoặc cấu hình API. Bốn focused tests local đạt, kiểm
cả trường hợp process exit 0 nhưng stderr báo lỗi sitecustomize; chưa chạy
repair trên Kaggle. Python tự import hook này khi khởi động theo
[tài liệu sitecustomize](https://docs.python.org/3.13/library/site.html#sitecustomize).

## Bản sửa setup sau lỗi ensurepip — 2026-10-12

Trace người dùng gửi từ Python 3.13 cho thấy `venv` thất bại khi gọi
`ensurepip`; chưa đến phép thử Gemini. Chưa có stderr để kết luận nguyên
nhân bên trong ensurepip. Bản notebook đã sửa dùng `venv --without-pip`,
tìm pip hiện có hỗ trợ `--python`, rồi cài SDK vào môi trường mới theo
[cách quản lý interpreter của pip](https://pip.pypa.io/en/stable/topics/python-option/).
Không cài package vào kernel đang chạy.

Import lại bản notebook đã sửa; cell 1 tạo thư mục run mới, giữ nguyên ZIP
setup lỗi cũ. Chỉ chạy cell 2 sau `SETUP_OK`. Setup kiểm import và phiên bản
SDK trước khi đọc Secret; `setup-status.json` ghi stage, loại lỗi và exit code
nếu subprocess lỗi, ZIP vẫn được lưu. Không cần đổi API key.

Ba focused tests local đạt: setup thành công/thất bại và fallback pip trên
PATH (giả lập), tạo venv thật không có pip rồi quản lý bằng pip bên ngoài
(offline), kiểm nguồn notebook và chặn cell 2 khi setup lỗi hoặc chạy trùng.
Môi trường kiểm tra là Windows/Python 3.10; chưa chạy bản sửa trên Kaggle
Python 3.13, chưa xác nhận cài package qua mạng hoặc khắc phục Gemini 503.

## Đọc kết quả

`probe/summary.json` có `backend_contract_pass` theo sdk/rest, và từng request
có role, HTTP status (SDK thành công có thể null), contract_pass, elapsed_ms,
request_sha256, error_message_redacted khi có, token usage nếu backend trả.

| Kết quả | Cách sử dụng bằng chứng |
| --- | --- |
| SDK và REST đều đạt hai vai trò | API contract hoạt động tại thời điểm thử; vẫn cần đánh giá lại Reader thật trong run phù hợp và kiểm quota. |
| REST đạt, SDK trượt | Có ứng viên đường gọi REST để kiểm thêm; chưa kết luận lỗi do SDK hoặc tự đổi backend. |
| SDK đạt, REST trượt | Kiểm message/status của REST; không đổi backend theo suy đoán. |
| Cả hai trượt | Dùng message và payload hash xác định hạn chế dịch vụ/request; dừng các lượt Reader hiện tại. |
| 400/401/403/404/429 | Probe dừng sớm; xử lý thông báo cụ thể trước khi phát sinh request tiếp. |

`quality_gate_pass=null` và `backend_promotion=false` là chủ ý: notebook chỉ
kiểm request/response. Frozen critique input là dữ liệu development đã trích
trước đây; notebook không thay thế review extraction hoặc nghiệm thu multi-agent.
