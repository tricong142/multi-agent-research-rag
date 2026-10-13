# Tiếp tục kiểm chứng, cập nhật 2026-09-27

## 1. Fact-Checker: bản thử nghiệm, chưa thay baseline serving

Code và dữ liệu huấn luyện xác nhận checkpoint chỉ học nhãn/giải thích SciFact; không có confidence ground truth. Runtime dùng cùng model cho một prompt confidence khác. Prediction thật Version 4 cho thấy nhiều nhãn đúng nhận score 0 và có false support với claim ghép. Chưa đủ dữ liệu để quy toàn bộ lỗi cho prompt hoặc checkpoint.

Đã thêm profile thử nghiệm `coverage`:

- Judge phải kiểm mọi mệnh đề, số liệu và điều kiện; ba ví dụ phân biệt hỗ trợ đầy đủ, hỗ trợ một phần và mâu thuẫn.
- Confidence là mức tự tin **nhãn được chọn là đúng**, không phải xác suất claim đúng; nhãn contradict/not_enough_info vẫn có thể có confidence cao.
- Giữ prompt huấn luyện/baseline và ngưỡng 0,7. Không tự fit calibration hoặc triển khai profile thử nghiệm.
- Collector giữ lý do judge/confidence và latency mỗi dòng, không tạo score giả cho lỗi runtime.
- 12 ca synthetic regression được đánh dấu rõ provenance; không gọi là dữ liệu con người gán nhãn hoặc test độc lập.

Các file: `04_factchecker/prompts.py`, `inference/judge.py`, `inference/confidence.py`, `eval_factchecker.py`; `research_rag/evaluation/compare_factchecker.py`, `factchecker_contract_cases.jsonl`. Test prompt/collection/integration: 26 pass. Bảy test prompt/collection/QASPER mapping cũng pass (có phần trùng test, không cộng thành 33 test riêng biệt).

Lệnh chạy so sánh trên host GPU, sau khi đồng bộ sáu file:

```bash
python -m research_rag.evaluation.compare_factchecker --output-dir /kaggle/working/factchecker-comparison-20260926
```

Script nạp một checkpoint 3B NF4, chạy baseline và coverage trên cùng 30 dev + 12 ca contract, lưu từng prediction sau mỗi dòng. Báo cáo riêng dev/contract, false support, precision/recall, ECE/Brier, latency và bộ nhớ. Không tự promote prompt. Xem lỗi theo từng ví dụ trước khi quyết định; tập dev dùng chọn prompt không trở thành tập test cuối. Nếu prompt vẫn thất bại, cần bổ sung hard negatives có nhãn và huấn luyện/đánh giá lại; không sửa gold label để nâng điểm.

Gói cũ `kaggle_transfer/factchecker-experiment-20260926.zip` (11.234 bytes) chưa upload. Đã gộp sáu file đó vào **`validation-update-20260927.zip`** cùng sửa Reader và benchmark QASPER để chỉ cần một lần xác nhận upload Private. Xem [payload và lệnh chạy](VALIDATION_UPDATE_20260927.md); manifest/hash gói ở `kaggle_transfer/validation-update-review.json`. Chưa chạy A/B bằng model thật, chưa có kết quả tốt hơn baseline.

Kaggle đã khôi phục venv pin, `pip check` đạt. Đã Quick Save chọn lưu Output; lịch sử hiển thị Version 5 (`done Quick Version`). UI có timestamp không nhất quán ở Version 5 nên không dùng timestamp đó làm mốc kiểm thử. Sau đó đã quan sát **Session stopped / Draft Session off**. Version 4 vẫn giữ kết quả GPU đã xác minh trước đó; Version 5 không có kết quả A/B mới.

## 2. Reader: API smoke đạt, PDF thật chưa đạt

Ngày 2026-09-27 đã kiểm endpoint và gọi API thật. `gemini-3.8-flash` generate được nhưng hai lượt smoke gặp 429/503. Chuyển cấu hình thử nghiệm sang `gemini-3.5-flash-lite`, giới hạn một request mỗi 61 giây: **3/3 PDF synthetic, 9/9 span trong cùng một lần**, 184.094,76 ms gồm pacing, 2.080 token. Chưa đo billing. Không đổi default model toàn repo; dùng env rõ ràng.

PDF thật QASPER từ ACL, ba trang chọn trước có **6/9 span**, dù cả sáu API calls đều thành công và critic chấp nhận các trang. Audit checkpoint LayoutLMv3 thật xác nhận 512-token truncation làm mất dòng. Đã sửa local bằng overflow windows, de-duplicate ID dòng và kiểm đủ coverage; scorer chuẩn hóa ligature NFKC, kiểm hash PDF. 8 regression/scorer test pass. Thêm pacing tùy chọn chung router/critic bằng `GEMINI_REQUEST_INTERVAL_SECONDS`; 5 test retry/pacing pass.

**Chưa rerun bản sửa bằng model thật.** Sau đồng bộ, đặt `GEMINI_MODEL=gemini-3.5-flash-lite`, `GEMINI_REQUEST_INTERVAL_SECONDS=61`, chạy lại smoke và `reader_real_manifest.jsonl`. Giữ nhãn đã chốt trước inference. Cần thêm PDF scan/layout đại diện và người rà nhãn; một paper với nhãn trợ lý chép chưa phải tập test độc lập. [Trạng thái và evidence chi tiết](KAGGLE_VALIDATION_STATUS.md).

Đã Quick Save **Version 6 kèm Output**, UI báo Quick version complete; sau đó **Session stopped**. Phiên Reader dùng CPU, GPU=0. Artifact `reader-validation-20260927.zip` đã tải về Windows và xác minh SHA-256 ZIP/21 payload. Gói upload 3,91 MB đã tạo trước xác nhận download, vẫn giữ nguyên hash để phê duyệt.

## 3. Qrels có annotation thật đã chuẩn bị local

`research_rag/evaluation/prepare_qasper.py` dùng cache QASPER native test tại revision `06806e4608976fc2fac0a090ac425d5b2b29caf4`. Đã kiểm metadata nguồn và checksum. Kết quả tại `kb_indexing/data/qasper_eval_20260926/`:

- 18.587 paragraph nguyên bản; ID ổn định `qasper:<paper_id>:paragraph:<index>`.
- 393 qrels dev, 417 qrels test candidate; hash paper quyết định split, không dùng kết quả retrieval.
- Loại 29 paper đã dùng trong Writer. Kiểm tra thêm chuỗi 12 token với context Summarizer không tìm thấy paper trùng; đây không phải bằng chứng không có trùng ngữ nghĩa.
- Evidence lấy từ annotation người của QASPER, gộp các paragraph dương tính của nhiều annotator; không suy ra nhãn từ output model. Bỏ cả câu khi annotation visual/unmatched hoặc mâu thuẫn, thay vì âm thầm bỏ positive.
- Prefix tiêu đề paper vào câu hỏi cho retrieval trên toàn corpus; đây là benchmark đã điều chỉnh, không phải điểm chuẩn QASPER gốc.
- Manifest giữ attribution CC BY 4.0, hash nguồn/đích, lý do loại và giới hạn. Ngày 2026-09-27 đã dựng BM25 riêng; FAISS chưa dựng. Chưa chạy final candidate hoặc chọn policy dựa trên nó.

### BM25 QASPER dev, 2026-09-27

Đã dựng `kb_indexing/indices/qasper_bm25_20260927/` bằng `research_rag.indexing`, dùng tokenizer và BM25Okapi hiện tại. Runtime kiểm tra khớp toàn bộ 18.587 ID/text. Có 15 paragraph chỉ chứa ký tự không sinh token, vẫn giữ ID gốc; không bỏ annotation để nâng điểm. Manifest ghi `dense_ready: false`; file ID mapping không phải index dense.

Chạy đủ **393 dev queries**, top-k=5: **hit@5 = 0,279898**, **recall@5 = 0,159664**, mean **478,45 ms**, p95 **844,30 ms**. Không fallback; máy Windows đang thiếu RAM nên latency này không đại diện host GPU/production. Score và hash ở `docs/qasper-bm25-dev-20260927.json`. Kết quả chưa đạt căn cứ để công bố retrieval có chất lượng tốt. Đây là recall paragraph có annotation trong benchmark đã đổi scope sang toàn corpus, không phải official QASPER score. Không chạy lại 417 test candidate để chọn cấu hình.

Lệnh tái tạo (output index phải là thư mục mới):

```bash
python -m research_rag.indexing --corpus kb_indexing/data/qasper_eval_20260926/corpus.jsonl --output-dir kb_indexing/indices/qasper_bm25_new
python -m research_rag.evaluate retrieval --qrels kb_indexing/data/qasper_eval_20260926/qrels_dev.jsonl --corpus kb_indexing/data/qasper_eval_20260926/corpus.jsonl --index-dir kb_indexing/indices/qasper_bm25_new --mode bm25 --top-k 5
```

Trên GPU có cache BGE, thêm `--dense --device cuda:0` khi dựng vào **thư mục mới**, rồi dùng `--mode dense` và cùng qrels dev. Nhánh dựng dense mới chưa được chạy bằng encoder thật; không xem sự tồn tại của CLI là kết quả benchmark.

`research_rag.local` cũng nhận `--corpus` và `--index-dir` để chạy graph với corpus được chọn. Cần truyền cả hai đường dẫn tương ứng; mặc định vẫn là corpus cũ. Ví dụ chỉ chạy sau khi gate model/dense đủ điều kiện:

```bash
python -m research_rag.local --question "Your research question" --quantize-4bit --corpus kb_indexing/data/qasper_eval_20260926/corpus.jsonl --index-dir kb_indexing/indices/qasper_dense_new --metrics-output metrics.json
```

Chưa chạy graph thật trên QASPER. Các thay đổi indexing, qrels, scorer, prompt, collection và integration được kiểm bằng 36 test; thêm 4 test trace/CLI sau khi thêm lựa chọn corpus đều pass.

**Chưa chứng minh độc lập end-to-end:** source_doc_id của dữ liệu Summarizer như `arxiv_2305_lora` không phải ID paper xác minh được. Kiểm tra token overlap không chứng minh không có trùng về ngữ nghĩa; exposure trong pretraining của base model cũng không biết. Không biến bộ này thành ground truth độc lập bằng cách chỉ đổi tên file. Cần rà provenance trước lần test cuối. Qrels này cũng không thay thế calibration labels của Fact-Checker.

## 4. Quyền corpus

Corpus `jamescalam/ai-arxiv-chunked` vẫn chưa được xác minh quyền phân phối. QASPER là corpus benchmark thay thế được chuẩn bị theo [license CC BY 4.0 do nguồn công bố](https://huggingface.co/datasets/allenai/qasper/blob/main/README.md), giữ attribution và ghi rõ biến đổi. Chưa thay corpus mặc định hoặc index hiện có. Không tự gửi thư xin quyền thay chủ tài khoản.

## 5. Điều kiện trước serving

### Kiểm tra thêm nguồn final/calibration ngày 2026-09-27

- [SciFact-Open: mô tả dữ liệu của tác giả](https://github.com/dwadden/scifact-open/blob/main/doc/data.md)
  phân biệt evidence gốc SciFact với evidence qua pooling; highlights của
  pooling là dự đoán model, không phải nhãn span thủ công. Không thể mặc định
  bộ này độc lập với checkpoint SciFact hiện tại; cần đối chiếu claim/paper.
- [Bài báo SCINLP](https://aclanthology.org/2026.findings-eacl.81.pdf), mục 3.1–3.3,
  mô tả trích/tạo claim bằng GPT-4 và rà soát thủ công với phạm vi cụ thể; một
  phần dataset dành cho nghiên cứu phi lợi nhuận được cung cấp khi yêu cầu.
  [Repo tác giả](https://github.com/nii-yamagishilab/scientific-fact-checking)
  công bố pipeline tạo dữ liệu. Chưa có bộ annotation độc lập tải về trong lần
  kiểm tra này; không lấy nhãn LLM mới sinh làm human ground truth. Chưa gửi
  yêu cầu cho tác giả thay người dùng.

Hai nguồn trên mới được khảo sát, chưa được nhập vào training/evaluation,
chưa thay thế split calibration/final cần đóng băng. Không đổi gold label hoặc
đổi tên dev thành test để vượt gate.

Sau khi sửa Fact-Checker có bằng chứng và Reader/API qua gate: dựng index cho corpus đã chọn, đóng băng split, đánh giá retrieval và calibration/final test tách biệt; chạy model thật trên thiếu evidence, nhiều claim, mâu thuẫn, lỗi API/OCR và retry budget. Chỉ thêm API/checkpoint bền vững khi các gate được xác nhận. Hiện chưa đạt điều kiện đó.
