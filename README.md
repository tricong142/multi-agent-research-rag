---
base_model: Qwen/Qwen2.5-7B-Instruct
library_name: peft
pipeline_tag: text-generation
tags:
- base_model:adapter:Qwen/Qwen2.5-7B-Instruct
- lora
- qlora
- sft
- transformers
- trl
- rag
- router
- critique
---

# QLoRA Adapter: Retrieval Router & Critique (Agent 1)

Đây là LoRA adapter được fine-tune từ mô hình nền **`Qwen/Qwen2.5-7B-Instruct`** phục vụ cho **Agent 1 (Retrieval Agent)** trong hệ thống Multi-Agent Research RAG.

Mô hình thực hiện 2 nhiệm vụ chính:
1. **Dynamic Retrieval Routing:** Phân tích truy vấn và lịch sử tìm kiếm để quyết định chiến lược tìm kiếm phù hợp (`bm25`, `faiss`, hoặc `hybrid`).
2. **Document Critique:** Tự động đánh giá chất lượng tài liệu trích xuất, xác định tài liệu có đủ thông tin trả lời truy vấn hay cần tinh chỉnh truy vấn để tìm lại.

---

## 📌 Thông tin mô hình

- **Mô hình gốc (Base Model):** `Qwen/Qwen2.5-7B-Instruct`
- **Phương pháp huấn luyện:** QLoRA 4-bit (BitsAndBytes NF4 + Double Quantization)
- **Thư viện sử dụng:** `peft`, `transformers`, `trl`, `torch`, `bitsandbytes`
- **Cấu hình LoRA:**
  - LoRA Rank ($r$): `16`
  - LoRA Alpha ($\alpha$): `32`
  - Dropout: `0.05`
  - Target Modules: Attention (`q_proj`, `k_proj`, `v_proj`, `o_proj`) & MLP (`gate_proj`, `up_proj`, `down_proj`)

---

## 🚀 Hướng dẫn nạp và sử dụng Adapter

```python
import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

# 1. Cấu hình Quantization 4-bit
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.float16,
    bnb_4bit_use_double_quant=True,
)

# 2. Tải base model và tokenizer
base_model_name = "Qwen/Qwen2.5-7B-Instruct"
tokenizer = AutoTokenizer.from_pretrained(base_model_name, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(
    base_model_name,
    quantization_config=bnb_config,
    device_map="auto",
    trust_remote_code=True,
)

# 3. Nạp LoRA adapter
adapter_dir = "01_retrieval/checkpoints/retrieval_router_critique_qlora/final"
model = PeftModel.from_pretrained(model, adapter_dir)
model.eval()

# 4. Định dạng prompt
system_prompt = "You are an expert Retrieval Router and Document Critique agent."
user_query = "What is the attention mechanism in Transformer architecture?"

messages = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": f"Decide retrieval strategy for query: {user_query}"}
]

prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

# 5. Sinh kết quả
with torch.no_grad():
    outputs = model.generate(
        **inputs,
        max_new_tokens=512,
        temperature=0.1,
        do_sample=False,
    )

response = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
print(response)
```

---

## 📊 Định dạng dữ liệu đầu ra (Structured Output)

Mô hình được huấn luyện để sinh ra định dạng JSON suy luận từng bước (Chain-of-Thought):

```json
{
  "thought_process": "Truy vấn chứa thuật ngữ chuyên ngành chính xác, phù hợp nhất với tìm kiếm từ khóa kết hợp ngữ nghĩa.",
  "tool_selected": "hybrid",
  "search_query": "attention mechanism Transformer architecture",
  "is_retrieval_sufficient": true,
  "critique_reasoning": "Tài liệu truy xuất chứa đầy đủ định nghĩa và công thức toán học cần thiết."
}
```

---

## ⚙️ Chi tiết huấn luyện

- **Dữ liệu huấn luyện:** Tập `retrieval_sft_train_validated.jsonl` đã được lọc qua pipeline kiểm chứng tính đúng đắn trên chỉ mục thực tế.
- **Tối ưu hóa:** Optimizer `paged_adamw_8bit`, Gradient Checkpointing kích hoạt.
- **Môi trường thực thi:** GPU hỗ trợ CUDA (Kaggle T4 x2 / VRAM ≥ 16GB).
