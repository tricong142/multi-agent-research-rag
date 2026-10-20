# Notebook cellfix3 chạy từ đầu

File chạy: `scripts/colab_atomic_verifier_cellfix3_fresh.ipynb`.
Notebook tự chứa 78 file đầu vào đã đóng băng, gồm 32 source/fixture file của đúng candidate cellfix3. Không đọc biến parent, không tìm workspace cũ và không áp thêm cell vá lúc khởi động.
Criteria SHA-256 giữ nguyên: `c38cf4cad12ce7ddcf257c1b80dff5467dc1d499a22f295d2824b0ca5c5a558f`.

**Cách chạy**

1. Upload file `.ipynb` vào Colab, dùng runtime mới và chọn GPU T4.
2. Chạy lần lượt năm code cell hoặc dùng Run all. Không cần upload ZIP cũ, mount Drive hoặc sao chép cellfix1/2/3.
3. Đợi cài môi trường và tải Qwen từ revision đã chốt; log mỗi bước được giữ trong ZIP. Sau regression và ba validate-only, notebook mới chạy assessment-smoke.
4. Giữ ZIP được tải về. Nếu smoke trượt, probe18 tự bỏ qua. Nếu smoke đạt, probe18 chạy và tải ZIP cập nhật; gửi **ZIP cuối cùng** để audit và review 18 mệnh đề.

Tên ZIP có dạng `output-cellfix3-fresh-<run_id>.zip`. Nếu trình duyệt thêm `(1)` cho lần tải sau probe, chọn bản cuối có thư mục `decomposition-probe`.
ZIP có `frozen-inputs.zip`, input/output manifest, provenance, log, predictions và metrics của các stage thực sự đã chạy.
Lỗi cài đặt, kiểm tra môi trường hoặc inference cũng kích hoạt tải ZIP chẩn đoán trước khi báo lỗi.

**Các bước trong notebook**

| Cell | Công việc | Điều kiện để tiếp tục |
| --- | --- | --- |
| 1 | Giải nén input nhúng sẵn, kiểm CRC/hash/path, tạo run mới | Đủ file và hash đúng |
| 2 | Kiểm nvidia-smi, tạo venv, cài dependency pins, pip check/freeze | Không có lỗi môi trường |
| 3 | Regression, CUDA, validate-only probe/smoke/full39 và model cache | Tất cả kiểm tra đạt |
| 4 | Chạy smoke 12 ca, xuất metrics và tải ZIP | Đúng toàn bộ nhãn, không false support, không incomplete và đạt các trace/budget gate |
| 5 | Chạy probe18 nếu smoke đã đạt trong chính run này | Nếu smoke trượt thì tự bỏ qua |

Model, revision, tokenizer, NF4/float16, seed 42, dataset và budget không đổi so với cellfix3 đã kiểm tra. Dependency/CUDA pins lấy nguyên từ notebook v8 đã dùng trước đó.
Mỗi case tối đa 8 call, 2 attempt/stage, 1536 generated token/call và deadline 180 giây. Smoke tối đa 96 call; probe18 tối đa 36 call. Notebook không tự chạy full39.

**Diễn giải kết quả**

- Cell kết thúc không có traceback chưa chứng minh gate đạt. Xem `automated_gate_pass` trong metrics của stage.
- `baseline-metrics.json` thuộc baseline lịch sử. Số 37/39 trong file này không phải kết quả candidate mới.
- Validate-only với 39 case chỉ kiểm freeze/cấu hình, chưa đo nhãn hoặc false support trên full39.
- Probe18 vẫn cần human review mới gắn đúng criteria/predictions của run này; chữ ký v7 trước đó không được dùng lại.
- Các case regression đã được dùng phát triển. Cần một bộ đánh giá độc lập để kết luận khả năng tổng quát hóa.
- Notebook này chạy verifier thử nghiệm; chưa xác nhận Reader/Summarizer E2E hoặc production readiness.

**Kiểm tra trước bàn giao**

Artifact được kiểm tra trong thư mục sạch: payload khớp 78 file, regression của payload giải nén đạt 153 test, ba validate-only đạt. Có kiểm tra notebook khởi động không cần session cũ, smoke trượt chặn probe, stale success flag không mở gate và lỗi hạ tầng vẫn tải chẩn đoán.
Metadata/hash chi tiết được ghi trong `atomic-verifier-cellfix3-fresh-colab-release.json` và `atomic-verifier-cellfix3-fresh-validation.json` cùng thư mục.

Chưa chạy cài đặt CUDA hoặc inference Qwen/T4 của notebook mới trong môi trường local CPU. Chưa có kết luận smoke 12/12, probe18 human review hoặc zero false support trên full39 cho lần chạy mới này.
