# Kiểm chứng điều phối tự chủ — 2026-10-01

> Snapshot lịch sử. Đã nhận kết quả E2E ngày 2026-10-02 và sửa runtime ngày
> 2026-10-07. Xem [E2E_AUDIT_20261007.md](E2E_AUDIT_20261007.md) để biết kết quả
> và hướng dẫn notebook hiện hành. Kích thước/hash notebook bên dưới thuộc bản cũ.

## Trạng thái có bằng chứng

- Runtime đã có kế hoạch nghiên cứu, năm node agent riêng, RetrievalAgent tự chọn
  truy vấn/BM25/dense trong phạm vi controller cho phép, trace và giới hạn vận hành.
- `python -m unittest discover -s research_rag/tests -q`: **91 test đạt**, 33,404 giây.
  Test dùng backend giả; không phải kết quả chất lượng của model thật.
- Test notebook giải nén bộ đánh giá rồi so từng byte với bộ dữ liệu đã đóng băng;
  xác nhận tám ca, hash manifest và mã nguồn nhúng đúng với repo hiện tại.
- Bộ dữ liệu và tiêu chí đã đóng băng tại `research-runs/autonomy-v1-20260930`.
  Criteria SHA-256: `fe82de19c6c7ddd9a679c83ea2e80ad7748d2c1fa951493846debf9cc9604e01`.
- Ngày 2026-09-30, notebook Kaggle đã mount thành công workspace và diagnostics
  qua `kagglehub`; output hiển thị cả `transfer-manifest.json` và
  `validation-update-manifest.json`.
- Ngày 2026-10-01, chủ dự án xác nhận đã nhập Gemini API key trong Kaggle.
  Chưa xác nhận được quyền truy cập secret bằng code và chưa gọi API của lượt E2E này.
- **Chưa chạy E2E model thật của bản điều phối mới.** Công cụ browser đọc được
  trang nhưng thao tác input liên tục timeout/ngắt kết nối. Lần quan sát thành
  công cuối hiển thị `Draft Session off (run a cell to start)`.

## Bản notebook cần dùng

File: `scripts/kaggle_autonomy_validation.ipynb`.

- Bản cập nhật 2026-10-02, kích thước: 145.636 byte.
- SHA-256: `c4c8b15aacafc2afbb2f25a6b16f7956af88ab3b3fd5e88fe6f835a64e9dad8c`.
- Bốn code cell: mount dữ liệu; setup và kiểm hash; khôi phục bộ đánh giá đã chốt;
  chạy model thật và đóng gói kết quả.
- Payload dùng zlib của Python chuẩn. Hash được kiểm trên nội dung sau giải nén.
  Việc giảm kích thước hỗ trợ tải editor; chưa có bằng chứng nó sửa lỗi kết nối browser.
- Deadline của ca PDF là 900 giây, các ca khác 300 giây; ca ngân sách vẫn giới hạn
  một bước. Điều chỉnh PDF được thực hiện trước inference vì Reader xử lý bốn trang
  đồng bộ với khoảng cách giữa các lần bắt đầu gọi API là 61 giây.
- Trace khi Fact-checker hết ngân sách vẫn ghi `authority=advise`.

Notebook đang lưu trên Kaggle được import trước các chỉnh sửa trên.
**Cần import lại file local này** vào notebook `research-rag-autonomy-v1` trước khi chạy.
Không sửa câu hỏi, gold documents hay tiêu chí sau khi xem kết quả.

### Sửa lỗi chạy lại cell 3 — 2026-10-02

Cell 3 cũ dùng `suite.mkdir(exist_ok=False)`, nên dừng bằng `FileExistsError`
khi thư mục đã tồn tại, kể cả dữ liệu đã giải nén đúng. Bản mới cho phép chạy lại:

- Kiểm hash file đã có và giữ nguyên nội dung cùng thời điểm sửa file.
- Chỉ bổ sung file thiếu khi chưa có thư mục `results` và chưa ghi nhận stage
  `autonomy-e2e` trong `statuses`.
- Từ chối file sai hash hoặc bộ dữ liệu thiếu sau khi E2E đã bắt đầu.
- Giữ nguyên mọi kết quả E2E. Chạy lại cell 3 không cấp quyền chạy lại cell 4
  trong cùng lượt đánh giá.

Nếu cell 2 đã thành công, có thể sửa cell 3 tại chỗ để giữ phiên hiện tại:
đổi `suite.mkdir(exist_ok=False)` thành `suite.mkdir(exist_ok=True)`;
thay dòng `(suite/item['name']).write_bytes(content)` bằng khối kiểm tra file
tồn tại trong bản notebook mới. Chỉ đổi `exist_ok` mà vẫn ghi đè file không
giữ được việc kiểm tra toàn vẹn dữ liệu trước đó.

## Chạy tiếp trên Kaggle

1. Mở `https://www.kaggle.com/code/trcng23/research-rag-autonomy-v1/edit`.
   Giữ notebook Private. Import file local mới qua File → Import Notebook.
2. Chọn GPU T4 x2, Internet On. Kiểm tra secret có nhãn chính xác
   `GEMINI_API_KEY` và được cho phép dùng trong notebook; không đưa key vào code.
3. Chạy cell mount. Cell setup kiểm phiên bản/hash dataset nên dữ liệu khác bản
   được duyệt sẽ bị từ chối, kể cả khi `kagglehub` lấy phiên bản mới nhất.
4. Chạy cell setup và chỉ tiếp tục khi có `SETUP COMPLETE`, `pip-check`,
   `contract-tests`, `preflight` đều hoàn tất thành công.
5. Chạy cell khôi phục bộ đánh giá, đối chiếu criteria hash ở trên.
6. Chạy cell E2E. Deadline tiến trình toàn stage là 5.400 giây. Kiểm tra
   `status.json` và stderr nếu stage lỗi; không coi thông báo bắt đầu là thành công.
7. Lưu phiên bản kèm Output, xác nhận lưu thành công, tải ZIP kết quả và dừng GPU.

## Bằng chứng cần rà sau khi chạy

- `autonomy-v1/results/summary.json`, `case-results.json`: tám ca và gate retrieval.
- Mỗi ca: `state.json`, `metrics.json`, `events.jsonl`; đối chiếu quyết định,
  nguồn, kế hoạch, giới hạn và lý do dừng.
- `generations.jsonl`: lượt gọi backend cùng case tương ứng; đây là trace riêng tư.
- `retrieval-policy.json`: so adaptive/BM25/dense với cùng câu hỏi và ngân sách.
- `run-manifest.json`, `preflight.json`, `runtime-patch-manifest.json`,
  `output-manifest.json`: nhận diện code/model/host và kiểm toàn vẹn output.

`overall_pass` giữ false trong runner cho đến khi có rà soát độc lập về câu trả lời
và trích dẫn. Chi phí/token không được backend đo sẽ là null. Ba câu QASPER là
held-out candidates trong phạm vi từng paper; audit semantic overlap chưa hoàn tất.
Ngay cả khi tám ca đạt, kết luận chỉ áp dụng cho phạm vi đánh giá này.
