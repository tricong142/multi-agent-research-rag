"""
01_retrieval/train_qlora.py

Fine-tune Qwen2.5-7B-Instruct bằng QLoRA để làm Router+Critique cho
Retrieval Agent, đúng theo Bước 3 của tài liệu.

CHẠY TRÊN: Kaggle T4 x2 (dùng 1 GPU là đủ cho 7B QLoRA 4-bit, GPU thứ 2
để dành chạy song song việc khác nếu cần) hoặc máy có GPU >=16GB VRAM.

QUYẾT ĐỊNH THIẾT KẾ:
1. Chọn Qwen2.5-7B-Instruct thay vì Llama-3.1-8B: Qwen2.5 có hiệu năng
   tốt hơn ở các tác vụ structured output/JSON tiếng Anh lẫn đa ngôn ngữ
   trong cùng tầm 7-8B, và license Apache 2.0 dễ dùng thương mại hơn.
2. LoRA rank=16, alpha=32 (tỷ lệ alpha/rank = 2, theo khuyến nghị phổ
   biến) - áp dụng lên q_proj, k_proj, v_proj, o_proj (attention) VÀ
   gate_proj, up_proj, down_proj (MLP) - tài liệu gốc yêu cầu train cả
   Attention + MLP, không chỉ Attention.
3. Format prompt: dùng đúng chat template của Qwen2.5, nhồi
   history_trials vào system/user prompt dưới dạng có cấu trúc rõ ràng,
   để model học cách "đọc" lịch sử thất bại trước khi quyết định.
4. Packing=False: vì mỗi mẫu là 1 đơn vị quyết định độc lập (không nên
   ghép nhiều mẫu vào 1 sequence dài, sẽ làm model học nhầm ngữ cảnh
   giữa các câu hỏi không liên quan).
"""

import os
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
# FIX OOM: Khóa chỉ dùng GPU 0. Trên Kaggle T4x2, nếu không set thì
# device_map có thể cố split sang GPU 1 gây tràn bộ nhớ.
os.environ["CUDA_VISIBLE_DEVICES"] = "0"

import json
from pathlib import Path

import torch
from datasets import Dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)
from trl import SFTTrainer, SFTConfig

try:
    BASE_DIR = Path(__file__).parent
except NameError:
    BASE_DIR = Path.cwd()

MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct"

possible_data_paths = [
    BASE_DIR / "data" / "retrieval_sft_train_validated.jsonl",
    BASE_DIR / "01_retrieval" / "data" / "retrieval_sft_train_validated.jsonl",
    Path("/kaggle/working/retrieval_sft_train_validated.jsonl"),
    Path("//kaggle/input/datasets/trcng23/validated25/retrieval_sft_train_validated.jsonl"),
    Path("./retrieval_sft_train_validated.jsonl"),
]
DATA_PATH = next((p for p in possible_data_paths if p.exists()), possible_data_paths[0])
OUTPUT_DIR = BASE_DIR / "checkpoints" / "retrieval_router_critique_qlora"

SYSTEM_PROMPT = """Bạn là Router + Critic của một hệ thống Retrieval Agent.
Nhiệm vụ: nhìn vào câu hỏi (sub_query) và lịch sử các lần thử trước
(history_trials), chọn 1 công cụ tìm kiếm phù hợp nhất trong tập
{bm25, dense, hyde, rewrite, decompose}, và tự phê bình mức độ liên
quan của kết quả trả về.

Luôn trả lời bằng JSON đúng định dạng:
{"thought": "...", "tool_selected": "...", "critique_is_relevant": true/false, "critique_reason": "..."}
"""


def format_sample(sample: dict) -> dict:
    """Chuyển 1 dòng data thành format chat (messages) chuẩn để SFTTrainer dùng."""
    history_text = "Chưa có lần thử nào trước đó."
    if sample["history_trials"]:
        lines = []
        for i, trial in enumerate(sample["history_trials"], 1):
            lines.append(
                f"  Lần {i}: tool={trial['tool']}, "
                f"is_relevant={trial['is_relevant']}, reason=\"{trial['reason']}\""
            )
        history_text = "\n".join(lines)

    user_content = f"Câu hỏi: {sample['sub_query']}\n\nLịch sử các lần thử trước:\n{history_text}"
    assistant_content = json.dumps(sample["target_output"], ensure_ascii=False)

    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": assistant_content},
        ]
    }


def load_dataset_for_training(path: Path) -> Dataset:
    with open(path, "r", encoding="utf-8") as f:
        raw_samples = [json.loads(line) for line in f]
    formatted = [format_sample(s) for s in raw_samples]
    return Dataset.from_list(formatted)


def main():
    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"Không tìm thấy {DATA_PATH}. Chạy generate_training_data.py rồi "
            f"validate_synthetic_data.py trước."
        )

    dataset = load_dataset_for_training(DATA_PATH)
    print(f"Tổng số mẫu train: {len(dataset)}")

    # Chia 90/10 để có eval set theo dõi overfitting trong lúc train
    split = dataset.train_test_split(test_size=0.1, seed=42)
    train_dataset, eval_dataset = split["train"], split["test"]
    print(f"Train: {len(train_dataset)} | Eval: {len(eval_dataset)}")

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    # === AGGRESSIVE CLEANUP: xóa model cũ nếu user re-run mà không restart kernel ===
    import gc
    # Xoá mọi biến toàn cục kiểu nn.Module (model cũ) trong VRAM
    for var_name in list(globals().keys()):
        obj = globals().get(var_name)
        if isinstance(obj, torch.nn.Module):
            try:
                del globals()[var_name]
            except Exception:
                pass
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        allocated = torch.cuda.memory_allocated() / 1024**3
        total = torch.cuda.get_device_properties(0).total_memory / 1024**3
        print(f"[GPU CHECK] VRAM đã dùng: {allocated:.2f} GB / {total:.2f} GB tổng")
        if allocated > 2.0:
            print("⚠️  CẢNH BÁO: Vẫn còn >2GB VRAM đang bị chiếm.")
            print("   → Hãy RESTART KERNEL (Runtime → Restart session) rồi chạy lại!")
            print("   → Nếu không restart, sẽ OOM khi load model.")
            return  # thoát sớm, không cố load model vào GPU đã đầy

    print(f"Đang tải model {MODEL_NAME} ở chế độ 4-bit...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # CUDA_VISIBLE_DEVICES="0" ở trên đã khóa chỉ thấy 1 GPU,
    # nên device_map="auto" giờ chỉ load lên GPU 0 duy nhất.
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        quantization_config=bnb_config,
        device_map="auto",
        torch_dtype=torch.bfloat16,
        low_cpu_mem_usage=True,
    )
    # FIX: tắt KV-cache - bắt buộc khi dùng gradient checkpointing
    model.config.use_cache = False
    model = prepare_model_for_kbit_training(
        model,
        use_gradient_checkpointing=True,  # giảm ~40% activation memory
    )

    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        # Train cả Attention lẫn MLP như tài liệu yêu cầu, không chỉ Attention
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # TRL >= 0.13: max_length và packing là tham số của SFTConfig,
    # KHÔNG phải của SFTTrainer.__init__() nữa.
    training_args = SFTConfig(
        output_dir=str(OUTPUT_DIR),
        num_train_epochs=3,
        # FIX OOM: bs=1 thay vì 2 để an toàn trên T4 16GB
        # grad_accum tăng lên 16 để giữ nguyên effective batch size = 16
        per_device_train_batch_size=1,
        gradient_accumulation_steps=16,  # effective batch size = 1 * 16 = 16
        learning_rate=2e-4,
        lr_scheduler_type="cosine",
        warmup_steps=10,
        logging_steps=10,
        eval_strategy="steps",
        eval_steps=50,
        save_strategy="steps",
        save_steps=50,
        save_total_limit=3,              # chỉ giữ 3 checkpoint gần nhất, tránh đầy ổ đĩa Kaggle
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        bf16=True,
        # FIX OOM: paged_adamw_8bit thay vì AdamW thường
        # giảm ~2-3GB optimizer state (AdamW lưu 2 moment fp32 = nặng)
        optim="paged_adamw_8bit",
        # FIX OOM: gradient checkpointing giảm ~40% activation memory
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},  # tương thích PEFT
        report_to="none",                # tắt wandb mặc định, bật lại nếu bạn có tài khoản riêng
        max_length=1024,             # đủ cho system+user+assistant của tác vụ này
        packing=False,                   # mỗi sample là 1 quyết định độc lập, không pack
    )

    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        processing_class=tokenizer,
        # dataset_text_field removed: TRL >= 0.13 auto-detects the 'messages'
        # column (chat format). Passing it explicitly causes TypeError.
    )

    print("\nBắt đầu train...")
    trainer.train()

    trainer.save_model(str(OUTPUT_DIR / "final"))
    tokenizer.save_pretrained(str(OUTPUT_DIR / "final"))
    print(f"\nĐã lưu model -> {OUTPUT_DIR / 'final'}")
    print("\n[BƯỚC TIẾP THEO BẮT BUỘC] Chạy eval_router_accuracy.py để đo Tool Decision")
    print("Accuracy và Critique Precision trên eval set TRƯỚC KHI đưa vào LangGraph.")


if __name__ == "__main__":
    main()
