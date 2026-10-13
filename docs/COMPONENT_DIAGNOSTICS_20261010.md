# Bước 3 — Diagnostic Reader và confidence, 2026-10-10

## 1. Đã làm đến đâu?

**Đã hoàn thiện code, test local và hai notebook chạy riêng. Chưa chạy model/API thật cho bản này.**
Lượt kiểm tra local đạt **147/147 test**, 20,650 giây theo unittest; model và
API trong các test đều được giả lập. Không dùng con số này để nghiệm thu năng
lực model. Cấu hình phục vụ vẫn là `repair`, ngưỡng 0.7, tối đa 3 attempts/stage.

Lượt Kaggle gần nhất `20261010T025939Z` đã được đối chiếu trong
[báo cáo ZIP](COMPLETION_REVIEW_20261010T025939Z.md):

- Reader phục hồi được bốn lần HTTP 503, nhưng PDF thật dừng tại `page_no=3`
  (trang thứ 4) vì critique trả 429 qua cả ba attempts. Log cũ thiếu metadata
  để biết chính xác quota nào; không thể kết luận chỉ cần đợi một phút.
- Candidate `explanation_repair` nhận 10/12 nhãn sai trong thử nghiệm nhãn có
  kiểm soát. Chưa đủ bằng chứng để đổi prompt/backend hoặc quyết định huấn luyện.

**Bây giờ dùng hai notebook bên dưới. Không cần chạy lại sáu cell cũ.**

## 2. Những thay đổi trong code

| File | Thay đổi |
|---|---|
| `train_agent2_reader/reader_policy.py` | Ghi phần metadata quota được cho phép; đọc `RetryInfo.retryDelay` cùng `Retry-After`, vẫn nằm trong budget hiện có |
| `research_rag/evaluation/reader_smoke.py` | Tách hàm chấm từ chunks đã lưu để dùng chung cho live và offline |
| `research_rag/evaluation/reader_reliability.py` | Xuất blocks theo trang, exact chunks, manifest/tiêu chí/hash; thêm `--replay-dir` để tính lại kết quả |
| `research_rag/evaluation/compare_confidence_backends.py` | Thử cùng nhãn đề xuất trên hai backend và hai prompt; lưu từng prediction/call, nguồn model và thông số sinh |
| `research_rag/evaluation/confidence_backend_criteria.json` | Đóng băng tiêu chí riêng trước khi chạy thử nghiệm backend |
| `research_rag/tests/test_reader_api_retry.py`, `test_reader_reliability.py`, `test_confidence_backends.py`, `test_validation_notebook.py` | Regression cho lọc log, deadline, replay, gate và đóng gói notebook |
| `scripts/build_validation_notebook.py`, `build_component_notebooks.py` | Đóng gói 45 file runtime/test vào notebook; tạo hai runner riêng |

Bốn notebook cũ cũng đã được tạo lại từ payload hiện tại để không mang code
cũ; ở bước này chỉ chạy hai notebook mới. Dataset đã upload không cần thay thế.

### Reader: bằng chứng lưu được và giới hạn

`api_attempts.jsonl` thêm `error_details` nếu SDK trả metadata cấu trúc:
status, error reason/domain, quota metric/id/value, model/location và thời
gian đợi. Không lưu nguyên exception message, headers, mô tả quota, project,
consumer hoặc metadata tùy ý. Có regression test cho lọc key và dữ liệu lỗi.
Nếu provider không cung cấp các trường này, log có thể rỗng; khi đó nguyên nhân
quota vẫn cần được kiểm tra trong tài khoản của bạn.

Mỗi lần gửi vẫn chịu pacing 61 giây trong notebook, tối đa ba attempts cho
mỗi logical call và budget 240 giây gồm chờ/retry. `RetryInfo` không tăng budget.
Hai stage Reader cách nhau ít nhất 61 giây; process khác cùng tài khoản vẫn
có thể tiêu thụ chung quota. Một trang có thể cần nhiều logical calls.

Blocks được lưu ngay khi `process_page` trả kết quả, kèm `page_no`, PDF hash,
text, bbox, label, confidence, source tool và cờ `accepted`. Nếu trang sau lỗi,
các trang trước đã ghi vẫn còn. Trang lỗi API có thể trả danh sách blocks rỗng;
không dựng lại text mà runtime chưa trả về. PDF đọc lỗi vẫn là thất bại,
không ghép các trang còn lại rồi coi như đã đọc đủ PDF.

### Confidence: thí nghiệm trả lời câu hỏi gì?

Ma trận **2 backend × 2 prompt × 24 lượt = 96 predictions**:

| Backend | Prompt |
|---|---|
| Checkpoint merged đang dùng | `repair`, `explanation_repair` |
| `Qwen/Qwen2.5-3B-Instruct` | `repair`, `explanation_repair` |

Base được pin revision `aa8e72537993ba99e69dfaafa59ed015b17504d1`, tra từ
[metadata chính thức của model](https://huggingface.co/api/models/Qwen/Qwen2.5-3B-Instruct).
Nếu chưa cache, cần tải thêm khoảng 6,2 GB weights. Mỗi lần chỉ nạp một model
lên GPU; cả hai dùng tokenizer và generation config từ merged checkpoint,
NF4/FP16, `do_sample=False`, seed 42 và tối đa 192 output tokens/lần gọi.
Hash weights/tokenizer/source được lưu trong `provenance.json`.

24 lượt là 12 contract đã biết, mỗi contract được đưa một nhãn đúng và một
nhãn sai. Gold label chỉ dùng chấm điểm; không được đưa làm đáp án trong prompt.
Thử nghiệm chỉ gọi ConfidenceEstimator, không gọi model Judge hoặc ActionRecommender.
96 predictions có thể cần nhiều hơn 96 backend calls khi phải repair JSON.

Điều kiện đạt **mỗi profile** đã ghi trước inference:

- Đủ 24 kết quả, không runtime failure.
- Nhận đủ 12 nhãn đúng ở score >= 0.7.
- Không nhận bất kỳ nhãn sai nào ở ngưỡng này.
- Tối đa ba attempts cho mỗi prediction.

`required_profile` được chọn trước là `base_instruct__explanation_repair`;
exit code và `automated_gate_pass` tổng dùng profile đó. Các profile đạt khác
vẫn được liệt kê trong `qualifying_profiles`. Không lựa chọn lại tiêu chí sau
khi nhìn kết quả. `human_review=pending`, `overall_pass=false`,
`promoted_to_serving=false` được giữ dù automated gate đạt.

Đây là đối chiếu artifact trên dữ liệu development. Revision base dùng lúc
fine-tune cũ chưa được xác lập, nên chưa thể quy nguyên nhân cho fine-tuning.
24 lượt không phải 24 mẫu độc lập, không phải calibration hay đánh giá cuối.

## 3. Chuẩn bị Kaggle

1. Giữ notebook và ZIP cũ. Import mỗi file mới vào một notebook **Private**.
2. Dùng GPU T4 và bật Internet. Có thể chạy confidence trước vì không phụ thuộc
   quota Gemini. Chạy lần lượt hai notebook để dễ quản lý tài nguyên.
3. Gắn đúng hai dataset đã dùng:
   `trcng23/research-rag-five-agents-workspace` và
   `trcng23/research-rag-runtime-diagnostics` bản diagnostics v2.
4. Cell 1 mount dataset; cell 2 kiểm hash, tạo workspace/output mới, cài môi
   trường, chạy `pip check`, contract tests và preflight. Đợi `SETUP COMPLETE`.
   Local có 147 tests; payload Kaggle có 139 tests, không đóng gói tám test
   kiểm chính các file notebook trên máy local.
5. Đọc `preflight.stdout.log`: confidence cần checkpoint factchecker đủ shards;
   Reader cần checkpoint LayoutLMv3 và binary Tesseract. Thiếu cache cho
   Summarizer/Writer không tự chứng minh hai diagnostic này không chạy được,
   cũng không được xem là toàn hệ đã sẵn sàng.

Setup cần hơn 35 GiB trống ở `/tmp` trước khi copy workspace. Nếu bước này
hoặc hash check lỗi, lưu log và xử lý nguyên nhân; không bỏ qua assertion.

### A. Confidence — ba code cell

Import [kaggle_confidence_backends.ipynb](../scripts/kaggle_confidence_backends.ipynb).

| Cell | Thao tác và kết quả cần đọc |
|---|---|
| 1 | Mount hai dataset |
| 2 | Setup/test/preflight; chỉ sang cell 3 khi hoàn tất |
| 3 | Chạy ma trận 96 predictions, timeout 5.400 giây; in `metrics.json` và `summary.json`; đóng gói ZIP |

Notebook này không cần Secret Gemini và không gọi Gemini. Cell 3 dùng
`required=False`: cell chạy hết **không đồng nghĩa model đạt**. Đọc
`experiment_completed`, `prediction_count`, `automated_gate_pass`, từng profile
và `status.json`. Nếu chưa có summary, đọc stderr để phân biệt lỗi tải model,
thiếu RAM/VRAM, timeout với gate chất lượng trượt.

### B. Reader — bốn code cell

Import [kaggle_reader_diagnostics.ipynb](../scripts/kaggle_reader_diagnostics.ipynb).

1. Cho notebook truy cập Secret hiện có tên `GEMINI_API_KEY`; không dán key vào
   code/output. Kiểm tra quota dự án trước khi chạy live.
2. Chạy cell 1–2. Cell 3 kiểm Tesseract trước khi gọi API; nếu thiếu binary,
   cài theo [README Reader](../train_agent2_reader/README.md) rồi tạo run mới.
3. **Cell 3:** chỉ đọc `page_no=3` của PDF thật, tức trang thứ 4 từng lỗi 429;
   timeout 900 giây. Xuất diagnostic rồi tự replay offline nếu có summary.
4. Chỉ chạy **cell 4** khi `reader-failed-page` có state `completed` và
   `automated_gate_pass=true`. Cell 4 đọc lại toàn PDF 12 trang, timeout 5.400
   giây, xuất diagnostic và tự replay. Nếu probe vẫn lỗi quota, giữ ZIP đó để
   chẩn đoán; chưa tiếp tục đọc toàn PDF.

Notebook giữ model ID mặc định của repo `gemini-3.6-flash`, hoặc `GEMINI_MODEL`
nếu đã đặt trong environment; in/lưu model được yêu cầu. Đây không phải lời
khẳng định endpoint đó luôn khả dụng cho mọi tài khoản. Nếu 403/404, xác minh
quyền/model từ lỗi nhận được trước lượt chạy mới.

### C. Lưu kết quả và chạy lại

Cuối mỗi stage, notebook ghi `/kaggle/working/rag-validation-<RUN_ID>.zip`.
Lưu phiên bản **kèm Output**, tải ZIP rồi dừng GPU. Gửi lại ZIP của từng notebook,
kể cả lượt trượt gate; không chỉ gửi ảnh chụp metrics.

Helper chặn chạy một stage hai lần vào cùng run. Nếu cần thử lại, giữ ZIP cũ,
chạy lại từ cell 1–2 để tạo workspace và run ID mới; không xóa output cũ hoặc
đổi `exist_ok=False` để ghi đè bằng chứng. Nếu process timeout trước khi có
summary, những log đã flush vẫn có ích nhưng chưa đủ để xác nhận pass/replay.

## 4. Cách đọc artifact và review offline

| Artifact | Dùng làm gì? |
|---|---|
| `output-manifest.json`, `runtime-patch-manifest.json`, `status.json` | Đối chiếu hash code/kết quả và trạng thái từng stage |
| `reader-*/api_attempts.jsonl` | Xác định trang, router/critique, số lần gửi, HTTP status, thời gian và metadata quota |
| `reader-*/page_trials.jsonl`, `page_blocks.jsonl` | Review quyết định tool và nội dung theo trang, kể cả các trang trước khi PDF lỗi |
| `reader-*/extractions.jsonl` | Exact chunks mà scorer nhận cho PDF thành công; PDF lỗi có `error_type` |
| `reader-*/input-manifest.jsonl`, `criteria.json`, `summary.json` | Nguồn/expected spans, tiêu chí trước chạy, metric và hash để replay |
| `reader-*-replay/replay.json` | Tính lại metric, API summary và gate từ artifact đã kiểm hash |
| `confidence-backends/*-calls.jsonl`, các file predictions | Từng lần gọi, output, nhãn đề xuất và confidence |
| `confidence-backends/criteria.json`, `provenance.json`, `metrics.json`, `summary.json` | Tiêu chí đóng băng, nguồn model/config và kết quả bốn profile |
| `confidence-backends/explanation-review.jsonl` | 96 dòng review đang pending; rubric và input/output để người đọc đánh giá |

Chạy lại Reader scorer tại repo có môi trường đã cài, không cần PDF/model/API:

```powershell
.\.venv\Scripts\python.exe -m research_rag.evaluation.reader_reliability --replay-dir "DUONG_DAN_KET_QUA/reader-real" --output-dir "DUONG_DAN_MOI/reader-real-replay"
```

Thay hai đường dẫn bằng vị trí thật; output phải chưa tồn tại. Replay kiểm
hash, source, expected spans và tính lại metric/gate. `replay_verified=true`
chỉ xác nhận có thể tái tạo kết quả đã ghi; `automated_gate_pass` vẫn có thể
false. Sửa nội dung trước khi replay sẽ bị từ chối. Replay không thay human review.

Review Reader bằng cách đối chiếu text với đúng trang PDF: câu/số/đơn vị, phần
phủ định, thiếu hoặc lặp nội dung, thứ tự đọc, bảng và công thức. Gate phrase
presence chỉ kiểm có cụm từ đúng trang, chưa đo toàn bộ chất lượng OCR/layout.

Review confidence bằng rubric có sẵn, đặc biệt các cặp wrong units, negation,
partial accuracy và thiếu thông tin. Lý do phải chỉ ra bằng chứng/mâu thuẫn
hoặc phần thiếu trong context; score đúng nhưng lý do bịa vẫn chưa đạt review.
Giữ bản raw, ghi nhận reviewer/quyết định vào bản review riêng.

ZIP Reader mới chứa **nội dung tài liệu đã trích xuất**; giữ private như PDF
nguồn. Việc lọc credential áp dụng cho log lỗi API, không xóa nội dung cần
review khỏi blocks/chunks.

## 5. Sau khi nhận hai ZIP

1. Kiểm hash/code thực chạy, tính lại metrics/gates, phân loại lỗi runtime và
   lỗi chất lượng; hoàn tất review nội dung Reader/explanation.
2. Nếu quota còn lỗi, dùng metadata mới để xác định quota cụ thể. Retry không
   thay đổi hạn mức tài khoản. Nếu confidence còn trượt, dùng ma trận để quyết
   định thử backend/prompt hay chuẩn bị dữ liệu huấn luyện riêng; chưa tự đổi serving.
3. Khi hai thành phần đạt, xử lý Summarizer `heldout_3` nhầm baseline, chạy
   regression thành phần, rồi chạy lại đủ tám ca autonomy trên model thật.
4. Chuẩn bị đánh giá độc lập/calibration và human sign-off trước khi tuyên bố
   hoàn thiện. Những benchmark đã xem hiện là regression, không phải final test.

## 6. Bằng chứng kiểm tra local

- 147/147 tests đạt trong lượt chạy được cấp quyền ngoài sandbox. Lượt đầu có
  fixture Torch thiếu `__version__` (đã sửa) và Windows chặn rename file tạm;
  không bỏ test hoặc nới gate để có kết quả đạt.
- Test xác nhận lọc quota metadata, RetryInfo trong deadline, replay khi PDF
  đã bị chuyển khỏi đường dẫn, giữ PDF lỗi là lỗi, phát hiện artifact thay đổi,
  pin model revision, giải phóng model, cùng input giữa backend, gate không
  nhận model luôn trả 0/1, compile và kiểm hash payload của notebook.
- Có warning dependency `requests` và khuyến nghị AFC từ SDK trong môi trường
  local; không có test thất bại. Kaggle setup vẫn phải đạt `pip check` riêng.
- Chưa chạy GPU/Gemini cho runtime mới; chưa thay backend/prompt phục vụ,
  chưa sửa Summarizer, chưa đóng gate toàn dự án.

Hash file và đường dẫn log: [component-diagnostics-validation-20261010.json](component-diagnostics-validation-20261010.json).
