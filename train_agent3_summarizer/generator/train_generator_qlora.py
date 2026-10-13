"""
train_generator_qlora.py - Huấn luyện Generator bằng phương pháp QLoRA

FIX DỨT ĐIỂM 2 LỖI LIÊN TIẾP:
  1) "_amp_foreach_non_finite_check_and_unscale_cuda not implemented for BFloat16"
  2) "ValueError: Attempting to unscale FP16 gradients"
- NGUYÊN NHÂN GỐC (cả 2 lỗi cùng 1 nguồn): dùng fp16=True (kích hoạt
  torch.amp.GradScaler) trên pipeline QLoRA + gradient checkpointing, nơi
  param/gradient bị trộn lẫn BF16 và FP16 tuỳ layer. GradScaler chỉ chấp
  nhận gradient FP32 duy nhất -> vá kiểu gì cũng crash ở điểm khác.
- GIẢI PHÁP DỨT ĐIỂM: bỏ hẳn fp16=True/GradScaler, luôn dùng bf16=True.
  BF16 không cần loss-scaling nên HF Trainer không khởi tạo GradScaler
  -> toàn bộ lớp lỗi "Attempting to unscale ..." không còn đường xảy ra.
  Trên T4 (CC 7.5): BF16 chạy chậm hơn FP16-native (không có tensor core
  BF16 chuyên dụng) nhưng ỔN ĐỊNH, không crash.
  Trên A100+ (CC 8+): BF16 chạy với hardware tensor cores, tốc độ tối ưu.
"""

import os
# BẮT BUỘC ĐẶT ĐẦU FILE
os.environ["CUDA_VISIBLE_DEVICES"] = "0"
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

import sys
import json
import inspect
import subprocess
import functools
from pathlib import Path

# ============================================================
# 1. TỰ ĐỘNG CÀI ĐẶT THƯ VIỆN KHI THIẾU
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

# Tối ưu hóa benchmark cuDNN
torch.backends.cudnn.benchmark = True

# Monkey-patch xử lý bug 'functools.partial' của TRL
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

# ============================================================
# ĐÃ BỎ MONKEY-PATCH GRADSCALER (2 lần vá trước đều chỉ chữa triệu chứng,
# không chữa gốc):
#   - GradScaler chỉ tồn tại để làm loss-scaling cho FP16 (chống underflow).
#   - BF16 có cùng dải exponent với FP32 → không cần loss-scaling → không
#     cần GradScaler.
#   - HF Trainer chỉ khởi tạo GradScaler khi TrainingArguments.fp16=True.
#     Nếu chỉ dùng bf16=True, GradScaler không bao giờ được tạo ra, nên
#     toàn bộ code path unscale_/clip_grad_norm_ từng gây crash (cả BF16
#     lẫn FP16) sẽ không bao giờ chạy tới nữa.
# → Fix triệt để: luôn train bằng BF16, bỏ hẳn nhánh fp16/GradScaler
#   (xem phần PRECISION trong main()).
# ============================================================


try:
    from trl import SFTConfig, SFTTrainer
    HAS_SFT_CONFIG = True
except ImportError:
    from trl import SFTTrainer
    HAS_SFT_CONFIG = False

# ============================================================
# 2. XÁC ĐỊNH MÔI TRƯỜNG & PROMPT
# ============================================================
IS_KAGGLE = Path("/kaggle").exists()

if "__file__" in globals():
    CURRENT_DIR = Path(__file__).resolve().parent
else:
    CURRENT_DIR = Path.cwd().resolve()

try:
    sys.path.insert(0, str(CURRENT_DIR.parent))
    sys.path.insert(0, str(CURRENT_DIR))
    import config
    from generator.prompts import GENERATOR_SYSTEM_PROMPT, build_generator_user_prompt
    HAS_LOCAL_MODULES = True
except ImportError:
    HAS_LOCAL_MODULES = False

if not HAS_LOCAL_MODULES or "GENERATOR_SYSTEM_PROMPT" not in globals():
    GENERATOR_SYSTEM_PROMPT = """Bạn là Generator của một hệ thống Summarizer Agent.
Nhiệm vụ: đọc context (đoạn văn bản trích từ paper AI) và câu hỏi, sinh
ra câu trả lời NGẮN GỌN, CHÍNH XÁC, kèm theo evidence_span - PHẢI là 1
câu trích dẫn NGUYÊN VĂN (verbatim, copy chính xác) từ context, làm căn
cứ cho câu trả lời. TUYỆT ĐỐI KHÔNG được trả lời bằng thông tin không có
trong context, kể cả khi bạn biết câu trả lời đúng từ kiến thức khác.
Nếu context không đủ thông tin để trả lời, phải nói rõ điều đó thay vì
suy diễn thêm.

Nếu được cung cấp thêm "instruction bổ sung" (do Critic yêu cầu ở lượt
thử trước), PHẢI tuân theo instruction đó khi sinh lại câu trả lời.

Luôn trả lời bằng JSON đúng định dạng:
{"answer": "...", "evidence_spans": ["..."]}
"""

    def build_generator_user_prompt(context: str, question: str, retry_instruction: str = None) -> str:
        prompt = f'Context:\n"""\n{context}\n"""\n\nCâu hỏi: {question}'
        if retry_instruction:
            prompt += f"\n\nInstruction bổ sung (từ lượt phê bình trước): {retry_instruction}"
        return prompt

# ============================================================
# 3. SIÊU THAM SỐ TỐI ƯU
# ============================================================
BASE_MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct"

LORA_RANK = 16
LORA_ALPHA = 32
LORA_DROPOUT = 0.05
LORA_TARGET_MODULES = [
    "q_proj", "k_proj", "v_proj", "o_proj",
    "gate_proj", "up_proj", "down_proj",
]

MAX_SEQ_LENGTH = 512
NUM_TRAIN_EPOCHS = 3
PER_DEVICE_TRAIN_BATCH_SIZE = 2
GRADIENT_ACCUMULATION_STEPS = 8
LEARNING_RATE = 2e-4

if IS_KAGGLE:
    OUTPUT_DIR = Path("/kaggle/working/checkpoints/generator_qlora")
else:
    OUTPUT_DIR = CURRENT_DIR / "checkpoints" / "generator_qlora"

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
    elif case_type == "unanswerable":
        answer = "Context được cung cấp không chứa thông tin để trả lời câu hỏi này."
        evidence_spans = []
    elif case_type == "partial_grounding":
        return None
    else:
        return None

    user_prompt = build_generator_user_prompt(sample["context"], sample["question"])
    assistant_content = json.dumps(
        {"answer": answer, "evidence_spans": evidence_spans}, ensure_ascii=False
    )

    return {
        "messages": [
            {"role": "system", "content": GENERATOR_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": assistant_content},
        ]
    }

def load_dataset_for_training(path: Path) -> Dataset:
    with open(path, "r", encoding="utf-8") as f:
        raw_samples = [json.loads(line) for line in f if line.strip()]

    formatted = [format_sample(s) for s in raw_samples]
    formatted = [s for s in formatted if s is not None]

    print(f"[*] Tổng mẫu đọc vào: {len(raw_samples)}")
    print(f"[*] Mẫu dùng train Generator (đã loại partial_grounding): {len(formatted)}")
    return Dataset.from_list(formatted)

# ============================================================
# 6. PIPELINE HUẤN LUYỆN CHÍNH
# ============================================================
def main():
    if not torch.cuda.is_available():
        raise RuntimeError("[LỖI]: Bạn chưa bật GPU trên Kaggle! Hãy bật GPU trong Settings -> Accelerator.")

    torch.cuda.empty_cache()

    gpu_name = torch.cuda.get_device_name(0)
    vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
    major_cc, minor_cc = torch.cuda.get_device_capability(0)
    print(f"[*] GPU khả dụng: {gpu_name} ({vram_gb:.2f} GB VRAM) - Compute Capability {major_cc}.{minor_cc}")

    # ============================================================
    # PRECISION: QUAY LẠI BF16 ỔN ĐỊNH.
    #
    # Bằng chứng thực nghiệm sau 2 lần thử FP16 sạch (không hack dtype):
    #   - Lần 1: crash "not implemented for BFloat16" (y hệt bug gốc)
    #   - Lần 2 (trước đó, có hack): crash "Attempting to unscale FP16 gradients"
    # => Có tham số trainable bị lệch dtype một cách không nhất quán do
    #    xung đột thư viện (Qwen2.5 + bitsandbytes + peft/trl version hiện
    #    tại), KHÔNG PHẢI do cách patch. Ngừng đoán-vá FP16, quay lại BF16
    #    (đã chứng minh chạy ổn định, chỉ chậm hơn do T4 thiếu tensor core
    #    BF16) và tối ưu tốc độ bằng các đòn bẩy khác không đụng precision.
    # ============================================================
    use_bf16 = True
    use_fp16 = False
    compute_dtype = torch.bfloat16
    print(f"[*] Cấu hình Precision: fp16={use_fp16}, bf16={use_bf16}, compute_dtype={compute_dtype} (ổn định, ưu tiên KHÔNG CRASH)")

    data_file = resolve_data_path()
    dataset = load_dataset_for_training(data_file)
    split = dataset.train_test_split(test_size=0.1, seed=42)
    train_dataset, eval_dataset = split["train"], split["test"]
    print(f"[*] Train set: {len(train_dataset)} | Eval set: {len(eval_dataset)}")

    effective_batch_size = PER_DEVICE_TRAIN_BATCH_SIZE * GRADIENT_ACCUMULATION_STEPS
    steps_per_epoch = max(1, len(train_dataset) // effective_batch_size)
    total_steps = steps_per_epoch * NUM_TRAIN_EPOCHS
    warmup_steps = max(1, int(total_steps * 0.05))

    print(f"\n=======================================================")
    print(f"[*] TỔNG TIẾN TRÌNH TRAIN: {total_steps} STEPS!")
    print(f"=======================================================\n")

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=compute_dtype,
        bnb_4bit_use_double_quant=True,
    )
    # GHI CHÚ TỐC ĐỘ (không ảnh hưởng crash/precision):
    # Nếu sau khi chạy BF16 ổn định mà vẫn muốn giảm thêm ETA, có thể thử
    # lần lượt (mỗi lần 1 thay đổi để biết cái nào thực sự có tác dụng):
    #   1) gradient_checkpointing_kwargs={"use_reentrant": True} thay vì False
    #      (một số version peft/transformers có bug hiệu năng với
    #      use_reentrant=False khi kết hợp 4-bit + LoRA).
    #   2) Giảm LORA_TARGET_MODULES xuống còn ["q_proj","v_proj"] thay vì
    #      cả 7 module (giảm số phép tính LoRA mỗi step, đánh đổi chất
    #      lượng nhẹ).
    #   3) Giảm MAX_SEQ_LENGTH nếu dữ liệu cho phép.
    #   4) Nếu VRAM còn dư (theo dõi qua nvidia-smi), tăng
    #      PER_DEVICE_TRAIN_BATCH_SIZE và giảm GRADIENT_ACCUMULATION_STEPS
    #      tương ứng để giữ effective batch size, giảm overhead mỗi step.

    print(f"[*] Đang load Tokenizer & Base Model {BASE_MODEL_NAME}...")
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_NAME, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    device_map = {"": 0}

    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL_NAME,
        quantization_config=bnb_config,
        device_map=device_map,
        torch_dtype=compute_dtype,
        trust_remote_code=True,
    )

    model.config.use_cache = False
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)

    lora_config = LoraConfig(
        r=LORA_RANK,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=LORA_TARGET_MODULES,
    )
    model = get_peft_model(model, lora_config)

    # DIAGNOSTIC: kiểm tra dtype thực tế của param trainable (LoRA) ngay
    # sau khi attach — nếu thấy dtype khác FP32 ở đây, ta biết ngay PEFT
    # không tự upcast như kỳ vọng, cần xử lý TRƯỚC khi train thay vì đợi
    # crash giữa chừng.
    trainable_dtypes = {}
    for name, param in model.named_parameters():
        if param.requires_grad:
            trainable_dtypes[str(param.dtype)] = trainable_dtypes.get(str(param.dtype), 0) + 1
    print(f"[DIAGNOSTIC] Dtype của các param trainable (LoRA): {trainable_dtypes}")
    if use_fp16 and any(dt != "torch.float32" for dt in trainable_dtypes):
        print("[CẢNH BÁO] Có param trainable KHÔNG phải FP32 trong khi fp16=True — "
              "rất có thể sẽ crash 'Attempting to unscale FP16 gradients' lần nữa. "
              "Nếu thấy cảnh báo này, dừng lại và báo lại cho tôi kèm dòng "
              "DIAGNOSTIC ở trên thay vì chạy tiếp.")

    # Không còn vòng lặp ép dtype thủ công: model load thẳng BF16
    # (torch_dtype=compute_dtype=bfloat16), LoRA adapter do PEFT tự tạo
    # cũng nhất quán BF16/FP32 theo cơ chế autocast_adapter_dtype mặc định
    # của PEFT — không có GradScaler nên không có ràng buộc "phải FP32"
    # như khi dùng fp16=True nữa.

    # Khóa chặn DataParallel
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
        "logging_steps": 5,
        "eval_strategy": "epoch",
        "save_strategy": "epoch",
        "save_total_limit": 1,
        "load_best_model_at_end": True,
        "metric_for_best_model": "eval_loss",
        "bf16": use_bf16,
        "fp16": use_fp16,
        "optim": "paged_adamw_8bit",
        "gradient_checkpointing": True,
        "gradient_checkpointing_kwargs": {"use_reentrant": False},
        "group_by_length": True,
        "dataloader_num_workers": 2,
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
    print("[*] BẮT ĐẦU HUẤN LUYỆN GENERATOR QLORA...")
    print("=======================================================")
    trainer.train()

    final_path = OUTPUT_DIR / "final"
    trainer.save_model(str(final_path))
    tokenizer.save_pretrained(str(final_path))
    print(f"\n[HOÀN TẤT] Đã lưu Generator adapter tại: {final_path}")

if __name__ == "__main__":
    main()