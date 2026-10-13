"""Evaluate existing labelled outputs and retrieval with real relevance judgements."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import time
from pathlib import Path
from typing import Any

from .local import ROOT
from .retrieval import CORPUS_PATH, INDEX_DIR, RetrievalService


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def factchecker_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("Fact-Checker predictions are empty")
    labels = ("support", "contradict", "not_enough_info")
    per_label = {}
    for label in labels:
        tp = sum(row["gold_label"] == label and row["predicted_label"] == label for row in rows)
        fp = sum(row["gold_label"] != label and row["predicted_label"] == label for row in rows)
        fn = sum(row["gold_label"] == label and row["predicted_label"] != label for row in rows)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        per_label[label] = {"precision": precision, "recall": recall,
                            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
                            "support": sum(row["gold_label"] == label for row in rows)}
    return {"n": len(rows), "accuracy": sum(row["gold_label"] == row["predicted_label"] for row in rows) / len(rows),
            "macro_f1": statistics.mean(value["f1"] for value in per_label.values()),
            "invalid_outputs": sum(row["predicted_label"] not in labels for row in rows), "per_label": per_label}


def summarizer_evidence_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("Summarizer predictions are empty")
    spans = [span for row in rows for span in row.get("predicted_evidence", []) if isinstance(span, str)]
    matched = sum(span in row["context"] for row in rows for span in row.get("predicted_evidence", [])
                  if isinstance(span, str))
    answerable = [row for row in rows if row["expected_is_answerable"] is True]
    unanswerable = [row for row in rows if row["expected_is_answerable"] is False]
    return {"n": len(rows), "evidence_spans": len(spans),
            "verbatim_span_rate": matched / len(spans) if spans else None,
            "answerable_supported_rate": sum(row.get("is_supported_final") is True for row in answerable) / len(answerable) if answerable else None,
            "unanswerable_supported_rate": sum(row.get("is_supported_final") is True for row in unanswerable) / len(unanswerable) if unanswerable else None,
            "note": "Verbatim matching and self-reported support do not measure factual answer correctness."}


def confidence_metrics(rows: list[dict[str, Any]], bins: int = 10, threshold: float = 0.7) -> dict[str, Any]:
    """Calibration of confidence that the predicted label is correct."""
    if not rows or type(bins) is not int or bins < 1:
        raise ValueError("Nonempty predictions and at least one bin are required")
    if type(threshold) not in (int, float) or not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("threshold must be finite and in [0, 1]")
    labels = ("support", "contradict", "not_enough_info")
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(bins)]
    squared_errors = []
    for row in rows:
        if row.get("gold_label") not in labels or row.get("predicted_label") not in labels:
            raise ValueError("Calibration requires valid gold_label and predicted_label")
        if row.get("status", "ok") != "ok":
            raise ValueError("Calibration cannot use failed runtime predictions; report failures separately")
        score = row.get("confidence_score")
        if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError("Every prediction needs confidence_score in [0, 1]")
        correct = int(row["gold_label"] == row["predicted_label"])
        buckets[min(int(score * bins), bins - 1)].append((float(score), correct))
        squared_errors.append((score - correct) ** 2)
    ece = sum(len(bucket) / len(rows) * abs(statistics.mean(score for score, _ in bucket) -
                                            statistics.mean(correct for _, correct in bucket))
              for bucket in buckets if bucket)
    by_label = {}
    for label in labels:
        selected = [row for row in rows if row["predicted_label"] == label]
        by_label[label] = {"n": len(selected),
                           "accuracy": statistics.mean(row["gold_label"] == label for row in selected) if selected else None,
                           "mean_confidence": statistics.mean(row["confidence_score"] for row in selected) if selected else None}
    accepted = [row for row in rows if row["predicted_label"] == "support" and row["confidence_score"] >= threshold]
    false_support = sum(row["gold_label"] != "support" for row in accepted)
    reliability = [{"lower": index / bins, "upper": (index + 1) / bins, "n": len(bucket),
                    "mean_confidence": statistics.mean(s for s, _ in bucket) if bucket else None,
                    "accuracy": statistics.mean(c for _, c in bucket) if bucket else None}
                   for index, bucket in enumerate(buckets)]
    return {"n": len(rows), "bins": bins, "ece": ece, "brier_score": statistics.mean(squared_errors),
            "reliability_bins": reliability, "per_predicted_label": by_label,
            "support_at_threshold": {"threshold": threshold, "accepted": len(accepted),
                                     "false_support": false_support, "coverage": len(accepted) / len(rows),
                                     "precision": 1 - false_support / len(accepted) if accepted else None},
            "note": "Confidence measures label correctness, not claim truth. Threshold diagnostics do not fit a calibration map or certify the graph."}


def snapshot_metrics() -> dict[str, Any]:
    fact_path = ROOT / "04_factchecker/data/eval_predictions.jsonl"
    summary_path = ROOT / "train_agent3_summarizer/data/eval_results.jsonl"
    return {"provenance": "Existing prediction files; no model inference in this command",
            "factchecker": factchecker_metrics(read_jsonl(fact_path)),
            "summarizer": summarizer_evidence_metrics(read_jsonl(summary_path))}


def retrieval_metrics(rows: list[dict[str, Any]], service: RetrievalService, top_k: int) -> dict[str, Any]:
    if not rows or not 1 <= top_k <= 50:
        raise ValueError("Nonempty qrels and top_k in [1, 50] are required")
    service._load_static()  # validates the corpus/index mapping before any metric
    corpus_ids = {row["doc_id"] for row in service._rows or []}
    hit_count = 0
    recalls = []
    latencies = []
    fallback_count = 0
    unsupported_count = 0
    for row in rows:
        query = row.get("query")
        relevant = row.get("relevant_doc_ids")
        if not isinstance(query, str) or not query.strip() or not isinstance(relevant, list) or not relevant:
            raise ValueError("Each qrel needs a nonempty query and relevant_doc_ids list")
        if any(not isinstance(doc_id, str) or doc_id not in corpus_ids for doc_id in relevant):
            raise ValueError("Qrel references a doc_id absent from the current corpus")
        started = time.perf_counter()
        result = service.search(query, top_k=top_k)
        latencies.append((time.perf_counter() - started) * 1000)
        found = {chunk["doc_id"] for chunk in result["chunks"]}
        expected = set(relevant)
        hit_count += bool(found & expected)
        recalls.append(len(found & expected) / len(expected))
        warning = result.get("warning") or ""
        fallback_count += "dense_unavailable" in warning
        unsupported_count += "unsupported_policy_action" in warning
    sorted_latencies = sorted(latencies)
    return {"n": len(rows), "top_k": top_k, "hit_at_k": hit_count / len(rows),
            "recall_at_k": statistics.mean(recalls),
            "latency_ms_mean": statistics.mean(latencies),
            "latency_ms_p95": sorted_latencies[math.ceil(0.95 * len(sorted_latencies)) - 1],
            "dense_fallback_queries": fallback_count, "unsupported_policy_queries": unsupported_count,
            "note": "Dense recall is not valid when dense_fallback_queries > 0. BM25 artifact loading is outside the timer; a first dense query can include encoder/index load."}


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate existing outputs or labelled retrieval queries")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("snapshot", help="Score existing Summarizer and Fact-Checker predictions")
    retrieval = sub.add_parser("retrieval", help="Compute recall@k from manually labelled relevant doc_ids")
    retrieval.add_argument("--qrels", type=Path, required=True)
    retrieval.add_argument("--mode", choices=("bm25", "dense", "policy"), default="bm25")
    retrieval.add_argument("--top-k", type=int, default=5)
    retrieval.add_argument("--corpus", type=Path, default=CORPUS_PATH)
    retrieval.add_argument("--index-dir", type=Path, default=INDEX_DIR)
    calibration = sub.add_parser("confidence", help="Score confidence when labelled predictions include confidence_score")
    calibration.add_argument("--predictions", type=Path, required=True)
    calibration.add_argument("--bins", type=int, default=10)
    calibration.add_argument("--threshold", type=float, default=0.7,
                             help="Report support precision at this provisional threshold; does not tune it")
    args = parser.parse_args()
    if args.command == "snapshot":
        output = snapshot_metrics()
    elif args.command == "retrieval":
        policy = None if args.mode == "policy" else lambda _query, _history: args.mode
        service = RetrievalService(corpus_path=args.corpus, index_dir=args.index_dir, policy=policy)
        output = {"mode": args.mode, "qrels_file": str(args.qrels),
                  "qrels_sha256": hashlib.sha256(args.qrels.read_bytes()).hexdigest(),
                  "corpus_sha256": hashlib.sha256(args.corpus.read_bytes()).hexdigest(),
                  "index_dir": str(args.index_dir),
                  **retrieval_metrics(read_jsonl(args.qrels), service, args.top_k)}
    else:
        output = confidence_metrics(read_jsonl(args.predictions), args.bins, args.threshold)
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
