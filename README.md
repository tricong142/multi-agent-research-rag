# Multi-Agent Research RAG — cấu trúc workspace

**Trạng thái hiện hành:** [PROJECT_STATUS.md](docs/PROJECT_STATUS.md) phân biệt
phần đã kiểm tra, bản sửa chưa chạy bằng model thật và thứ tự các gate còn lại.
Notebook phục hồi: [kaggle_resume_validation.ipynb](scripts/kaggle_resume_validation.ipynb).

```text
AI ENGINEER/
├── research_rag/              # Runtime: graph, adapters, retrieval, evaluation, tests
├── train_agent1_retrieval/    # Dữ liệu/train/policy Retrieval (repo Git riêng)
├── train_agent2_reader/       # Dữ liệu/train/runtime Reader (repo Git riêng)
├── train_agent3_summarizer/   # Dữ liệu/train/runtime Summarizer (repo Git riêng)
├── 04_factchecker/            # Dữ liệu/train/runtime Fact-Checker (repo Git riêng)
├── 05_writer/                 # Dữ liệu/train/runtime Writer
├── kb_indexing/               # Corpus và index dùng chung
├── docs/                      # Hướng dẫn vận hành và audit
├── scripts/                   # Tiện ích đóng gói/chuyển môi trường
├── kaggle_transfer/           # Gói xuất cục bộ, không commit
└── _archive/                  # Snapshot tham khảo, không dùng ở runtime
```

Các module đang có đường dẫn tương đối, import và lịch sử Git riêng. Giữ vị trí của chúng để bảo toàn lệnh train/inference và thay đổi chưa commit; cấu trúc này phân tách runtime, dữ liệu, tài liệu và công cụ vận hành mà không sao chép code. `kb_indexing/` chứa corpus và index dùng chung cho Retrieval và Summarizer.

| Stage | Directory | Current runtime entry point | Status for graph integration |
| --- | --- | --- | --- |
| 1. Retrieval | `research_rag/retrieval.py` | `RetrievalAgent.run` → `RetrievalService.search` | Agent tự chọn query và BM25/dense theo nhiệm vụ, feedback và lịch sử; router LoRA ở thư mục train chưa nối vào runtime. |
| 2. PDF Reader | `train_agent2_reader/` | `ReaderAgent.process_page(pdf_path, page_no)` | `research_rag/adapters.py` gom trang và chunk; `research_rag/retrieval.py` lập index tạm cho PDF. |
| 3. Summarizer | `train_agent3_summarizer/` | `SummarizerNode.run(context, question)` | Graph đổi kết quả thành state update và ghép evidence nguyên văn với nguồn. |
| 4. Fact-Checker | `04_factchecker/` | `FactCheckerNode(state)` | Graph kiểm tra từng claim với evidence span và các chunk truy xuất khác; chặn mâu thuẫn hoặc lỗi kiểm chứng. |
| 5. Writer | `05_writer/` | `WriterNode(state)` | Graph chỉ đưa pool `verified_claims` đúng schema vào Writer. |

Xem [các gate còn lại](docs/NEXT_STEPS_LANGGRAPH.md) trước production. Tài liệu vận hành nằm trong [`docs/`](docs/); script đóng gói Kaggle nằm trong [`scripts/`](scripts/). Giữ checkpoint của 5 agent và corpus/index khi chạy local; chúng là model/data artifact lớn, không phải source code cần commit vào repo mới. `_archive/writer_agent_5_publish/` là repo Git Writer đã publish và kết quả evaluation, chỉ giữ làm tham chiếu; code Writer đang dùng là `05_writer/`.

`research_rag/` hiện chứa LangGraph orchestrator nối 5 thành phần. Nó có test luồng bằng backend giả và đã tìm kiếm BM25 trên corpus thật. Kiểm tra host/artifact bằng `python -m research_rag.preflight --faiss` và chấm prediction có sẵn bằng `python -m research_rag.evaluate snapshot`. Để chạy model thật trên máy có đủ tài nguyên: cài PyTorch phù hợp CUDA, `pip install -r requirements-orchestrator.txt`, đặt API key cho Reader nếu dùng Gemini, cài Tesseract nếu cần OCR, rồi chạy `python -m research_rag.local --question "..."` (thêm `--pdf file.pdf` khi hỏi về PDF). Mặc định loader chỉ dùng model đã có trong cache; `--online-model-downloads` cho phép tải base model còn thiếu. Xem [hướng dẫn tích hợp](research_rag/README.md) và [các gate còn lại](docs/NEXT_STEPS_LANGGRAPH.md) trước khi triển khai production.

**Trạng thái Git:** thư mục gốc chưa có `.git`, nên hiện là workspace, chưa phải một monorepo. Retrieval, Reader, Summarizer, Fact-Checker và bản Writer trong `_archive/` có `.git` riêng; `05_writer/` đang là bản code hoạt động nhưng không có `.git` riêng. Trước khi tạo một repo Git thống nhất, cần quyết định giữ lịch sử riêng hay chuyển sang monorepo; không xóa các thư mục `.git` để "dọn".
