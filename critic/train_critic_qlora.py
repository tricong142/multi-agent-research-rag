"""
03_summarizer/critic/train_critic_qlora.py

CHẠY Ở: KAGGLE NOTEBOOK (GPU T4 x2 hoặc tương đương).
    python critic/train_critic_qlora.py

KHÁC BIỆT CỐT LÕI với train_generator_qlora.py: Critic KHÔNG học sinh
văn bản, chỉ học ĐÁNH GIÁ văn bản có sẵn. Vì vậy input của Critic luôn
gồm ĐẦY ĐỦ (context, question, answer, evidence_spans) - answer ở đây
có thể là answer TỐT (Case A) hoặc answer XẤU cố tình (Case B) - Critic
phải phân biệt được.

CÁCH DÙNG 3 CASE (ngược lại với Generator):
  - fully_grounded (Case A): input = (context, question, target_answer
    ĐÚNG, evidence ĐÚNG) -> target: is_supported=true.
  - partial_grounding (Case B): input = (context, question,
    overreaching_answer SAI cố tình, evidence CÓ THẬT nhưng chỉ hỗ trợ
    1 phần) -> target: is_supported=false, action dựa theo
    missing_part_reason. ĐÂY LÀ CASE QUAN TRỌNG NHẤT của Critic - dạy
    nhận diện hallucination tinh vi.
  - unanswerable (Case C): input = (context không liên quan, question,
    answer="Context không chứa thông tin...", evidence=[]) -> target:
    is_supported=true (vì answer "từ chối" chính là câu trả lời ĐÚNG
    cho tình huống không có evidence - Critic phải công nhận việc từ
    chối là hành vi đúng, không phải lỗi).
"""

import json
import sys
from pathlib import Path

import torch
from datasets import Dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TrainingArguments,
)
from trl import SFTTrainer

sys.path.insert(0, str(Path(__file__).parent.parent))
import config  # noqa: E402
from critic.prompts import CRITIC_SYSTEM_PROMPT, build_critic_user_prompt  # noqa: E402


def format_sample(sample: dict) -> dict | None:
    case_type = sample["case_type"]

    if case_type == "fully_grounded":
        answer = sample["target_answer"]
        evidence_spans = [sample["target_evidence_span"]]
        target = {"is_supported": True, "reason": "Evidence trích dẫn hỗ trợ đầy đủ câu trả lời.", "action": ""}

    elif case_type == "partial_grounding":
        answer = sample["target_answer"]  # đây chính là overreaching_answer đã lưu ở field này
        evidence_spans = [sample["target_evidence_span"]]
        reason = sample.get(
            "expected_critique_reason_hint",
            "Answer vượt quá phạm vi thông tin mà evidence thực sự chứng minh.",
        )
        target = {"is_supported": False, "reason": reason, "action": "rewrite"}

    elif case_type == "unanswerable":
        answer = "Context được cung cấp không chứa thông tin để trả lời câu hỏi này."
        evidence_spans = []
        target = {
            "is_supported": True,   # từ chối đúng cách = hành vi ĐÚNG, không phải lỗi
            "reason": "Answer từ chối phù hợp vì context không liên quan tới câu hỏi.",
            "action": "",
        }

    else:
        return None

    user_prompt = build_critic_user_prompt(sample["context"], sample["question"], answer, evidence_spans)
    assistant_content = json.dumps(target, ensure_ascii=False)

    return {
        "messages": [
            {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": assistant_content},
        ]
    }


def load_dataset_for_training(path: Path) -> Dataset:
    with open(path, "r", encoding="utf-8") as f:
        raw_samples = [json.loads(line) for line in f]
    formatted = [format_sample(s) for s in raw_samples]
    formatted = [s for s in formatted if s is not None]
    print(f"Tổng mẫu dùng train Critic (cả 3 case): {len(formatted)}")
    return Dataset.from_list(formatted)


def main():
    if not config.VALIDATED_DATA_PATH.exists():
        raise FileNotFoundError(
            f"Không tìm thấy {config.VALIDATED_DATA_PATH}. Chạy generate_training_data.py "
            f"rồi validate_evidence_span.py trước."
        )

    dataset = load_dataset_for_training(config.VALIDATED_DATA_PATH)
    split = dataset.train_test_split(test_size=0.1, seed=42)
    train_dataset, eval_dataset = split["train"], split["test"]
    print(f"Train: {len(train_dataset)} | Eval: {len(eval_dataset)}")

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    print(f"Đang tải base model {config.BASE_MODEL_NAME} ở chế độ 4-bit...")
    tokenizer = AutoTokenizer.from_pretrained(config.BASE_MODEL_NAME)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # QUAN TRỌNG: load 1 INSTANCE MODEL MỚI hoàn toàn, KHÔNG load lại từ
    # generator checkpoint. Critic phải là 1 adapter độc lập gắn trên
    # CÙNG base model gốc (chưa fine-tune), để đảm bảo tính độc lập đánh
    # giá đã thống nhất từ đầu (không kế thừa "thói quen" của Generator).
    model = AutoModelForCausalLM.from_pretrained(
        config.BASE_MODEL_NAME,
        quantization_config=bnb_config,
        device_map="auto",
        torch_dtype=torch.bfloat16,
    )
    model = prepare_model_for_kbit_training(model)

    lora_config = LoraConfig(
        r=config.LORA_RANK,
        lora_alpha=config.LORA_ALPHA,
        lora_dropout=config.LORA_DROPOUT,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=config.LORA_TARGET_MODULES,
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    training_args = TrainingArguments(
        output_dir=str(config.CRITIC_ADAPTER_DIR),
        num_train_epochs=config.NUM_TRAIN_EPOCHS,
        per_device_train_batch_size=config.PER_DEVICE_TRAIN_BATCH_SIZE,
        gradient_accumulation_steps=config.GRADIENT_ACCUMULATION_STEPS,
        learning_rate=config.LEARNING_RATE,
        lr_scheduler_type="cosine",
        warmup_ratio=0.03,
        logging_steps=10,
        eval_strategy="steps",
        eval_steps=config.EVAL_STEPS,
        save_strategy="steps",
        save_steps=config.SAVE_STEPS,
        save_total_limit=config.SAVE_TOTAL_LIMIT,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        bf16=True,
        report_to="none",
    )

    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        tokenizer=tokenizer,
        max_seq_length=config.MAX_SEQ_LENGTH,
        packing=False,
        dataset_text_field="messages",
    )

    print("\nBắt đầu train Critic...")
    trainer.train()

    final_path = config.CRITIC_ADAPTER_DIR / "final"
    trainer.save_model(str(final_path))
    tokenizer.save_pretrained(str(final_path))
    print(f"\nĐã lưu Critic adapter -> {final_path}")
    print("[TIẾP THEO] Chạy merge_lora_weights.py rồi eval_generator_critic.py")


if __name__ == "__main__":
    main()
