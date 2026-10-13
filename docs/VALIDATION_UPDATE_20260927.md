# Gói kiểm chứng ngày 2026-09-27

Gói `validation-update-20260927.zip` gộp thay đổi runtime đã có, thử nghiệm
Fact-Checker, sửa Reader và benchmark QASPER. Gói này thay đề xuất upload riêng
`factchecker-experiment-20260926.zip`; không cần upload cả hai.

**Trạng thái:** đã upload và xác nhận Dataset Version 2, Private. Đích:
`trcng23/research-rag-runtime-diagnostics`, gắn vào notebook
`research-rag-gpu-validation`. Không chứa `.env`, key, venv, checkpoint hay
corpus/index `jamescalam/ai-arxiv-chunked`. Có code, test, SciFact dev đã dùng,
12 ca synthetic, QASPER paragraph/qrels, một PDF ACL công khai và attribution.
Không chứa BM25/FAISS mới; dựng chúng trên host bằng code đi kèm.

Kết quả áp dụng, môi trường và từng lần chạy được ghi riêng trong
[VALIDATION_RUN_20260927.md](VALIDATION_RUN_20260927.md). ZIP đã duyệt giữ nguyên
hash; tài liệu hiện tại có thể cập nhật trạng thái sau thời điểm đóng gói.

## Áp dụng sau khi được phép upload

1. Giữ dataset/notebook Private; không tạo API token. Add Input version mới.
2. Dùng một thư mục workspace **mới** trong `/tmp`, copy workspace v2 giữ đủ
   checkpoint/layout. Không ghi vào `/kaggle/input` hoặc bản kết quả đã lưu.
3. Tìm `validation-update-manifest.json`. Kiểm hash mọi payload và
   `base_sha256` với workspace v2 gốc trước khi copy đè vào bản sao mới.
   `base_sha256=null` là file mới. Từ chối đường dẫn tuyệt đối/`..` hoặc file
   không có trong manifest. Ghi manifest đã áp dụng vào Output.
4. Tạo lại venv serving theo `requirements-orchestrator.txt`, dùng CUDA torch
   của Kaggle và chạy `pip check`. Chạy `research_rag.preflight --faiss`.
   Kết quả Reader Version 6 dùng transformers 5.0.0; phải xác minh lại khi
   chuyển sang pin 5.16.1, không gọi hai môi trường đó là giống nhau.

## Thứ tự chạy và quyết định

### 1. Fact-Checker

```bash
python -m research_rag.evaluation.compare_factchecker --output-dir /kaggle/working/factchecker-comparison-20260927
```

Chạy cùng model 3B NF4, 30 dev + 12 synthetic cho mỗi prompt. Giữ prediction,
reasoning, lỗi và latency. Chỉ cân nhắc dùng `coverage` sau khi đọc false-support
và precision/recall, không chỉ accuracy. Confidence là mức đúng của **nhãn**;
chưa phải xác suất đã calibration. Không fit trên 30 mẫu đã dùng chọn prompt,
không thay ngưỡng 0,7 để che lỗi. Nếu chưa cải thiện, giữ baseline và xử lý
training/hard negatives trước khi chạy gate cuối.

### 2. Reader

Đặt env `GEMINI_MODEL=gemini-3.5-flash-lite`,
`GEMINI_REQUEST_INTERVAL_SECONDS=61`; lấy key bằng Kaggle Secrets và không in
giá trị. Chạy lại ba fixture, sau đó PDF QASPER với nhãn đã chốt. Audit
LayoutLMv3 trước/sau phải giữ đủ dòng và không lặp dòng do overlap. Dùng scorer
mới có NFKC và SHA-256; không dùng điểm trước sửa như kết quả sau sửa. Full
Reader có thể xử lý cả 12 trang, dù manifest chỉ gán nhãn trang 0/3/8.

```bash
python -m research_rag.evaluation.reader_smoke --manifest research_rag/evaluation/reader_smoke_manifest.jsonl > /kaggle/working/reader-smoke-fixed.json
python -m research_rag.evaluation.reader_smoke --manifest research_rag/evaluation/reader_real_manifest.jsonl > /kaggle/working/reader-real-fixed.json
```

Chín span chỉ đo có đúng đoạn ở đúng trang; chưa đo bảng/thứ tự đọc hoặc tính
đại diện. Cần người rà nhãn và thêm scan thực tế trước khi tuyên bố chất lượng.

### 3. Retrieval và split

Chỉ dùng 393 dev để so policy. Không chấm 417 test candidate để chọn cấu hình.
Nhánh dense cần cached BGE-Large; preflight phải xác nhận tải đúng revision.

```bash
python -m research_rag.indexing --corpus kb_indexing/data/qasper_eval_20260926/corpus.jsonl --output-dir /kaggle/working/qasper-dense-20260927 --dense --device cuda:0 --batch-size 16
python -m research_rag.evaluate retrieval --qrels kb_indexing/data/qasper_eval_20260926/qrels_dev.jsonl --corpus kb_indexing/data/qasper_eval_20260926/corpus.jsonl --index-dir /kaggle/working/qasper-dense-20260927 --mode bm25 --top-k 5
python -m research_rag.evaluate retrieval --qrels kb_indexing/data/qasper_eval_20260926/qrels_dev.jsonl --corpus kb_indexing/data/qasper_eval_20260926/corpus.jsonl --index-dir /kaggle/working/qasper-dense-20260927 --mode dense --top-k 5
```

Ghi cả fallback, corpus/qrels/index hashes, cold/warm latency. Không so latency
máy local thiếu RAM với GPU để kết luận thuật toán nhanh hơn. Đóng băng split
calibration/final theo claim/paper sau audit exposure; hiện chưa đủ provenance
để gọi QASPER candidate là independent end-to-end test.

### 4. Corpus và gate cuối

QASPER có license nguồn/attribution trong `THIRD_PARTY_NOTICES.md`; đây là hướng
thay thế corpus cũ chưa rõ quyền. Chỉ chuyển default sau khi index, retrieval
và model được đánh giá trên corpus mới. Chạy adverse E2E bằng model thật:
không evidence, support một phần, nhiều claim, mâu thuẫn, OCR/API lỗi, retry
hết budget. Review nguồn/citation và báo cáo, đo p95/usage/cost. Chỉ thêm
serving/checkpoint sau khi các gate đó đạt.

Kết thúc mỗi phiên: lưu Quick Save **kèm Output**, xác minh hoàn tất, rồi
Stop session. Không dùng Save & Run All vì notebook còn các cell lịch sử.
