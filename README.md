<<<<<<< HEAD
"# multi-agent-research-rag" 
=======
# Train Agent 3: Summarizer Agent (Generator + Critic độc lập)

## Phân định nơi chạy (đúng yêu cầu: tách rõ Kaggle vs Local)

| File | Chạy ở | Cần gì |
|---|---|---|
| `config.py` | Cả 2 | Không cần gì đặc biệt |
| `generate_training_data.py` | **Local** | `OPENAI_API_KEY`, không cần GPU |
| `validate_evidence_span.py` | **Local** | Không cần gì (string matching thuần) |
| `generator/train_generator_qlora.py` | **Kaggle** (GPU T4x2) | GPU ≥16GB VRAM |
| `critic/train_critic_qlora.py` | **Kaggle** (GPU T4x2) | GPU ≥16GB VRAM |
| `merge_lora_weights.py` | **Kaggle** | GPU để load model 7B |
| `eval_generator_critic.py` | **Kaggle** | GPU (load 2 model đã merge) |
| `llm_judge_eval.py` | **Local** | `OPENAI_API_KEY`, không cần GPU |
| `node.py` | Cả 2 | Import thuần, không tự chạy |
| `notebooks/00_quick_inference_check.py` | **Kaggle** (copy từng cell, không `python file.py`) | GPU |

## Thứ tự chạy đầy đủ

```bash
# --- LOCAL ---
export OPENAI_API_KEY=sk-...
python generate_training_data.py         # ~8-15 USD, sinh 800 mẫu 3 case
python validate_evidence_span.py         # BẮT BUỘC, lọc evidence không verbatim

# --- upload thư mục 03_summarizer/ (đã có data/*.jsonl) lên Kaggle ---

# --- KAGGLE (GPU T4 x2) ---
python generator/train_generator_qlora.py
python critic/train_critic_qlora.py
python merge_lora_weights.py
# copy-paste notebooks/00_quick_inference_check.py để test nhanh bằng mắt
python eval_generator_critic.py          # cần data/summarizer_eval_manual.jsonl viết tay trước

# --- tải data/eval_results.jsonl về LOCAL ---

# --- LOCAL ---
python llm_judge_eval.py                 # cần bổ sung "expected_answer" vào eval_manual.jsonl
```

## Dùng chung corpus với Agent 1 (Retrieval)

`config.CORPUS_PATH` trỏ thẳng vào `kb_indexing/data/corpus.jsonl` — **không tự tải/xử lý lại**
dataset `ai-arxiv-chunked`. Nếu file không tồn tại, nghĩa là chưa chạy xong pipeline
`kb_indexing/scripts/01_prepare_corpus.py` của Agent 1, phải chạy xong đó trước.

## 3 quyết định thiết kế cốt lõi

1. **Generator và Critic là 2 adapter LoRA độc lập, merge thành 2 model riêng.**
   Không gộp chung 1 model đa nhiệm — tránh rủi ro "tự thỏa hiệp" (model tự sinh answer rồi
   tự chấm đạt để tránh phải sửa) khi 2 vai trò share cùng trọng số.

2. **3 case data (fully_grounded, partial_grounding, unanswerable) được dùng KHÁC NHAU
   giữa Generator và Critic:**
   - Generator chỉ học từ Case A (trả lời đúng) và Case C (biết từ chối) — **không học
     trực tiếp từ Case B** vì đó là ví dụ hành vi xấu (overreaching answer).
   - Critic học từ CẢ 3 case, đặc biệt Case B là case quan trọng nhất — dạy nhận diện
     hallucination tinh vi (answer đúng hướng nhưng vượt quá evidence thật).

3. **`node.py` không bao giờ raise exception hay treo vô hạn** — đúng nguyên tắc "lối
   thoát an toàn" đã thống nhất từ Bước 1 (Retrieval Agent): hết `MAX_INTERNAL_RETRY` vẫn
   phải trả kết quả, kèm `confidence="low"` để tầng ngoài biết mà xử lý thận trọng hơn.

## Việc ĐÃ thực sự verify được (không chỉ rà soát logic bằng mắt)

`validate_evidence_span.is_verbatim_match()` đã được unit test trực tiếp với 3 case:
exact substring, near-exact (khác dấu câu), và paraphrase (phải bị từ chối) — cả 3 đều
cho kết quả đúng như thiết kế. Đây là phần duy nhất trong toàn bộ pipeline không cần
GPU/mạng nên tự chạy kiểm chứng được ngay trong quá trình soạn code.

## Giới hạn cần biết trước khi chạy

Các phần còn lại (sinh data qua OpenAI API, train QLoRA, merge, eval) **chưa được chạy
thực tế** — môi trường soạn thảo không có GPU và không có mạng ra ngoài (`pypi.org`,
`huggingface.co` bị chặn ở tầng egress). Đã kiểm tra cú pháp toàn bộ bằng `py_compile`
(pass 100%) và rà soát logic thủ công, nhưng runtime thật (đặc biệt là chất lượng data
GPT-4o sinh ra, tốc độ train trên T4x2, độ chính xác model sau fine-tune) cần bạn tự
chạy và gửi lại log nếu có lỗi để sửa trên hành vi thật.

## Tiếp theo

Agent 4 (Fact-Checker) khác biệt kỹ thuật lớn nhất trong 5 agent: dùng SciBERT
(encoder classifier trên SciFact), không phải LLM decoder như Retrieval/Summarizer —
cấu trúc thư mục và pipeline train sẽ khác hẳn, không tái sử dụng được `train_*_qlora.py`
pattern đã dùng ở đây.
>>>>>>> b68ce42 (feat: complete implementation for agent 03 summarizer)
