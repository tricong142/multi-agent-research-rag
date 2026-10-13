# Bước 1 — sửa contract confidence và chuẩn bị kiểm chứng model thật

## 1. Trạng thái

Đã nhận lượt model thật `20261009T120708Z`: **repair đạt gate tự động, runtime
failure 7/47 → 0/47**, cả 7 trường hợp output lỗi được sửa ở attempt thứ hai.
Chưa đóng nghiệm thu đầy đủ: human review chưa xác nhận và còn vấn đề chất
lượng explanation/ý nghĩa confidence. Prompt thử nghiệm chưa được promote.
Xem [đối chiếu kết quả mới](CONFIDENCE_STEP1_REVIEW_20261009T120708Z.md).
Các phần bên dưới ghi thiết kế, thay đổi và cách tái tạo; không đồng nghĩa toàn
bộ dự án đã đạt.

Lỗi đã thấy trong ZIP 20261009T103057Z: 15 output
`{"confidence_score":1.0,"reasoning":""}` trong 5 review, mỗi review thử 3 lần.
Đây là JSON parse được nhưng không thỏa contract. Retry cũ đưa cùng input với
`do_sample=False`, không truyền lỗi validation cho lần thử sau.

## 2. Thay đổi và luồng thực thi

1. `TransformersJSONBackend` giữ raw text trong `ModelOutputError` khi JSON không
   parse được. Raw text không nằm trong thông báo lỗi công khai.
2. `ConfidenceEstimator` yêu cầu score là JSON number hữu hạn trong [0,1], không
   chấp nhận bool/chuỗi. `reasoning` phải là string có nội dung; không ép `null`
   hoặc list thành chuỗi để qua validator.
3. `FactCheckerNode` vẫn sở hữu **một** vòng retry: tối đa 3 attempts cho mỗi
   stage theo cấu hình mặc định. Một attempt là một lần gọi backend; estimator
   không mở thêm vòng retry.
4. Khi confidence sai contract/JSON, lần tiếp theo nhận claim/context gốc,
   lỗi validation và output trước đó. Chỉ giữ output lỗi gần nhất, tối đa 4.000
   ký tự; không tích lũy lịch sử prompt vô hạn. Lỗi transport không được đưa vào prompt.
5. Hết attempts vẫn trả `confidence_failed`; graph tiếp tục chặn xác minh claim.
   Runtime vẫn có fallback score 0, nhưng evaluator lưu score `null` cho runtime
   lỗi, không coi fallback là confidence model.
6. Judge mặc định, ngưỡng 0.7 và prompt confidence của lần gọi đầu mặc định giữ
   nguyên. Prompt `LABEL_CONFIDENCE_SYSTEM_PROMPT` được làm rõ yêu cầu explanation
   không rỗng; chỉ dùng trong profile thử nghiệm.

### File liên quan

| File | Mục đích thay đổi |
|---|---|
| `04_factchecker/inference/judge.py` | Exception giữ output để sửa; thêm prompt token count vào callback chẩn đoán hiện có |
| `04_factchecker/inference/confidence.py` | Validation đúng kiểu; tạo feedback cho lần retry |
| `04_factchecker/node.py` | Chuyển lỗi attempt trước cho confidence trong cùng ngân sách retry |
| `04_factchecker/prompts.py` | Làm rõ prompt confidence thử nghiệm, không thay Judge |
| `04_factchecker/eval_factchecker.py` | Giữ attempts trong prediction phục vụ audit |
| `research_rag/evaluation/compare_factchecker.py` | Thêm `--comparison confidence`, trace, metric và gate |
| `research_rag/evaluation/confidence_criteria.json` | Tiêu chí chốt trước khi inference |
| `research_rag/evaluation/confidence_failures_20261009.jsonl` | 5 review lỗi thực tế; nhãn do assistant rà từ evidence, không phải human gold độc lập |
| `research_rag/tests/test_confidence_repair.py` | Regression cho output rỗng, JSON sai, kiểu sai, giới hạn retry và cô lập feedback |
| `research_rag/tests/test_confidence_diagnostic.py` | Kiểm số liệu, trace và gate không chấp nhận bỏ lỗi/abstain toàn bộ |
| `research_rag/tests/test_validation_notebook.py` | Kiểm notebook mới compile được và dùng đúng setup/payload |
| `scripts/build_validation_notebook.py` | Đóng gói các file runtime/test/data mới với before/after hash |
| `scripts/build_autonomy_notebook.py` | Cập nhật revision của bản E2E dùng runtime mới |
| `scripts/build_confidence_notebook.py` | Tạo notebook riêng bước 1 từ setup đã kiểm hash |

Ba notebook sinh lại: `kaggle_resume_validation.ipynb`,
`kaggle_autonomy_validation.ipynb`, `kaggle_confidence_validation.ipynb`.

## 3. Thí nghiệm đã chuẩn bị

Mỗi profile chạy cùng **30 dev + 12 synthetic contracts + 5 review lỗi = 47
prediction**. Ba profile tạo 141 predictions; số lần gọi model lớn hơn vì mỗi
prediction gồm Judge, confidence và có thể action/retry. Năm review lỗi chỉ có
bốn cặp claim/context phân biệt; giữ duplicate để đối chiếu hai ca E2E, báo
riêng nhóm này và không coi là năm mẫu độc lập.

| Profile | Prompt confidence | Feedback retry |
|---|---|---|
| `legacy_retry` | Mặc định hiện có | Tắt, lặp prompt như trước |
| `repair` | Mặc định hiện có | Bật — khớp serving mới |
| `label_confidence_repair` | Diễn giải rõ confidence của nhãn | Bật — thử nghiệm |

Cả ba dùng **cùng Judge**, threshold 0.7, tối đa 3 attempts/stage, cùng model
merged NF4/FP16. `legacy_retry` dùng validator strict mới giống hai profile còn
lại để tách tác động retry/prompt; không phải toàn bộ runtime lịch sử nguyên byte.

Không đổi threshold sau khi thấy kết quả. Gate yêu cầu đủ dòng, không còn runtime
failure cuối cùng, Judge predictions không đổi, label accuracy/macro-F1 không
giảm, false support không tăng, không chấp nhận false support tại threshold,
số true support được chấp nhận không giảm, có ít nhất một support được chấp
nhận và attempts trong ngân sách. Lỗi ở attempt đầu đã sửa được vẫn được đếm
trong `confidence_invalid_attempts`, không bị xóa khỏi báo cáo.

Tiêu chí trên là gate diagnostic của dự án, không phải chuẩn phổ quát. Calibration
metrics chỉ tính khi cả nhóm không có runtime failure; confidence vẫn là
self-assessment chưa hiệu chuẩn. Latency và calls được báo; một lượt tuần tự
không đủ làm benchmark hiệu năng tổng quát. Chi phí USD chưa đo được, lưu `null`.

## 4. Bạn chạy trên Kaggle như sau

1. Tạo notebook mới và import **`scripts/kaggle_confidence_validation.ipynb`**.
   Giữ notebook Private, bật GPU T4 và Internet. Chỉ riêng bước này không cần
   Gemini API key vì không gọi Reader.
2. Gắn hai dataset đã dùng: `trcng23/research-rag-five-agents-workspace` và
   `trcng23/research-rag-runtime-diagnostics` (diagnostics version 2). Payload
   mới nằm trong notebook, không cần upload lại bộ weights.
3. Chạy **code cell 1** để mount dữ liệu. Hai manifest phải được tìm thấy.
4. Chạy **code cell 2**, đợi `SETUP COMPLETE`. Cell này tạo workspace mới, kiểm
   hash, áp dụng runtime mới, cài môi trường và chạy contract tests/preflight.
   Nếu cell lỗi, giữ stdout/stderr và xử lý trước khi tiếp tục.
5. Chạy **code cell 3**. Cell chạy diagnostic tối đa 5.400 giây, lưu từng stage,
   rồi in `gate-results.json`, `metrics.json` và đường dẫn ZIP. Đây không phải
   lượt E2E tám ca; Reader/Summarizer không được đánh giá ở bước này.
6. Đọc gate và trace. `repair.automated_gate_pass=true` mới là đạt các điều kiện
   tự động của bản serving. Nếu chỉ profile thử nghiệm đạt thì cần rà chất lượng
   và quyết định riêng trước khi thay prompt mặc định.
7. Lưu phiên bản có Output, kiểm ZIP đã được giữ, tải file
   `/kaggle/working/rag-validation-<RUN_ID>.zip`, rồi dừng GPU session.
   Gửi ZIP này để đối chiếu. Không chọn riêng những dòng thành công.

Cell 3 dùng `required=False` để vẫn đóng gói bằng chứng khi gate thất bại;
**cell chạy xong không có nghĩa gate đạt**. CLI exit 1 nếu profile `repair`
không qua gate. `overall_pass=false` và `human_review=pending` vẫn được giữ
kể cả khi automated gate đạt; script không tự ký nghiệm thu hoặc promote prompt.

Không chạy lại cell 3 trên cùng thư mục kết quả: runner chủ động từ chối ghi
đè. Muốn chạy lại, lưu ZIP rồi dùng session/run mới. Không sửa `exist_ok` để
trộn hai lượt đo vào cùng output.

### Artifact cần xem

Trong ZIP, thư mục `confidence-step1/` có:

- `criteria.json`, `provenance.json`: tiêu chí trước inference, IDs, hashes,
  prompts và cấu hình thực sự dùng.
- `metrics.json`: metric tách riêng theo profile/dataset; coverage có mẫu số
  là toàn bộ dòng, gồm cả runtime failure.
- `gate-results.json`: từng check, chưa có human review.
- `<profile>-<dataset>.jsonl`: nhãn, score thực hoặc null, explanations, attempts,
  calls và latency của từng prediction.
- `<profile>-<dataset>-calls.jsonl`: prompt/feedback, parsed output hoặc raw text
  JSON lỗi, stage và latency của từng lần gọi. Đây là trace chứa nội dung nguồn,
  nên giữ cùng notebook Private.
- `resources.json`: GPU/dtype/quantization; `cost_usd=null` nghĩa là chưa đo.

Human review: kiểm explanation confidence có nhắc đúng bằng chứng/thiếu sót,
không chỉ điền một câu vô nghĩa để qua schema; nhãn contradict/NEI có thể có
confidence cao nếu phân loại đúng. Không coi score 1.0 là chính xác 100%.

## 5. Lệnh tái tạo local

Đã chạy **118/118 test research_rag đạt, 15,519 giây** trên môi trường local
Windows/Python 3.10. Có 13 test mới cho confidence/diagnostic và 1 test notebook
mới. Đây là kiểm logic với backend giả và kiểm đóng gói; không có inference GPU.
CLI `--help` cũng đã kiểm tra, có `--comparison confidence`.

Lượt đầu có 1 lỗi môi trường: Windows sandbox báo `WinError 5 Access is denied`
khi test đổi tên ZIP tạm. Chạy lại đầy đủ ngoài sandbox đạt; không đổi logic
đóng gói để bỏ qua lỗi này. Môi trường còn cảnh báo Requests dependency và
Google AFC; chúng không gây test failure ở lượt chạy lại.
Hash artifact và bằng chứng lệnh: `confidence-step1-validation-20261009.json`.

```powershell
.\.venv\Scripts\python.exe scripts/build_validation_notebook.py
.\.venv\Scripts\python.exe scripts/build_autonomy_notebook.py
.\.venv\Scripts\python.exe scripts/build_confidence_notebook.py
$env:OMP_NUM_THREADS='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
.\.venv\Scripts\python.exe -m unittest discover -s research_rag/tests -q
```

CLI diagnostic, chạy trong workspace trên host có CUDA/model:

```text
python -m research_rag.evaluation.compare_factchecker --comparison confidence --output-dir <THU_MUC_MOI>
```

Thay `<THU_MUC_MOI>` bằng đường dẫn chưa tồn tại. Contract tests dùng backend
giả để kiểm logic. Chúng không chứng minh model thật sẽ sinh explanation hợp lệ.
Rủi ro còn lại: prompt sửa lỗi tăng input/latency; strict validator có thể bộc lộ
thêm output sai kiểu; model vẫn có thể trả reasoning vô nghĩa hoặc lặp lỗi.
