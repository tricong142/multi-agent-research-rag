"""Schema rate, independently reviewed faithfulness, and warning incidence.

Exact-copy support is reported separately as a proxy, never as a semantic gold
score. Human labels are bound to the SHA256 of the actual evaluated report.
"""
from __future__ import annotations

if __package__ in (None, ""):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "05_writer"

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from .inference.critic import exact_copy_reviews
from .report_schema_validator import parse_claims, validate_report


def report_hash(report: dict) -> str:
    return hashlib.sha256(json.dumps(report, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def evaluate(cases: list[dict], predictions: list[dict]) -> dict:
    if not cases:
        raise ValueError("evaluation set is empty; populate reviewed cases or use explicit candidates")
    case_ids = [c["example_id"] for c in cases]
    prediction_ids = [p["example_id"] for p in predictions]
    if len(set(case_ids)) != len(case_ids) or len(set(prediction_ids)) != len(prediction_ids):
        raise ValueError("duplicate evaluation/prediction example_id")
    if set(prediction_ids) - set(case_ids):
        raise ValueError("predictions contain examples not present in evaluation cases")
    by_id = {p["example_id"]: p for p in predictions}
    valid, warned, warnings_known, empty = 0, 0, 0, 0
    copied, sentences, reviewed_supported, reviewed_total, human_cases = 0, 0, 0, 0, 0
    warning_reasons, records = Counter(), []
    for case in cases:
        pred = by_id.get(case["example_id"], {})
        record = {"example_id": case["example_id"], "schema_valid": False}
        if type(pred.get("low_confidence_warning")) is bool:
            warnings_known += 1
            warned += pred["low_confidence_warning"]
        for reason in set(pred.get("writer_diagnostics", {}).get("warning_reasons", [])):
            warning_reasons[reason] += 1
        try:
            claims = parse_claims(case["verified_claims"])
            report = validate_report(pred["final_report"], claims)
        except (ValueError, TypeError, KeyError) as exc:
            record["error_type"] = type(exc).__name__
            records.append(record)
            continue
        valid += 1
        empty += not report.sentences
        record["schema_valid"] = True
        dumped = report.model_dump(mode="json")
        digest = report_hash(dumped)
        record["report_sha256"] = digest
        local_copied = sum(r.verdict == "supported" for r in exact_copy_reviews(claims, report))
        copied += local_copied
        sentences += len(report.sentences)
        record["exact_copy_support_proxy"] = local_copied / len(report.sentences) if report.sentences else None
        labels = case.get("human_sentence_labels")
        if case.get("human_reviewed") is True and labels is not None:
            expected_ids = {s.sentence_id for s in report.sentences}
            if (case.get("reviewed_report_sha256") != digest or not isinstance(labels, dict)
                    or set(labels) != expected_ids or any(type(v) is not bool for v in labels.values())):
                raise ValueError(f"{case['example_id']}: human labels must cover exactly this report and match its hash")
            human_cases += 1
            reviewed_total += len(labels)
            reviewed_supported += sum(labels.values())
        records.append(record)
    total = len(cases)
    return {
        "n_cases": total,
        "schema_validity_rate": valid / total,
        "faithfulness_score": reviewed_supported / reviewed_total if reviewed_total else None,
        "faithfulness_basis": "independent human sentence labels bound to report SHA256",
        "human_reviewed_cases": human_cases,
        "human_reviewed_sentences": reviewed_total,
        "exact_copy_support_proxy": copied / sentences if sentences else None,
        "valid_report_sentences": sentences,
        "empty_report_rate": empty / total,
        "low_confidence_warning_rate": warned / warnings_known if warnings_known else None,
        "low_confidence_warning_percent": 100 * warned / warnings_known if warnings_known else None,
        "warning_field_coverage": warnings_known / total,
        "warning_reason_counts": dict(warning_reasons),
        "per_case": records,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, help="Evaluate stored predictions instead of running a model")
    parser.add_argument("--output", type=Path, default=Path("writer_eval_metrics.json"))
    parser.add_argument("--save-predictions", type=Path)
    parser.add_argument("--model", help="HF model; omit for conservative offline baseline")
    parser.add_argument("--adapter")
    parser.add_argument("--load-in-4bit", action="store_true")
    args = parser.parse_args()
    cases = read_jsonl(args.data)
    if args.predictions:
        predictions = read_jsonl(args.predictions)
    else:
        from .node import WriterNode
        from .loop_controller import WriterLoopController
        from .inference.backend import HFJsonBackend
        from .inference.report_generator import ReportGenerator
        from .inference.critic import Critic
        from .inference.action_selector import ActionSelector
        backend = HFJsonBackend(args.model, adapter_path=args.adapter, load_in_4bit=args.load_in_4bit) if args.model else None
        node = WriterNode(WriterLoopController(ReportGenerator(backend), Critic(backend), ActionSelector(backend)))
        predictions = [{"example_id": case["example_id"], **node(case)} for case in cases]
    if args.save_predictions:
        args.save_predictions.parent.mkdir(parents=True, exist_ok=True)
        args.save_predictions.write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in predictions), encoding="utf-8")
    metrics = evaluate(cases, predictions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in metrics.items() if k != "per_case"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
