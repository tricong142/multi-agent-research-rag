"""Evaluate label accuracy and macro-F1 on the labelled SciFact dev set."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import config
from inference import FactCheckJudge, TransformersJSONBackend


def read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def metrics(gold: list[str], predicted: list[str]) -> dict:
    per_label = {}
    for label in config.LABELS:
        tp = sum(g == label and p == label for g, p in zip(gold, predicted))
        fp = sum(g != label and p == label for g, p in zip(gold, predicted))
        fn = sum(g == label and p != label for g, p in zip(gold, predicted))
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_label[label] = {"precision": precision, "recall": recall, "f1": f1, "support": sum(g == label for g in gold)}
    accuracy = sum(g == p for g, p in zip(gold, predicted)) / len(gold) if gold else 0.0
    return {
        "n": len(gold),
        "accuracy": accuracy,
        "macro_f1": sum(v["f1"] for v in per_label.values()) / len(config.LABELS),
        "per_label": per_label,
        "confusion": dict(Counter(f"{g}->{p}" for g, p in zip(gold, predicted))),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=config.MODEL_PATH)
    parser.add_argument("--data", type=Path, default=config.DEV_DATA_PATH)
    parser.add_argument("--output", type=Path, default=config.EVAL_PREDICTIONS_PATH)
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--load-in-4bit",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Load the merged model in NF4 on CUDA (default: true).",
    )
    args = parser.parse_args()

    import torch
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    has_cuda = torch.cuda.is_available()
    # T4 (compute capability 7.5) has no native BF16 tensor cores even when a
    # recent torch build reports BF16 as supported. Use BF16 only on Ampere+.
    use_bf16 = has_cuda and torch.cuda.get_device_capability(0)[0] >= 8
    # Use float16 on CPU too to halve memory usage (~6 GB vs ~12 GB for 3B model)
    dtype = torch.bfloat16 if use_bf16 else torch.float16
    model_kwargs = {
        "device_map": {"": 0} if has_cuda else {"": "cpu"},
        "trust_remote_code": True,
        "low_cpu_mem_usage": True,
    }
    if has_cuda and args.load_in_4bit:
        model_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=dtype,
        )
    if int(transformers.__version__.split(".", 1)[0]) >= 5:
        model_kwargs["dtype"] = dtype
    else:
        model_kwargs["torch_dtype"] = dtype
    print(
        f"Loading model: device={'cuda:0' if has_cuda else 'cpu'}, "
        f"dtype={dtype}, load_in_4bit={has_cuda and args.load_in_4bit}"
    )
    model = AutoModelForCausalLM.from_pretrained(args.model, **model_kwargs).eval()
    judge = FactCheckJudge(TransformersJSONBackend(model, tokenizer))
    rows = read_jsonl(args.data)
    if args.limit is not None:
        rows = rows[: args.limit]

    outputs = []
    gold: list[str] = []
    predicted: list[str] = []
    for row in rows:
        try:
            decision = judge.judge(row["claim"], row["context"])
            prediction = decision.fact_check_label
            reasoning = decision.reasoning
            error = None
        except Exception as exc:
            prediction = "invalid_output"
            reasoning = ""
            error = f"{type(exc).__name__}: {exc}"
        gold.append(row["label"])
        predicted.append(prediction)
        outputs.append(
            {
                "example_id": row["example_id"],
                "gold_label": row["label"],
                "predicted_label": prediction,
                "reasoning": reasoning,
                "error": error,
            }
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for output in outputs:
            handle.write(json.dumps(output, ensure_ascii=False) + "\n")
    result = metrics(gold, predicted)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Predictions: {args.output}")


if __name__ == "__main__":
    main()
