# Trạng thái xác minh Kaggle (cập nhật 2026-09-27)

Tài liệu này phân biệt kết quả đã quan sát với gate còn thiếu. Lệnh và điều kiện đạt nằm trong `KAGGLE_GPU_RUNBOOK.md`.

## Mới nhất: Reader API chạy được, phát hiện lỗi mất nội dung PDF

Phiên ngày 2026-09-27 dùng **CPU, CUDA=false, 0 GPU**. Đã lưu **Version 6**, chọn **Quick Save / Save output for this version**; UI báo **Quick version complete**, rồi **Session stopped / off (run a cell to start)**. Không còn job đang chạy tại thời điểm quan sát. Chưa có kết quả Fact-Checker A/B mới.

Môi trường Reader lần này: google-genai 2.22.0, PyMuPDF 1.27.2.3, pytesseract 0.3.13, langgraph 1.2.12, pydantic 2.13.5, transformers **5.0.0**, torch **2.10.0+cpu**. Đây không phải venv serving đã pin transformers 5.16.1. Secret chỉ được lấy từ Kaggle Secrets, không ghi giá trị vào kết quả.

| Kết quả trực tiếp | Quan sát | Kết luận |
| --- | --- | --- |
| `reader-endpoint-20260927.json` | `gemini-3.8-flash` generate nhỏ thành công, 4.111,04 ms, 75 token | Xác thực và endpoint generate được. |
| `reader-live-20260927.json` | 3.8: 2/3 PDF hoàn tất, 7/7 span đã chấm; scan lỗi 429; 51.969,15 ms | **Fail**, không suy diễn loại quota khi response chưa đủ thông tin. |
| `reader-paced-20260927.json` | 3.8, cách request tối thiểu 61 giây: 2/3 PDF hoàn tất, 5/5 span đã chấm; two-column lỗi 503; 190.655,95 ms | **Fail**. Không gộp với lần khác. |
| `reader-lite-20260927.json` | 3.5-flash-lite, cách request tối thiểu 61 giây: **3/3 PDF, 9/9 span, exit 0**; 184.094,76 ms; 2.080 token | **Smoke pass trong một lần chạy**. Bốn trang qua API; scan dùng Tesseract (18 block). Không phải SLA hay đánh giá PDF đại diện. |
| `reader-external-20260927.json` | 3.5-flash-lite, PDF QASPER gốc: **6/9 span**, token recall 0,805556, 306.237,13 ms; cả 6 API calls thành công, 3.447 token | **Quality fail**, mặc dù critic chấp nhận ba trang. |

Latency các lần có pacing bao gồm thời gian chờ chủ động, không phải latency inference thuần. Usage được ghi khi API trả về; không suy ra token cho call lỗi hoặc billing từ đó. `billing_cost_usd` chưa đo. Model được chọn bằng env trong harness, không tự đổi default serving.

PDF thật: [Dasigi et al., 2021](https://aclanthology.org/2021.naacl-main.365/), 524.772 bytes, SHA-256 `b15b4378988ed4e553dd312eaf334411abcf1fb28c53b846d360435eb55cd193`. Chọn trước trang 0/3/8 và 9 span sau khi xem ảnh Poppler, lưu `reader_real_manifest.jsonl`. Nhãn do trợ lý chép trước inference; chưa có adjudication độc lập, không gọi là benchmark human-labelled cuối. PDF 12 trang nhưng lần này chỉ chấm ba trang đã chọn.

### Root cause và sửa local

Audit không gọi API bằng checkpoint LayoutLMv3 thật (`reader-layout-audit-20260927.json`) cho thấy trang 0: **135 dòng → 55 block**; trang 3: **128 → 88**; trang 8: **127 → 100**. Processor cũ bật truncation 512 token và chỉ đọc batch 0, làm mất các dòng cuối. Scorer còn chưa chuẩn hóa ligature `ﬁ`.

- `train_agent2_reader/tools/tool_layoutlmv3.py`: xử lý toàn bộ overflow windows, stride 64, loại trùng theo ID dòng gốc trong từng trang, kiểm không mất dòng; inference mỗi window để giới hạn bộ nhớ.
- `train_agent2_reader/reader_policy.py`: pacing tùy chọn bằng `GEMINI_REQUEST_INTERVAL_SECONDS`, dùng chung router/critic trong một process; giữ timeout/retry có giới hạn.
- `research_rag/evaluation/reader_smoke.py`: chuẩn hóa Unicode NFKC khi chấm span; xác minh SHA-256 PDF khi manifest có khai báo. Không đổi nhãn để nâng điểm.

Test local: 1 regression overflow + 7 scorer pass; 5 test retry/pacing pass. **Bản sửa overflow, scorer và pacing chưa được chạy lại trên Kaggle với model thật.** Chưa tuyên bố Reader đạt gate chất lượng. Pacing 61 giây đã được dùng trong harness thực tế, nhưng implementation mới trong module chỉ được unit test.

Kaggle đã tạo `reader-validation-20260927.zip`: **21 payload, 21.404 bytes**, SHA-256 `bb7730fedd7e0c65a37b90eb40686c455ee9e08ce3a5c36fd78b0e9fed3eec9c`. Gồm kết quả, page/API diagnostics, scripts và manifest; nằm trong Output Version 6. Sau lần tải đầu timeout, đã tải thành công từ [Output Version 6](https://www.kaggle.com/code/trcng23/research-rag-gpu-validation/output?scriptVersionId=353191638&select=reader-validation-20260927.zip), đối chiếu hash ZIP và đủ **21 payload**, giữ bản sao/giải nén tại `kaggle_transfer/reader-validation-20260927/` trên Windows. Xác nhận download này xảy ra sau khi đóng gói bản cập nhật 3,91 MB; ZIP cập nhật giữ nguyên hash đã đề nghị phê duyệt.

### Dữ liệu và gate còn lại

QASPER đã chuẩn bị riêng 18.587 paragraph, **393 dev / 417 test candidate chưa chấm**, loại 29 paper đã dùng trong Writer. BM25 trên đủ dev: hit@5 **0,279898**, paragraph recall@5 **0,159664**. Chưa dựng FAISS QASPER hoặc chạy graph trên corpus này. Test candidate chưa được chứng minh độc lập toàn graph do provenance Summarizer chưa đầy đủ.

Nguồn QASPER công bố CC BY 4.0; đã giữ attribution và manifest. Corpus `jamescalam/ai-arxiv-chunked` cũ vẫn chưa được xác minh quyền phân phối, chưa được thay mặc định. Chi tiết ở `FACTCHECKER_NEXT_VALIDATION.md` và `THIRD_PARTY_NOTICES.md`.

Tiếp tục: **(1)** so baseline/coverage của Fact-Checker bằng model thật, **(2)** rerun Reader đã sửa trên cùng nhãn, **(3)** BGE/QASPER dev + tách calibration/final theo provenance, **(4)** quyết định corpus có quyền rõ, **(5)** adverse E2E/citation rồi mới serving/checkpoint. Các phần bên dưới là lịch sử, không thay thế trạng thái mới nhất này.

## Kết quả GPU mới: graph có citation đã chạy qua (2026-09-26)

Sau khi áp dụng 12 file runtime đã xác minh hash, venv serving cài đúng requirements và `pip check` báo không có dependency hỏng. Preflight xác nhận đủ Qwen 7B/1.5B, Fact-Checker merged đúng Qwen 3B, FAISS 41.549 vector × 1024 và ID cùng thứ tự. Hai Tesla T4 cùng hoạt động.

### Chẩn đoán và sửa evidence

Ca hỏi: `How much smaller is DistilBERT than BERT, and how much language understanding performance does it retain?`

- Trước sửa: `distilbert-trace.private.jsonl` có JSON generator/critic hợp lệ; lượt đầu critic chấp nhận nhưng evidence không khớp chuỗi gốc. Đã đối chiếu đúng các ID của lượt truy xuất đầu: nguồn chứa `task-speciﬁc` và xuống dòng, model trả `task-specific` và khoảng trắng. Sau một graph retry vẫn `insufficient_evidence`, 0 verified claim. Graph 157.333,52 ms, Fact-Checker chưa suy luận.
- Sửa `research_rag/graph.py`: đối chiếu chỉ chuẩn hóa whitespace và bảy ligature PDF phổ biến; lấy lại substring nguyên bản từ nguồn bằng offset. Không đổi hoa/thường, dấu câu hoặc số; không fuzzy match. Evidence đưa sang Fact-Checker vẫn nguyên văn. Test regression + integration: **26 test pass**, trong đó 4 regression mới.
- Sau sửa: `distilbert-formatting-result.json` có `status=completed`, `errors=[]`, `low_confidence_warning=false`, retry=0, 1 verified claim. Nội dung: ít hơn 40% tham số và giữ lại 97% khả năng hiểu ngôn ngữ; source `1910.01108::chunk_0`. Đây là nhãn đã qua model, không phải chứng nhận đúng từ con người.
- `distilbert-citation-audit.private.json`: tất cả claim ID resolve được và evidence là substring nguyên văn của nguồn. Writer trace có `generate ok=true`, `critic ok=true`, internal retry=0, không dùng deterministic fallback. Fact-Checker đã suy luận 6 cặp claim–evidence/chunk, tất cả status=ok.
- Giới hạn phát hiện: Fact-Checker gán support cho cả chunk chỉ nói giảm tham số/tăng tốc mà không có phần giữ lại 97%. Do vậy một ca graph thành công không chứng minh kiểm chứng từng claim luôn đúng. Writer cũng ghi limitation về mức độ trả lời đầy đủ intent; critic báo quote consistency, chưa có human semantic review.

| Đo sau sửa | Giá trị |
| --- | --- |
| Graph tổng, không gồm load model ban đầu | 163.219,17 ms |
| Retrieval / Summarizer | 8.943,60 / 51.997,22 ms |
| Fact-Checker / Writer | 72.859,05 / 29.415,49 ms |
| RSS sau graph | 2.670 GiB (không phải peak RSS) |
| Peak CUDA allocated GPU 0 / 1 | 5.979 / 10.136 GiB (không phải toàn bộ VRAM theo nvidia-smi) |
| Token usage / cost | null; backend chưa cung cấp |

Bản graph thực thi được giữ tại Output `validated-runtime/research_rag/graph.py`; sửa này tạo sau dataset runtime 12 file. File local và bản notebook cùng logic, khác một dòng trắng nên SHA-256 khác nhau. Source thực thi SHA-256: `f447b2ca488252d8285b67baf14ecaeb096b55915d5550b3a0c253ce1f173480`.

### Confidence có nhãn và kết thúc session

Đã chạy node thật trên **30 mẫu dev**, chọn 10 dòng đầu mỗi nhãn trong SciFact dev đã loại trùng trước inference. Exit=0, 30/30 status=ok; accuracy **0,600**, macro-F1 **0,59337**, recall contradict **0,400**. ECE (10 bins) **0,402**; Brier **0,400087**. Nhiều dự đoán đúng ở nhãn not_enough_info/contradict vẫn có confidence=0. Đây là bằng chứng score chưa thể diễn giải như xác suất nhãn đúng; chưa đủ để kết luận nguyên nhân chỉ do prompt hay checkpoint. Không sửa ngưỡng 0,7 hoặc tự điền score để nâng metric.

`calibration_ready=true` trong CLI chỉ có nghĩa tất cả dòng có score hợp lệ và status=ok, **không có nghĩa đã calibration tốt**. Tập 30 mẫu có các hàng cùng claim/paper, không phải 30 quan sát độc lập và không đại diện toàn bộ 466 dev. Không so trực tiếp accuracy này với 0,799 trên 468 prediction cũ để kết luận chất lượng tăng/giảm. Chưa fit calibration map, chưa có tập test độc lập. Không chạy tiếp toàn bộ dev chỉ để lặp lại gate đang có lỗi; cần xử lý confidence/partial-support và chuẩn bị split trước.

Đã lưu **Version #4 — Successful**, Quick Save chọn rõ **Save output for this version**. Sau đó chọn Stop session và quan sát **Draft Session off (run a cell to start)**. Không còn job GPU đang chạy tại thời điểm kết thúc lượt này. Các kết quả Reader trước đó được lưu trong Version #3.

Gói `research-rag-validation-20260926.zip` đã tải về Windows: **57.623 bytes**, SHA-256 `191c40a591668e5d32ce3b895bdac4e8281301f7cdf4e5862ce5c9491d719759`. Đã đối chiếu SHA-256 đủ **27 file** và giải nén tại `kaggle_transfer/validation-20260926/` (được `.gitignore` loại trừ). Có raw trace Private, metrics, citation audit, dev predictions, calibration metrics, dependency lock và hai source runtime mới. ZIP không chứa `.env`, credential, checkpoint hoặc toàn bộ corpus; trace có đoạn nguồn nên giữ Private. Bản sao ZIP trong workspace: `kaggle_transfer/research-rag-validation-20260926.zip`.

### Các gate phải làm tiếp theo

1. **Fact-Checker/confidence:** phân tích false support cho claim ghép và score=0 trên nhãn đúng; sửa prompt/training/calibration trên tập dành cho phát triển, giữ nguyên nhãn gốc và lưu baseline. Tách tập calibration và final test theo claim/paper, chưa dùng final test để chọn ngưỡng. Sau sửa, chạy toàn bộ contract và đo coverage/failure, precision/recall từng nhãn, ECE/Brier; không chỉ accuracy.
2. **Reader API:** gate vẫn fail vì 503 với gemini-3.6-flash và 404 với lần thử gemini-2.5-flash. Retry giới hạn đã thêm; cần một lần chạy đủ ba fixture qua API ổn định, sau đó PDF thật có nhãn trang/layout/scan. Không ghép các PDF pass rải rác thành một lần pass giả.
3. **Dữ liệu giữ lại:** qrels hiện là 10 câu pilot, PDF hiện là ba fixture tự tạo. Cần câu hỏi độc lập, nhãn các chunk liên quan và PDF đại diện được người đánh giá kiểm tra. Không gọi nhãn tự sinh từ output model là ground truth độc lập.
4. **Quyền corpus:** vẫn chưa có bằng chứng quyền phân phối corpus/index. Hoàn tất xác nhận quyền hoặc chọn nguồn có license rõ rồi xây lại corpus/index/qrels. Mẫu thư trong `THIRD_PARTY_NOTICES.md` chưa gửi; không tự gửi thay chủ tài khoản.
5. **Gate cuối:** chạy model thật trên nhiều claim, thiếu evidence, nguồn mâu thuẫn, lỗi OCR/API và retry hết budget; human review citation/answer, đo latency p95 và usage/cost. Chỉ sau khi đạt các gate mới thêm checkpoint bền vững/API serving theo phạm vi đã thống nhất.

Các mục dưới đây là lịch sử; thông tin chưa chạy GPU/Writer ở phiên cũ không còn là trạng thái mới nhất.

## Tiếp tục ngày 2026-09-26: runtime đã đồng bộ, Reader API có lỗi dịch vụ

Sau xác nhận cụ thể của chủ tài khoản, đã tạo dataset **Private** `trcng23/research-rag-runtime-diagnostics` và Add Input thành công. Trang dataset có 13 file, gồm 12 payload + manifest; notebook báo dataset sẵn sàng. Cell overlay xác nhận `updated_files=12`, `all_hashes_verified=true`, kiểm cả hash bản nguồn rồi sao chép sang `/tmp/research-rag-workspace-diagnostics`. Gói ZIP gốc không thay đổi.

Đã chạy Reader thật trên CPU với Secret, PyMuPDF và Tesseract. Kết quả đọc trực tiếp từ output notebook (chưa tải file gốc về Windows):

| Lần chạy | SDK / cấu hình | Kết quả |
| --- | --- | --- |
| `reader-api-result.json` | google-genai 1.68.0, gemini-3.6-flash | 23.073,50 ms; scan khớp 2/2 span; simple_text và two_columns_table lỗi HTTP 503; **passed=false**. |
| `reader-api-retry-result.json` | google-genai 2.22.0, gemini-3.6-flash, timeout 30 giây/request, tối đa 3 attempts | 31.139,09 ms; two_columns_table khớp 4/4 span; simple_text và scan lỗi HTTP 503; **passed=false**. Dùng scorer mới từ overlay. |
| `reader-api-flash25-result.json` | Cùng SDK/retry, gemini-2.5-flash | 1.504,78 ms; cả ba PDF lỗi HTTP 404 khi generate; **passed=false**. Model đã xuất hiện trong models.list nhưng điều đó không bảo đảm generate dùng được. Không đổi mặc định sang model này. |

Các file `*-pages.json` giữ loại lỗi, mã HTTP và latency từng trang. Không cộng các PDF pass từ nhiều lần chạy để gọi một lần đánh giá đầy đủ là pass. API đã được gọi thật; gate Reader vẫn chưa đạt. HTTP 503 là lỗi từ dịch vụ; timeout browser và lỗi key không giải thích kết quả này.

Sửa local `train_agent2_reader/reader_policy.py`: dùng retry sẵn của google-genai, timeout 30.000 ms, tối đa 3 attempts cho 408/429/500/502/503/504. Test HTTP giả lập thật qua SDK: 503→200 phục hồi, 503 kéo dài dừng sau 3 lần, 401 không retry; **3 test pass**. Reader smoke + graph integration: **27 test pass**. Các test không gọi API mạng. Hai lần chạy SDK 2.22.0 trên Kaggle dùng cấu hình client tương đương trong cell; bản sửa reader_policy mới chưa nằm trong ZIP 12 file đã upload. Retry giới hạn không bảo đảm khắc phục một dịch vụ đang lỗi.

Tham khảo xử lý lỗi: [Gemini troubleshooting](https://ai.google.dev/gemini-api/docs/troubleshooting). Không tự bật billing hoặc mua quota để xử lý lỗi.

Đã lưu **Version #3 — Successful** bằng Quick Save kèm Output sau các lần Reader/overlay; sau đó dừng session CPU và quan sát `Session stopped`. Tiếp tục bật T4 x2 với xác nhận dùng quota miễn phí đã có; Kaggle báo còn 27 giờ. Host mới xác nhận hai Tesla T4, torch 2.10.0+cu128 và 29,64 GiB RAM khả dụng. Overlay tiếp tục kiểm đủ 12 hash trên GPU. Đang tạo lại venv serving; chưa có kết quả trace GPU mới tại thời điểm ghi nhận này. Cần lưu Output và Stop session sau khi hoàn tất inference; không coi lần dừng CPU là bằng chứng session GPU mới đã tắt.

## Lịch sử Version 2: Secret/API preflight

Ngày 2026-09-26, đã quan sát trực tiếp output notebook:

- `UserSecretsClient().get_secret('GEMINI_API_KEY')` thành công; output chỉ có `secret_available: true`, không chứa giá trị key.
- `google.genai.Client.models.list()` thành công, danh sách trả về có `models/gemini-3.6-flash` đúng cấu hình Reader. Đây là kiểm tra xác thực/liệt kê model, **chưa phải inference hoặc Reader pass**.
- Kernel Kaggle dùng `google-genai==1.68.0`, khác bản pin serving `2.22.0`. Venv `/tmp/research-rag-serving` không còn trong session mới. Đã cài PyMuPDF 1.27.2.3 thành công; pytesseract 0.3.13 và Tesseract binary có sẵn.
- Đã thêm cell chạy Reader với timeout 240 giây và ghi latency/lỗi từng trang, nhưng **chưa thực thi**. Cell trong Version 2 còn import `research_rag.evaluation.reader_smoke`, trong khi workspace v2 không có module này: phải lấy `score` từ script thuộc dataset fixture bằng `runpy.run_path` trước khi chạy. Cell độc lập đã sửa nằm tại `docs/KAGGLE_READER_CELL.py` ở máy local.
- **Version #2 — Successful**, lưu bằng Quick Save với tùy chọn **Save output for this version**. Sau đó đã chọn Stop session và quan sát **Session stopped / Draft Session off**. Bản Version 1 vẫn là nơi lưu kết quả inference GPU trước đó. Chưa tải bản gốc Output của Version 2 về Windows.
- Sau khi dừng, công cụ browser tiếp tục timeout khi mở Settings và mở tab mới; chưa đổi sang CPU, chưa chạy Reader. Không suy ra model/API lỗi từ lỗi điều khiển trình duyệt.

Gói `runtime-update-20260926.zip` chưa tạo thành dataset. Auto-review từ chối thao tác upload mới vì cần xác nhận cụ thể payload code/dev-data và nơi nhận Kaggle Private; câu hỏi xác nhận đang chờ trả lời. Không dùng notebook hoặc một đường upload khác để lách yêu cầu này. Gói ZIP và hash bên dưới giữ nguyên.

Các phần sau ghi lại kết quả của những phiên trước; thông tin Secret trống và session chưa rõ trạng thái ở cuối lịch sử đã được thay thế bằng cập nhật này.

| Gate | Bằng chứng hiện có | Trạng thái |
| --- | --- | --- |
| Chuyển workspace | Dataset `trcng23/research-rag-five-agents-workspace` đã tạo ở chế độ **Private**; Data Explorer hiển thị 195 file, 7,57 GB giải nén và các thư mục gốc cần thiết. ZIP nguồn đã kiểm SHA-256 đầy đủ 194 file tại máy Windows; `.env` không nằm trong ZIP. | **Đạt với gói v2.** Ngày 2026-09-26 đã đọc được output lưu trong notebook: `Directory verified: 194 files; hashes_checked=True`. Cell kiểm đủ tám đường dẫn gốc, không có `.env`, và kết thúc với `Verified workspace: /kaggle/input/datasets/trcng23/research-rag-five-agents-workspace`. |
| Bộ fixture đánh giá | Dataset `trcng23/research-rag-evaluation-fixtures` đã tạo **Private**, 10 file. | Có 10 câu pilot với một chunk dương tính xác nhận cho mỗi câu và ba PDF tự tạo; chưa có qrels giữ lại, nhãn đầy đủ hoặc PDF đại diện có nhãn. |
| Môi trường GPU và model | Ngày 2026-09-26 đã bật T4 x2 sau xác nhận dùng quota miễn phí; Kaggle lúc bật báo 30 giờ còn lại. Python 3.12.13, torch 2.10.0+cu128, CUDA=True, mỗi GPU 14,56 GiB, RAM 31,35 GiB. Venv serving riêng: `pip check` không có dependency hỏng. BGE/Qwen 7B/Qwen 1.5B đã tải đủ và preflight xác nhận đủ shard, Fact-Checker merged đúng base 3B. | Hai Summarizer 7B và Fact-Checker 3B đã nạp cùng nhau ở 4-bit. Writer chưa được nạp vì chưa có verified claim. Chưa đạt gate nạp toàn bộ model. |
| Reader fixture trên Kaggle CPU | PyMuPDF trích đúng 7/7 span của hai PDF văn bản. PDF scan không có text layer; Tesseract đọc được 2/2 cụm từ mong đợi. | Đây là kiểm tra trích xuất trực tiếp. Chưa chạy Reader đầy đủ với Gemini API, chưa kiểm thứ tự đọc/bảng trên PDF đại diện. |
| Dense retrieval | Kaggle GPU: BGE thật + FAISS 41.549 vector, 1024 chiều, ID khớp; năm kết quả đều `dense`, warning=null. Cold 19.799,92 ms gồm tải artifact/encoder; warm 45,13 ms. Pilot 10 câu: BM25 hit@5=0,7; dense=0,8; policy=0,8; cả ba không fallback. | Đường chạy dense **đạt**. Đây là pilot một positive/câu, chưa có recall@k trên qrels giữ lại. |
| Graph/contract | Fact-Checker mặc định Qwen2.5-3B khớp adapter; graph kiểm claim với evidence được chọn và các chunk truy xuất khác, có giới hạn 40 lần gọi. Test mock trước đó: 86 pass; riêng integration ngày 2026-09-25: 21 pass. Lần GPU thật ngày 2026-09-26: exit=0, graph 84.600,18 ms, hai lượt `summary_unverified`, retry=1, `insufficient_evidence`, 0 verified claim, errors=[] và cảnh báo độ tin cậy thấp. | Graph đã chạy với Retrieval/Summarizer thật và từ chối viết khi thiếu evidence. Fact-Checker chỉ được nạp, chưa suy luận; Writer dùng nhánh trả thông báo cố định. **Chưa đạt end to end sinh báo cáo có citation.** |
| Quyền dữ liệu | Dataset nguồn `jamescalam/ai-arxiv-chunked` chưa thấy khai báo license trên trang nguồn. Dataset Kaggle giữ **Private**, license đặt Unknown. | Quyền phân phối corpus và index dẫn xuất **chưa được xác minh**; không công bố Public hoặc chia sẻ rộng. |

## Tiếp tục theo thứ tự

1. Gate chuyển gói v2 đã đạt. Khi khởi động session mới, chạy lại cell thiết lập `root`; kiểm checksum lại nếu đổi version dataset hoặc thay artifact. Hai dataset đã được attach vào notebook. Đối chiếu local ngày 2026-09-26 không thấy thay đổi các file runtime nhỏ `.py`/`.txt`/`.json` đã có trong manifest; script đóng gói hiện nằm tại `scripts/transfer_kaggle.py` thay vì gốc.
2. Môi trường GPU, base weights và preflight đã đạt trong session ngày 2026-09-26. Tiếp tục ghi RSS, peak CUDA, `nvidia-smi` và latency của graph model thật. Venv/cache nằm trong `/tmp`, phải tạo lại khi thay session.
3. Dense và pilot đã chạy. Tạo bộ qrels giữ lại có nhãn đầy đủ trước khi công bố recall@k hoặc so sánh policy. Pilot dùng chung encoder đã warm: mean/p95 ms BM25=263,75/347,29; dense=62,63/198,93; policy=62,58/195,07. Không so cold latency với các số warm này.
4. Chạy Reader fixture qua Tesseract **và** Gemini API bằng Kaggle Secrets; sau đó dùng PDF giữ lại nhiều layout/scan có nhãn. Chạy graph model thật với ca thiếu chứng cứ, nhiều claim, nguồn mâu thuẫn, lỗi API và retry; review citation đến đúng `source_id`, latency và chi phí.

Không tạo Kaggle API token theo quyết định của chủ tài khoản. Không đưa `.env` hoặc giá trị secret vào notebook output, ZIP hay Git. Truy cập notebook bằng trình duyệt đã hoạt động lại ngày 2026-09-26. Auto-review ban đầu từ chối chọn GPU; sau xác nhận rõ ràng của chủ tài khoản, GPU đã bật thành công. Kaggle Secrets chưa có key ở lần quan sát gần nhất; Reader API chờ chủ tài khoản tự thêm và attach `GEMINI_API_KEY`.

`KAGGLE_GPU_RUNBOOK.md` và tài liệu trạng thái này được sửa **sau** khi tạo ZIP chính; bản trong dataset chính có thể cũ hơn. Dùng bản local được liên kết ở đây khi tiếp tục, hoặc chỉ đồng bộ lại tài liệu sau khi xác minh nội dung ZIP/dataset và có quyền truy cập phù hợp.

## Bằng chứng lần chạy GPU đầu tiên

Notebook: <https://www.kaggle.com/code/trcng23/research-rag-gpu-validation/edit>.
Các số dưới đây được đọc trực tiếp từ output notebook và `first-run-metrics.json` hiển thị trong output ngày 2026-09-26. Chưa tải bản gốc file về Windows.

- Câu hỏi: `What does the corpus say about knowledge distillation?`
- `total_ms=84600.18` đo graph sau model load. Số `elapsed_seconds=3128.6` trong cell theo dõi là thời gian từ lúc khởi chạy đến lúc đọc kết quả, **không phải latency inference**.
- Retrieval: 8.002,12 ms ở lượt đầu (5 chunk); 45,17 ms ở lượt retry (10 chunk).
- Summarizer: 41.399,20 ms và 35.142,69 ms. Cả hai lượt chưa đạt contract; chưa lưu raw summary trong lần chạy này nên chưa xác định do critic, JSON hay span không khớp.
- Fact-check node: 0,68/0,63 ms vì bỏ qua model khi summary chưa được hỗ trợ. Writer node: 5,58 ms ở nhánh không có claim đã xác minh.
- RSS sau graph: 2.742.571.008 bytes (~2,55 GiB). Peak PyTorch allocated GPU 0/1: 6.427.351.040 / 10.892.055.552 bytes (~5,99 / 10,14 GiB). Đây không phải peak toàn bộ VRAM và chưa gồm Writer.
- Sau tiến trình kết thúc, `nvidia-smi` hiển thị 3 MiB/GPU và utilization=0%; điều này không đồng nghĩa session Kaggle đã dừng tính quota.
- `token_usage=null`, `estimated_cost=null`; không suy ra chi phí bằng 0 từ hai trường này.

Model revisions đã tải từ repo gốc:

| Model | Revision |
| --- | --- |
| BAAI/bge-large-en-v1.5 | `d4aa6901d3a41ba39fb536a557fa166f842b0e09` |
| Qwen/Qwen2.5-7B-Instruct | `a09a35458c702b33eeacc393d103063234e8bc28` |
| Qwen/Qwen2.5-1.5B-Instruct | `989aa7980e4cf806f80c7fef2b1adb7bc71aa306` |

File đã thấy trong Output của session: `gpu-host.json`, `base-weights.json`, `preflight-gpu.json`, `requirements-serving-kaggle.lock.txt`, `dense-probe.json`, `retrieval-pilot-metrics.json`, `first-run-metrics.json`, `first-run-result.json`, `first-run-stderr.log`.

Local ngày 2026-09-26: sửa `research_rag/evaluation/reader_smoke.py` để thiếu PDF/span hoặc lỗi API trả exit 1, và tránh khớp một phần từ; 5 regression test pass. Đã kiểm cú pháp 11 cell Python trong runbook cùng các chương trình con; đây không phải chạy toàn bộ runbook bằng model.

## Điểm dừng phiên làm việc

Ngày 2026-09-26 đã phục hồi thao tác bằng tab editor mới: **Save Version → Quick Save → Advanced Settings → Save output for this version → Save**. Kaggle hiển thị **Version #1 — Successful**. Trang notebook đã lưu hiển thị **Private**; tab Output có các file metrics, result, lock, preflight và log kể trên. Đã chọn **Stop session** và nhận thông báo **Session stopped**. Bước lưu Output và dừng GPU đã được xác nhận, thay cho trạng thái chưa rõ trước đó. Đã bấm Download output nhưng chưa xác nhận file tải về Windows, vì vậy bản gốc được xác nhận hiện nằm trong Version #1 trên Kaggle.

Ca chẩn đoán DistilBERT **chưa được gửi/chạy**. Notebook có thêm một cell trống sau cell đầu do lần thử trước. Công cụ trình duyệt vẫn timeout gián đoạn. Đây là lỗi điều khiển trình duyệt, không phải bằng chứng model hoặc CUDA bị lỗi.

Code local mới: `--trace-output` ghi raw generator/critic và state cuối vào JSONL riêng khi bật; `summary_diagnostics` giải thích nhánh từ chối. `04_factchecker/eval_factchecker.py --runtime-contract` thu score từ đúng node serving, không dùng fallback score khi runtime lỗi. Các sửa đổi này **chưa được đồng bộ vào dataset v2 hoặc kiểm bằng GPU**. Local: 31 test trace/integration/Reader pass, thêm 2 test thu confidence pass. Không tính các mock test này là inference model thật.

Audit dữ liệu: 1.312 train / 468 dev, 2 cặp claim/context trùng sau chuẩn hóa, 181 doc ID dùng chung. Đã giữ nguyên bản gốc và tạo `research_rag/evaluation/scifact_dev_deduplicated.jsonl` gồm 466 dòng; fingerprint và quy tắc loại trùng tại `factchecker_split_audit.json`. Đây vẫn là dev, chưa phải final test độc lập. Calibration chưa chạy. Quyền corpus đã kiểm lại nguồn và ví dụ DistilBERT, vẫn chưa có đủ bằng chứng cho phép tái phân phối; xem `THIRD_PARTY_NOTICES.md`.

Gói đồng bộ nhỏ: `kaggle_transfer/runtime-update-20260926.zip`, 244.446 bytes, 12 file + manifest, SHA-256 `3ef4dde8ba0ce21583ed304a20ad4624469acb5af0541d73f3e2b255b682cc45`. Đã kiểm hash tất cả file. Hướng dẫn áp dụng vào bản sao workspace trong `/tmp`: `KAGGLE_RUNTIME_UPDATE.md`. File đã được chọn và upload vào form tạo dataset mới, Visibility=Private; tiêu đề chưa nhập thành công do công cụ điều khiển lỗi, **chưa tạo dataset** và chưa Add Input. Không nhầm file trong form upload với dataset đã xuất bản.

Kaggle Secrets: đã mở Add-ons → Secrets → Add secret và điền LABEL=`GEMINI_API_KEY`; VALUE trống, Save disabled. Chủ tài khoản cần tự nhập/lưu credential theo quy tắc của công cụ computer-use, rồi bật secret cho notebook. Chưa có Secret/API call thành công. Lần quan sát editor cuối cùng vẫn hiển thị **Draft Session off**.

Thứ tự tiếp tục: (1) hoàn tất đồng bộ gói runtime Private; (2) chạy câu DistilBERT từ pilot với `--trace-output`, đối chiếu JSON/critic/evidence; (3) sau khi có summary đạt contract, chạy Fact-Checker/Writer thật và đo bộ nhớ/latency; (4) Reader API khi có Secret; (5) dữ liệu giữ lại, calibration và quyền corpus vẫn là các gate riêng chưa đạt. Không hạ ngưỡng hoặc bỏ kiểm evidence để làm ca đầu tiên pass.
