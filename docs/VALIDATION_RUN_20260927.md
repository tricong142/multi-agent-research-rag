# Vòng kiểm chứng trên Kaggle — 2026-09-27

## Đồng bộ đã xác nhận

- Chủ tài khoản đã xác nhận upload gói `validation-update-20260927.zip`.
- ZIP: 3.914.720 bytes, SHA-256 `d36c94e92fd5ee9a7c41ccd597a9cb2cf4f8bbf93c29720c00ae58c184805477`.
- Dataset `trcng23/research-rag-runtime-diagnostics`: **Version 2, Private**, UI xác nhận tạo thành công; Data Explorer có **50 file** (49 payload + manifest), 26 MB giải nén.
- Notebook `research-rag-gpu-validation` đã nhận cập nhật dataset từ Version 1 lên 2; UI báo `Updated datasets/trcng23/research-rag-runtime-diagnostics`.
- Bật T4 x2 theo quyền dùng quota miễn phí đã có; Kaggle báo **26 giờ còn lại** trước khi bật. Chưa mua tài nguyên hoặc tạo API token.

## Workspace và môi trường đã đạt

- Đủ 49 payload khớp kích thước/SHA-256; các `base_sha256` khớp workspace v2.
- Bản sao mới `/tmp/research-rag-validation-20260927`; không ghi đè bản nguồn.
- Python 3.12.13, torch 2.10.0+cu128, CUDA 12.8; **hai Tesla T4**; RAM khả dụng lúc bắt đầu 29,64 GiB.
- Venv riêng `/tmp/research-rag-serving-20260927`; bootstrap, PyTorch, requirements serving và `pip check` đều exit 0; `No broken requirements found`.
- Preflight: Fact-Checker merged đủ weights, base khớp Qwen 3B; FAISS đọc được 41.549 vector, chiều 1024, cùng số ID, load 889,64 ms. Việc cùng số lượng chưa tự chứng minh chất lượng retrieval.
- Cache base Summarizer/Writer/BGE của phiên cũ không còn. Chưa nạp toàn bộ model graph trong phiên này; Fact-Checker merged không cần tải base riêng.

## Fact-Checker: đã khởi chạy, chưa thu kết quả

Đã khởi chạy `compare_factchecker` trong venv: baseline và coverage trên cùng
30 dev + 12 ca synthetic (84 prediction). Giữ raw reasoning/score và peak CUDA;
harness đo thêm peak RSS bằng lấy mẫu 0,25 giây. Chưa promote prompt hoặc sửa
ngưỡng confidence. Chưa có kết luận A/B tại thời điểm ghi mục này.

Runbook: `VALIDATION_UPDATE_20260927.md`. Kết quả các phiên trước:
`KAGGLE_VALIDATION_STATUS.md`. Không nhầm việc upload thành công với gate
chất lượng model đã đạt.

## Phục hồi sau gián đoạn

- Khi kết nối lại notebook, UI báo `Draft Session off`; output của cell cũ chỉ
  xác nhận PID 187 đã khởi chạy. Chưa có bằng chứng tiến trình hoàn tất hay lỗi.
- Đã thử khởi động lại bằng quota miễn phí để đọc file; trình duyệt liên tục
  timeout và kẹt `Editor Loading`. Chưa chạy được cell kiểm tra file. Không được
  diễn giải việc này thành model chạy thất bại hoặc prediction đã mất.
- Đã **Quick Save Version 7**, chọn **Save output for this version**; lịch sử
  xác nhận `done Quick Version`. Sau đó đã thao tác Stop session và quan sát
  **Session stopped**. Phiên GPU phục hồi đã dừng, không để chạy chờ vô hạn.
- Bước kế tiếp là thu Output Version 7 và kiểm tra log/prediction trước khi
  quyết định chạy lại. Chưa rerun Reader sửa overflow hoặc BGE/QASPER trong
  phiên phục hồi này. Chưa promote prompt hoặc đánh dấu gate chất lượng đạt.

### Output và notebook phục hồi

Đã mở Output Version 7 (`scriptVersionId=353250921`): Data Explorer chỉ có
`.virtual_documents/__notebook_source__.ipynb` (39,97 kB), không có log hay
prediction Fact-Checker. Bản lưu này không cung cấp kết quả A/B; không suy ra
điểm số từ thông báo PID khởi chạy của phiên cũ.

Đã tạo `scripts/kaggle_resume_validation.ipynb` (4 code cells) để chạy theo thứ
tự trên chính hai dataset đã có: kiểm 49 payload/base hashes, tạo venv serving,
Fact-Checker, Reader API cả PDF thật 12 trang, rồi BGE/QASPER dev. Các subprocess
chạy gắn với cell, có timeout và lưu status/log; gói Output có manifest hashes.
Không chấm 417 test candidate, không tự promote prompt, không đưa key vào file.
Chưa upload notebook này hoặc chạy nó bằng model thật.

Kiểm tra local ở `validation-resume-notebook-check.json`: biên dịch 4 cell;
thử subprocess thành công, thất bại, lỗi bắt buộc phải dừng; từ chối chạy đè
stage cũ; kiểm hash 7 payload trong ZIP mẫu. **Không chạy model/API**; nhánh
kill process group khi timeout Linux chưa được thử trên Windows. Đây là kiểm
tra harness, không thay thế gate chất lượng AI.

Tái tạo notebook bằng `python kaggle_transfer/build_resume_notebook.py`.
ZIP `validation-update-20260927.zip` giữ nguyên SHA-256 đã phê duyệt.

### Phiên phục hồi thứ hai — đã dừng qua Active Events

Sau Version 7 đã mở một phiên T4 x2 mới và chạy một cell phục hồi đồng bộ
(setup + Fact-Checker, chưa chạy Reader/BGE). Run ID quan sát trực tiếp từ
Output: `20260927T101018Z`; thư mục `/kaggle/working/rag-resume-20260927T101018Z`.
Venv và bootstrap đã exit 0; log cuối đọc được là `torch starting`. Chưa đọc
được kết quả các stage tiếp theo. Không chạy lại cell khi chưa xác định tiến trình cũ.

Khoảng 17:30 giờ Việt Nam, Active Events còn báo **Interactive Session with
GPU T4 x2 — Running (21m)**. Đây là phiên mới, không phải phiên đã dừng sau
Version 7. Công cụ trình duyệt timeout cả khi mở log và thao tác menu; chưa có
bằng chứng lưu Output phiên thứ hai tại thời điểm đó.

Đã chọn **Active Events → đúng phiên Interactive Session → Stop Session**.
Khoảng **17:33 giờ Việt Nam**, UI xác nhận **0 Active Events** và phiên
**Interactive Session with GPU T4 x2 — Cancelled** (thời gian hiển thị 24m).
Đây là bằng chứng dừng phiên thứ hai; không suy ra từ trạng thái phiên trước.
Chưa khôi phục được log mới hoặc lưu Output phiên này do tab editor tiếp tục
timeout. Version 7 đã lưu trước đó chỉ có notebook, không chứa kết quả A/B.
Không có điểm Fact-Checker/Reader/dense mới để báo cáo. Không bật lại GPU.

Bước tiếp theo khi editor hoạt động: kiểm tra Draft/Output còn lại trước khi
chạy lại. Nếu không có kết quả, dùng notebook phục hồi tuần tự nêu trên; lưu
Quick Save kèm Output ngay sau từng stage, xác nhận thành công rồi mới dừng.
