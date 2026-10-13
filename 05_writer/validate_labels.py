"""Validate schema, citations, derivation rules, and native paper boundaries.

This validator can certify exact-copy consistency and the explicit synthetic
corruption protocol. It cannot certify open-ended semantic truth. Hand-written
paraphrase/entailment labels must be reviewed separately before extending this
training curriculum.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any, Mapping

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "05_writer"

from .schemas import TrainingExample
from .report_schema_validator import parse_claims, parse_critique, validate_action, validate_report
from .generate_training_data import unsupported_text

DATA_DIR = Path(__file__).resolve().parent / "data"
DERIVED_ORIGINS = {"derived_evidence_quote", "synthetic_unsupported", "synthetic_reselection"}


def validate_example(payload: Mapping[str, Any] | TrainingExample) -> TrainingExample:
    """Return a validated example or raise ValueError with a useful reason."""
    row = TrainingExample.model_validate(payload)
    claims = parse_claims(row.verified_claims)
    report = validate_report(row.report, claims)
    critique = parse_critique(row.critique, report)
    claim_map = {claim.claim_id: claim for claim in claims}
    if row.label_origin not in DERIVED_ORIGINS:
        raise ValueError("Unsupported label_origin; this validator covers the documented derived curriculum only")
    if row.human_reviewed:
        raise ValueError("Derived training rows must not claim human_reviewed=True; use separate manual evaluation annotations")
    if row.provenance.get("dataset") != "allenai/qasper":
        raise ValueError("Missing QASPER provenance")
    if row.provenance.get("claim_verification") != "verbatim_source_match":
        raise ValueError("Missing documented claim verification method")
    for claim in claims:
        if claim.text not in claim.evidence:
            raise ValueError(f"Claim {claim.claim_id!r} is not a verbatim substring of its evidence")
        if not claim.source_id.startswith(f"qasper:{row.paper_id}:paragraph:"):
            raise ValueError(f"Claim {claim.claim_id!r} has a source outside this paper")
        if claim.evidence.lstrip().startswith("FLOAT SELECTED"):
            raise ValueError("Visual-only QASPER evidence cannot certify a textual claim")
    synthetic = row.provenance.get("synthetic_corruption")
    corrupt_id: str | None = None
    if synthetic is not None:
        if not isinstance(synthetic, dict) or synthetic.get("kind") != "unsupported_marker":
            raise ValueError("Unknown synthetic corruption protocol")
        marker = synthetic.get("marker")
        corrupt_id = synthetic.get("sentence_id")
        if not isinstance(marker, str) or not marker.startswith("WRITER_SYNTHETIC_UNSUPPORTED_"):
            raise ValueError("Missing explicit synthetic marker")
        if any(marker in claim.evidence or marker in claim.text for claim in claims) or marker in row.intent:
            raise ValueError("Synthetic marker occurs in the claim pool or intent")
        matches = [sentence for sentence in report.sentences if sentence.sentence_id == corrupt_id]
        if len(matches) != 1 or matches[0].text != unsupported_text(marker):
            raise ValueError("Synthetic target sentence does not match the recorded corruption")
        if row.label_origin not in {"synthetic_unsupported", "synthetic_reselection"}:
            raise ValueError("Synthetic candidate is mislabeled as a clean quote target")
    elif row.label_origin != "derived_evidence_quote":
        raise ValueError("Synthetic label_origin requires a reproducible corruption")
    expected_reviews: dict[str, str] = {}
    for sentence in report.sentences:
        exact_quote = any(sentence.text == claim_map[claim_id].text for claim_id in sentence.claim_ids)
        if sentence.sentence_id == corrupt_id:
            expected_reviews[sentence.sentence_id] = "unsupported"
        elif exact_quote:
            expected_reviews[sentence.sentence_id] = "supported"
        else:
            raise ValueError(f"Cannot certify sentence {sentence.sentence_id!r}: not an exact cited quote or documented synthetic negative")
    for review in critique.sentence_reviews:
        if review.verdict != expected_reviews[review.sentence_id]:
            raise ValueError(f"Incorrect verdict for {review.sentence_id!r}")
    if critique.needs_more_evidence != (not bool(claims)):
        raise ValueError("Derived quote task must flag evidence shortage exactly when its claim pool is empty")
    if row.task == "report":
        if synthetic is not None:
            raise ValueError("Unsupported synthetic text must never become a report SFT target")
        if claims and not report.sentences:
            raise ValueError("A report target must quote available evidence")
    if row.task == "action":
        if row.action is None:
            raise ValueError("Action task requires an action target")
        action = validate_action(row.action, report, claims)
        if action.action != "reselect_claims":
            raise ValueError("Action curriculum contains only internal reselect_claims targets")
        if synthetic is None or action.sentence_id != corrupt_id:
            raise ValueError("Action must repair the documented unsupported target sentence")
        target = next(sentence for sentence in report.sentences if sentence.sentence_id == action.sentence_id)
        if not action.claim_ids or set(action.claim_ids) & set(target.claim_ids):
            raise ValueError("Reselection must choose OTHER claims already in the supplied pool")
        if action.replacement_text not in [claim_map[claim_id].text for claim_id in action.claim_ids]:
            raise ValueError("Reselection replacement must exactly copy a selected existing claim")
    elif row.action is not None:
        raise ValueError("Only action tasks may contain an action target")
    return row


def validate_file(input_path: Path, validated_path: Path, rejected_path: Path) -> dict[str, Any]:
    resolved = [path.resolve() for path in (input_path, validated_path, rejected_path)]
    if len(set(resolved)) != 3:
        raise ValueError("Input, validated output, and rejection output must be different files")
    rows: list[tuple[int, Any]] = []
    rejected: list[dict[str, Any]] = []
    paper_splits: dict[str, set[str]] = {}
    ids: Counter[str] = Counter()
    for line_number, line in enumerate(input_path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError("Expected a JSON object")
            rows.append((line_number, payload))
            paper_id, split = payload.get("paper_id"), payload.get("split")
            if isinstance(paper_id, str) and isinstance(split, str):
                paper_splits.setdefault(paper_id, set()).add(split)
            if isinstance(payload.get("example_id"), str):
                ids[payload["example_id"]] += 1
        except (ValueError, TypeError) as exc:
            rejected.append({"line": line_number, "reason": str(exc), "raw_line": line})
    accepted: list[TrainingExample] = []
    counts: Counter[str] = Counter()
    for line_number, payload in rows:
        try:
            example = validate_example(payload)
            if example.split == "test":
                raise ValueError("Test/manual evaluation records may not enter the SFT corpus")
            if len(paper_splits.get(example.paper_id, set())) > 1:
                raise ValueError("Paper occurs in multiple native splits; every row for that paper is rejected")
            if ids[example.example_id] > 1:
                raise ValueError("Duplicate example_id; every duplicate is rejected")
            accepted.append(example)
            counts[f"{example.split}_{example.task}"] += 1
        except (ValueError, TypeError, KeyError) as exc:
            rejected.append({"line": line_number, "reason": str(exc), "example": payload})
    validated_path.parent.mkdir(parents=True, exist_ok=True)
    rejected_path.parent.mkdir(parents=True, exist_ok=True)
    with validated_path.open("w", encoding="utf-8", newline="\n") as handle:
        for example in accepted:
            handle.write(example.model_dump_json() + "\n")
    with rejected_path.open("w", encoding="utf-8", newline="\n") as handle:
        for rejection in sorted(rejected, key=lambda item: item["line"]):
            handle.write(json.dumps(rejection, ensure_ascii=False) + "\n")
    return {"accepted": len(accepted), "rejected": len(rejected), "counts": dict(sorted(counts.items()))}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--validated", type=Path)
    parser.add_argument("--rejected", type=Path)
    parser.add_argument("--allow-rejections", action="store_true", help="Exit successfully when some rows were rejected, provided accepted rows remain")
    args = parser.parse_args(argv)
    result = validate_file(args.input or args.data_dir / "writer_sft_raw.jsonl", args.validated or args.data_dir / "writer_sft_validated.jsonl", args.rejected or args.data_dir / "writer_sft_rejected.jsonl")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["accepted"] and (not result["rejected"] or args.allow_rejections) else 1


if __name__ == "__main__":
    raise SystemExit(main())
