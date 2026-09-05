# Train Agent 1: Retrieval Agent (Router + Critique)

## Thứ tự chạy

### Phần A — Hạ tầng (chạy trên Kaggle Notebook, GPU T4 x2)
Các file trong `01_retrieval/notebooks/*.py` là **nội dung từng cell**, copy-paste
trực tiếp vào Kaggle Notebook theo đúng thứ tự số — **không chạy bằng `python file.py`**
vì cell đầu có `!pip install` (cú pháp riêng của Jupyter, không phải Python thuần).

1. `00_setup_and_data.py` — cài thư viện, tải dataset, **in thử 1 dòng để xác nhận
   tên cột** trước khi đi tiếp (đã sửa lỗi `doc['text']` → `doc['chunk']` so với bản gốc)
2. `01_prepare_corpus.py` — gắn `doc_id` thống nhất, lọc chunk rỗng
3. `02_build_bm25.py` — build BM25 (đã bỏ `nltk` thừa, dùng regex tokenizer nhất quán)
4. `03_build_faiss.py` — build FAISS bằng `bge-large-en-v1.5` (đã thêm lưu `doc_ids`
   mapping — bản gốc thiếu, sẽ không biết vector nào ứng với chunk nào)

Tải 2 file `faiss_arxiv.index` + `faiss_doc_ids.json` + `bm25_index.pkl` về máy, đặt vào
`kb_indexing/indices/` (đúng path mà các script Phần B/C bên dưới trỏ tới).

### Phần B — Sinh & validate synthetic training data (chạy local hoặc Colab)
```bash
# Cách 1: Dùng Google Gemini API (MIỄN PHÍ 100%)
export GEMINI_API_KEY="AIzaSy..."   # Lấy miễn phí tại https://aistudio.google.com/
# Trên Windows PowerShell: $env:GEMINI_API_KEY="AIzaSy..."
# Trên Windows CMD: set GEMINI_API_KEY=AIzaSy...

# Cách 2: Dùng OpenAI API (Có tính phí)
# export OPENAI_API_KEY=sk-...

python 01_retrieval/generate_training_data.py       # Tự động dùng Gemini 2.0 Flash nếu có GEMINI_API_KEY
python 01_retrieval/validate_synthetic_data.py      # BẮT BUỘC — lọc bỏ mẫu gán nhãn sai
```

### Phần C — Fine-tune + Eval (chạy trên Kaggle T4x2 hoặc GPU ≥16GB VRAM)
```bash
python 01_retrieval/train_qlora.py           # ~3 epoch, theo dõi eval_loss để tránh overfit
python 01_retrieval/eval_router_accuracy.py  # BẮT BUỘC — cần tự viết retrieval_eval_manual.jsonl trước
```

## 3 lỗi đã sửa so với code Kaggle bạn dán ban đầu

| Lỗi | Code gốc | Đã sửa |
|---|---|---|
| Sai tên cột | `doc['text']` | `row['chunk']` (verify qua HF dataset card) |
| Tokenizer thừa/thiếu nhất quán | tải `nltk.punkt` nhưng dùng `.split()` | bỏ nltk, dùng 1 regex tokenizer dùng chung cho build lẫn validate |
| Thiếu `doc_id` xuyên suốt | không có | `"<arxiv_id>::chunk_<n>"` sinh 1 lần, dùng chung BM25 + FAISS |

## Vì sao cần bước "validate_synthetic_data.py" mà tài liệu gốc không nhắc tới

GPT-4o có thể tự tin gán `"tool_selected": "bm25"` cho 1 câu hỏi, nhưng khi chạy BM25
**thật** trên corpus, chunk gốc dùng để sinh câu hỏi đó lại không nằm trong top-10 kết quả
(câu hỏi bị diễn đạt mơ hồ hơn dự tính, hoặc từ khoá không đủ đặc trưng). Nếu bỏ qua bước
này, model SFT học phải các cặp (câu hỏi, nhãn) sai — hậu quả là Router kém đi thay vì tốt
lên. Script tự động chạy lại đúng tool đã gán nhãn trên index thật, loại các mẫu không khớp.

## Vì sao "eval_router_accuracy.py" cần 1 tập eval viết tay, không dùng lại eval set lúc train

Eval set trích từ `train_test_split` lúc `train_qlora.py` vẫn do GPT-4o sinh — cùng
"văn phong" với tập train. Nếu chỉ đo trên tập này, số liệu đẹp có thể chỉ phản ánh việc
model học thuộc phong cách câu hỏi của GPT-4o, không phản ánh khả năng tổng quát hoá sang
câu hỏi thật của người dùng cuối. Bắt buộc phải có 1 tập nhỏ (50-100 câu) do người review
tự viết tay, độc lập hoàn toàn với pipeline sinh data.

## Giới hạn cần biết

Toàn bộ code trong thư mục này được rà soát logic và kiểm tra cú pháp (`py_compile`)
nhưng **chưa được chạy thực tế** — môi trường soạn thảo không có GPU, không có mạng ra
`pypi.org`/`huggingface.co`/OpenAI API. Khi bạn chạy trên Kaggle/máy có GPU, nếu gặp lỗi
runtime (khác lỗi cú pháp), gửi lại log để sửa trực tiếp trên hành vi thật thay vì đoán.

## Tiếp theo

Sau khi Retrieval Agent đạt Tool Decision Accuracy + Critique Precision chấp nhận được
(khuyến nghị ngưỡng tối thiểu: ≥80% accuracy, ≥75% precision trên tập eval viết tay — điều
chỉnh theo yêu cầu thực tế của dự án), chuyển sang Agent 2 (Reader — fine-tune LayoutLMv3,
KHÁC hoàn toàn về kỹ thuật train so với Retrieval, sẽ trình bày ở phần kế tiếp).
