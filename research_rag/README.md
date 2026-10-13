# LangGraph orchestration

Runtime hiện dùng **controller theo luật để điều phối tự chủ một nhiệm vụ**.
Hướng dẫn cấu trúc, ngân sách, checkpoint/resume và cách chạy:
[AUTONOMOUS_RESEARCH.md](../docs/AUTONOMOUS_RESEARCH.md).

Trạng thái/gate mới nhất: [PROJECT_STATUS.md](../docs/PROJECT_STATUS.md).
Graph giữ `seen_chunks` qua mọi lượt retry để nguồn phản bác không bị bỏ mất;
tất cả evidence span phải khớp nguồn. Fact-Checker có đầu ra sai contract được
coi là lỗi kiểm chứng, chặn claim. Indexing và retrieval cùng pin BGE revision
để dùng cache offline theo SHA trong notebook phục hồi.

`graph.py` chạy vòng `prepare -> controller -> reader/retrieval/summarizer/factchecker/writer -> controller`, kết thúc qua `stop`.
`planning.py` lập các nhiệm vụ con, điều kiện hoàn thành, quan hệ phụ thuộc và cập nhật kế hoạch sau kết quả.
Controller chọn `read/search/summarize/factcheck/write/stop` theo kết quả và ngân sách.
Summarizer có thể yêu cầu thêm context; Fact-checker đề xuất tìm thêm/làm rõ; Writer
có thể báo thiếu phạm vi trả lời. `max_graph_retries` giới hạn số lượt search bổ sung.

`retrieval.py` đọc corpus/index hiện có, kiểm tra thứ tự `doc_id` giữa JSONL, BM25 và FAISS,
rồi tìm theo query/method do `RetrievalAgent` chọn trong quyền controller cấp. Runtime chỉ hỗ trợ `bm25/dense`;
`hyde/rewrite/decompose` bị từ chối vì chưa được hiện thực. Dense lỗi thì báo fallback
và phương pháp đã chạy là BM25. `PdfReader.read_for_question` chọn một nhóm trang theo
câu hỏi, lưu page/bbox/source tool; `read()` vẫn đọc toàn bộ PDF cho bài đánh giá trích xuất.
Index PDF là **tạm thời trong nhiệm vụ**, không ghi đè index arXiv.

Summarizer nhận context mới kèm context đã thấy nếu còn chỗ. Evidence span được đối
chiếu với nguồn, cho phép khoảng trắng/ligature PDF, rồi lấy lại substring nguyên bản.
Graph kiểm từng claim với evidence và các chunk đã quan sát để phát hiện nguồn phản
bác. Mâu thuẫn, backend lỗi hoặc vượt `max_factcheck_calls` (120 trên toàn nhiệm vụ)
sẽ chặn xác minh. Mỗi lời gọi FactCheckerNode có thể gồm nhiều lượt LLM nội bộ.
`verified` nghĩa là **qua kiểm tra bằng model và có nguồn**, chưa phải ground truth.

Chạy test luồng trên máy hiện tại:

```powershell
.venv\Scripts\python.exe -m unittest discover -s research_rag/tests -v
.venv\Scripts\python.exe -m unittest discover -s 05_writer/tests -q
```

Kiểm tra tài nguyên và artifact mà không nạp LLM:

```powershell
python -m research_rag.preflight --faiss
python -m research_rag.evaluate snapshot
```

`snapshot` chỉ chấm các file prediction đã có; không chạy model mới. Fact-Checker hiện có 468 dự đoán có nhãn; Summarizer có 18 hàng. Để đo Retrieval recall@k, cần tạo JSONL qrels do người đánh giá gán, mỗi dòng dạng `{"query":"<câu hỏi>","relevant_doc_ids":["<doc_id có trong corpus>"]}`. File `retrieval_eval_manual.jsonl` hiện chỉ gán nhãn chọn tool, **không** phải qrels. Khi đã có nhãn:

```powershell
python -m research_rag.evaluate retrieval --qrels path\to\qrels.jsonl --mode bm25 --top-k 5
python -m research_rag.evaluate retrieval --qrels path\to\qrels.jsonl --mode dense --top-k 5
python -m research_rag.evaluate retrieval --qrels path\to\qrels.jsonl --mode policy --top-k 5
```

Nếu `dense_fallback_queries > 0`, số đo đó không phải recall của dense. Có thể đo calibration của Fact-Checker bằng `python -m research_rag.evaluate confidence --predictions path\to\predictions.jsonl` sau khi ghi thêm `confidence_score`, `gold_label` và `predicted_label` cho từng ví dụ. File prediction hiện có không có score, nên chưa tính calibration được.

Chạy model thật trên host có đủ GPU/RAM:

```powershell
python -m pip install -r requirements-orchestrator.txt
python -m research_rag.local --question "Câu hỏi của bạn" --quantize-4bit --profile-resources --metrics-output run-metrics.json
python -m research_rag.local --question "Câu hỏi về PDF" --pdf path\to\paper.pdf
```

Loader local mặc định không tải base model qua mạng. Thêm `--online-model-downloads` khi bạn đã quyết định tải các base model của adapter. `--quantize-4bit` dùng NF4 cho Summarizer và Fact-Checker trên CUDA; Writer đã tự nạp 4-bit khi có CUDA. Một ca DistilBERT đã chạy đủ Retrieval → Summarizer → Fact-Checker → Writer thật trên Kaggle T4 x2 ngày 2026-09-26 sau bản sửa đối chiếu evidence; đây chưa phải đánh giá chất lượng tổng quát. `--allow-cpu` chỉ dành cho host có đủ RAM; mặc định chương trình từ chối nạp đồng thời các model lớn khi không có CUDA. `--profile-resources` ghi RAM tiến trình và CUDA memory sau mỗi model được nạp và sau graph. `--metrics-output` ghi thời gian/trạng thái/số lượng, không ghi prompt, chunk hoặc report; `token_usage` và `estimated_cost` để `null` vì backend hiện không trả usage. Reader cần `GEMINI_API_KEY` nếu dùng bước critique Gemini; OCR cần binary Tesseract ngoài package Python. Xem [Kaggle GPU runbook](../docs/KAGGLE_GPU_RUNBOOK.md) để cài môi trường mới và kiểm thử có model thật.

Máy Windows local vẫn không có CUDA. Trên Kaggle, base Qwen 7B/1.5B đã tải đủ, BGE dense search thật đã chạy và graph đã sinh một báo cáo có citation hợp lệ. Ngày 2026-09-27, Reader dùng `gemini-3.5-flash-lite` qua đủ ba fixture (9/9 span), nhưng PDF nghiên cứu thật chỉ đạt 6/9 span trên ba trang chọn trước. Đã sửa local lỗi LayoutLMv3 cắt nội dung sau 512 token; chưa chạy lại bản sửa bằng model thật. Fact-Checker vẫn có false support và confidence chưa calibration. Xem [trạng thái có bằng chứng](../docs/KAGGLE_VALIDATION_STATUS.md).

QASPER đã có 393 qrels dev từ annotation gốc và 417 test candidate chưa chấm, với provenance/giới hạn độc lập trong [kế hoạch kiểm chứng](../docs/FACTCHECKER_NEXT_VALIDATION.md). BM25 dev hit@5=0,279898, paragraph recall@5=0,159664; FAISS cho corpus này chưa dựng. Dùng `research_rag.indexing --corpus ... --output-dir <thư mục mới>` để dựng index riêng; thêm `--dense --device cuda:0` khi có BGE trong cache. Cả `research_rag.evaluate retrieval` và `research_rag.local` nhận `--corpus` và `--index-dir`. Mặc định vẫn giữ corpus cũ; quyền phân phối corpus cũ chưa được xác minh.
