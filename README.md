# Multi-Agent Research RAG — cấu trúc workspace

**Trạng thái hiện hành:** [PROJECT_STATUS.md](docs/PROJECT_STATUS.md) phân biệt
phần đã kiểm tra, bản sửa chưa chạy bằng model thật và thứ tự các gate còn lại.
Notebook phục hồi: [kaggle_resume_validation.ipynb](scripts/kaggle_resume_validation.ipynb).

**Chưa Ready với atomic verifier mới:** Agent 3/Summarizer và Agent 5/Writer
chưa được nghiệm thu E2E; loader vẫn dùng FactChecker cũ. [Gate hiện hành và
benchmark QASPER](docs/QASPER_BM25_DENSE_REVIEW_20261017.md): đã audit đủ393 dev
cho mỗi phương pháp, zero fallback. Dense Hit@5 **40,97%**, paragraph Recall@5
**27,07%**; BM25 lần lượt **27,99%** và **15,97%**. FAISS QASPER mới có18.587
vector×1.024 chiều, hash và trace replay khớp. Đây là retrieval dev, chưa phải
chất lượng câu trả lời hoặc false support39.
[Notebook Colab BM25 vs Dense](scripts/colab_qasper_bm25_dense_dev.ipynb)
dựng index QASPER mới và từ chối tính điểm Dense khi fallback. Reader mặc định
dùng PyMuPDF/Tesseract local; cần binary Tesseract để chạy scan.

Candidate verifier **v8** đã bổ sung ràng buộc evidence/operand theo nguồn,
giới hạn prose, repair thiếu numeric, binding predicate và deadline khi decode.
[Validation local](docs/ATOMIC_VERIFIER_V8_VALIDATION.md) và
[hướng dẫn T4](docs/ATOMIC_VERIFIER_V8_RUN_GUIDE.md) ghi rõ phạm vi đã kiểm tra.
Notebook mới chạy smoke12 trước probe18; chưa có inference/human review/full39
của v8. V7 và các ZIP gốc được giữ riêng để replay; chưa promotion serving.

Atomic verifier v7: [full39 đã audit](docs/ATOMIC_VERIFIER_V7_FULL39_REVIEW_20261016T071213Z-7c8c33c6.md)
**không đạt**, timeout 5.400 giây: 22 predictions, 21 incomplete, một completed
nhưng sai nhãn. Không có nhãn support ở phần đã lưu; chưa kết luận false support
toàn39. Các lỗi này là đầu vào sửa candidate v8; kết quả GPU mới vẫn đang chờ.
[Probe T4](docs/DECOMPOSITION_PROBE_REVIEW_20261016T024708Z-a57ee72a.md) vẫn đạt18/18;
human reviewer **tricong** đã xác nhận và admission đã đạt, nhưng không thay gate39.
299 regression, 7 kiểm thử đóng gói probe, 4 kiểm thử đóng gói39 và hai
validate-only đạt; [validation/freeze](docs/ATOMIC_VERIFIER_V7_VALIDATION.md).
V5/v6 và các ZIP/predictions gốc được bảo toàn. Bước2 và gate toàn dự án chưa hoàn tất.

Demo metrics từng agent trên local: chạy `run_agent_tests.bat` hoặc
`python -m research_rag.evaluation.local_demo --agent all`, rồi mở `report.html`
được xuất. [Hướng dẫn và kết quả thực đo](docs/LOCAL_AGENT_DEMO.md) ghi rõ chạy
trực tiếp, baseline offline và chấm predictions cũ. `web_demo` là mô phỏng workflow.

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

`research_rag/` hiện chứa LangGraph orchestrator nối 5 thành phần, với FactChecker serving cũ. Nó có test luồng bằng backend giả và đã tìm kiếm BM25 trên corpus thật. Kiểm tra host/artifact bằng `python -m research_rag.preflight --faiss` và chấm prediction có sẵn bằng `python -m research_rag.evaluate snapshot`. Để chạy model thật trên máy có đủ tài nguyên: cài PyTorch phù hợp CUDA, `pip install -r requirements-orchestrator.txt`, cài binary Tesseract local nếu cần OCR, rồi chạy `python -m research_rag.local --question "..."` (thêm `--pdf file.pdf` khi hỏi về PDF). Reader mặc định không gọi Gemini; diagnostic Gemini cần opt-in rõ ràng và API key. Mặc định loader chỉ dùng model đã có trong cache; `--online-model-downloads` cho phép tải base model còn thiếu. Xem [hướng dẫn tích hợp](research_rag/README.md) và [các gate còn lại](docs/NEXT_STEPS_LANGGRAPH.md) trước khi triển khai production.

**Trạng thái Git:** thư mục gốc hiện có Git repository, đồng thời một số thành phần giữ lịch sử riêng. Workspace có nhiều thay đổi chưa commit; không reset hoặc xóa `.git` để "dọn" cấu trúc.
