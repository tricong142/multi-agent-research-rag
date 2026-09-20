"""Single source of configuration for the Fact-Checker agent."""

from __future__ import annotations

import os
from pathlib import Path


FACTCHECKER_ROOT = Path(__file__).resolve().parent
DATA_DIR = FACTCHECKER_ROOT / "data"
CHECKPOINT_DIR = FACTCHECKER_ROOT / "checkpoints"

TRAIN_DATA_PATH = DATA_DIR / "scifact_train.jsonl"
DEV_DATA_PATH = DATA_DIR / "scifact_dev.jsonl"
REJECTED_DATA_PATH = DATA_DIR / "rejected_rows.jsonl"
EVAL_PREDICTIONS_PATH = DATA_DIR / "eval_predictions.jsonl"

ADAPTER_DIR = CHECKPOINT_DIR / "factchecker_qlora"
MERGED_MODEL_DIR = CHECKPOINT_DIR / "factchecker_merged"

# Override these via environment variables when deploying a different model.
BASE_MODEL_NAME = os.getenv("FACTCHECKER_BASE_MODEL", "Qwen/Qwen2.5-7B-Instruct")

MODEL_PATH = os.getenv("FACTCHECKER_MODEL_PATH", str(MERGED_MODEL_DIR))

LABELS = ("support", "contradict", "not_enough_info")
RECOMMENDED_ACTIONS = ("expand_context", "other_source", "ask_clarify")

# Local retry is only for malformed/invalid LLM output. It is unrelated to the
# orchestrator's retry_count and never causes graph routing.
MAX_INTERNAL_RETRY = int(os.getenv("FACTCHECKER_MAX_INTERNAL_RETRY", "3"))
CONFIDENCE_THRESHOLD = float(os.getenv("FACTCHECKER_CONFIDENCE_THRESHOLD", "0.70"))

MAX_NEW_TOKENS_JUDGE = 384
MAX_NEW_TOKENS_CONFIDENCE = 192
MAX_NEW_TOKENS_ACTION = 192

# QLoRA defaults. Tune against dev metrics; these are starting values, not a
# claim that they are optimal for SciFact.
LORA_RANK = 16
LORA_ALPHA = 32
LORA_DROPOUT = 0.05
LORA_TARGET_MODULES = (
    "q_proj", "k_proj", "v_proj", "o_proj",
    "gate_proj", "up_proj", "down_proj",
)
MAX_SEQ_LENGTH = 2048
NUM_TRAIN_EPOCHS = 3
PER_DEVICE_TRAIN_BATCH_SIZE = 2
GRADIENT_ACCUMULATION_STEPS = 8
LEARNING_RATE = 2e-4
SEED = 42


def validate_config() -> None:
    if MAX_INTERNAL_RETRY < 1:
        raise ValueError("MAX_INTERNAL_RETRY must be >= 1")
    if not 0.0 <= CONFIDENCE_THRESHOLD <= 1.0:
        raise ValueError("CONFIDENCE_THRESHOLD must be in [0, 1]")


validate_config()
