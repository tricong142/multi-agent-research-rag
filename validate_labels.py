"""Validate generated labels, rationale indices, and duplicate examples."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import config


REQUIRED_FIELDS = {
    "example_id", "claim_id", "doc_id", "claim", "context", "label",
    "reasoning", "evidence_sentence_indices", "evidence_sentences", "source",
}


def validate_row(row: dict, line_number: int) -> list[str]:
    errors: list[str] = []
    missing = REQUIRED_FIELDS - row.keys()
    if missing:
        errors.append(f"line {line_number}: missing fields {sorted(missing)}")
        return errors
    if row["label"] not in config.LABELS:
        errors.append(f"line {line_number}: invalid label {row['label']!r}")
    if not isinstance(row["claim"], str) or not row["claim"].strip():
        errors.append(f"line {line_number}: empty claim")
    if not isinstance(row["context"], str) or not row["context"].strip():
        errors.append(f"line {line_number}: empty context")
    if not isinstance(row["reasoning"], str) or not row["reasoning"].strip():
        errors.append(f"line {line_number}: empty reasoning")
    indices = row["evidence_sentence_indices"]
    sentences = row["evidence_sentences"]
    if not isinstance(indices, list) or not all(isinstance(i, int) for i in indices):
        errors.append(f"line {line_number}: evidence indices must be integers")
    if not isinstance(sentences, list) or not all(isinstance(s, str) for s in sentences):
        errors.append(f"line {line_number}: evidence sentences must be strings")
    if isinstance(indices, list) and isinstance(sentences, list) and len(indices) != len(sentences):
        errors.append(f"line {line_number}: evidence index/text length mismatch")
    if row["label"] == "not_enough_info" and (indices or sentences):
        errors.append(f"line {line_number}: NEI must not contain gold evidence")
    if row["label"] != "not_enough_info" and not sentences:
        errors.append(f"line {line_number}: labelled evidence is empty")
    if isinstance(sentences, list):
        for sentence in sentences:
            if isinstance(sentence, str) and sentence.strip() not in row["context"]:
                errors.append(f"line {line_number}: evidence is not verbatim in context")
    return errors


def validate_file(path: Path) -> tuple[list[str], Counter]:
    errors: list[str] = []
    labels: Counter = Counter()
    seen: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"line {line_number}: invalid JSON: {exc}")
                continue
            errors.extend(validate_row(row, line_number))
            example_id = str(row.get("example_id", ""))
            if example_id in seen:
                errors.append(f"line {line_number}: duplicate example_id {example_id}")
            seen.add(example_id)
            labels[str(row.get("label", "<missing>"))] += 1
    return errors, labels


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path, default=[config.TRAIN_DATA_PATH, config.DEV_DATA_PATH])
    args = parser.parse_args()
    failed = False
    for path in args.paths:
        errors, labels = validate_file(path)
        print(f"{path}: labels={dict(labels)}, errors={len(errors)}")
        for error in errors[:50]:
            print(f"  - {error}")
        if len(errors) > 50:
            print(f"  ... {len(errors) - 50} more errors")
        failed = failed or bool(errors)
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
