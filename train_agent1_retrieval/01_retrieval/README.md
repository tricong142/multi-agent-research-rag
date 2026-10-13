# Agent 1: Retrieval Agent (Router + Critique)

Thư mục này chứa toàn bộ pipeline xây dựng, huấn luyện và đánh giá **Agent 1 (Retrieval Agent)** — đóng vai trò là Router phân loại truy vấn (BM25 vs FAISS vs Hybrid) và Critique tự đánh giá kết quả retrieval trong kiến trúc Multi-Agent Research RAG.

---

## 📁 Cấu trúc thư mục `01_retrieval/`

```text
01_retrieval/
├── notebooks/                     # Các cell code chuẩn bị dữ liệu và build index (chạy trên Kaggle/Jupyter)
│   ├── 00_setup_and_data.py       # Cài thư viện, tải dataset, kiểm tra schema
│   ├── 01_prepare_corpus.py       # Gắn doc_id thống nhất, làm sạch chunk
│   ├── 02_build_bm25.py           # Xây dựng BM25 index bằng regex tokenizer
│   └── 03_build_faiss.py          # Xây dựng FAISS index bằng BAAI/bge-large-en-v1.5
├── generate_training_data.py      # Sinh synthetic data dạng CoT (hỗ trợ Groq, Gemini, OpenAI)
├── validate_synthetic_data.py     # Lọc & xác thực dữ liệu bằng cách query trực tiếp vào index thật
├── train_qlora.py                 # Huấn luyện SFT QLoRA 4-bit trên Qwen/Qwen2.5-7B-Instruct
├── eval_router_accuracy.py        # Đánh giá độ chính xác quyết định Router và Critique
├── router_policy.py               # Logic heuristic & deterministic guardrails
└── README.md                      # Hướng dẫn chi tiết pipeline Agent 1
```

---

## 🔄 Quy trình thực thi từng bước (Step-by-Step Pipeline)

### Bước 1: Chuẩn bị Corpus & Xây dựng Index (Chạy trên Kaggle Notebook)

Các file trong `notebooks/` được thiết kế theo dạng từng cell để chạy tuần tự trên môi trường Kaggle Notebook (GPU T4 x2 hoặc CPU):

1. **`00_setup_and_data.py`**:
   - Cài đặt các thư viện phụ thuộc (`rank_bm25`, `faiss-gpu`/`faiss-cpu`, `sentence-transformers`, `datasets`).
   - Tải dataset arXiv RAG từ Hugging Face.
   - Xác nhận cấu trúc dữ liệu (`row['chunk']`).

2. **`01_prepare_corpus.py`**:
   - Gắn định danh duy nhất deterministic `doc_id` theo format: `"<arxiv_id>::chunk_<idx>"`.
   - Lọc bỏ các chunk rỗng hoặc quá ngắn.

3. **`02_build_bm25.py`**:
   - Tokenize văn bản bằng regex tokenizer đồng bộ.
   - Xây dựng và serialize `bm25_index.pkl`.

4. **`03_build_faiss.py`**:
   - Encode văn bản thành dense vectors bằng embedding model `BAAI/bge-large-en-v1.5`.
   - Tạo index FAISS (`faiss_arxiv.index`) và lưu file ánh xạ ID (`faiss_doc_ids.json`).

> **Lưu ý**: Sau khi hoàn thành, copy các file index (`bm25_index.pkl`, `faiss_arxiv.index`, `faiss_doc_ids.json`) vào thư mục `kb_indexing/indices/` của dự án.

---

### Bước 2: Sinh dữ liệu huấn luyện Synthetic CoT (`generate_training_data.py`)

Script sử dụng LLM để sinh các kịch bản truy vấn đa dạng kèm suy luận từng bước (Chain-of-Thought) và nhãn quyết định:

- **Hỗ trợ API**: Groq (ưu tiên Qwen-2.5/Llama models), Google Gemini API, OpenAI API.
- **Cơ chế an toàn**: 
  - Incremental save: Ghi từng mẫu vào file `.jsonl` ngay khi sinh xong để tránh mất mát dữ liệu nếu ngắt kết nối.
  - Tự động fallback model khi gặp rate limit / quota exhaustion.
  - Đọc `retry-after` header để backoff thông minh khi gặp HTTP 429.

**Cách chạy:**
```bash
# Thiết lập API Key trong file .env hoặc export trực tiếp
export GROQ_API_KEY="gsk_..."
# hoặc
export GEMINI_API_KEY="AIzaSy..."

python 01_retrieval/generate_training_data.py
```

---

### Bước 3: Xác thực dữ liệu Synthetic (`validate_synthetic_data.py`)

**Bắt buộc thực hiện trước khi huấn luyện.**
- LLM khi sinh dữ liệu có thể gán nhãn công cụ sai (hallucination).
- Script này thực hiện query thử nghiệm trực tiếp trên `bm25_index.pkl` và `faiss_arxiv.index` thật.
- Chỉ giữ lại các mẫu mà chunk gốc thực sự xuất hiện trong Top-K kết quả trả về của công cụ được chọn, tạo ra file `retrieval_sft_train_validated.jsonl`.

**Cách chạy:**
```bash
python 01_retrieval/validate_synthetic_data.py
```

---

### Bước 4: Fine-tune QLoRA cho Router + Critique (`train_qlora.py`)

Huấn luyện mô hình `Qwen/Qwen2.5-7B-Instruct` để thực hiện đồng thời 2 nhiệm vụ: Chọn công cụ retrieval phù hợp và Critique chất lượng đoạn văn bản truy xuất.

- **Kỹ thuật tối ưu hóa bộ nhớ:**
  - 4-bit Quantization (BitsAndBytes NF4, Double Quantization).
  - Target Modules: LoRA trên cả Attention (`q_proj, k_proj, v_proj, o_proj`) và MLP (`gate_proj, up_proj, down_proj`).
  - Optimizer: `paged_adamw_8bit`.
  - Gradient Checkpointing kích hoạt, phân bổ GPU 0 tránh OOM trên môi trường Kaggle 2x T4.

**Cách chạy:**
```bash
python 01_retrieval/train_qlora.py
```

---

### Bước 5: Đánh giá mô hình (`eval_router_accuracy.py`)

Đánh giá hiệu năng của model sau fine-tuning trên tập benchmark kiểm thử độc lập:
- Đo lường **Tool Selection Accuracy** (Độ chính xác chọn tool: BM25, FAISS, Hybrid).
- Đo lường **Critique Precision / Recall** (Độ chính xác khi nhận diện tài liệu có liên quan/không liên quan).

**Cách chạy:**
```bash
python 01_retrieval/eval_router_accuracy.py
```

---

## 🛡️ Router Policy & Guardrails (`router_policy.py`)

File `router_policy.py` định nghĩa các luật kiểm soát xác định (deterministic rules) cho Router:
- Xử lý các edge-cases khi model trả về format không hợp lệ.
- Áp dụng các quy tắc an toàn (fallback về Hybrid search nếu độ tự tin thấp hoặc retry quá số lần cho phép).
- Tích hợp chuẩn hóa schema `RetrievalDecision` trong orchestration pipeline (LangGraph).
