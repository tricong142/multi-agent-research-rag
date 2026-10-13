"""Compare confidence backends with fixed label interventions; never change serving."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import copy
import gc
import hashlib
import importlib
import json
from pathlib import Path
import time

from research_rag.evaluation.compare_factchecker import (
    ProposedLabelJudge, TracedBackend, build_label_challenges, explanation_review_row,
    profiles_for, score_label_challenges,
)

ROOT = Path(__file__).resolve().parents[2]
CRITERIA = Path(__file__).with_name("confidence_backend_criteria.json")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def assess(estimator, row, max_attempts):
    """Confidence-only bounded repair using the production estimator and validator."""
    started = time.perf_counter()
    previous, estimate, attempts = None, None, []
    for attempt in range(1, max_attempts + 1):
        try:
            estimate = estimator.estimate(row["claim"], row["context"], row["proposed_label"],
                ProposedLabelJudge(row["proposed_label"]).judge("", "").reasoning, previous_error=previous)
            attempts.append({"stage": "confidence", "attempt": attempt, "ok": True})
            break
        except Exception as exc:
            previous = exc
            attempts.append({"stage": "confidence", "attempt": attempt, "ok": False,
                             "error_type": type(exc).__name__})
    return {"example_id": row["example_id"], "gold_label": row["label"],
            "predicted_label": row["proposed_label"], "judge_mode": "controlled_proposed_label",
            "status": "ok" if estimate is not None else "confidence_failed",
            "confidence_score": estimate.confidence_score if estimate is not None else None,
            "confidence_reasoning": estimate.reasoning if estimate is not None else "No valid structured output",
            "attempts": attempts, "elapsed_ms": round((time.perf_counter() - started) * 1000, 2)}


def run_experiment(output_dir: Path, backend_loader) -> dict:
    criteria = json.loads(CRITERIA.read_text(encoding="utf-8"))
    contracts = CRITERIA.with_name("factchecker_contract_cases.jsonl")
    if sha256(contracts) != criteria["contracts_sha256"]:
        raise ValueError("Contracts changed; create new prospective criteria before inference")
    cases = build_label_challenges([json.loads(line) for line in contracts.read_text().splitlines() if line.strip()],
                                  criteria["label_challenges"])
    profiles = profiles_for("explanation")
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "criteria.json").write_bytes(CRITERIA.read_bytes())
    write_json(output_dir / "cases.json", cases)
    provenance = {"criteria_sha256": sha256(CRITERIA), "contracts_sha256": sha256(contracts),
        "models": {}, "prompts": {name: profiles[name][1] for name in criteria["prompt_profiles"]},
        "source_sha256": {name: sha256(ROOT / name) for name in (
            "04_factchecker/inference/confidence.py", "04_factchecker/inference/judge.py", "04_factchecker/prompts.py",
            "research_rag/evaluation/compare_factchecker.py", "research_rag/evaluation/compare_confidence_backends.py")},
        "serving_modified": False, "cost_usd": None, "limitations": criteria["limitations"]}
    write_json(output_dir / "provenance.json", provenance)
    rubric = json.loads(CRITERIA.with_name("confidence_explanation_criteria.json").read_text())["human_review_rubric"]
    inference = importlib.import_module("04_factchecker.inference")
    metrics, count = {}, 0
    with (output_dir / "explanation-review.jsonl").open("x", encoding="utf-8") as review:
        for kind in criteria["backends"]:
            # Loader owns exactly one model at a time, including cleanup on a failed profile.
            with backend_loader(kind, criteria) as (backend, metadata):
                provenance["models"][kind] = metadata
                write_json(output_dir / "provenance.json", provenance)
                for prompt_profile in criteria["prompt_profiles"]:
                    name = kind + "__" + prompt_profile
                    outputs = []
                    with (output_dir / (name + ".jsonl")).open("x", encoding="utf-8") as predictions, \
                            (output_dir / (name + "-calls.jsonl")).open("x", encoding="utf-8") as trace:
                        for row in cases:
                            calls = []
                            traced = TracedBackend(backend, "confidence", {"profile": name,
                                "dataset": "label_challenges", "example_id": row["example_id"]}, trace, calls)
                            estimator = inference.ConfidenceEstimator(traced, system_prompt=profiles[prompt_profile][1])
                            output = assess(estimator, row, criteria["max_attempts"])
                            output["backend_calls"] = len(calls)
                            predictions.write(json.dumps(output, ensure_ascii=False) + "\n")
                            predictions.flush()
                            review.write(json.dumps(explanation_review_row(name, "label_challenges", row, output, rubric),
                                                    ensure_ascii=False) + "\n")
                            review.flush()
                            outputs.append(output)
                            count += 1
                    m = score_label_challenges(outputs, criteria["label_challenges"], criteria["threshold"])
                    m.update(backend_calls=sum(r["backend_calls"] for r in outputs),
                             elapsed_ms=round(sum(r["elapsed_ms"] for r in outputs), 2),
                             max_attempts=max(len(r["attempts"]) for r in outputs))
                    metrics[name] = m
                    write_json(output_dir / "metrics.json", metrics)
                    print(json.dumps({"profile": name, **m}), flush=True)
    complete = count == criteria["expected_predictions"] and len(metrics) == 4
    summary = {"experiment_completed": complete, "prediction_count": count,
        "backend_calls": sum(m["backend_calls"] for m in metrics.values()),
        "required_profile": criteria["required_profile"],
        "automated_gate_pass": complete and metrics[criteria["required_profile"]]["automated_gate_pass"],
        "qualifying_profiles": [name for name, m in metrics.items() if m["automated_gate_pass"]],
        "human_review": "pending", "overall_pass": False, "promoted_to_serving": False, "cost_usd": None}
    write_json(output_dir / "summary.json", summary)
    return summary


def model_loader(*, online: bool):
    @contextmanager
    def load(kind, criteria):
        import torch
        from huggingface_hub import snapshot_download
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, GenerationConfig
        if not torch.cuda.is_available():
            raise RuntimeError("Confidence comparison requires a CUDA host")
        merged = ROOT / "04_factchecker/checkpoints/factchecker_merged"
        path = merged if kind == "finetuned" else Path(snapshot_download(
            criteria["base_model"], revision=criteria["base_revision"], local_files_only=not online,
            allow_patterns=["*.json", "*.safetensors", "*.txt", "LICENSE"]))
        # Use identical tokenization and generation defaults for the paired weight comparison.
        tokenizer = AutoTokenizer.from_pretrained(merged, local_files_only=True)
        generation = GenerationConfig.from_pretrained(merged, local_files_only=True)
        metadata = {"backend": kind, "repo_id": criteria["base_model"] if kind == "base_instruct" else None,
            "revision": criteria["base_revision"] if kind == "base_instruct" else None,
            "model_files": {p.name: sha256(p) for p in sorted(path.iterdir()) if p.is_file() and p.suffix in (".json", ".safetensors", ".txt")},
            "shared_tokenizer_files": {p.name: sha256(p) for p in merged.iterdir() if p.name in
                ("tokenizer.json", "tokenizer_config.json", "vocab.json", "merges.txt")},
            "shared_generation_config": generation.to_dict(), "torch_version": torch.__version__,
            "device": torch.cuda.get_device_name(0), "dtype": "float16", "quantization": "NF4", "seed": criteria["seed"],
            "do_sample": False, "max_new_tokens": criteria["max_new_tokens"]}
        torch.manual_seed(criteria["seed"])
        model = AutoModelForCausalLM.from_pretrained(path, local_files_only=True, device_map={"": 0}, dtype=torch.float16,
            quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.float16)).eval()
        try:
            merged_config = json.loads((merged / "config.json").read_text(encoding="utf-8"))
            if any(getattr(model.config, key) != merged_config[key] for key in
                   ("model_type", "vocab_size", "hidden_size", "num_hidden_layers")):
                raise ValueError("Model is not compatible with the shared Qwen tokenizer")
            model.generation_config = copy.deepcopy(generation)
            backend = importlib.import_module("04_factchecker.inference").TransformersJSONBackend(model, tokenizer)
            yield backend, metadata
        finally:
            # Clear the adapter reference as well, before loading the next model on the same GPU.
            if "backend" in locals():
                backend.model = None
            del model
            gc.collect()
            torch.cuda.empty_cache()
    return load


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--online-model-downloads", action="store_true")
    args = parser.parse_args()
    config = importlib.import_module("04_factchecker.config")
    if config.MAX_NEW_TOKENS_CONFIDENCE != json.loads(CRITERIA.read_text())["max_new_tokens"]:
        raise ValueError("Generation budget changed; freeze new criteria before running")
    result = run_experiment(args.output_dir, model_loader(online=args.online_model_downloads))
    print(json.dumps(result, indent=2))
    if not result["automated_gate_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
