# Multi-Agent Research RAG — cấu trúc workspace

**Trạng thái hiện hành:** [PROJECT_STATUS.md](docs/PROJECT_STATUS.md) phân biệt
phần đã kiểm tra, bản sửa chưa chạy bằng model thật và thứ tự các gate còn lại.
Notebook phục hồi: [kaggle_resume_validation.ipynb](scripts/kaggle_resume_validation.ipynb).

## Demo R8 v12 từ PDF đến báo cáo có trích dẫn

[Hồ sơ bàn giao và kịch bản bảo vệ 3–5 phút](docs/R8_V12_HANDOFF.md) dùng
bản demo `table-proof` trên hai PDF thật. Tài liệu có hướng dẫn Kaggle và
cách trình bày từ ZIP kết quả đã chấm khi cần chạy ngoại tuyến.

[Mở demo web local](docs/R8_V12_HANDOFF.md#demo-web-local) để nhập câu hỏi,
theo dõi sự kiện của 5 agent và mở trích dẫn PDF. Web cũng hiển thị riêng
kết quả Kaggle đã lưu.

[Mở notebook smoke R8 v12](scripts/kaggle_r8_v12_e2e_smoke.ipynb) trên Kaggle Private.
Bật T4 x2 và Internet, gắn dataset Private chứa `research-rag-kaggle-v2.zip`,
rồi chạy Cell 1–4. Cell 3 gọi `research_rag.local --verifier r8-v12`.
Để thử PDF và câu hỏi khác, sao chép notebook, chạy Cell 1–2, rồi đổi
`--question` và `--pdf` trong Cell 3. Đọc kết quả ở `stdout.log` và
`trace.private.jsonl`. Cell 4 chấm riêng câu smoke gốc.

Ca smoke hỏi “Was the treatment evaluated against a control group?”.
Agent 4 trả `support` cho `claim:1` dựa trên câu
“The treatment was evaluated against a control group.” ở trang PDF 1
(`pdf:2d4ca361beeb8a03:p0:b3:c0`). Câu trả lời của Writer tham chiếu đúng
`claim:1`. Báo cáo có một cảnh báo chung về độ đầy đủ.

| Kết quả | Phạm vi |
| --- | --- |
| Smoke GPU R8 v12 · **8/8 kiểm tra** | Một PDF tổng hợp. ZIP `r8-v12-e2e-smoke-nl127zjx.zip`, SHA-256 `486f8c877eab25afdbb5fddf4c6674829fd3d547438f77d787a3024f0ad75042`. |
| Demo GPU R8 v12 table-proof · **3/3 sau sửa** | Ba câu trên hai PDF thật, chạy bằng [notebook Kaggle table-proof](scripts/kaggle_r8_v12_e2e_real_pdf_table_proof.ipynb) với T4 x2. Lượt trước sửa đạt **1/3** trên cùng bộ câu. |
| Holdout R8 v12 gốc · **24/30, đạt 2/4 ngưỡng ban đầu** | False support 0, precision 100%, Macro-F1 80,54%, abstention 6/20. [Bản khóa](artifacts/factcheck-verdict-r8-v12-holdout/holdout-lock.json). |
| Candidate trước lượt sửa bảng · **26/30, đạt 4/4 trên replay CPU development** | False support 0, precision 100%, Macro-F1 86,60%, abstention 2/20. Gold đã mở. Báo cáo replay lưu local tại `research-runs/r8-v12-support-guard/metric-bindings-replay.json`. |

ZIP đã chấm `r8-v12-e2e-real-pdf-table-proof-w3dquqnw.zip` có SHA-256
`d12dff01150ca1d83f9b5479a5fe75ffd186f0415d1bac03401bb14fd8b4ef8d`.
Hai câu có đáp án đều được Agent 4 xác nhận và liên kết qua `claim:1`
đến đúng ô nguồn.

- `fires-exact-match` · **17,33%**, Bảng 4, trang PDF **7**, RAT-SQL trên Fires
  trong điều kiện Without fine-tuning.
- `temp-sst2-accuracy` · **82,6%**, Bảng 2, trang PDF **5**, SST2 của Llama 2 7B
  với +TEMP.
- `missing-seeds` · Báo thiếu dữ kiện, không sinh giá trị seed và có
  **0 cuộc gọi Agent 4**.

Hai báo cáo có đáp án mang trạng thái `partial` do cảnh báo độ tin cậy từ
bước trước. Cả hai trả lời đủ và có trích dẫn đúng nên được tính đạt. Bộ ba câu
đã dùng trong quá trình sửa demo.

### SLA bàn giao đồ án

Ngưỡng bàn giao được điều chỉnh sau khi xem kết quả holdout R8 v12. Hai ngưỡng
về false support và support precision được giữ nguyên.

| Chỉ số | Ngưỡng ban đầu | Ngưỡng bàn giao | Holdout R8 v12 |
| --- | ---: | ---: | ---: |
| False support | 0 | 0 | 0 |
| Support precision | ≥85% | ≥85% | 100% |
| Macro-F1 | ≥85% | ≥80,54% | 80,54% |
| Abstention trên ca đủ bằng chứng | ≤15% | ≤30% | 30% (6/20) |

Trên holdout đã chấm, R8 v12 đáp ứng **4/4 ngưỡng bàn giao** và đạt
**2/4 ngưỡng ban đầu**. Việc đối chiếu ngưỡng bàn giao dùng lại kết quả
holdout hiện có. Bộ chấm và bản khóa đánh giá giữ nguyên.

## Chạy thử PDF với Cellfix29

Candidate E2E dùng Cellfix29 qua lựa chọn `--verifier atomic` và các bản sửa
kiểm chứng số đếm. Lượt GPU ghi nhận **3/3 smoke QASPER**, **3/9 trên paper mới
với bản đã khóa trước sửa** và **7/9 development sau sửa**. Kết quả holdout
verifier được ghi riêng. [Báo cáo và kịch bản demo](docs/CELLFIX29_E2E_RESULTS.md)

1. Mở [notebook Kaggle development](scripts/kaggle_cellfix29_e2e_cross_paper_development.ipynb).
   Bật T4 x2, Internet và gắn dataset Private chứa `research-rag-kaggle-v2.zip`.
2. Với bộ chín câu đã khóa, chạy Cell 1–4. Với PDF và câu hỏi riêng, tạo bản sao
   của notebook. Chạy Cell 1–2 để nạp runtime, rồi dùng lệnh dưới đây trong một
   ô mới. Tải PDF lên thư mục làm việc hoặc gắn PDF từ dataset của bạn.

```python
pdf = Path("/kaggle/working/my-paper.pdf")
question = "Your question about the PDF"
assert pdf.is_file()
report_dir = Path(tempfile.mkdtemp(prefix="pdf-report-", dir="/kaggle/working"))
command = [
    python, "-u", "-m", "research_rag.local",
    "--verifier", "atomic", "--question", question, "--pdf", str(pdf),
    "--retrieval-policy", "dense", "--initial-top-k", "5",
    "--quantize-4bit", "--online-model-downloads", "--profile-resources",
    "--process-timeout", "3600",
    "--metrics-output", str(report_dir / "metrics.json"),
    "--events-output", str(report_dir / "events.jsonl"),
    "--trace-output", str(report_dir / "trace.private.jsonl"),
]
with (report_dir / "report.json").open("w", encoding="utf-8") as report:
    subprocess.run(command, cwd=root, env=env, stdout=report, check=True)
print(report_dir)
```

3. Mở `report.json`. Nối `final_report.sentences[].claim_ids` với
   `verified_claims[].claim_id` để đọc `evidence` và `source_id`. Với ZIP
   benchmark, `review.json` có sẵn số trang PDF. Giữ trace ở chế độ Private.

## Đánh giá retrieval trước đây

[Benchmark QASPER](docs/QASPER_BM25_DENSE_REVIEW_20261017.md) đã audit đủ393 dev
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
trực tiếp, baseline offline và chấm predictions cũ. `web_demo` dùng
[pipeline R8 v12 local hoặc kết quả GPU lưu sẵn](docs/R8_V12_HANDOFF.md#demo-web-local).

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
