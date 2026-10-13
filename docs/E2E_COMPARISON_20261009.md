# Đối chiếu hai lượt E2E và kế hoạch hoàn thiện — 2026-10-09

## 1. Kết luận có bằng chứng

Lượt mới chạy đúng runtime sửa ngày 2026-10-07, có cải thiện thực tế nhưng chưa
đạt nghiệm thu. Gate tự động tăng từ **2/8 lên 3/8**; `overall_pass=false`.
Không diễn giải 3/8 là tỷ lệ hoàn thành dự án hoặc độ chính xác tổng quát.

- Ca `missing` nay trả lời đúng số lượng, thay vì chỉ dẫn sang phụ lục.
- Ca `conflict` ghi nhận nguồn phản bác và không công bố claim tranh chấp.
  Tuy nhiên lượt đó vẫn kết thúc bằng `factchecker_failed`, nên không được coi
  là bằng chứng toàn bộ đường xử lý mâu thuẫn đã vận hành ổn định.
- Ca `budget` tiếp tục dừng đúng giới hạn.
- Nút thắt chính: confidence output thiếu giải thích; Reader bị HTTP 503;
  Summarizer nhầm baseline với phương pháp chính ở `heldout_3`.

## 2. Kiểm tra artifact

- ZIP mới: `C:/Users/dellcuatri142/Downloads/rag-validation-20261009T103057Z.zip`.
- SHA256: `7edebdadde2dba6076de407214abada845821047a8bf5de64c634811114f6016`.
- **80/80 file** trong output manifest đúng kích thước và SHA256. Tổng 81 entry
  gồm manifest; không giải mã/nạp các index pickle.
- Bản sao nguyên byte: `research-runs/kaggle-20261009T103057Z/`.
- `criteria.json`, `cases.json`, `frozen-manifest.json` giống byte lượt 2026-10-02.
- 10 module runtime sửa ngày 07/10 và file regression mới đều khớp hash đã lưu
  trong audit 07/10, khớp `run-manifest.json` mới và source local.
- Re-score offline tái tạo đúng **8/8 case results và summary**. Không gọi model.
- Kaggle ghi **99 contract tests đạt**, 7,852 giây; không nhầm với 104 test local
  ngày 07/10. Năm test đóng gói notebook local không nằm trong bộ test đưa lên host.
- Hai Tesla T4, PyTorch 2.10.0+cu128; stage E2E mới mất 1.232,188 giây
  (~20 phút 32 giây), lượt cũ 1.283,429 giây (~21 phút 23 giây).
  Đây không phải benchmark tốc độ công bằng vì đường chạy và kết quả khác nhau.
- Stage mới có exit 1 do `automated_gates_failed`; suite vẫn đã ghi đủ tám ca
  và summary. Không phải exception làm chương trình chết giữa chừng.
- Trace mới ghi 116 backend calls: generator 16, critic 16, Fact-checker 82,
  Writer 2. Chưa bao gồm đầy đủ API calls của Reader; token/cost tổng vẫn `null`.

## 3. Đối chiếu từng ca

| Ca | 02/10 | 09/10 | Kết luận từ trace mới |
|---|---|---|---|
| sufficient | Trượt: hết search budget | Trượt: confidence_failed | Draft đã sửa từ `42` thành câu đầy đủ. Judge chấm support nhưng phần giải thích confidence rỗng. |
| missing | Đạt tự động, câu trả lời chưa đủ | Đạt, có câu trả lời đúng nguồn | Ba search, tám bước; báo cáo `Forty-two participants were enrolled in Orion.`, trích `missing:1`. |
| conflict | Trượt, không gọi Fact-checker | Đạt gate chống công bố claim mâu thuẫn | Quan sát cả 42 và 71; nhãn contradict trên `conflict:1`; verified_claims rỗng. Vẫn có confidence_failed trên nguồn support. |
| pdf_pages | Reader RuntimeError, mất diagnostics | ReaderBatchError với HTTP 503 | Trang 0, tool alt_segmentation, stage critique, ServerError. Chưa tới trang cuối. |
| budget | Đạt | Đạt | Một search, một bước, step_budget_exhausted; không model call tiếp. |
| heldout_1 | confidence_failed | confidence_failed | Có support trên span đúng, nhưng review full chunk bị thiếu giải thích confidence. |
| heldout_2 | Nguồn support bị bỏ qua, hết search | confidence_failed | Full chunk có thể được xét sau sửa; hai review confidence lỗi khiến claim vẫn bị chặn dù nguồn khác đạt. |
| heldout_3 | confidence_failed | Hết search, không tới Fact-checker | Các summary đầu không trả lời cách huấn luyện; summary cuối lấy thông tin MTL-LSTM baseline và sửa câu evidence. Verbatim gate chặn. |

Ca `missing` còn một câu limitations chung “The available claims may not fully
answer the intent.” dù status completed; nên sửa độ nhất quán thông báo sau khi
giải quyết các lỗi chặn. Đây không phủ nhận câu trả lời 42 khớp nguồn hiện có.

Ba policy adaptive/BM25/dense tiếp tục hòa union recall=1.0 trên ba câu hỏi
paper-scoped. Không có bằng chứng adaptive tốt hơn, hoặc retrieval toàn kho đạt 100%.

## 4. Root cause và mức chắc chắn

### A. Confidence — đã tái hiện lỗi validator

Output điển hình trong `results/generations.jsonl`:

```json
{"confidence_score":1.0,"reasoning":""}
```

`04_factchecker/inference/confidence.py:53` yêu cầu reasoning không rỗng.
Replay output đã lưu qua ConfidenceEstimator trả đúng lỗi
`Confidence reasoning must not be empty`. Đây là JSON hợp lệ; không phải lỗi parse JSON.

Có 15 output như vậy trong 35 lần sinh confidence: 5 review lỗi, mỗi review
thử 3 lần, thuộc sufficient/conflict/heldout_1/heldout_2. Các output này chỉ dài
14 token với giới hạn 192; tăng max_new_tokens không giải quyết triệu chứng đã thấy.
`_retry` gọi lại cùng lambda, prompt không đổi; backend dùng `do_sample=False`.
Trace xác nhận cả ba lần lặp cùng output rỗng.

Tất cả 35 score được sinh ở lượt này chỉ là 0 hoặc 1; có review contradict với
score 0 nhưng explanation nói 0.99. Vì vậy sửa schema thành công vẫn chưa chứng
minh confidence được calibration hay phản ánh đúng độ chắc chắn của nhãn.
Không chuyển nhãn support thành score 1 bằng luật để làm gate đạt.

### B. Reader — biết điểm lỗi, chưa biết căn nguyên phía dịch vụ

`results/pdf_pages/state.json` ghi:

```text
page_no=0
stage=critique
tool=alt_segmentation
error_type=ServerError
http_status=503
```

Không có bằng chứng API key sai hoặc PDF hỏng. Theo
[hướng dẫn Gemini chính thức](https://ai.google.dev/gemini-api/docs/troubleshooting),
503 UNAVAILABLE là một trường hợp có thể retry với backoff; không bảo đảm lần sau
sẽ thành công. Repo đã cấu hình SDK tối đa 3 attempts, initial_delay=1s,
max_delay=4s, gồm HTTP 503. Trace hiện không ghi từng transport attempt, nên
không suy ra chính xác đã có bao nhiêu HTTP request từ một page_trial.

### C. heldout_3 — nhầm phương pháp và câu evidence không nguyên văn

Gold document được đánh dấu là `qasper:1909.01720:paragraph:11`; nó có trong
seen_chunks ngay search đầu. Vì vậy “retrieval không lấy được gold” không giải
thích đầy đủ lỗi. Gold đoạn này mô tả joint training stance detection và fake
news detection; mức độ đủ để trả lời câu hỏi “how trained” cần người rà nhãn.

Summary cuối dựa vào paragraph:41 nói về baseline **MTL-LSTM**, với ba nhiệm vụ
veracity classification, rumor detection, stance detection. Nó không phải bằng
chứng về phương pháp selected sharing layer đang được hỏi. Span sinh ra còn bỏ
`MTL-LSTM` và `BIBREF14`, nên không có nguyên văn trong nguồn. Critic vẫn chấm
supported nhưng graph chặn tại `no_verbatim_evidence` — giữ được cơ chế bảo vệ.

Không nới sang fuzzy matching để làm ca này đạt: có cả vấn đề diễn giải sai nguồn.
Không tự sửa gold labels theo prediction; nếu rà nhãn phát hiện sai/thiếu, ghi
adjudication và tạo phiên bản benchmark mới, giữ kết quả cũ.

## 5. Kế hoạch thực hiện theo thứ tự

### Bước 1 — sửa và đánh giá riêng contract confidence

Phạm vi: `04_factchecker/inference/confidence.py`, `04_factchecker/node.py`,
`04_factchecker/prompts.py` và test liên quan.

1. Tạo regression từ dạng output rỗng đã quan sát; thêm malformed JSON,
   score ngoài khoảng/không hợp lệ, reasoning rỗng và output hợp lệ.
2. Đưa lỗi validation và output trước vào yêu cầu sửa ở lần retry, vẫn giới hạn
   tổng số attempts. Tránh nhân hai vòng retry 3×3 hoặc gọi lại prompt y hệt.
3. Thử prompt yêu cầu rõ reasoning không rỗng, diễn giải confidence của **nhãn**.
   Repo đã có `LABEL_CONFIDENCE_SYSTEM_PROMPT` thử nghiệm, chưa được chứng minh
   tốt hơn. Khi đo riêng tác động confidence, giữ judge không đổi.
4. So trước/sau trên dev/contracts và các failure đã ghi nhận; báo cả tỷ lệ lỗi
   schema, label metrics, false support, accepted support precision/coverage,
   số model calls và latency. Bộ đã xem là development/regression.
5. Không tăng score mặc định, bỏ trạng thái lỗi hoặc giảm threshold để pass.

Điều kiện qua bước: toàn bộ regression contract trả đúng hành vi; lượt model
thật trên tập diagnostic đã chốt không còn lỗi schema bắt buộc; quality gate đã
chốt không suy giảm. Confidence vẫn phải ghi là uncalibrated đến khi được đánh giá riêng.

### Bước 2 — kiểm tra Reader độc lập và xử lý lỗi API có giới hạn

Phạm vi: `train_agent2_reader/reader_policy.py`, `reader_agent.py`,
`research_rag/adapters.py` nếu cần.

1. Ghi model ID thực sự dùng và kết quả một lời gọi critique, không ghi API key.
2. Thử riêng trang 0 của extra-pages.pdf; giữ page_trials, HTTP status và timing.
3. Thiết kế backoff/jitter có trần thời gian/attempts, tính cả retry SDK và
   retry tầng ngoài. Tăng thời gian chờ hợp lý không được biến thành retry vô hạn.
4. Nếu vẫn unavailable, báo lỗi phụ thuộc bên ngoài. Không tự đánh dấu trang
   accepted; không đổi model âm thầm. Nếu dùng model khác, ghi cấu hình và đánh giá lại.
5. Chạy reader_smoke rồi PDF thật; sau đó kiểm đúng hai batch và evidence trang
   cuối trong ca E2E. Reader.read smoke đọc mọi trang, chưa chứng minh graph biết
   yêu cầu đọc thêm trang — đó là tiêu chí riêng của ca pdf_pages.

Điều kiện qua bước: extraction có span đúng trang, không lỗi API trong lượt đánh
giá đã định trước, lỗi 503 kéo dài vẫn dừng rõ ràng và giữ trace. Một lượt thành
công không phải SLA khả dụng; báo cả những lần thất bại đã quan sát.

### Bước 3 — sửa chọn bằng chứng và câu trả lời của Summarizer

Phạm vi: `train_agent3_summarizer/node.py`, generator/critic prompts,
`research_rag/graph.py` phần xây context; retrieval chỉ sửa khi có bằng chứng cần.

1. Rà câu hỏi/gold cùng nguồn độc lập; phân biệt “cấu trúc layer” với “cách huấn luyện”.
2. Theo dõi source ID, section và đoạn context thực sự đưa vào mỗi summary.
3. Phân biệt proposed method với baseline/related work; yêu cầu chọn evidence
   hỗ trợ trực tiếp câu hỏi, không chỉ cùng chủ đề.
4. Khi span không nguyên văn, cho một lần sửa có thông báo lỗi trên context hiện
   có trong ngân sách đã chốt. Không mặc định search thêm cho lỗi định dạng trích dẫn.
5. Giữ nguyên kiểm tra verbatim và Fact-checker. Nếu context chưa đủ, trả thiếu
   thông tin thay vì đưa thông tin của baseline thành phương pháp chính.
6. Đo trên nhiều ca cùng loại, không hard-code paper ID hoặc đáp án của heldout_3.

Điều kiện qua bước: câu trả lời đúng phương pháp và đúng câu hỏi; mọi citation
khớp nguồn; test đối kháng proposed method/baseline không công bố claim sai.

### Bước 4 — sửa thông báo rồi chạy lại toàn bộ regression

1. Với mâu thuẫn đã kiểm chứng, biểu diễn rõ conflict và nguồn liên quan trong
   kết quả/limitations. Giữ riêng lỗi backend; không đổi tên factchecker_failed
   thành success để đạt gate.
2. Loại bỏ limitations chung mâu thuẫn với trạng thái completed khi coverage
   đã được đánh giá; vẫn giữ cảnh báo khi coverage thật sự chưa đủ.
3. Chạy test local, dựng lại notebook bằng hai script build, kiểm hash payload.
4. Chạy cả tám ca ở run directory mới. Gate đã chốt vẫn yêu cầu tám ca + safety
   + policy + human review; không lấy mỗi ca đạt tốt nhất từ các run khác nhau.
5. Đọc claim/citation thủ công, không dựa vào exit code hoặc summary duy nhất.

Lệnh local sau khi triển khai các sửa ở bước 1–3:

```powershell
.\.venv\Scripts\python.exe scripts/build_validation_notebook.py
.\.venv\Scripts\python.exe scripts/build_autonomy_notebook.py
$env:OMP_NUM_THREADS='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
.\.venv\Scripts\python.exe -m unittest discover -s research_rag/tests -q
```

Các script diagnostic có sẵn, chạy bằng Python của môi trường serving trên
host GPU, với working directory là workspace và credential qua environment:

```text
python -m research_rag.evaluation.compare_factchecker --output-dir <THU_MUC_MOI>
python -m research_rag.evaluation.reader_smoke
python -m research_rag.evaluation.reader_smoke --manifest research_rag/evaluation/reader_real_manifest.jsonl
```

`<THU_MUC_MOI>` là placeholder phải thay bằng đường dẫn mới. compare_factchecker
hiện so **hai profile thay cả judge và confidence**, tổng 84 predictions
(30 dev + 12 contracts × 2). Không dùng nó để kết luận riêng tác động của
confidence nếu chưa thêm thí nghiệm giữ judge cố định. Nó cũng không tự promote prompt.

### Bước 5 — đánh giá cuối và baseline để bảo vệ đồ án

1. Khóa code/model/prompt/ngân sách trước final test; tạo tập chưa dùng sửa lỗi.
   Gợi ý pilot 20–30 câu để bắt đầu, không phải chuẩn đủ cho production.
2. Bao phủ đủ bằng chứng, thiếu bằng chứng, mâu thuẫn, PDF đọc thêm trang/scan,
   so sánh hai phương pháp, không có đáp án và hết ngân sách.
3. Reviewer độc lập rà đáp án, độ đầy đủ và citations; kiểm trùng dữ liệu theo
   claim/paper. Tách development/calibration/final. Bộ tám ca hiện tại là regression.
4. So workflow cố định với controller trên cùng model/corpus/budgets. So BM25,
   dense và adaptive riêng. Công bố cả lỗi và từ chối, không chỉ các answer thành công.
5. Chốt rubric/ngưỡng chất lượng trước inference; báo latency/calls, token/cost
   nếu đo được. Không dùng confidence 1.0 làm bằng chứng độ chính xác 100%.

### Bước 6 — đóng gói đồ án

- README chạy lại được; phiên bản model/dependency/data và cấu hình không chứa secret.
- Sơ đồ năm agent + controller; quyền thực thi/đề xuất; schema state/evidence;
  planner theo code, LangGraph điều khiển graph/checkpoint.
- Bảng so sánh hai lượt hiện có và final evaluation; error analysis, limitations.
- Demo thành công, tìm thêm, mâu thuẫn, hết ngân sách; có trace và output lưu sẵn
  từ lượt thật để minh họa khi API không khả dụng, ghi rõ đó là replay.
- Báo cáo và slide: vấn đề, dữ liệu, phương pháp, thuật toán/tool, thực nghiệm,
  đánh đổi và phần chưa hoàn thiện.

Tiêu chí hoàn thành đồ án phụ thuộc rubric giảng viên; không bắt buộc dựng thêm
API/UI nếu scope không yêu cầu. Production deployment cần scope riêng về
authentication, concurrent jobs, monitoring và vận hành dữ liệu.

## 6. Công việc đã làm ở lượt rà soát này

Đã xác minh/giữ nguyên artifact, đối chiếu code hash, tái hiện lỗi validator,
re-score offline và lập kế hoạch. Không sửa runtime/notebook, không chạy model
mới; không ghi nhận đây là independent human review. Bản notebook 07/10 vẫn còn
các vấn đề nêu trên, nên chưa có cơ sở chạy nguyên bản nhiều lần để mong đạt 8/8.
