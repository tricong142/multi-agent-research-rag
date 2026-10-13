# Hoàn thiện explanation và Reader — 2026-10-10

## 1. Trạng thái và phạm vi

Đã hoàn thiện code, regression tests và notebook để bạn chạy thủ công trên
Kaggle. **Chưa có inference GPU/API mới cho bản sửa này.** 137 kiểm thử local
đạt không phải bằng chứng chất lượng model thật hoặc dịch vụ Gemini hết 503.

Giữ cấu hình `repair` đã được kiểm chứng bằng ZIP `20261009T120708Z`: prompt
Judge/confidence mặc định, retry feedback, threshold 0.7, tối đa 3 attempts
mỗi stage. Không promote `label_confidence_repair`, không sửa kết quả/tiêu chí
v1 sau khi đã thấy kết quả. Chi tiết bằng chứng cũ ở
[báo cáo đối chiếu](CONFIDENCE_STEP1_REVIEW_20261009T120708Z.md).

## 2. Vấn đề và cách sửa

### Confidence explanation

Lượt cũ chứng minh sửa được output sai contract, nhưng chưa chứng minh lời
giải thích có căn cứ. Ví dụ `wrong_units`: claim nói 12 giây, nguồn nói 12 giờ;
reasoning lại viện dẫn annotation hỗ trợ. Prompt thử nghiệm cũ còn cho 1.0 ở
cả 47 dòng, kể cả nhãn sai theo gold. Không thể dùng score cao làm bằng chứng
rằng model đã hiểu mâu thuẫn.

Ứng viên mới `explanation_repair` chỉ được dùng khi chạy diagnostic
`--comparison explanation`. Prompt yêu cầu so claim với context: nêu chi tiết
hỗ trợ, hai chi tiết mâu thuẫn hoặc thông tin còn thiếu; không viện dẫn annotation
không có trong đầu vào. Nhãn Judge đề xuất sai cần confidence thấp. Runtime
mặc định vẫn dùng prompt `repair` cũ; không có promotion tự động.

Tiêu chí mới nằm trong `confidence_explanation_criteria.json`, version
`confidence-explanation-20261009-v2`, được sao chép vào kết quả trước inference:

- So hai profile trên cùng 47 dòng: dev30 + 12 contracts + 5 review lỗi cũ.
  Giữ 9 gate: đủ dòng, không runtime failure, nhãn Judge không đổi, metric nhãn
  không giảm, false support không tăng, không nhận false support, support đúng
  được nhận không giảm, có support được nhận, attempts trong budget.
- Thêm 24 lượt đánh giá nhãn có kiểm soát: mỗi contract có một nhãn đúng và
  một nhãn sai được đưa vào ConfidenceEstimator với cùng claim/context.
  Phải nhận đủ 12 nhãn đúng tại score >= 0.7, không nhận nhãn sai nào tại ngưỡng
  này, không runtime failure. Vì vậy model luôn trả 1 hoặc luôn trả 0 đều trượt.
- Tổng cộng **142 predictions = 2 × (47 + 24)** nếu chạy đủ. Đây không phải số
  backend calls: retry/action có thể tạo thêm calls. 24 ca mỗi profile dùng
  nhãn đưa vào sẵn, **không gọi model Judge**; không được tính chúng thành
  accuracy của Judge hoặc calibration độc lập. Nhãn gold không được đưa vào
  prompt confidence như đáp án.
- Xuất 71 dòng candidate vào `explanation-review.jsonl` để người đọc đánh giá.
  `human_review=pending`, `overall_pass=false`, `promoted_to_serving=false`
  được giữ dù automated gate đạt.

Các ca này là dữ liệu development/regression đã được xem. Chúng không chứng
minh khả năng tổng quát hóa; năm review lỗi cũng không phải năm input độc lập.

### Reader / HTTP 503

Log cũ chứng minh Gemini trả 503 ở critique trang 0. Code cũ pacing ở wrapper
nhưng SDK có retry bên trong, nên không áp dụng được cùng pacing cho mọi lần
gửi. Đây là thiếu sót phía ứng dụng đã xác định; chưa đủ bằng chứng kết luận
nguyên nhân gây 503 ở máy chủ Gemini.

`reader_policy.py` hiện sở hữu retry, SDK được đặt `attempts=1`:

| Chính sách | Giá trị / ý nghĩa |
|---|---|
| Số lần gửi | Tối đa 3 mỗi logical call router hoặc critique |
| Lỗi được retry | HTTP 408, 429, 500, 502, 503, 504 và `httpx.TransportError` |
| Lỗi dừng ngay | Ví dụ 400/401/403/404; không tiếp tục gửi do lỗi auth/model |
| Backoff | Tăng theo lần thử, có jitter, tối đa 4 giây; tôn trọng Retry-After trong budget |
| Pacing | Áp dụng mọi attempt trong cùng process; notebook đặt 61 giây |
| Call budget | `GEMINI_CALL_BUDGET_SECONDS=240`, tính cả đợi lock/pacing/backoff |
| HTTP timeout | Tối đa 30 giây mỗi phase, giảm theo budget còn lại |
| Outer timeout | Notebook dừng cả tiến trình khi vượt thời gian của stage |

Một trang có thể cần nhiều logical calls; giới hạn 3 không phải giới hạn API
calls của cả PDF. HTTPX phase timeout không phải hard wall-clock cancellation;
response về sau deadline bị từ chối, nhưng vẫn cần outer timeout cho call treo.
Pacing này không điều phối quota với notebook/process khác của cùng tài khoản.

Metadata được ghi cho từng API attempt: call ID, stage, model được cấu hình,
attempt, status khi SDK cung cấp, latency/chờ, kết quả retry hoặc lý do dừng.
SDK đang pin 2.22.0 không cung cấp HTTP status cho response thành công ở đường
này, nên log để `null`, không tự gán 200. Không ghi key, headers hay prompt vào
API attempt log. Không tự đổi model hoặc chấp nhận text khi API thất bại.
Chi phí USD để `null` khi backend chưa đo được.

## 3. Chạy notebook mới trên Kaggle

Dùng **[kaggle_completion_validation.ipynb](../scripts/kaggle_completion_validation.ipynb)**.
Đây là notebook mới có 6 code cell; không chạy nhầm notebook confidence cũ
3 cell hoặc autonomy 4 cell.

### Chuẩn bị

1. Giữ notebook/output cũ làm bằng chứng. Import file mới vào notebook Private.
2. Bật GPU T4 và Internet; dùng hai dataset đã dùng ở lượt trước:
   `trcng23/research-rag-five-agents-workspace` và
   `trcng23/research-rag-runtime-diagnostics` (diagnostics v2).
3. Cho notebook truy cập Secret `GEMINI_API_KEY` hiện có. Không dán giá trị
   key vào cell. Cell 3 dùng model local; cells 4–6 mới sử dụng Secret.
4. Chạy từng code cell và đọc kết quả trước khi sang cell tiếp theo.

| Cell | Công việc | Điều kiện để tiếp tục |
|---|---|---|
| 1 | Mount hai dataset hiện có | In đường dẫn mount thành công |
| 2 | Workspace mới, kiểm base/payload hashes, cài môi trường, `pip check`, contract tests, preflight | Có `SETUP COMPLETE`, các stage exit 0 |
| 3 | `repair` đối chiếu `explanation_repair`; timeout 5.400 giây | Đọc `gate-results.json`, `metrics.json`; lưu ZIP kể cả thất bại |
| 4 | Khôi phục đúng PDF từng lỗi, chỉ đọc trang 0; timeout 900 giây | `reader-page0` exit 0 và `automated_gate_pass=true` |
| 5 | Reader smoke; timeout 3.600 giây | `reader-smoke` exit 0 và `automated_gate_pass=true` |
| 6 | PDF thật 12 trang; timeout 5.400 giây | `reader-real` exit 0 và `automated_gate_pass=true`; lưu Output rồi dừng GPU |

Cell 3 dùng `required=False` để giữ kết quả khi candidate không đạt; cell chạy
xong không đồng nghĩa diagnostic pass. Candidate confidence trượt vẫn có thể
chạy Reader vì hai phần độc lập. Cell 5/6 chặn nếu Reader stage trước chưa đạt.

Cell 4 in model ID được yêu cầu và lưu vào log. Notebook giữ default cấu hình
repo (`gemini-3.6-flash`), chấp nhận `GEMINI_MODEL` đã đặt rõ trong environment.
Tên trong repo không chứng minh endpoint hiện có cho tài khoản; không suy ra
đó là model thực tế của lượt 503 cũ vì log cũ thiếu thông tin này. Nếu có lỗi
404/403, lưu lỗi và xác minh model/quyền trước lần chạy mới; không dùng việc
đổi model để tuyên bố cùng cấu hình đã khắc phục 503.

Nếu cell 4 báo thiếu `tesseract`, host thiếu binary OCR; dừng trước API và cài
binary theo hướng dẫn Reader. `pytesseract` là Python wrapper, chưa đủ để OCR.

### Nếu cell lỗi hoặc cần chạy lại

- Mở `status.json`, `<stage>.stderr.log` và summary của stage để biết lỗi thực.
  Lỗi `confidence-explanation-v2` exit 1 có thể là gate trượt, không phải lỗi cài đặt.
- Giữ ZIP hiện tại; không xóa thư mục kết quả hoặc đổi `exist_ok=False` để ghi
  đè inference đã có. Helper chặn một stage bị chạy hai lần trong cùng run.
- Nếu muốn thử lại, lưu Output/ZIP rồi chạy từ cell 1–2 để tạo run ID và
  workspace mới. Nếu chỉ mất kết nối, kiểm Output cũ trước khi tạo run mới.
- Stage timeout có thể chưa có summary cuối. Attempt log đã flush giúp xác
  định bước cuối; thiếu summary không được xem là pass.
- Cuối mỗi stage, notebook đóng gói
  `/kaggle/working/rag-validation-<RUN_ID>.zip`. Lưu phiên bản **kèm Output**, xác
  nhận đã lưu, tải ZIP về rồi dừng GPU. ZIP trên working chưa bảo đảm bền vững
  nếu phiên làm việc bị mất trước khi lưu.

## 4. Đọc kết quả và nghiệm thu

### Bước 1 — confidence

Trong `confidence-explanation-v2/`, giữ nguyên `criteria.json`, `provenance.json`,
`metrics.json`, `gate-results.json`, các prediction/call JSONL và
`explanation-review.jsonl`.

1. Kiểm hash/provenance, đủ 142 prediction và đủ 71 review rows. Đọc số backend
   calls thực từ trace; không lấy số prediction thay cho số call.
2. Candidate cần đạt gate gốc và gate phân biệt nhãn đúng/sai mới. Nếu trượt,
   giữ `repair`, phân tích ca trượt; không hạ tiêu chí sau khi thấy kết quả.
3. Tạo bản sao `explanation-review.completed.jsonl`, giữ nguyên fields kết quả
   gốc. Người thực sự đọc claim/context điền tên `reviewer`, `note`, bốn boolean
   trong `judgments`; điền `review_status=passed` khi cả bốn true, ngược lại failed:

   | Field | Cách đánh giá |
   |---|---|
   | `grounded_in_context` | Mọi chi tiết viện dẫn có trong context, không bịa annotation/số liệu |
   | `explains_proposed_label` | Nêu được căn cứ đánh giá nhãn đề xuất; nếu nhãn sai, giải thích vì sao không tin nhãn |
   | `identifies_conflict_or_missing_fact_when_applicable` | Chỉ ra hai vế mâu thuẫn hoặc thông tin chưa biết; ca support không áp dụng thì ghi rõ trong note |
   | `score_explanation_consistent` | Score nhất quán với mức tin nhãn mà lời giải thích thể hiện |

   Ví dụ ca đơn vị phải chỉ ra **giây so với giờ**; ca thiếu thông tin phải
   nêu đúng thông tin chưa có. Một câu chung chung “context có hỗ trợ” chưa đủ.
   Không tự điền pass hàng loạt hoặc coi template do script tạo là human review.
4. Gửi ZIP gốc kèm bản review đã điền để đối chiếu. File gate gốc luôn giữ
   `overall_pass=false` trong diagnostic; quyết định nghiệm thu phải được ghi
   thành báo cáo riêng sau review, không sửa lịch sử JSON để tạo pass.

Contract/retry của bước 1 đã có bằng chứng đạt ở lượt cũ. Phần explanation cần
bằng chứng mới. Đạt diagnostic mới cũng chưa tự động đổi serving prompt hoặc
chứng minh confidence đã calibration.

### Bước 2 — Reader

Mỗi thư mục `reader-page0/`, `reader-smoke/`, `reader-real/` có:

- `criteria.json`: tiêu chí, PDF/manifest hashes, model/SDK/config trước API.
- `api_attempts.jsonl`: trace API phục vụ kiểm retry, pacing, budget, status.
- `page_trials.jsonl`: tool được chọn, attempts, success, số block từng trang.
- `summary.json`: phrase/page coverage, lỗi PDF/API, gate, latency; cost chưa đo.

Gate yêu cầu toàn bộ expected spans hiện diện đúng trang, không PDF failure,
không terminal API failure, có ít nhất một API attempt và đúng giới hạn attempt/
deadline. Một call 503 rồi thành công có thể đạt; hết retry/budget phải fail.

Người đọc vẫn cần so PDF với nội dung trích xuất cho chất lượng bảng, thứ tự đọc
và chi tiết ngoài expected spans. Các gate hiện kiểm phrase/page presence, chưa
đo đầy đủ semantic/OCR quality. `human_review=pending`, `overall_pass=false`
trong summary là trạng thái có chủ ý. PDF smoke/page0 là fixture regression;
không coi chúng là mẫu thực tế độc lập.

## 5. File đã sửa và kiểm tra local

| Nhóm | File |
|---|---|
| Candidate confidence và diagnostic | `04_factchecker/prompts.py`, `research_rag/evaluation/compare_factchecker.py`, `confidence_explanation_criteria.json` |
| Reader runtime | `train_agent2_reader/reader_policy.py`, `reader_agent.py` |
| Reader diagnostic | `research_rag/evaluation/reader_smoke.py`, `reader_reliability.py` |
| Regression | `test_confidence_explanations.py`, `test_reader_api_retry.py`, `test_reader_reliability.py`, `test_validation_notebook.py` trong `research_rag/tests/` |
| Packaging | `scripts/build_validation_notebook.py`, `build_completion_notebook.py`; tái tạo các notebook resume/autonomy/confidence/completion |
| Hướng dẫn | README Fact-checker/Reader, tài liệu này, `PROJECT_STATUS.md`, `completion-validation-20261010.json` |

Chạy full suite bằng Python 3.10 local: **137 tests, 27.011 giây, OK**. Lượt
sandbox đầu có 136 pass và 1 lỗi `PermissionError/WinError 5` khi đổi tên ZIP
tạm; lượt chạy lại ngoài sandbox được phê duyệt đạt cả 137. Không thay behavior
để che lỗi quyền. Test dùng backend giả và HTTP transport mock, không API/GPU.
Có kiểm 503 rồi hồi phục, 503 kéo dài, lỗi auth, Retry-After/deadline, model
luôn score 1/0, review chưa được điền, payload hash và notebook compile.

Có warning dependency của `requests` và cảnh báo AFC của Google SDK ở local;
không gây test failure. Kaggle vẫn phải qua `pip-check` của môi trường riêng.
Nhánh terminate process group trên Linux chưa được thực thi bằng test Windows.

Lệnh tái tạo notebook, chạy lần lượt từ gốc repo:

```powershell
.\.venv\Scripts\python.exe scripts/build_validation_notebook.py
.\.venv\Scripts\python.exe scripts/build_autonomy_notebook.py
.\.venv\Scripts\python.exe scripts/build_confidence_notebook.py
.\.venv\Scripts\python.exe scripts/build_completion_notebook.py
$env:OMP_NUM_THREADS='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
.\.venv\Scripts\python.exe -m unittest discover -s research_rag/tests -q
```

Generator dùng base ZIP đã có trong `kaggle_transfer/` và frozen PDF trong
`research-runs/autonomy-v1-20260930/`; không cần upload lại dataset để dùng bản
vá 42 file nhúng trong notebook. Không sửa notebook payload bằng tay.

## 6. Công việc còn lại để đóng dự án

1. Chạy notebook này, đối chiếu ZIP và hoàn tất review explanation/Reader.
2. Xử lý Summarizer `heldout_3`: đã biết nhầm baseline với phương pháp được hỏi,
   evidence span bị verbatim gate chặn. Chưa sửa ở lượt này; giữ chặn để tránh
   biến lỗi nội dung thành câu trả lời có vẻ hợp lệ.
3. Sau các sửa thành phần, chạy lại **đủ 8 ca E2E** bằng notebook autonomy hiện
   có; giữ frozen criteria. Diagnostic ở đây không chạy controller/graph đủ
   để chứng minh toàn hệ đã đạt.
4. Chốt nguồn và human annotations; đánh giá trên dữ liệu độc lập với dữ liệu
   đã chọn prompt/ngưỡng; đo abstention/citation, độ trễ, tài nguyên và chi phí
   khi có phép đo. Viết báo cáo nghiệm thu với trace và giới hạn thực tế.

Chỉ sau khi có các bằng chứng trên mới kết luận phạm vi nào đã đạt. Hiện mô tả
phù hợp là **multi-agent được điều phối với phạm vi nhiệm vụ và giới hạn vận
hành**, chưa có căn cứ gọi “hoàn toàn tự chủ” hoặc “sẵn sàng production”.
