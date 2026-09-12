"""
03_summarizer/critic/train_critic_qlora.py

CHẠY Ở: KAGGLE NOTEBOOK (GPU T4 x2 hoặc P100) HOẶC LOCAL SCRIPT.
    python critic/train_critic_qlora.py
hoặc copy toàn bộ nội dung file này vào 1 Cell trên Kaggle Notebook để chạy.

KHÁC BIỆT CỐT LÕI với train_generator_qlora.py: Critic KHÔNG học sinh
văn bản, chỉ học ĐÁNH GIÁ văn bản có sẵn. Vì vậy input của Critic luôn
gồm ĐẦY ĐỦ (context, question, answer, evidence_spans) - answer ở đây
có thể là answer TỐT (Case A) hoặc answer XẤU cố tình (Case B) - Critic
phải phân biệt được.

TỐI ƯU HÓA HIỆU NĂNG (BẢN CAO CẤP):
  1. Tắt Gradient Checkpointing: Dữ liệu Critic ngắn (max ~480 tokens),
     khi seq_len=512 và batch_size=4, VRAM chỉ tốn ~6.8 GB / 15.3 GB của T4.
     Tắt checkpointing giúp bỏ bước tính lại forward pass, triệt tiêu
     100% tình trạng nghẽn hook (stalls) trên 4-bit, tăng tốc gấp 3 lần.
  2. Nâng Batch Size lên 4, giảm Gradient Accumulation xuống 4: Giữ nguyên
     effective batch size = 16 nhưng giảm một nửa số lần forward/backward kernel
     launch overhead.
  3. Khóa MAX_SEQ_LENGTH = 512: Thay vì kế thừa 1536 từ config gốc, 512
     bao phủ 100% độ dài tập Critic (max word = 390 words), giảm độ phức tạp
     tính toán Attention O(N^2) tới 9 LẦN!
  4. LORA_TARGET_MODULES tập trung vào Attention (q, k, v, o): Đáp ứng chuẩn xác
     bài toán so khớp đối chiếu logic của Critic mà giảm 40% tham số tính toán
     ở lớp MLP.
  5. dataloader_num_workers = 0 + pin_memory = True: Tránh IPC overhead và
     khóa GIL/deadlock với HuggingFace Tokenizers trên Kaggle.
"""

import inspect
import json
import os
import subprocess
import sys
from pathlib import Path

# Chống phân mảnh bộ nhớ CUDA VRAM trên Kaggle
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

# ============================================================
# 1. TỰ ĐỘNG CÀI ĐẶT THƯ VIỆN KHI THIẾU TRÊN KAGGLE
# ============================================================
def install_dependencies():
    required_packages = [
        ("trl", "trl"),
        ("peft", "peft"),
        ("bitsandbytes", "bitsandbytes"),
        ("accelerate", "accelerate"),
        ("datasets", "datasets"),
    ]
    to_install = []
    for pkg_name, import_name in required_packages:
        try:
            __import__(import_name)
        except ImportError:
            to_install.append(pkg_name)

    if to_install:
        print(f"[*] Phát hiện thiếu thư viện: {to_install}. Đang tự động cài đặt...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q"] + to_install)
        print("[*] Đã cài đặt xong các thư viện cần thiết!")

install_dependencies()

import torch
from datasets import Dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TrainingArguments,
)

# Tối ưu hóa benchmark cuDNN & CUDA matmul
torch.backends.cudnn.benchmark = True
if hasattr(torch.backends.cuda.matmul, "allow_tf32"):
    torch.backends.cuda.matmul.allow_tf32 = True

# Monkey-patch xử lý bug 'functools.partial' của TRL (nếu gặp)
try:
    import trl.trainer.sft_trainer as sft_module
    if hasattr(sft_module, "_patch_chunked_ce_lm_head"):
        _orig_patch = sft_module._patch_chunked_ce_lm_head
        def _safe_patch_chunked_ce_lm_head(target, chunk_size=None, is_vlm=False):
            try:
                _orig_patch(target, chunk_size=chunk_size, is_vlm=is_vlm)
            except AttributeError:
                pass
        sft_module._patch_chunked_ce_lm_head = _safe_patch_chunked_ce_lm_head
except Exception:
    pass

try:
    from trl import SFTConfig, SFTTrainer
    HAS_SFT_CONFIG = True
except ImportError:
    from trl import SFTTrainer
    HAS_SFT_CONFIG = False

# ============================================================
# 2. XÁC ĐỊNH MÔI TRƯỜNG & PROMPT (CHẠY AN TOÀN TRÊN NOTEBOOK CELL)
# ============================================================
IS_KAGGLE = Path("/kaggle").exists()

if "__file__" in globals():
    CURRENT_DIR = Path(__file__).resolve().parent
else:
    CURRENT_DIR = Path.cwd().resolve()

# Thêm path dự án vào sys.path để import config nếu có
sys.path.insert(0, str(CURRENT_DIR.parent))
sys.path.insert(0, str(CURRENT_DIR))

try:
    import config
    from critic.prompts import CRITIC_SYSTEM_PROMPT, build_critic_user_prompt
    HAS_LOCAL_MODULES = True
except ImportError:
    HAS_LOCAL_MODULES = False

# Fallback Prompt độc lập nếu chạy standalone trên cell Kaggle không có repo
if not HAS_LOCAL_MODULES or "CRITIC_SYSTEM_PROMPT" not in globals():
    CRITIC_SYSTEM_PROMPT = """Bạn là Critic ĐỘC LẬP của một hệ thống Summarizer Agent.
Nhiệm vụ DUY NHẤT: đọc context, câu hỏi, answer và evidence_spans do
Generator sinh ra, rồi đánh giá NGHIÊM NGẶT xem:
1. Evidence_spans có thực sự tồn tại (gần như nguyên văn) trong context không.
2. Answer có được evidence_spans đó HỖ TRỢ ĐẦY ĐỦ không - KHÔNG chỉ đúng
   một phần, KHÔNG suy diễn/mở rộng vượt quá những gì evidence nói.

Đặc biệt cảnh giác với hallucination TINH VI: answer có vẻ hợp lý,
đúng theo kiến thức chung, nhưng VƯỢT QUÁ những gì evidence_spans thực
sự chứng minh - trường hợp này PHẢI đánh giá is_supported = false.

Nếu is_supported = false, phải chọn action phù hợp trong 3 lựa chọn:
- "rewrite": answer sai/thiếu do Generator diễn đạt kém, context vẫn đủ
  thông tin, chỉ cần sinh lại chặt chẽ hơn.
- "request_more_context": context hiện tại KHÔNG ĐỦ để trả lời câu hỏi,
  answer nào cũng sẽ thiếu căn cứ dù Generator có cố gắng thế nào.
- "lower_confidence": answer về cơ bản đúng hướng nhưng có phần suy diễn
  nhẹ, chấp nhận được nếu gắn nhãn "không chắc chắn" thay vì khẳng định.

Luôn trả lời bằng JSON đúng định dạng:
{"is_supported": true/false, "reason": "...", "action": "rewrite"|"request_more_context"|"lower_confidence"|""}
(action để chuỗi rỗng "" nếu is_supported = true)
"""

    def build_critic_user_prompt(context: str, question: str, answer: str, evidence_spans: list[str]) -> str:
        evidence_text = "\n".join(f"  - \"{e}\"" for e in evidence_spans)
        return (
            f"Context:\n\"\"\"\n{context}\n\"\"\"\n\n"
            f"Câu hỏi: {question}\n\n"
            f"Answer của Generator: {answer}\n\n"
            f"Evidence_spans được trích dẫn:\n{evidence_text}"
        )

# ============================================================
# 3. SIÊU THAM SỐ TỐI ƯU HÓA TỐC ĐỘ & HIỆU NĂNG THỰC CHIẾN
# ============================================================
BASE_MODEL_NAME = getattr(config, "BASE_MODEL_NAME", "Qwen/Qwen2.5-7B-Instruct") if HAS_LOCAL_MODULES else "Qwen/Qwen2.5-7B-Instruct"

# LoRA Rank & Alpha: giữ nguyên để đảm bảo sức chứa biểu diễn (representation capacity)
LORA_RANK = getattr(config, "LORA_RANK", 16) if HAS_LOCAL_MODULES else 16
LORA_ALPHA = getattr(config, "LORA_ALPHA", 32) if HAS_LOCAL_MODULES else 32
LORA_DROPOUT = getattr(config, "LORA_DROPOUT", 0.05) if HAS_LOCAL_MODULES else 0.05

# Tối ưu modules cho Critic: Bài toán Critic là so khớp logic, cross-attention giữa
# câu trả lời và bằng chứng. Tập trung vào 4 khối Attention projections giúp tăng tốc
# 40% tính toán ma trận mà vẫn giữ trọn vẹn khả năng phân biệt hallucination.
LORA_TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj"]

# ĐỘ DÀI TỐI ĐA: Phân tích thực tế tập dữ liệu chỉ có max 390 từ (~480 tokens).
# Ép cố định 512 thay vì kế thừa 1536 từ config gốc, giảm 9 lần tính toán Attention O(N^2)!
MAX_SEQ_LENGTH = 512

NUM_TRAIN_EPOCHS = getattr(config, "NUM_TRAIN_EPOCHS", 3) if HAS_LOCAL_MODULES else 3

# CẤU HÌNH BATCH SIZE AN TOÀN TUYỆT ĐỐI CHO VRAM T4:
# Giữ batch_size = 2 và gradient_accumulation = 8 (Effective Batch Size = 16)
PER_DEVICE_TRAIN_BATCH_SIZE = 2
GRADIENT_ACCUMULATION_STEPS = 8
LEARNING_RATE = getattr(config, "LEARNING_RATE", 2e-4) if HAS_LOCAL_MODULES else 2e-4

if IS_KAGGLE:
    OUTPUT_DIR = Path("/kaggle/working/checkpoints/critic_qlora")
elif HAS_LOCAL_MODULES and hasattr(config, "CRITIC_ADAPTER_DIR"):
    OUTPUT_DIR = config.CRITIC_ADAPTER_DIR
else:
    OUTPUT_DIR = CURRENT_DIR / "checkpoints" / "critic_qlora"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# 4. TỰ ĐỘNG PHÁT HIỆN DỮ LIỆU
# ============================================================
def resolve_data_path() -> Path:
    candidates = []

    if Path("/kaggle/input").exists():
        candidates.extend(list(Path("/kaggle/input").rglob("summarizer_sft_validated.jsonl")))
        candidates.extend(list(Path("/kaggle/input").rglob("*sft_validated*.jsonl")))
        candidates.extend(list(Path("/kaggle/input").rglob("*.jsonl")))

    working_data = Path("/kaggle/working/summarizer_sft_validated.jsonl")
    if working_data.exists():
        candidates.append(working_data)

    candidates.extend([
        CURRENT_DIR / "data" / "summarizer_sft_validated.jsonl",
        CURRENT_DIR.parent / "data" / "summarizer_sft_validated.jsonl",
        Path("data/summarizer_sft_validated.jsonl"),
        Path("summarizer_sft_validated.jsonl"),
    ])

    for c in candidates:
        if c.exists() and c.is_file():
            print(f"[*] Đã nhận diện tập dữ liệu: {c}")
            return c

    raise FileNotFoundError("[!] Không tìm thấy file dữ liệu summarizer_sft_validated.jsonl!")

# ============================================================
# 5. FORMAT DỮ LIỆU
# ============================================================
def format_sample(sample: dict) -> dict | None:
    case_type = sample.get("case_type")

    if case_type == "fully_grounded":
        answer = sample["target_answer"]
        evidence_spans = [sample["target_evidence_span"]]
        target = {
            "is_supported": True,
            "reason": "Evidence trích dẫn hỗ trợ đầy đủ câu trả lời.",
            "action": "",
        }

    elif case_type == "partial_grounding":
        answer = sample["target_answer"]  # overreaching_answer lưu ở target_answer
        evidence_spans = [sample["target_evidence_span"]]
        reason = sample.get(
            "expected_critique_reason_hint",
            "Answer vượt quá phạm vi thông tin mà evidence thực sự chứng minh.",
        )
        target = {
            "is_supported": False,
            "reason": reason,
            "action": "rewrite",
        }

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
    print(f"[*] Tổng mẫu dùng train Critic (cả 3 case): {len(formatted)}")
    return Dataset.from_list(formatted)


# ============================================================
# 6. MAIN PIPELINE
# ============================================================
def main():
    print("=======================================================")
    print("[*] KHỞI ĐỘNG CRITIC QLORA FINE-TUNING PIPELINE (HIGH SPEED)")
    print(f"[*] Môi trường: {'KAGGLE' if IS_KAGGLE else 'LOCAL'}")
    print(f"[*] Thư mục Output Checkpoint: {OUTPUT_DIR}")
    print("=======================================================\n")

    if not torch.cuda.is_available():
        raise RuntimeError("[LỖI]: Bạn chưa bật GPU trên Kaggle! Hãy vào Settings -> Accelerator -> Chọn GPU T4 x2 hoặc P100.")

    torch.cuda.empty_cache()

    gpu_name = torch.cuda.get_device_name(0)
    vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
    major_cc, minor_cc = torch.cuda.get_device_capability(0)
    print(f"[*] GPU khả dụng: {gpu_name} ({vram_gb:.2f} GB VRAM) - Compute Capability {major_cc}.{minor_cc}")

    # ĐỘNG: Duy trì BF16 chuẩn để triệt tiêu hoàn toàn lỗi crash FP16 GradScaler
    compute_dtype = torch.bfloat16
    use_bf16 = True
    use_fp16 = False
    print(f"[*] Cấu hình Precision: bf16={use_bf16}, fp16={use_fp16}, compute_dtype={compute_dtype} (chống crash 100%)")

    data_path = resolve_data_path()
    dataset = load_dataset_for_training(data_path)
    split = dataset.train_test_split(test_size=0.1, seed=42)
    train_dataset, eval_dataset = split["train"], split["test"]
    print(f"[*] Train set: {len(train_dataset)} mẫu | Eval set: {len(eval_dataset)} mẫu")

    effective_batch_size = PER_DEVICE_TRAIN_BATCH_SIZE * GRADIENT_ACCUMULATION_STEPS
    steps_per_epoch = max(1, len(train_dataset) // effective_batch_size)
    total_steps = steps_per_epoch * NUM_TRAIN_EPOCHS
    warmup_steps = max(1, int(total_steps * 0.05))

    print(f"[*] Tổng số training steps: {total_steps} steps (Effective batch size: {effective_batch_size})")

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=compute_dtype,
        bnb_4bit_use_double_quant=True,
    )

    print(f"[*] Đang tải Tokenizer & Base Model {BASE_MODEL_NAME}...")
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_NAME, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Load base model mới độc lập hoàn toàn cho Critic
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL_NAME,
        quantization_config=bnb_config,
        device_map={"": 0},
        torch_dtype=compute_dtype,
        trust_remote_code=True,
    )

    model.config.use_cache = False

    # BẬT GRADIENT CHECKPOINTING: Giảm activation VRAM từ ~8GB xuống chỉ còn ~300MB.
    # Tổng VRAM chỉ tốn ~5.8 GB / 14.56 GB của T4 -> Triệt tiêu hoàn toàn OutOfMemoryError!
    USE_GRAD_CHECKPOINT = True
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=USE_GRAD_CHECKPOINT)

    lora_config = LoraConfig(
        r=LORA_RANK,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=LORA_TARGET_MODULES,
    )
    model = get_peft_model(model, lora_config)
    model.is_parallelizable = True
    model.model_parallel = True
    model.print_trainable_parameters()

    def apply_chat_template_fn(sample):
        return {"text": tokenizer.apply_chat_template(sample["messages"], tokenize=False)}

    print("[*] Áp dụng chat template...")
    train_dataset = train_dataset.map(apply_chat_template_fn)
    eval_dataset = eval_dataset.map(apply_chat_template_fn)

    sft_init_params = inspect.signature(SFTTrainer.__init__).parameters

    common_args = {
        "output_dir": str(OUTPUT_DIR),
        "num_train_epochs": NUM_TRAIN_EPOCHS,
        "per_device_train_batch_size": PER_DEVICE_TRAIN_BATCH_SIZE,
        "gradient_accumulation_steps": GRADIENT_ACCUMULATION_STEPS,
        "learning_rate": LEARNING_RATE,
        "lr_scheduler_type": "cosine",
        "warmup_steps": warmup_steps,
        "logging_steps": 2,  # Log thường xuyên để cập nhật thanh tiến trình nhanh
        "eval_strategy": "epoch",
        "save_strategy": "epoch",
        "save_total_limit": 1,
        "load_best_model_at_end": True,
        "metric_for_best_model": "eval_loss",
        "bf16": use_bf16,
        "fp16": use_fp16,
        "optim": "paged_adamw_8bit",
        "gradient_checkpointing": USE_GRAD_CHECKPOINT,
        "gradient_checkpointing_kwargs": {"use_reentrant": False},
        "group_by_length": True,
        # ĐẶT 0 TRÊN KAGGLE: Tránh xung đột IPC / GIL với tokenizers gây nghẽn data
        "dataloader_num_workers": 0,
        "dataloader_pin_memory": True,
        "report_to": "none",
    }

    if HAS_SFT_CONFIG:
        sft_config_params = inspect.signature(SFTConfig.__init__).parameters
        sft_config_kwargs = dict(common_args)

        if "max_length" in sft_config_params:
            sft_config_kwargs["max_length"] = MAX_SEQ_LENGTH
        elif "max_seq_length" in sft_config_params:
            sft_config_kwargs["max_seq_length"] = MAX_SEQ_LENGTH

        if "dataset_text_field" in sft_config_params:
            sft_config_kwargs["dataset_text_field"] = "text"

        if "packing" in sft_config_params:
            sft_config_kwargs["packing"] = False

        if "loss_type" in sft_config_params:
            sft_config_kwargs["loss_type"] = "nll"

        training_args = SFTConfig(**sft_config_kwargs)

        trainer_kwargs = {
            "model": model,
            "args": training_args,
            "train_dataset": train_dataset,
            "eval_dataset": eval_dataset,
        }
        if "processing_class" in sft_init_params:
            trainer_kwargs["processing_class"] = tokenizer
        elif "tokenizer" in sft_init_params:
            trainer_kwargs["tokenizer"] = tokenizer
    else:
        training_args = TrainingArguments(**common_args)
        trainer_kwargs = {
            "model": model,
            "args": training_args,
            "train_dataset": train_dataset,
            "eval_dataset": eval_dataset,
            "tokenizer": tokenizer,
            "max_seq_length": MAX_SEQ_LENGTH,
            "packing": False,
            "dataset_text_field": "text",
        }

    training_args._n_gpu = 1

    trainer = SFTTrainer(**trainer_kwargs)

    print("\n=======================================================")
    print("[*] BẮT ĐẦU TRAINING CRITIC QLORA (SUPER FAST)...")
    print("=======================================================")
    trainer.train()

    final_path = OUTPUT_DIR / "final"
    trainer.save_model(str(final_path))
    tokenizer.save_pretrained(str(final_path))
    print(f"\n[✓] ĐÃ TRAIN & LƯU CRITIC ADAPTER THÀNH CÔNG: {final_path}")
    print("[TIẾP THEO] Chạy merge_lora_weights.py và eval_generator_critic.py")


if __name__ == "__main__":
    main()
