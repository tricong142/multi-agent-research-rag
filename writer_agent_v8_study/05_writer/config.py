"""Measured starting points, not claims of optimal hardware performance."""
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
ADAPTER_DIR = ROOT / "checkpoints" / "writer_qlora"
MAX_INTERNAL_RETRY = 3  # revisions after the initial draft; zero is allowed


@dataclass(frozen=True)
class ModelConfig:
    base_model: str = "Qwen/Qwen2.5-1.5B-Instruct"
    revision: str = "main"
    load_in_4bit: bool = True
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    target_modules: str = "all-linear"
    attn_implementation: str = "sdpa"


@dataclass(frozen=True)
class TrainingConfig:
    max_seq_length: int = 1536
    # Train one epoch, evaluate, then resume to two only when held-out metrics
    # justify the extra pass.
    num_train_epochs: float = 1.0
    per_device_train_batch_size: int = 2
    per_device_eval_batch_size: int = 1
    gradient_accumulation_steps: int = 8
    learning_rate: float = 2e-4
    seed: int = 42
    gradient_checkpointing: bool = True
    logging_steps: int = 10
    save_steps: int = 250
    eval_steps: int = 250
    eval_strategy: str = "no"
    save_strategy: str = "epoch"
    optimizer: str = "adamw_torch_fused"
    warmup_ratio: float = 0.03
    weight_decay: float = 0.01
