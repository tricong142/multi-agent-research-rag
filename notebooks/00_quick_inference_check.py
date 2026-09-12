# ============================================================
# notebooks/00_quick_inference_check.py
# CHẠY Ở: KAGGLE NOTEBOOK, copy từng cell — không chạy bằng `python file.py`
# (giống quy ước đã dùng ở Agent 1: đây là nội dung cell, không phải script CLI)
#
# MỤC ĐÍCH: test nhanh 3-5 câu hỏi thủ công qua SummarizerNode NGAY SAU
# khi merge xong 2 model, để bằng mắt kiểm tra hành vi (đọc log lý luận
# qua từng vòng lặp) TRƯỚC KHI chạy eval_generator_critic.py đầy đủ (tốn
# thời gian hơn) hoặc ráp vào LangGraph.
# ============================================================

# ============================================================
# CELL 1 — Load 2 model đã merge
# ============================================================
import sys
sys.path.insert(0, "/kaggle/working/03_summarizer")  # sửa path cho khớp nơi bạn upload code

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
import config
from node import SummarizerNode

def load_merged_model(model_dir):
    tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
    model = AutoModelForCausalLM.from_pretrained(
        str(model_dir), torch_dtype=torch.bfloat16, device_map="auto"
    )
    model.eval()
    return model, tokenizer

print("Đang tải Generator...")
generator_model, generator_tokenizer = load_merged_model(config.GENERATOR_MERGED_DIR)
print("Đang tải Critic...")
critic_model, critic_tokenizer = load_merged_model(config.CRITIC_MERGED_DIR)

node = SummarizerNode(generator_model, generator_tokenizer, critic_model, critic_tokenizer)
print("Sẵn sàng test.")

# ============================================================
# CELL 2 — Test case 1: câu hỏi có evidence rõ ràng (kỳ vọng: is_supported=True, 1 lần thử)
# ============================================================
context_1 = """
LoRA (Low-Rank Adaptation) freezes the pretrained model weights and injects
trainable rank decomposition matrices into each layer of the Transformer
architecture, greatly reducing the number of trainable parameters for
downstream tasks.
"""
question_1 = "LoRA hoạt động bằng cách nào để giảm số lượng tham số cần train?"

result_1 = node.run(context=context_1, question=question_1)
print(f"Answer: {result_1.answer}")
print(f"Evidence: {result_1.evidence_spans}")
print(f"Is supported: {result_1.is_supported} | Confidence: {result_1.confidence}")
print(f"Số lần thử nội bộ: {len(result_1.reasoning_trace)}")
for i, trial in enumerate(result_1.reasoning_trace, 1):
    print(f"  Lần {i}: is_supported={trial.is_supported}, action={trial.action}, reason={trial.critique_reason}")

# ============================================================
# CELL 3 — Test case 2: câu hỏi KHÔNG có evidence trong context
# (kỳ vọng: model từ chối trả lời thay vì suy diễn, is_supported=True vì
#  từ chối đúng cách được coi là hành vi đúng)
# ============================================================
context_2 = """
The Transformer architecture relies entirely on attention mechanisms,
dispensing with recurrence and convolutions entirely.
"""
question_2 = "Tác giả của paper LoRA là ai?"  # context không hề nói về LoRA hay tác giả

result_2 = node.run(context=context_2, question=question_2)
print(f"Answer: {result_2.answer}")
print(f"Evidence: {result_2.evidence_spans}")
print(f"Is supported: {result_2.is_supported} | Confidence: {result_2.confidence}")

# ============================================================
# CELL 4 — Test case 3: câu hỏi "bẫy" đòi hỏi suy diễn vượt evidence
# (kỳ vọng: LẦN ĐẦU model có thể trả lời vượt evidence, Critic phát hiện,
#  quay lại sinh answer lượt 2 chặt chẽ hơn - quan sát reasoning_trace
#  để xác nhận vòng lặp có hoạt động đúng không)
# ============================================================
context_3 = """
FlashAttention reduces memory usage by avoiding materialization of the
large attention matrix, using tiling and recomputation techniques.
"""
question_3 = "FlashAttention nhanh hơn attention thông thường bao nhiêu lần trên GPU A100?"
# Context KHÔNG nói con số cụ thể - đây là bẫy suy diễn

result_3 = node.run(context=context_3, question=question_3)
print(f"Answer cuối: {result_3.answer}")
print(f"Số lần thử nội bộ: {len(result_3.reasoning_trace)}  <- nếu > 1, vòng lặp đã kích hoạt đúng")
for i, trial in enumerate(result_3.reasoning_trace, 1):
    print(f"  Lần {i}: answer='{trial.answer[:80]}...', is_supported={trial.is_supported}, action={trial.action}")
