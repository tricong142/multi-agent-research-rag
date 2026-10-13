# Full system audit trước khi chuyển lên Kaggle

Ngày kiểm tra: 2026-09-24. Phạm vi: workspace `AI ENGINEER`, source code, artifact, test và các lệnh kiểm tra cục bộ. Đây là báo cáo hiện trạng, **không xóa hoặc sửa code**. `NOT VERIFIED` nghĩa là chưa có lần chạy/nhãn đánh giá đủ để kết luận.

## 1. Executive Summary

Hệ thống đã có một **LangGraph workflow năm thành phần** với state chung, các nhánh điều kiện, retry có giới hạn, kiểm tra evidence nguyên văn và Writer nhận `verified_claims`. Chưa thể gọi đây là hệ thống năm autonomous agents hoặc một research RAG đã hoàn thiện: routing cấp graph được viết cố định; Retrieval runtime dùng heuristic thay vì LoRA router; ba policy action chưa thực thi transformation; chưa chạy inference đồng thời với model thật; chưa có qrels retrieval, kiểm thử PDF nhiều layout/scan và đánh giá citation end-to-end.

**Gate hiện tại:** có thể chuyển **bản thử nghiệm private** để chạy preflight trên GPU sau khi kiểm tra quyền sử dụng artifact, nhưng không nên tuyên bố Kaggle runtime đã chạy hoặc portfolio/research đã hoàn chỉnh. Gói ZIP đã được tạo và xác thực SHA-256 ở máy local; chưa được xác nhận sau giải nén trên Kaggle.

### Bằng chứng thực thi

- `python -m pytest -q research_rag/tests 05_writer/tests`: **84 passed** (CPU, backend giả cho graph/Writer). File `train_agent2_reader/test_tool_layoutlmv3.py` là script thủ công, không thuộc 84 test.
- `python train_agent1_retrieval/01_retrieval/eval_router_accuracy.py`: **30/30 nhãn chọn tool**, critique precision 100%, parse error 0%. Tập này không có qrels và không chứng minh recall của retrieval hoặc LoRA adapter.
- `python -m research_rag.evaluate snapshot`: chấm **prediction đã có**, không chạy model mới. Fact-Checker n=468: accuracy 0,7991; macro-F1 0,7831; recall `contradict` 0,615. Summarizer n=18: 13/15 evidence span khớp nguyên văn. Không phải đánh giá độ đúng của toàn graph.
- `python -m research_rag.preflight --faiss` ở host hiện tại: PyTorch `2.6.0+cpu`, CUDA=false, RAM khả dụng ~99 MiB lúc chạy; hai adapter Summarizer 7B và Writer 1.5B có mặt nhưng **base weights offline chưa đủ**; Fact-Checker merged có 2/2 shard, BGE encoder có 1/1 shard; lần đọc FAISS này trả `MemoryError`. Một lần kiểm tra trước đó đã đọc được index khi RAM trống lớn hơn. Chưa đủ bằng chứng để kết luận index hỏng hoặc dense query hoạt động.
- `pip check` trên `.venv` local báo xung đột `protobuf 3.20.2` với `proto-plus`, `grpcio-status`, `googleapis-common-protos`, `google-api-core`. Đây là tình trạng môi trường local; môi trường sạch trên Kaggle **NOT VERIFIED**.

## 2. Project Structure / inventory

| Vị trí | Vai trò và entry point | Được gọi / gọi tiếp | Trạng thái runtime |
| --- | --- | --- | --- |
| `research_rag/local.py` | CLI `python -m research_rag.local`; lắp model và graph | Import `graph`, `adapters`, `retrieval`, `observe`, các node Agent 3–5 | Entry point local thực tế; thiếu base weights để chạy offline |
| `research_rag/graph.py`, `state.py` | `build_graph`, `ResearchState`, `SourceChunk` | Gọi Reader, Retrieval, Summarizer, Fact-Checker, Writer qua dependency injection | Được 19 integration tests kiểm tra với backend giả |
| `research_rag/retrieval.py` | `RetrievalService.search` | Router policy, BM25, FAISS, SentenceTransformer | BM25/index mapping có test; dense real query chưa kiểm tra |
| `train_agent1_retrieval/01_retrieval` | Policy, train/eval router; notebooks tạo index | `retrieval.py` gọi `router_policy.select_tool`; adapter LoRA chỉ dùng trong script eval tùy chọn | Policy heuristic được dùng; router checkpoint không dùng trong graph |
| `train_agent2_reader` | `ReaderAgent.process_page`; PyMuPDF/OCR/LayoutLMv3/Gemini | `PdfReader` gọi theo từng trang khi có PDF | Mẫu PDF text có test với critique mock; layout/scan/API thật chưa đánh giá |
| `train_agent3_summarizer` | `SummarizerNode.run`; Generator và Critic | `graph.summarize` gọi trực tiếp | Có prediction cũ; hai model thật chưa nạp cùng graph |
| `04_factchecker` | `FactCheckerNode.__call__`; Judge, Confidence, Action | `graph.factcheck` gọi theo claim × evidence | Có prediction cũ; end-to-end model thật chưa chạy |
| `05_writer` | `WriterNode.__call__`, `WriterLoopController` | `graph.write` gọi với pool claim đã kiểm tra | Schema/loop có unit tests; model thật chưa chạy với graph |
| `kb_indexing` | 4 artifact corpus/index | `RetrievalService` đọc corpus, BM25 pickle, FAISS, doc-id map | Không phải database server; FAISS `IndexFlatIP` cục bộ |
| `research_rag/evaluate.py`, `preflight.py`, `observe.py` | Evaluation snapshot/qrels/calibration; host/artifact check; metrics | CLI dùng trực tiếp; `local.py` dùng `observe` khi có `--metrics-output` | Không tạo prediction mới trong `snapshot` |
| `research_rag/tests`, `05_writer/tests` | Unit/integration với fake backend | `pytest` | 84 test pass; chưa có GPU/model thật E2E |
| `README.md`, `research_rag/README.md`, `NEXT_STEPS_LANGGRAPH.md`, `KAGGLE_TRANSFER.md` | Hướng dẫn layout và các gate | Người vận hành | Có tài liệu, cần đồng bộ sau khi chốt cấu hình Kaggle |
| `requirements-orchestrator.txt`, requirements Agent 1/Writer | Khai báo môi trường | `pip` | Chưa có một lock serving đã kiểm thử trên Kaggle |
| `_archive`, `.venv`, `kaggle_transfer` | Bản lưu, môi trường local, gói chuyển | Không được graph import | Không có trong nội dung ZIP (ZIP ở `kaggle_transfer`) |

Gốc workspace **không có một `.git` thống nhất**. Retrieval, Reader, Summarizer, Fact-Checker có Git riêng và còn thay đổi chưa commit; không reset/xóa `.git`. Không thấy Dockerfile, compose, CI workflow hoặc API serving trong phạm vi source được quét. Các script train/eval vẫn có giá trị phát triển, nên không gọi là dead code chỉ vì graph không import chúng. Những phần **không được dùng trong runtime hiện tại**: router LoRA adapter, `FactChecker.recommended_action` ở graph, transformation cho `hyde/rewrite/decompose`; `request_more_context` của Summarizer chỉ đổi instruction, không tìm context mới.

## 3. 5-Agent Audit

### Agent 1 — Retrieval

- **File/entry:** `train_agent1_retrieval/01_retrieval/router_policy.py:156` (`select_tool`), `:216` (`make_decision`); runtime `research_rag/retrieval.py:141` (`RetrievalService.search`). Graph gọi `search`, không gọi trực tiếp `make_decision`.
- **Input → output/state:** `question`, `retrieval_history`, `pdf_chunks`, `top_k` → `retrieved_chunks` (`doc_id`, `source_id`, `text`, metadata, score, method), `retrieval_decision`, `retrieval_warning`. Lịch sử chỉ chứa các trial trong **một lượt graph**, không có memory bền vững.
- **Tools/model/prompt:** BM25 từ pickle; FAISS IndexFlatIP + `BAAI/bge-large-en-v1.5` cho dense. Runtime policy là luật Python. Router Qwen 7B LoRA và prompt trong `eval_router_accuracy.py` chỉ dùng khi eval với `--use-model`; checkpoint có trong ZIP nhưng runtime không nạp.
- **Decision/loop/error:** policy chọn 5 tên tool; graph retry tăng top-k, loại doc_id đã xem; dense lỗi thường fallback BM25 kèm warning, mismatch index thì fail. `hyde/rewrite/decompose` chỉ đổi `mode=dense` trên **query gốc** (`retrieval.py:163-168`). Có validation query/top-k và mapping corpus–BM25–FAISS. Logging runtime chủ yếu qua warning/state, không có trace tool/LLM đầy đủ.
- **Test:** heuristic 30/30 nhãn tool; integration test FAISS bằng encoder/index nhỏ giả và mismatch ID. Recall@k corpus thật **NOT VERIFIED** vì thiếu `relevant_doc_ids`.
- **Phân loại:** router deterministic + search service, **chưa là autonomous retrieval agent** theo tiêu chí tool-action-observation-replan bằng model.

### Agent 2 — Reader

- **File/entry:** `train_agent2_reader/reader_agent.py:66`, `:201`; adapter `research_rag/adapters.py:13` xử lý PDF từng trang.
- **Input → output/state:** `pdf_path`, `page_no` → blocks, tool được chọn, attempts, success; adapter tạo `pdf_chunks` với `source_id`, page, bbox, label. Không có memory xuyên lượt hỏi; chỉ giữ features/attempts của trang hiện tại.
- **Tools/model/prompt:** PyMuPDF (`alt_segmentation`), Tesseract OCR (`ocr_fallback`), LayoutLMv3 checkpoint; Gemini router/critique cho một số quyết định. Prompt/Pydantic schema ở `reader_policy.py`. Model Gemini mặc định từ `GEMINI_MODEL`; khả dụng của ID mặc định/API trên host mục tiêu **NOT VERIFIED**.
- **Decision/loop/error:** heuristic chọn tool cho trang đơn giản/không text; trường hợp mơ hồ gọi Gemini; critique có thể chọn retry tool khác, tối đa 3 lần (`reader_agent.py:201-233`). Với blocks không rỗng và confidence không quá thấp, `_critique` gọi Gemini (`:152-199`), nên PDF text đơn giản vẫn có thể cần `GEMINI_API_KEY` và mạng. `PdfReader` giới hạn 20 trang, chunk tối đa 2.000 ký tự bằng lát ký tự không overlap; có thể cắt qua câu. Lỗi một trang làm Reader fail toàn PDF theo adapter hiện tại.
- **Logging/test:** log tool/action và attempts; test graph dùng PDF text tạo ra và mock critique. `test_tool_layoutlmv3.py` là script chạy tay. Chưa có manifest PDF nhiều layout/scan có nhãn.
- **Phân loại:** đây là **agent-like page tool router** có chọn action, quan sát kết quả và retry cục bộ; chưa có chứng cứ về chất lượng extraction trên dữ liệu thật.

### Agent 3 — Summarizer

- **File/entry:** `train_agent3_summarizer/node.py:71`, `SummarizerNode.run(context, question)`; graph map output ở `research_rag/graph.py:90-125`.
- **Input → output/state:** context ghép `[source_id] text` + question → answer, evidence spans, support flag, confidence, reasoning trace; graph ghi `draft_answer`, `evidence_spans`, `evidence_refs`, `summary_supported`. Evidence chỉ vào `evidence_refs` khi là substring nguyên văn trong chunk đã chọn.
- **Model/prompt/tool:** Generator + Critic là hai Qwen2.5-7B LoRA adapter; prompt ở `generator/prompts.py` và `critic/prompts.py`. Không gọi external tool trong node; `request_more_context` không truy xuất lại (`node.py:128-135`). Context là nội dung retrieval trong lượt hỏi, không có memory lâu dài.
- **Decision/loop/error:** Critic quyết định support/rewrite/lower confidence/request more context; tối đa `config.MAX_INTERNAL_RETRY`, trả confidence thấp khi hết budget. `_generate_json` parse JSON nhưng truy cập key trực tiếp trong `run`, lỗi được graph bắt để fail closed. Graph giới hạn 10 evidence spans, context 6.000 **ký tự** và có thể bỏ toàn bộ chunk quá dài; đây không phải token budget.
- **Test/eval:** 18 prediction cũ, 13/15 span khớp nguyên văn; không đo answer correctness. Model thật trong graph **NOT VERIFIED**.
- **Phân loại:** **LLM generator–critic loop**, có phản hồi và retry, nhưng action lấy thêm context chưa thực thi; chưa là autonomous tool agent.

### Agent 4 — Fact-Checker

- **File/entry:** `04_factchecker/node.py:19`, `FactCheckerNode.__call__`; graph gọi tại `research_rag/graph.py:127-162` theo từng claim × evidence ref.
- **Input → output/state:** một `claim` + một `context` (span), trả label `support/contradict/not_enough_info`, score, reason, action đề xuất, status/attempts. Graph tổng hợp `fact_check_results` và `verified_claims` chứa `source_id` + evidence. Không có memory ngoài input/attempts của lần gọi.
- **Model/prompt/tool:** Judge, ConfidenceEstimator, ActionRecommender dùng cùng backend Qwen2.5-3B merged (adapter config xác nhận base 3B); prompt trong `04_factchecker/prompts.py`. Không có tool truy xuất nguồn khác. `recommended_action` chỉ là đề xuất và **graph không đọc**.
- **Decision/loop/error:** ba stage JSON với validation label/score/action và retry nội bộ tối đa 3 cho lỗi backend/parse. Confidence là tự đánh giá của model, **chưa calibration**; ngưỡng 0,7 là rule routing. Graph chặn claim nếu ref được kiểm tra trả `contradict`, nhưng chỉ kiểm tra các **span do Summarizer chọn**, không rà tất cả chunk đối lập. Split claim bằng regex dấu câu (`graph.py:11-17`), giới hạn 8 claim; câu có cấu trúc phức tạp có rủi ro tách sai. Status lỗi sẽ không tạo claim verified.
- **Logging/test/eval:** attempts/status trong output; snapshot n=468 accuracy 0,799/macro-F1 0,783/recall contradict 0,615. Chưa đánh giá calibration/claim-level end-to-end. `04_factchecker/config.py:22` mặc định base 7B, trái adapter 3B; `train_factchecker_qlora.py:103-122` import config có thể lấy mặc định này khi retrain. Merge hiện đọc base từ adapter config, runtime nạp merged local.
- **Phân loại:** **structured LLM verification chain** với retry/đề xuất action; không tự thực thi action hoặc tái lập kế hoạch.

### Agent 5 — Writer

- **File/entry:** `05_writer/node.py:8`, `WriterLoopController.run` tại `05_writer/loop_controller.py:45`; graph gọi tại `research_rag/graph.py:179-192`.
- **Input → output/state:** `intent`, `verified_claims`, upstream warning → `final_report`, `writer_diagnostics`, warning/status. VerifiedClaim schema bắt buộc claim_id/text/evidence/source_id; final report sentence trích claim_id, nguồn trực tiếp nằm trong pool claim, chưa được in ngay cạnh câu báo cáo.
- **Model/prompt/tool:** Qwen2.5-1.5B LoRA qua HFJsonBackend cho ReportGenerator/Critic/ActionSelector; prompt ở `05_writer/prompts.py`. Tool local là sửa/xóa/chọn lại câu từ **pool claim cố định**; không gọi retrieval/API ngoài. Context chỉ là claim pool của lượt hỏi.
- **Decision/loop/error:** schema Pydantic strict, validation citation ID, critique sentence-level, action `delete_sentence/rewrite_sentence/reselect_claims`, tối đa 3 retry nội bộ; fallback chép claim nguyên văn nếu model fail. Critic baseline chỉ xác nhận exact copy, không chứng minh semantic entailment (`inference/critic.py:16-69`). Model critique không được cho non-copy pass một mình. Output có thể là partial report kèm warning khi hết budget.
- **Logging/test/eval:** diagnostics/trace không chứa nội dung ở metrics graph; 65 Writer tests pass. 100 candidate reports cũ: schema 100%, **0 câu được người đánh giá**, `faithfulness_score=null`, 28% empty report, warning 100%. Exact-copy proxy 100% không phải faithfulness thực tế. Model thật nối graph **NOT VERIFIED**.
- **Phân loại:** **bounded local revision agent** với quyết định action và observation, nhưng không tự mở rộng bằng chứng hoặc quyết định thứ tự workflow.

## 4. LangGraph Audit

Source: `research_rag/graph.py:19-208`, `state.py:22-45`. `StateGraph(ResearchState)` nhận node trả partial state updates và `compile()`.

```text
START → prepare
          ├─ invalid question → END
          ├─ pdf_path → reader ── có pdf_chunks → retrieval
          │                    └─ lỗi/rỗng → writer → END
          └─ không PDF → retrieval
retrieval ├─ có chunks → summarize → factcheck
          ├─ no_hits và còn retry → retry → retrieval
          └─ hết retry/lỗi → writer → END
factcheck ├─ tất cả claim verified → writer → END
          ├─ thiếu/mâu thuẫn và còn retry → retry → retrieval
          └─ hết retry → writer → END
```

`retry` tăng `retry_count`, xóa draft/evidence/claim cũ, ghi lịch sử doc_ids, rồi gọi retrieval lại. `max_graph_retries` mặc định 1, validation cho 0–5. Reader chỉ chạy khi có PDF. Summarizer và Fact-Checker chạy khi có hit; Writer chạy cả khi thiếu bằng chứng để trả báo cáo cảnh báo. Graph không có checkpointer; state chỉ tồn tại trong lượt gọi. `prepare` reset lịch sử/claim/error; các node sau trả partial dict, nên field chỉ được giữ/ghi đè theo LangGraph state. Test đã đi qua nhánh lỗi, no evidence, conflict, retry và PDF bằng fake backend. **Model thật + concurrency/latency chưa xác minh.**

## 5. Orchestrator / Planner Audit

**Không tìm thấy Planner node độc lập** có input task → plan có schema → chọn Agent → quan sát → replan. `build_graph` chính là orchestrator điều kiện bằng Python. Nó có quyết định **có/không Reader**, **retry Retrieval**, **Writer khi thiếu evidence** dựa trên state; thứ tự Retrieval→Summarizer→Fact-Checker→Writer được hard-code. `RetrievalService` có router chọn công cụ search, **không phải planner chọn agent**. Không có LLM planner, schema plan, fallback plan hay checkpoint. Có thể gọi Retrieval nhiều lần; có thể bỏ Reader/Summarizer/Fact-Checker theo nhánh; Writer vẫn kết thúc workflow. Tên “multi-agent” chỉ phù hợp nếu giải thích là phối hợp nhiều thành phần agent-like qua workflow; đừng mô tả là autonomous multi-agent planning.

## 6. State Flow

| Bước | Đọc | Ghi | Kiểm tra/rủi ro |
| --- | --- | --- | --- |
| prepare | `question`, `pdf_path` | `intent`, counters, history, errors, claim pool | Query rỗng đi END; `pdf_path` là input tùy chọn |
| reader | `pdf_path` | `pdf_chunks` | `source_id` chứa hash PDF/trang/block/part; metadata giữ page/bbox/tool; lỗi trang làm thất bại nhánh PDF |
| retrieval | `question`, `pdf_chunks`, history, retries | `retrieved_chunks`, decision, warning | `doc_id`/source_id theo corpus; mapping index được đối chiếu; policy branch chưa triển khai đầy đủ |
| summarize | question + selected chunks | draft, spans, refs, support/confidence | Ref chỉ từ exact span; chunk bị bỏ do budget không còn trong refs; model output chưa schema strict |
| factcheck | draft, refs, support | review, verified claims, warning | Mỗi claim kiểm với mỗi **ref**, không với mọi chunk; score chưa calibration; regex claim split có giới hạn |
| retry | old result + history | tăng count, xóa intermediate fields | Không query rewrite; doc_ids cũ bị loại |
| writer | intent, verified claims, warning | final report/diagnostics/status | Schema citation đến claim ID; cần resolver hoặc trình bày `source_id` cho người dùng cuối |

Các field `context_source_ids`, `evidence_spans`, `summary_confidence`, `fact_check_results`, `writer_diagnostics` được dùng như diagnostic/output; không phải tất cả tham gia routing. Không phát hiện field bắt buộc được đọc trước khi tạo trên các nhánh đã được test; nhưng schema `TypedDict(total=False)` không tự validate runtime, nên contract model thật còn cần kiểm thử. Mọi nội dung evidence/claim là per-run, không có cross-session memory.

## 7. RAG Audit

- **Ingestion/index:** `train_agent1_retrieval/01_retrieval/notebooks/01_prepare_corpus.py` chuẩn hóa chunk có sẵn từ dataset nguồn, lọc text <20 ký tự, gắn `doc_id`; không thấy bước tự chunk toàn bộ paper trong runtime. Bốn artifact nằm ở `kb_indexing`: corpus JSONL, BM25 pickle, FAISS index, ID map. Runtime validate thứ tự ID và corpus text (`retrieval.py:53-75`). Pickle chỉ an toàn khi artifact đáng tin; dataset upload không nên cho bên khác thay thế tự do.
- **PDF parsing/chunking:** Reader xử lý từng trang; adapter cắt block ở 2.000 ký tự, không overlap/semantic boundary (`adapters.py:14-65`). PDF được index tạm cho lượt hỏi, không nhập chung vào arXiv index. Giới hạn 20 trang là policy hiện tại, chưa benchmark.
- **Embedding/vector:** BGE-Large `BAAI/bge-large-en-v1.5`; script build passage chuẩn hóa vector, query có prefix, FAISS `IndexFlatIP` nên dot product của vector normalized tương đương cosine. Index có 41.549 vector/1024 chiều theo lần đọc thành công trước; lần preflight hiện tại không đọc được vì RAM cạn. Query dense thật **NOT VERIFIED**.
- **Retrieval/rerank:** top-k 5 mặc định, retry có thể tăng tới 50. BM25 và dense là hai mode; router chọn một, không fusion; **không có reranker**. `hyde/rewrite/decompose` chưa biến đổi query. Không có qrels nên chất lượng top-k/param **NOT VERIFIED**.
- **Context/generation/citation:** graph chọn cả chunk cho tối đa 6.000 ký tự, nối `[source_id]`; Summarizer tạo draft/span; graph bắt exact substring; Fact-Checker kiểm span; Writer cite claim_id. Đây là chuỗi grounding có guardrail, nhưng source relevance, contradictory passages bị bỏ qua, factual answer và citation correctness cần human-labelled E2E. Không gọi chỉ số `confidence_score` là xác suất sự thật.

## 8. Code Quality, config và bảo mật

**Điểm tốt:** tách graph/adapters/retrieval/state/evaluate; injectable backend giúp test không cần GPU; validation ID index, exact evidence, Writer Pydantic schema; retry graph và nội bộ có giới hạn. **Các điểm cần sửa:**

1. `04_factchecker/config.py:22` base mặc định 7B lệch adapter 3B; `train_factchecker_qlora.py:103-122` có thể import giá trị này khi train. Chốt cấu hình train theo adapter/CLI và thêm check mismatch trước khi train. `merge_lora_weights.py` đã đọc base từ adapter, nên không đồng nhất các lối chạy.
2. `train_agent3_summarizer/node.py:128-135` nói `request_more_context` nhưng không gọi Retrieval; `research_rag/graph.py` cũng không đọc action này. Cần hoặc truyền reason/action ra graph và route, hoặc đổi tên/giới hạn contract để không hứa tính năng chưa có.
3. `research_rag/graph.py:127-161` chỉ xem refs do Summarizer chọn; đối chứng mâu thuẫn trong retrieved chunks khác có thể bị bỏ sót. Thêm test nguồn đối lập **không xuất hiện trong evidence_spans** và thiết kế retrieval/verification chéo trước khi khẳng định conflict handling đầy đủ.
4. `graph.py:11-17` claim segmentation regex và giới hạn 8 claim có thể bỏ câu/cắt sai; cần eval trên câu thực, có thể dùng structured claim extractor khi chứng minh cần thiết. Fact-check calls tăng theo claim × refs, chưa có budget tổng số model calls/timeout.
5. `train_agent2_reader/reader_policy.py` mặc định model ID qua env; availability chưa kiểm tra. `_critique` có thể gọi API với PDF text thường; cần secret trên host và xử lý API outage bằng policy rõ. `reader_agent.py` có logger nhưng các adapter/graph chủ yếu trả status; chưa có structured trace end-to-end.
6. Các script train/eval dùng import `config` trần và đường dẫn Kaggle cũ; runtime dùng qualified import và import smoke trong cùng process **đã pass**, nhưng chạy script train/eval lẫn nhau trong process chung không nên được giả định an toàn. `eval_generator_critic.py` và vài script khác hard-code dataset slug cũ, không phải entry point runtime.

**Secret:** `SECRET DETECTED` tại `train_agent3_summarizer/.env:13` (key `GROQ_API_KEY` có giá trị). Không ghi giá trị ở đây. File `.env` bị ignore và không nằm trong ZIP theo manifest; vẫn cần kiểm tra key còn hiệu lực, phạm vi đã chia sẻ trước đây và xoay key nếu có rủi ro. Scan tên file/biểu thức trong source không chứng minh toàn bộ data/binary vô hại. Không đưa `.env`, key, token lên Git hoặc Kaggle dataset.

## 9. Dependencies / environment

Serving deps nằm ở `requirements-orchestrator.txt`: LangGraph, BM25, FAISS CPU, SentenceTransformer, PyMuPDF, Transformers/PEFT, Pydantic, google-genai, pytesseract, psutil. PyTorch CUDA phải cài riêng. `05_writer/requirements-train.txt` pin Transformers **4.48.3/PEFT 0.14.0**, trong khi orchestrator pin Transformers **5.16.1/PEFT 0.20.0**. Không cài đồng thời hai bộ pin vào một env; chọn một serving contract và kiểm thử model load/generate tương ứng. Writer HF backend bật 4-bit trên CUDA (`05_writer/inference/backend.py:120-125`) nhưng `bitsandbytes` không nằm trong orchestrator requirements. `accelerate` cũng không được pin trực tiếp ở đó dù loader dùng `device_map=auto`; có thể được kéo transitively, nhưng môi trường Kaggle chưa chứng minh. OCR cần binary Tesseract ngoài `pytesseract`.

`pip check` local fail vì protobuf như ở mục 1. Chưa có lock/reproducible GPU env, Dockerfile, CI. **Kaggle compatibility NOT VERIFIED** cho CUDA/PyTorch, `transformers` v5, PEFT, bitsandbytes, FAISS, model IDs, network/API. Thực hiện setup trong notebook sạch, `pip check`, import smoke, preflight, rồi model load từng phần.

## 10. Testing và evaluation

84 pytest pass gồm 19 graph/retrieval/PDF integration tests và 65 Writer tests; các test chủ yếu fake backend hoặc tiny index. Reader có script thủ công LayoutLMv3, chưa có automated labelled layout/scan suite. Retrieval thiếu qrels `relevant_doc_ids`; router 30/30 là nhãn chọn tool, không đo search. Fact-Checker dev prediction có nhãn nhưng thiếu `confidence_score` để calibration; contradict recall 0,615 là hạn chế cần ưu tiên. Summarizer evidence 13/15 không đo answer truth. Writer 100 report candidate chưa được human review; `faithfulness_score` null.

**Test tối thiểu tiếp theo:** (1) clean Kaggle import/model load smoke và mỗi adapter một câu; (2) dense query thật với đúng BGE encoder + index; (3) Reader PDF text/2 cột/bảng/scan có nhãn, API/OCR lỗi; (4) qrels giữ lại để đo recall@k/hit@k và latency cho BM25/dense/policy; (5) fact-check calibration + mâu thuẫn từ nguồn không được Summarizer cite; (6) end-to-end 5–10 câu có gold claim/source citation, no evidence, multi-claim, timeout/retry; (7) đo VRAM/RAM/tokens/cost/latency. Không nâng 84 pass thành khẳng định chất lượng mô hình.

## 11. Kaggle Readiness và kích thước gói

`kaggle_transfer/research-rag-kaggle.zip`: **7.383.328.712 byte**, 190 file, đã verify SHA-256 ở máy local. Bốn artifact `kb_indexing` và layout của bảy thư mục được giữ. ZIP tự nó nằm ngoài danh sách đóng gói, tránh lồng ZIP. Đóng gói hiện bỏ `.git`, `.venv`, `.env`, cache, `_archive`. Sau giải nén trên Kaggle phải chạy `transfer_kaggle.py verify-dir --full` và kiểm tra `research_rag.local.ROOT` theo `KAGGLE_TRANSFER.md`.

| Nhóm | Khuyến nghị | Bằng chứng / ảnh hưởng |
| --- | --- | --- |
| 7 thư mục source, `requirements-orchestrator.txt`, 4 artifact `kb_indexing` | **KEEP / MOVE TO PRIVATE KAGGLE DATASET** | Runtime tính ROOT từ vị trí `research_rag`; BM25/dense cần corpus/index/map cùng layout |
| Fact-Checker merged 2 shard **6.172 GB** | **KEEP nếu chạy runtime hiện tại; MOVE** | `local.py` nạp `factchecker_merged`; đây là ~84% ZIP. Muốn giảm mạnh phải đổi chiến lược load/quantize, rồi kiểm thử; không xóa trước |
| Reader LayoutLMv3 **504 MB**, Summarizer adapters **202 MB**, Writer adapter **74 MB** | **KEEP nếu giữ 5 component; MOVE** | Reader tool có thể chọn LayoutLMv3; Summarizer/Writer loader dùng adapters |
| Retrieval router LoRA **81 MB**, Fact-Checker LoRA **60 MB**, train/eval JSONL/notebooks | **KEEP local/research; có thể bỏ khỏi bản runtime-only sau khi tách bundle** | Router LoRA và FC LoRA không được runtime graph nạp (FC dùng merged). Không xóa khỏi project gốc |
| `05_writer/data/writer_sft_raw.jsonl` và `writer_sft_validated.jsonl` | **REVIEW / runtime-only có thể chỉ mang một bản hoặc không mang** | Cùng SHA-256, mỗi file 40.642.489 byte; vẫn giữ cả hai local nếu provenance train cần |
| `train_agent3_summarizer/data/corpus.jsonl` | **REVIEW** | Chỉ 3.803 byte và hash khác corpus `kb_indexing` 48 MB; **không gọi là bản trùng** chỉ vì tên giống |
| `.venv`, `.git`, `.env`, `__pycache__`, `.pytest_cache`, `_archive`, ZIP tự thân | **REMOVE FROM TRANSFER, KEEP LOCAL** | Đã bị exclude; `.env` chứa secret; nested Git có uncommitted changes |
| Base Qwen 7B/1.5B, BGE cache | **PROVISION ON GPU HOST / CACHE SECURELY** | Base weights Summarizer/Writer thiếu offline; BGE cache local có nhưng **không nằm trong ZIP**. Không giả định Kaggle có sẵn hoặc tự tải được |
| Index nếu rebuild | **REGENERATE chỉ khi artifact không khớp/không đọc được sau khi đủ RAM** | Build phải đúng corpus order, tokenizer, BGE model/prefix/normalization; tốn thời gian GPU |

Gói “full workspace” hiện phù hợp giữ code/data/checkpoint để audit, nhưng không tối ưu runtime-only. Muốn giảm dung lượng có ý nghĩa cần xử lý Fact-Checker merged; bỏ JSONL/router adapter chỉ giảm hàng chục đến vài trăm MB. Trước khi đưa dataset public, kiểm tra license và quyền phân phối của corpus/checkpoint/training data; tình trạng này **NOT VERIFIED**. Hiện chưa có dataset tại slug Kaggle được thử trước đó; upload đã dừng theo yêu cầu audit-first.

## 12. AI Engineer Readiness

| Tiêu chí | Mức | Bằng chứng ngắn |
| --- | --- | --- |
| Architecture | PARTIALLY READY | Phân lớp rõ, nhưng runtime/model memory và packaging chưa chốt |
| Agent Design | PARTIALLY READY | Reader/Writer có loop; các thành phần khác chủ yếu chain/policy |
| Multi-Agent Coordination | PARTIALLY READY | Có state/conditional graph, không có dynamic planner |
| LangGraph | READY cho workflow thử nghiệm | `StateGraph`, conditional edges, bounded retry, tests |
| RAG | PARTIALLY READY | Corpus/index + grounding guardrails; chưa E2E thật |
| Retrieval | PARTIALLY READY | BM25/index map có test; dense recall chưa đo |
| LLM Integration | CRITICAL ISSUE trước demo GPU | Base weights thiếu, đồng nạp model chưa thử |
| Tool Calling | PARTIALLY READY | Reader chọn tools; Retrieval policy ba action chưa chạy |
| State Management | READY cho một lượt | State partial update/source_id; chưa checkpoint/persistence |
| Evaluation | PARTIALLY READY | Snapshot FC/Summarizer, thiếu qrels/citation/human review |
| Testing | PARTIALLY READY | 84 test CPU pass; thiếu real-model E2E/OCR/API |
| Observability | PARTIALLY READY | Node timing/status/count; chưa token/cost/tracing |
| Error Handling | PARTIALLY READY | Fallback/retry/warning; thiếu timeout/budget API tổng |
| Security | PARTIALLY READY | `.env` excluded; secret local hiện hữu, pickle trusted-only, license chưa kiểm |
| Deployment | MISSING | Chưa Docker/API/checkpoint/serving |
| Documentation | PARTIALLY READY | Có README/hướng dẫn; cần cập nhật kết quả GPU thực tế |
| Reproducibility | CRITICAL ISSUE trước production | Chưa clean Kaggle env lock/model versions/base weights đầy đủ |
| Code Quality | PARTIALLY READY | Contracts rõ, còn mismatch config/legacy hard-coded paths |

## 13. Research Readiness và technical interview

**Đã có:** một pipeline engineering có baseline tự nhiên BM25, dense option, candidate metrics/evaluation CLI, test graph và model adapters. **Chưa đủ cho đóng góp nghiên cứu:** không thấy research question/hypothesis/gap được định nghĩa bằng protocol đo lường trong repo; chưa có qrels retrieval, baseline chạy cùng test set, ablation (bỏ Reader/critic/factcheck/policy), nhiều seed, calibration, human-labelled citation, kết quả latency/cost/VRAM và phân tích lỗi. BM25 + BGE/FAISS + LangGraph là **integration/engineering**, không tự động thành proposed research method. Nếu muốn paper/research, chốt câu hỏi cụ thể (ví dụ lợi ích của evidence-gated verification so với baseline) rồi đóng băng dataset, metric, split chống leakage, baseline, ablation và protocol tái lập.

Khi đưa vào CV, mô tả trung thực: “Xây dựng LangGraph RAG workflow 5 thành phần; implemented evidence/source contracts, bounded retries, CPU fake-backend tests, Fact-Checker offline evaluation.” Tránh “5 autonomous agents chạy production”, “dense vượt BM25”, “citation faithful” hoặc “Kaggle deployed” trước khi có số đo. Câu hỏi interviewer dễ gặp: router LoRA có được sử dụng không; tại sao 5 agent thay vì workflow; hai 7B + 3B cùng GPU ra sao; recall@k và held-out set ở đâu; tại sao model confidence 0,7; source đối lập bị bỏ qua thì sao; phiên bản Transformers nào là contract serving; secret/licensing và rollback/monitoring thế nào.

## 14. Critical Issues trước upload/chạy Kaggle

| Mức | Vấn đề/root cause | Impact | Hướng xử lý và verification |
| --- | --- | --- | --- |
| **P0** | `.env:13` có key thật, dù không trong ZIP; quyền phân phối artifact/dataset chưa kiểm | Rò secret hoặc phân phối sai phạm vi nếu gói khác/upload public | Giữ private; verify manifest và scan artifact trước upload; kiểm license/provenance; xoay key nếu từng lộ |
| **P0** | Base Qwen 7B/1.5B offline thiếu; `local.py:40-82` nạp 2×7B + 3B + Writer, chưa đo VRAM | Không chạy 5-model graph offline; có nguy cơ OOM | Provision base model, chọn GPU đủ tài nguyên; load từng model, đo peak RAM/VRAM; nếu thiếu dùng tuần tự/quantization đã kiểm thử |
| **P0** | Serving deps chưa chốt: orchestrator Transformers 5.x vs Writer train 4.x; `bitsandbytes` thiếu direct requirement; local `pip check` fail | Model load/generate có thể lỗi trước inference | Tạo env sạch trên Kaggle, pin một runtime stack, `pip check`, import + model smoke; cài binary OCR nếu cần |
| **P1** | Dense BGE query + FAISS chưa chạy end-to-end; host chỉ ~99 MiB RAM khi thử và FAISS MemoryError | Không thể chứng minh dense hoặc policy quality | Chạy `preflight --faiss`, một query dense thật trên host đủ RAM; qrels/latency; đừng xem BM25 fallback là dense result |
| **P1** | Reader critique có thể cần Gemini secret/API; default model chưa xác minh | PDF path có thể fail ngay cả khi text layer có sẵn | Chọn model ID hiện hỗ trợ, cấu hình secret host, test PDF text/scan/API error và policy offline |
| **P1** | FC `config.py:22` base 7B trái adapter 3B, train script import config | Retrain có thể dùng sai base | Đồng bộ config với adapter và assertion fail-fast; chạy dry-run train config |
| **P1** | Router action `hyde/rewrite/decompose` không thực thi, FC action không được graph dùng | Claim “planner/tool routing” sai thực tế, extra cost không rõ lợi ích | Đánh giá bm25/dense/policy với qrels; thu hẹp action hoặc implement + ablation |
| **P1** | Contradiction chỉ trong selected evidence spans; Writer citation là claim ID, chưa trực tiếp source | Có thể bỏ sót nguồn đối lập/citation khó audit | Regression test opposing uncited chunk; source resolver + human citation check |
| **P2** | Runtime-only bundle lẫn training data/adapter không dùng, hai Writer JSONL trùng hash | Upload nặng/thời gian lâu, không phá runtime | Tạo manifest runtime-only sau khi xác nhận gate; giữ full local/research bundle |

Không có kết luận “index hỏng” từ MemoryError trong điều kiện RAM gần cạn.

## 15. Recommended Fix Order

1. **P0 — trước transfer:** đảm bảo ZIP không có secret, dataset private, provenance/license hợp lệ; giữ manifest checksum. Không xóa file local.
2. **P0 — trên GPU host:** tạo env sạch từ serving pins thống nhất; đưa base model thiếu vào cache hoặc cho phép tải; `preflight --faiss`; nạp lần lượt model và đo peak VRAM/RAM, latency. Chỉ sau đó thử `python -m research_rag.local --question ... --metrics-output /kaggle/working/metrics.json`.
3. **P1 — sửa sai hợp đồng:** đồng bộ Fact-Checker config 3B; chốt Reader secret/model/fallback; quyết định thu hẹp policy hoặc implement transformation; kiểm nguồn mâu thuẫn ngoài evidence refs.
4. **P1 — đánh giá:** chuẩn bị held-out qrels, Reader PDF manifest, FactChecker score/calibration, Writer/citation gold và end-to-end real-model cases. So sánh quality/latency/cost của BM25/dense/policy bằng cùng query set.
5. **P2 — sản phẩm/portfolio:** tách runtime bundle khỏi training artifacts; thêm host setup/CI smoke, timeouts, token usage/tracing đã lọc nội dung nhạy cảm; update README với số đo thật.
6. **P3 — sau khi gate chất lượng đạt:** checkpoint bền vững, API serving, Docker/CI, nghiên cứu baseline/ablation có protocol.

## 16. Final Pre-Kaggle Checklist

- [x] Cấu trúc bảy thư mục và bốn artifact được đóng trong ZIP; SHA-256 local đã verify.
- [x] `.env`, `.git`, `.venv`, `_archive`, cache không nằm trong ZIP theo manifest; cần kiểm lại ZIP/manifest ngay trước transfer nếu rebuild.
- [x] Graph và Writer fake-backend tests pass (84); router policy manual eval 30/30.
- [ ] Key local tại `.env:13` được quản lý/đánh giá vòng đời; license và quyền dataset/model đã kiểm; dataset đặt Private.
- [ ] Kaggle giải nén đúng layout, `verify-dir --full` pass, `research_rag.local.ROOT` đúng.
- [ ] CUDA/PyTorch/Transformers/PEFT/bitsandbytes/FAISS/Gemini/Tesseract trên Kaggle được xác minh; `pip check` pass.
- [ ] Base Summarizer/Writer được provision; Fact-Checker merged/Reader/BGE load thật; peak VRAM/RAM và latency được đo.
- [ ] Dense search một query thật, qrels recall@k và no-fallback mode được xác minh.
- [ ] Reader PDF đa layout/scan/OCR/API thật; Fact-Checker calibration; Writer human citation evaluation.
- [ ] Toàn graph 5 thành phần chạy model thật qua ca no evidence, multi-claim, contradiction, error, retry hết budget và citation đúng nguồn.
- [ ] README diễn đạt đúng: bounded workflow 5 component, chưa có autonomous planner; mô tả measured limitations/trade-offs.
- [ ] Nếu công bố CV/research: test set, baseline, ablation, latency/cost, reproducibility và nguồn dữ liệu được công khai phù hợp quyền sử dụng.

**Kết luận:** project có khung engineering đáng tiếp tục, nhưng inference/model quality/Kaggle deployment và research contribution hiện **NOT VERIFIED**. Không có file nào bị xóa trong cuộc audit này.
