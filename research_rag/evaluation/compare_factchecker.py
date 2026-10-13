"""Paired baseline/candidate GPU diagnostic; never promotes prompts or tunes a threshold."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib
import json
from pathlib import Path
import time


def profiles_for(comparison: str) -> dict:
    prompts = importlib.import_module("04_factchecker.prompts")
    if comparison == "explanation":
        return {
            "repair": (prompts.JUDGE_SYSTEM_PROMPT, prompts.CONFIDENCE_SYSTEM_PROMPT, True),
            "explanation_repair": (prompts.JUDGE_SYSTEM_PROMPT, prompts.EXPLANATION_CONFIDENCE_SYSTEM_PROMPT, True),
        }
    if comparison == "confidence":
        # Isolate confidence: every profile uses exactly the same Judge prompt.
        return {
            "legacy_retry": (prompts.JUDGE_SYSTEM_PROMPT, prompts.CONFIDENCE_SYSTEM_PROMPT, False),
            "repair": (prompts.JUDGE_SYSTEM_PROMPT, prompts.CONFIDENCE_SYSTEM_PROMPT, True),
            "label_confidence_repair": (prompts.JUDGE_SYSTEM_PROMPT, prompts.LABEL_CONFIDENCE_SYSTEM_PROMPT, True),
        }
    return {
        "baseline": (prompts.JUDGE_SYSTEM_PROMPT, prompts.CONFIDENCE_SYSTEM_PROMPT, True),
        "coverage": (prompts.COVERAGE_JUDGE_SYSTEM_PROMPT, prompts.LABEL_CONFIDENCE_SYSTEM_PROMPT, True),
    }


def build_label_challenges(contracts: list[dict], criteria: dict) -> list[dict]:
    """Controlled label interventions, clearly separate from Judge accuracy."""
    rows = []
    for row in contracts:
        for variant, proposed in (("correct", row["label"]),
                                  ("wrong", criteria["wrong_label_map"][row["label"]])):
            rows.append({**row, "example_id": row["example_id"] + ":label_" + variant,
                         "proposed_label": proposed})
    if len(rows) != criteria["n"]:
        raise ValueError("Label challenge count does not match frozen criteria")
    return rows


class ProposedLabelJudge:
    """Diagnostic intervention only; no model call and no gold rationale in the input."""

    def __init__(self, label: str):
        self.label = label

    def judge(self, claim, context):
        decision_class = importlib.import_module("04_factchecker.inference.judge").FactCheckDecision
        explanation = "This proposed label requires assessment against the supplied context."
        return decision_class(self.label, explanation,
                              {"fact_check_label": self.label, "reasoning": explanation})


def score_label_challenges(rows: list[dict], criteria: dict, threshold: float) -> dict:
    correct = [r for r in rows if r["predicted_label"] == r["gold_label"]]
    wrong = [r for r in rows if r["predicted_label"] != r["gold_label"]]
    accepted_correct = sum(r["status"] == "ok" and r["confidence_score"] >= threshold for r in correct)
    accepted_wrong = sum(r["status"] == "ok" and r["confidence_score"] >= threshold for r in wrong)
    failed = sum(r["status"] != "ok" for r in rows)
    checks = {
        "all_challenges_present": len(rows) == len({r["example_id"] for r in rows}) == criteria["n"]
                                  and len(correct) == len(wrong) == criteria["n"] // 2,
        "no_runtime_failures": failed <= criteria["max_runtime_failed_rows"],
        "wrong_proposed_labels_not_trusted": accepted_wrong <= criteria["max_wrong_labels_at_or_above_threshold"],
        "correct_proposed_labels_recognized": accepted_correct >= criteria["min_correct_labels_at_or_above_threshold"],
    }
    return {"n": len(rows), "runtime_failed_rows": failed, "correct_labels_accepted": accepted_correct,
            "wrong_labels_accepted": accepted_wrong, "checks": checks, "automated_gate_pass": all(checks.values()),
            "note": "Proposed labels are controlled inputs, not Judge model predictions; this is not calibration on independent data."}


def explanation_review_row(profile: str, dataset: str, row: dict, output: dict, rubric: list[str]) -> dict:
    return {"profile": profile, "dataset": dataset, "example_id": row["example_id"],
            "claim": row["claim"], "context": row["context"], "gold_label": row["label"],
            "proposed_label": output["predicted_label"], "confidence_score": output["confidence_score"],
            "reasoning": output["confidence_reasoning"], "runtime_status": output["status"],
            "reviewer": "", "judgments": dict.fromkeys(rubric), "note": "", "review_status": "pending"}


class TracedBackend:
    """Record each actual call, including rejected outputs, in the private diagnostic."""

    def __init__(self, backend, stage, scope, handle, calls):
        self.backend, self.stage, self.scope = backend, stage, scope
        self.handle, self.calls = handle, calls

    def generate_json(self, messages, *, max_new_tokens):
        event = {**self.scope, "stage": self.stage, "messages": messages, "max_new_tokens": max_new_tokens}
        started = time.perf_counter()
        try:
            result = self.backend.generate_json(messages, max_new_tokens=max_new_tokens)
            event["parsed_output"] = result
            return result
        except Exception as exc:
            event["error_type"] = type(exc).__name__
            # ModelOutputError carries model text; generic transport errors may contain secrets.
            output_error = importlib.import_module("04_factchecker.inference.judge").ModelOutputError
            if isinstance(exc, output_error):
                event["raw_output"] = exc.raw_output
            raise
        finally:
            event["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
            self.calls.append(event)
            self.handle.write(json.dumps(event, ensure_ascii=False) + "\n")
            self.handle.flush()


def diagnostic_metrics(outputs: list[dict], *, threshold: float) -> dict:
    evaluation = importlib.import_module("04_factchecker.eval_factchecker")
    from research_rag.evaluate import confidence_metrics
    result = evaluation.metrics([r["gold_label"] for r in outputs], [r["predicted_label"] for r in outputs])
    valid = [r for r in outputs if r["status"] == "ok"]
    accepted = [r for r in valid if r["predicted_label"] == "support" and r["confidence_score"] >= threshold]
    false_accepted = sum(r["gold_label"] != "support" for r in accepted)
    attempts = [a for r in outputs for a in r["attempts"]]
    confidence_attempts = [a for a in attempts if a["stage"] == "confidence"]
    result.update(
        runtime_failed_rows=len(outputs) - len(valid),
        confidence_failed_rows=sum(r["status"] == "confidence_failed" for r in outputs),
        false_support=sum(r["predicted_label"] == "support" and r["gold_label"] != "support" for r in outputs),
        confidence_invalid_attempts=sum(not a["ok"] and a.get("error_type") == "ModelOutputError" for a in confidence_attempts),
        confidence_invalid_attempt_rate=(sum(not a["ok"] and a.get("error_type") == "ModelOutputError" for a in confidence_attempts)
                                         / len(confidence_attempts) if confidence_attempts else None),
        max_attempts_per_stage=max((a["attempt"] for a in attempts), default=0),
        backend_calls=sum(r["backend_calls"] for r in outputs),
        elapsed_ms=round(sum(r["elapsed_ms"] for r in outputs), 2),
        support_at_threshold={"threshold": threshold, "accepted": len(accepted), "false_support": false_accepted,
                              "true_support": len(accepted) - false_accepted,
                              "coverage": len(accepted) / len(outputs) if outputs else 0,
                              "precision": 1 - false_accepted / len(accepted) if accepted else None},
        # Never quietly drop failed rows to obtain a better calibration number.
        calibration=confidence_metrics(outputs, threshold=threshold) if outputs and len(valid) == len(outputs) else None,
        cost_usd=None,
    )
    return result


def compare_gates(results: dict, predictions: dict, criteria: dict) -> dict:
    baseline = criteria["baseline"]
    candidates = {}
    for candidate in criteria["candidates"]:
        checks = dict.fromkeys(criteria["gates"], True)
        total_accepted = 0
        for dataset, expected in criteria["datasets"].items():
            before, after = results[baseline][dataset], results[candidate][dataset]
            old_rows, new_rows = predictions[baseline][dataset], predictions[candidate][dataset]
            old_labels = {r["example_id"]: r["predicted_label"] for r in old_rows}
            new_labels = {r["example_id"]: r["predicted_label"] for r in new_rows}
            checks["all_expected_rows_present"] &= (before["n"] == after["n"] == len(old_labels) == len(new_labels) == expected)
            checks["no_runtime_failures"] &= after["runtime_failed_rows"] == 0
            checks["judge_predictions_unchanged"] &= old_labels == new_labels
            checks["label_metrics_not_lower"] &= all(after[k] >= before[k] for k in ("accuracy", "macro_f1"))
            checks["false_support_not_increased"] &= after["false_support"] <= before["false_support"]
            old_support, new_support = before["support_at_threshold"], after["support_at_threshold"]
            checks["no_accepted_false_support"] &= new_support["false_support"] == 0
            checks["accepted_true_support_not_lower"] &= new_support["true_support"] >= old_support["true_support"]
            checks["attempts_within_budget"] &= after["max_attempts_per_stage"] <= criteria["max_attempts_per_stage"]
            total_accepted += new_support["accepted"]
        checks["some_support_accepted"] = total_accepted > 0
        candidates[candidate] = {"checks": checks, "automated_gate_pass": all(checks.values())}
    return {"criteria_version": criteria["version"], "candidates": candidates,
            "human_review": "pending", "promoted_to_serving": False, "overall_pass": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--comparison", choices=("coverage", "confidence", "explanation"), default="coverage")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[2]
    evaluation = importlib.import_module("04_factchecker.eval_factchecker")
    inference = importlib.import_module("04_factchecker.inference")
    node_class = importlib.import_module("04_factchecker.node").FactCheckerNode
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    assert torch.cuda.is_available(), "Use an authorized GPU host"
    paths = [root / "research_rag/evaluation/scifact_dev_deduplicated.jsonl",
             root / "research_rag/evaluation/factchecker_contract_cases.jsonl"]
    counts, dev = Counter(), []
    for row in evaluation.read_jsonl(paths[0]):
        if counts[row["label"]] < 10:
            dev.append(row)
            counts[row["label"]] += 1
    datasets = {"dev30": dev, "contracts": evaluation.read_jsonl(paths[1])}
    criteria_path = root / "research_rag/evaluation" / (
        "confidence_explanation_criteria.json" if args.comparison == "explanation" else "confidence_criteria.json")
    criteria = json.loads(criteria_path.read_text(encoding="utf-8"))
    if args.comparison in ("confidence", "explanation"):
        paths.append(root / "research_rag/evaluation/confidence_failures_20261009.jsonl")
        datasets["observed_failures"] = evaluation.read_jsonl(paths[-1])
        assert {name: len(rows) for name, rows in datasets.items()} == criteria["datasets"]
        # Save the frozen gates before model loading or inference.
        (args.output_dir / "criteria.json").write_bytes(criteria_path.read_bytes())
    if args.comparison == "explanation":
        datasets["label_challenges"] = build_label_challenges(datasets["contracts"], criteria["label_challenges"])
    profiles = profiles_for(args.comparison)
    provenance = {"purpose": "Prompt-development diagnostic, not independent held-out evaluation",
                  "comparison": args.comparison,
                  "selection": "First 10 dev rows per label, selected before inference",
                  "input_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
                  "example_ids": {name: [r["example_id"] for r in rows] for name, rows in datasets.items()},
                  "profiles": {name: {"judge_prompt": judge, "confidence_prompt": confidence, "repair": repair}
                               for name, (judge, confidence, repair) in profiles.items()},
                  "max_attempts_per_stage": criteria["max_attempts_per_stage"], "threshold": criteria["threshold"],
                  "criteria_sha256": hashlib.sha256(criteria_path.read_bytes()).hexdigest() if args.comparison != "coverage" else None,
                  "controlled_label_dataset": "label_challenges" if args.comparison == "explanation" else None,
                  "source_sha256": {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in (
                      "04_factchecker/inference/confidence.py", "04_factchecker/inference/judge.py",
                      "04_factchecker/node.py", "04_factchecker/prompts.py", "04_factchecker/eval_factchecker.py",
                      "research_rag/evaluation/compare_factchecker.py")},
                  "baseline_note": "legacy_retry disables repair feedback under the same strict validator; not a byte-for-byte old runtime"}
    (args.output_dir / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    model_path = root / "04_factchecker/checkpoints/factchecker_merged"
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_path, local_files_only=True, device_map={"": 0}, dtype=torch.float16,
        quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.float16),
    ).eval()
    backend = inference.TransformersJSONBackend(model, tokenizer)
    results, predictions, review_rows = {}, {}, []
    for profile, (judge_prompt, confidence_prompt, repair) in profiles.items():
        results[profile] = {}
        predictions[profile] = {}
        for name, rows in datasets.items():
            outputs = []
            with (args.output_dir / f"{profile}-{name}.jsonl").open("x", encoding="utf-8") as handle, \
                    (args.output_dir / f"{profile}-{name}-calls.jsonl").open("x", encoding="utf-8") as trace:
                for row in rows:
                    calls = []
                    scope = {"profile": profile, "dataset": name, "example_id": row["example_id"]}
                    judge = (ProposedLabelJudge(row["proposed_label"]) if name == "label_challenges" else
                             inference.FactCheckJudge(TracedBackend(backend, "judge", scope, trace, calls), system_prompt=judge_prompt))
                    node = node_class(
                        judge,
                        inference.ConfidenceEstimator(TracedBackend(backend, "confidence", scope, trace, calls),
                                                      system_prompt=confidence_prompt, repair_invalid_output=repair),
                        inference.ActionRecommender(TracedBackend(backend, "action_recommender", scope, trace, calls)),
                        max_internal_retry=criteria["max_attempts_per_stage"], confidence_threshold=criteria["threshold"])
                    output = evaluation.runtime_prediction(node, row)
                    output["backend_calls"] = len(calls)
                    if args.comparison == "explanation":
                        output["judge_mode"] = "controlled_proposed_label" if name == "label_challenges" else "model"
                        if profile in criteria["candidates"]:
                            review_rows.append(explanation_review_row(profile, name, row, output, criteria["human_review_rubric"]))
                    handle.write(json.dumps(output, ensure_ascii=False) + "\n")
                    handle.flush()
                    outputs.append(output)
                    print(json.dumps({"profile": profile, "dataset": name, "done": len(outputs),
                                      "total": len(rows), "status": output["status"]}), flush=True)
            predictions[profile][name] = outputs
            results[profile][name] = (score_label_challenges(outputs, criteria["label_challenges"], criteria["threshold"])
                                      if name == "label_challenges" else diagnostic_metrics(outputs, threshold=criteria["threshold"]))
            if name == "label_challenges":
                results[profile][name].update(backend_calls=sum(r["backend_calls"] for r in outputs),
                                              elapsed_ms=round(sum(r["elapsed_ms"] for r in outputs), 2))
            (args.output_dir / "metrics.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
            if review_rows:
                (args.output_dir / "explanation-review.jsonl").write_text(
                    "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in review_rows), encoding="utf-8")
    gates = None
    if args.comparison in ("confidence", "explanation"):
        gates = compare_gates(results, predictions, criteria)
        if args.comparison == "explanation":
            for candidate in criteria["candidates"]:
                challenge = results[candidate]["label_challenges"]
                gates["candidates"][candidate]["checks"]["controlled_labels_discriminated"] = challenge["automated_gate_pass"]
                gates["candidates"][candidate]["automated_gate_pass"] = all(gates["candidates"][candidate]["checks"].values())
        (args.output_dir / "gate-results.json").write_text(json.dumps(gates, indent=2), encoding="utf-8")
    (args.output_dir / "resources.json").write_text(json.dumps({
        "device": torch.cuda.get_device_name(0), "dtype": "float16", "quantization": "NF4",
        "peak_cuda_allocated_bytes": torch.cuda.max_memory_allocated(0),
        "promoted_to_serving": False,
        "cost_usd": None, "torch_version": torch.__version__,
    }, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    if gates:
        print(json.dumps(gates, indent=2))
        required_profile = "explanation_repair" if args.comparison == "explanation" else "repair"
        if not gates["candidates"][required_profile]["automated_gate_pass"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
