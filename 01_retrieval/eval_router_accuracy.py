"""
Evaluate Agent 1 Retrieval Router.

Default mode is lightweight and deterministic:
    python 01_retrieval/eval_router_accuracy.py

Kaggle/model mode keeps the LoRA adapter for thought/reason text, then applies
router_policy as a final guardrail for a LangGraph-ready contract:
    python 01_retrieval/eval_router_accuracy.py --use-model
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import re
import subprocess
import sys
import importlib
import importlib.util
from pathlib import Path
from typing import Any

RUNNING_AS_NOTEBOOK_CELL = "__file__" not in globals()
SCRIPT_DIR = Path(__file__).resolve().parent if not RUNNING_AS_NOTEBOOK_CELL else Path.cwd()

try:
    from router_policy import VALID_TOOLS, make_decision
except ModuleNotFoundError:
    if "VALID_TOOLS" not in globals() or "make_decision" not in globals():
        sys.path.append(str(SCRIPT_DIR))
        from router_policy import VALID_TOOLS, make_decision


BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"
ADAPTER_PATH = "/kaggle/input/datasets/trcng23/eval000"
KAGGLE_EVAL_PATH = Path("/kaggle/input/datasets/trcng23/eval25/retrieval_eval_manual.jsonl")
LOCAL_EVAL_PATH = SCRIPT_DIR / "data" / "retrieval_eval_manual.jsonl"

SYSTEM_PROMPT = """Bạn là Router + Critic của một hệ thống Retrieval Agent.
Nhiệm vụ: nhìn vào câu hỏi (sub_query) và lịch sử các lần thử trước
(history_trials), chọn 1 công cụ tìm kiếm phù hợp nhất trong tập
{bm25, dense, hyde, rewrite, decompose}, và tự phê bình mức độ liên
quan của kết quả trả về.

Luôn trả lời bằng JSON đúng định dạng:
{"thought": "...", "tool_selected": "...", "critique_is_relevant": true/false, "critique_reason": "..."}

Quy tắc chọn tool:
- bm25: câu hỏi fact/keyword/thuật ngữ cụ thể, acronym, tên riêng, ngày tháng.
- dense: câu hỏi ngữ nghĩa/khái niệm cần hiểu quan hệ nhưng không quá mơ hồ.
- hyde: câu hỏi why/how chuyên sâu cần tạo giả thuyết tài liệu, hoặc nhiều lần retrieve thất bại.
- rewrite: câu hỏi mơ hồ, nói vòng, sai thực thể/nghĩa sau lần retrieve trước.
- decompose: câu hỏi nhiều phần, so sánh, phân tích nhiều khía cạnh/nguyên nhân/hệ quả.
"""


def extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in model output: {text[:200]}")
    return json.loads(match.group(0))


def normalize_model_prediction(raw: dict[str, Any]) -> dict[str, Any]:
    tool = str(raw.get("tool_selected", "")).strip().lower()
    raw["tool_selected"] = tool if tool in VALID_TOOLS else ""
    raw["critique_is_relevant"] = bool(raw.get("critique_is_relevant", True))
    raw["thought"] = str(raw.get("thought", ""))
    raw["critique_reason"] = str(raw.get("critique_reason", ""))
    return raw


def load_model():
    os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

    try:
        import torch
    except AttributeError as exc:
        if "partially initialized module 'torch'" in str(exc):
            for name in list(sys.modules):
                if name == "torch" or name.startswith("torch."):
                    sys.modules.pop(name, None)
            import torch
        else:
            raise

    if importlib.util.find_spec("bitsandbytes") is None:
        subprocess.run([sys.executable, "-m", "pip", "install", "bitsandbytes>=0.46.1", "-q"], check=True)
        importlib.invalidate_caches()
    print("bitsandbytes ready")

    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    gc.collect()
    torch.cuda.empty_cache()
    free, total = torch.cuda.mem_get_info()
    print(f"VRAM free: {free/1e9:.2f} GB / {total/1e9:.2f} GB")

    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    print("Loading base model (4-bit)...")
    base = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        quantization_config=bnb,
        device_map="cuda:0",
        low_cpu_mem_usage=True,
    )
    print("Loading LoRA adapter...")
    model = PeftModel.from_pretrained(base, ADAPTER_PATH)
    model.eval()
    gc.collect()
    torch.cuda.empty_cache()
    print(f"Ready. VRAM used: {torch.cuda.memory_allocated()/1e9:.2f} GB")
    return model, tokenizer, torch


def predict_with_model(model, tokenizer, torch, sub_query: str, history_trials: list[dict[str, Any]]) -> dict[str, Any]:
    history_text = "Chưa có lần thử nào trước đó."
    if history_trials:
        history_text = "\n".join(
            f"  Lần {i}: tool={t['tool']}, is_relevant={t['is_relevant']}, reason=\"{t['reason']}\""
            for i, t in enumerate(history_trials, 1)
        )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Câu hỏi: {sub_query}\n\nLịch sử các lần thử trước:\n{history_text}"},
    ]
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(prompt, return_tensors="pt").to("cuda:0")
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=256, do_sample=False)
    text = tokenizer.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    try:
        return normalize_model_prediction(extract_json_object(text))
    except Exception:
        return {"_parse_error": True, "_raw": text}


def predict(sub_query: str, history_trials: list[dict[str, Any]], model_bundle=None) -> dict[str, Any]:
    model_prediction = None
    if model_bundle is not None:
        model, tokenizer, torch = model_bundle
        model_prediction = predict_with_model(model, tokenizer, torch, sub_query, history_trials)
        if model_prediction.get("_parse_error"):
            return model_prediction
    return make_decision(sub_query, history_trials, model_prediction=model_prediction)


def resolve_eval_path(path_arg: str | None) -> Path:
    if path_arg:
        return Path(path_arg)
    return KAGGLE_EVAL_PATH if KAGGLE_EVAL_PATH.exists() else LOCAL_EVAL_PATH


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-path", default=None)
    parser.add_argument(
        "--use-model",
        action="store_true",
        help="Load Qwen + LoRA adapter. Tool decision is still guarded by router_policy.",
    )
    args, _ = parser.parse_known_args()

    eval_path = resolve_eval_path(args.eval_path)
    with open(eval_path, "r", encoding="utf-8") as f:
        samples = [json.loads(line) for line in f]

    use_model = args.use_model or RUNNING_AS_NOTEBOOK_CELL
    model_bundle = load_model() if use_model else None

    n_total = len(samples)
    n_correct_tool = 0
    n_parse_errors = 0
    n_pred_irrel = 0
    n_pred_irrel_correct = 0

    print(f"\nĐánh giá {n_total} mẫu từ {eval_path}...")
    for i, sample in enumerate(samples, 1):
        pred = predict(sample["sub_query"], sample.get("history_trials", []), model_bundle=model_bundle)
        if pred.get("_parse_error"):
            n_parse_errors += 1
            print(f"  [{i}/{n_total}] Parse error")
            continue

        correct = pred["tool_selected"] == sample["expected_tool"]
        n_correct_tool += int(correct)
        if pred["critique_is_relevant"] is False:
            n_pred_irrel += 1
            if sample["expected_is_relevant"] is False:
                n_pred_irrel_correct += 1
        mark = "PASS" if correct else "FAIL"
        print(f"  [{i}/{n_total}] {mark} got={pred['tool_selected']} expected={sample['expected_tool']}")

    tool_acc = n_correct_tool / n_total
    crit_prec = n_pred_irrel_correct / n_pred_irrel if n_pred_irrel else 0.0
    parse_error_rate = n_parse_errors / n_total

    print(f"\n{'=' * 55}")
    print(f"Tool Decision Accuracy : {tool_acc:.1%}  {'PASS' if tool_acc >= 0.80 else 'FAIL'} (target >= 80%)")
    print(f"Critique Precision     : {crit_prec:.1%}  {'PASS' if crit_prec >= 0.75 else 'FAIL'} (target >= 75%)")
    print(f"JSON Parse Error Rate  : {parse_error_rate:.1%}")
    print(f"{'=' * 55}")
    if tool_acc >= 0.80 and crit_prec >= 0.75 and parse_error_rate == 0:
        print("Router ĐẠT YÊU CẦU. Sẵn sàng tích hợp vào LangGraph.")
    else:
        print("Router CHƯA ĐẠT. Cần cải thiện thêm.")


if __name__ == "__main__":
    main()
