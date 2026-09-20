"""Notebook-friendly smoke check. Run cells after setting MODEL_PATH."""

# %%
from pathlib import Path
import sys

ROOT = Path.cwd()
if not (ROOT / "inference").exists():
    ROOT = ROOT / "04_factchecker"
sys.path.insert(0, str(ROOT))

# %%
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

import config
from inference import (
    ActionRecommender,
    ConfidenceEstimator,
    FactCheckJudge,
    TransformersJSONBackend,
)
from node import FactCheckerNode

MODEL_PATH = config.MODEL_PATH
tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_PATH, device_map="auto", torch_dtype="auto", trust_remote_code=True
).eval()
backend = TransformersJSONBackend(model, tokenizer)
node = FactCheckerNode(
    FactCheckJudge(backend),
    ConfidenceEstimator(backend),
    ActionRecommender(backend),
)

# %%
state = {
    "claim": "The intervention reduced mortality.",
    "context": "The study reported no statistically significant difference in mortality.",
}
result = node(state)
print(result)
assert result["fact_check_label"] in config.LABELS
assert 0.0 <= result["confidence_score"] <= 1.0
assert result["recommended_action"] in (*config.RECOMMENDED_ACTIONS, None)
