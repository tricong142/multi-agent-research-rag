"""Frozen Reader acceptance gates plus per-attempt API diagnostics for manual Kaggle runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter, defaultdict
from importlib.metadata import version
from pathlib import Path
from types import SimpleNamespace

from research_rag.adapters import PdfReader
from research_rag.evaluation.reader_smoke import score, score_extractions
from train_agent2_reader.reader_agent import ReaderAgent
from train_agent2_reader.reader_policy import GEMINI_MODEL, request_policy


def summarize_attempts(events: list[dict], policy: dict) -> dict:
    attempts = [event for event in events if event["event"] == "reader_api_attempt"]
    calls = defaultdict(list)
    for event in attempts:
        calls[event["call_id"]].append(event)
    terminal = [event for event in events if event["outcome"] in
                {"exhausted", "non_retryable", "deadline_exceeded"}]
    within_budget = all(
        len(items) <= policy["max_attempts"]
        and [item["attempt"] for item in items] == list(range(1, len(items) + 1))
        and all(0 < item["timeout_ms"] <= policy["request_timeout_seconds"] * 1000 for item in items)
        and all(item["total_elapsed_ms"] <= policy["call_budget_seconds"] * 1000
                for item in items if item["outcome"] == "success")
        for items in calls.values())
    return {"logical_call_count": len({event["call_id"] for event in events}), "transport_attempt_count": len(attempts),
            "http_status_counts": dict(Counter(str(event["http_status"]) if event["http_status"] is not None
                                                else "not_available" for event in attempts)),
            "outcome_counts": dict(Counter(event["outcome"] for event in attempts)),
            "terminal_failure_events": len(terminal), "within_attempt_and_deadline_policy": within_budget,
            "total_transport_ms": round(sum(event["elapsed_ms"] for event in attempts), 3),
            "total_wait_ms": round(sum(event["wait_ms"] for event in attempts), 3),
            "model_ids": sorted({event["model"] for event in attempts}), "cost_usd": None}


def run_diagnostic(manifest: Path, output_dir: Path, *, page_no: int | None = None) -> dict:
    manifest = manifest.resolve()
    rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows or (page_no is not None and (type(page_no) is not int or page_no < 0)):
        raise ValueError("Provide a nonempty manifest and a valid page number")
    sources, evaluation_rows = [], []
    for row in rows:
        relative = Path(row["pdf_path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("PDF paths must be relative to the manifest directory")
        path = (manifest.parent / relative).resolve()
        spans = [span for span in row["expected_spans"] if page_no is None or span["page_no"] == page_no]
        if not spans:
            raise ValueError("Every selected PDF/page needs expected_spans before inference")
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if row.get("source_sha256") and row["source_sha256"] != actual_hash:
            raise ValueError("PDF hash does not match manifest")
        sources.append({"pdf_path": relative.as_posix(), "sha256": actual_hash, "expected_spans": spans})
        evaluation_rows.append({**row, "pdf_path": relative.as_posix(), "source_sha256": actual_hash,
                                "expected_spans": spans})
    if len({row["pdf_path"] for row in evaluation_rows}) != len(evaluation_rows):
        raise ValueError("Duplicate PDFs in manifest")
    policy = request_policy()
    criteria = {"schema_version": 2, "recorded_before_inference": True,
                "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(), "sources": sources,
                "selected_page": page_no, "configured_model": GEMINI_MODEL,
                "google_genai_version": version("google-genai"), "request_policy": policy,
                "gates": {"overall_exact_span_rate": 1.0, "pdf_failures": 0,
                          "api_terminal_failures": 0, "minimum_api_attempts": 1,
                          "within_attempt_and_deadline_policy": True},
                "scope": "Phrase/page presence on supplied regression fixtures; not independent generalization or table/reading-order quality.",
                "timeout_limit": "HTTPX phase timeouts; late responses are rejected. A separate process timeout must terminate a stalled call."}
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "criteria.json").write_text(json.dumps(criteria, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "input-manifest.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in evaluation_rows), encoding="utf-8")
    events = []
    context = {}
    started = time.monotonic()
    with (output_dir / "api_attempts.jsonl").open("w", encoding="utf-8") as api_stream, \
            (output_dir / "page_trials.jsonl").open("w", encoding="utf-8") as page_stream, \
            (output_dir / "page_blocks.jsonl").open("w", encoding="utf-8") as blocks_stream, \
            (output_dir / "extractions.jsonl").open("w", encoding="utf-8") as chunks_stream:
        def record_api(event):
            event = {**context, **event}
            events.append(event)
            api_stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            api_stream.flush()

        model_dir = Path(__file__).resolve().parents[2] / "train_agent2_reader/layoutlmv3_doclaynet_model"
        agent = ReaderAgent(str(model_dir), on_api_attempt=record_api, allow_remote=True)

        def process_page(pdf_path, selected_page):
            context.update(pdf_path=Path(pdf_path).relative_to(manifest.parent).as_posix(), page_no=selected_page)
            result = agent.process_page(pdf_path, selected_page)
            blocks = [{"page_no": selected_page, "text": block.text, "bbox": list(block.bbox),
                       "label": block.label, "confidence": getattr(block, "confidence", None),
                       "source_tool": block.source_tool} for block in result.get("blocks", [])]
            blocks_stream.write(json.dumps({**context, "accepted": result.get("success") is True,
                "source_sha256": next(row["source_sha256"] for row in evaluation_rows if row["pdf_path"] == context["pdf_path"]),
                "final_tool": result.get("final_tool"), "blocks": blocks}, ensure_ascii=False) + "\n")
            blocks_stream.flush()
            page_stream.write(json.dumps({**context, "success": result.get("success"),
                "final_tool": result.get("final_tool"), "attempts": result.get("attempts", []),
                "block_count": len(result.get("blocks", []))}, ensure_ascii=False) + "\n")
            page_stream.flush()
            return result

        reader = PdfReader(SimpleNamespace(process_page=process_page))

        def read_selected(pdf_path):
            if page_no is None:
                return reader.read(pdf_path)
            import fitz
            with fitz.open(pdf_path) as doc:
                if page_no >= len(doc):
                    raise ValueError("Selected page is outside PDF")
                excluded = [i for i in range(len(doc)) if i != page_no]
            return reader.read_for_question(pdf_path, question="", excluded_pages=excluded, page_batch=1)["chunks"]

        def read(pdf_path):
            relative = Path(pdf_path).relative_to(manifest.parent).as_posix()
            record = {"pdf_path": relative, "source_sha256": next(
                row["source_sha256"] for row in evaluation_rows if row["pdf_path"] == relative)}
            try:
                record["chunks"] = read_selected(pdf_path)
                return record["chunks"]
            except Exception as exc:
                record["error_type"] = type(exc).__name__
                # Partial accepted pages remain in page_blocks; never pass a failed PDF as complete.
                raise
            finally:
                chunks_stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                chunks_stream.flush()

        result = score(manifest, SimpleNamespace(read=read), page_no=page_no)
    api_summary = summarize_attempts(events, policy)
    passed = (not result["failures"] and result["overall_exact_span_rate"] == 1.0
              and api_summary["transport_attempt_count"] > 0 and api_summary["terminal_failure_events"] == 0
              and api_summary["within_attempt_and_deadline_policy"])
    result.update(api=api_summary, elapsed_ms=round((time.monotonic() - started) * 1000, 3),
                  automated_gate_pass=passed, human_review="pending", overall_pass=False,
                  status="awaiting_human_review" if passed else "automated_gates_failed")
    result["artifact_sha256"] = {name: hashlib.sha256((output_dir / name).read_bytes()).hexdigest()
        for name in ("criteria.json", "input-manifest.jsonl", "api_attempts.jsonl", "page_trials.jsonl",
                     "page_blocks.jsonl", "extractions.jsonl")}
    (output_dir / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def replay_diagnostic(directory: Path) -> dict:
    """Verify saved artifacts and reproduce metrics without PDFs, models, or API calls."""
    saved = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    files = ("criteria.json", "input-manifest.jsonl", "api_attempts.jsonl", "page_trials.jsonl",
             "page_blocks.jsonl", "extractions.jsonl")
    for name in files:
        expected = saved.get("artifact_sha256", {}).get(name)
        if not expected or hashlib.sha256((directory / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Missing or changed replay artifact: " + name)
    def rows(name):
        return [json.loads(line) for line in (directory / name).read_text(encoding="utf-8").splitlines() if line.strip()]
    manifest, records = rows("input-manifest.jsonl"), rows("extractions.jsonl")
    hashes = {r["pdf_path"]: r["source_sha256"] for r in manifest}
    if any(r.get("source_sha256") != hashes.get(r["pdf_path"]) for r in records):
        raise ValueError("Extraction source hash does not match frozen manifest")
    result = score_extractions(manifest, records)
    criteria = json.loads((directory / "criteria.json").read_text(encoding="utf-8"))
    if [{"pdf_path": r["pdf_path"], "sha256": r["source_sha256"], "expected_spans": r["expected_spans"]}
            for r in manifest] != criteria["sources"]:
        raise ValueError("Replay manifest differs from preregistered sources/spans")
    result["api"] = summarize_attempts(rows("api_attempts.jsonl"), criteria["request_policy"])
    if any(value != saved.get(key) for key, value in result.items()):
        raise ValueError("Recomputed metrics differ from recorded summary")
    passed = (not result["failures"] and result["overall_exact_span_rate"] == 1.0
              and result["api"]["transport_attempt_count"] > 0 and result["api"]["terminal_failure_events"] == 0
              and result["api"]["within_attempt_and_deadline_policy"])
    if passed != saved["automated_gate_pass"]:
        raise ValueError("Recomputed gate differs from recorded summary")
    return {"replay_verified": True, "automated_gate_pass": passed, "metrics": result,
            "source_summary_sha256": hashlib.sha256((directory / "summary.json").read_bytes()).hexdigest(),
            "human_review": "pending", "overall_pass": False,
            "note": "Successful replay verifies recorded evidence; it does not turn failed quality gates into passes."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--manifest", type=Path)
    mode.add_argument("--replay-dir", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--page", type=int)
    args = parser.parse_args()
    if args.replay_dir:
        if args.page is not None:
            parser.error("--page applies only to a live diagnostic")
        result = replay_diagnostic(args.replay_dir)
        args.output_dir.mkdir(parents=True, exist_ok=False)
        (args.output_dir / "replay.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    else:
        result = run_diagnostic(args.manifest, args.output_dir, page_no=args.page)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not args.replay_dir and not result["automated_gate_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
