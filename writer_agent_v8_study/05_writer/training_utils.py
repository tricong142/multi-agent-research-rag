"""CPU-testable data preparation; no torch/transformers import at module import."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_training_splits(path: Path) -> tuple[list[Any], list[Any]]:
    """Revalidate labels and retain QASPER's native paper-disjoint split."""
    from .validate_labels import validate_example

    if "manual" in path.name.lower():
        raise ValueError("Manual evaluation data must never be used by the trainer.")
    splits: dict[str, list[Any]] = {"train": [], "validation": []}
    ids: set[str] = set()
    with path.open(encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = validate_example(json.loads(line))
                if row.split not in splits:
                    raise ValueError("Only native train/validation are allowed; test is held out.")
                if not row.paper_id.strip():
                    raise ValueError("paper_id is required to check split leakage.")
                if row.example_id in ids:
                    raise ValueError(f"Duplicate example_id: {row.example_id}")
                ids.add(row.example_id)
                splits[row.split].append(row)
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                raise ValueError(f"{path}:{line_number}: {exc}") from exc
    if not all(splits.values()):
        raise ValueError("The validated file must contain nonempty native train AND validation splits.")
    overlap = {row.paper_id for row in splits["train"]} & {
        row.paper_id for row in splits["validation"]
    }
    if overlap:
        raise ValueError(f"Train/validation paper leakage: {sorted(overlap)[:10]}")
    return splits["train"], splits["validation"]


def encode_completion(
    messages: list[dict[str, str]], tokenizer: Any, max_length: int
) -> dict[str, list[int]] | None:
    """Mask the exact chat prompt, including the assistant header.

    Long examples are excluded as a whole. Cropping a structured target would
    teach invalid JSON; cropping a prompt could remove supporting evidence.
    """
    if max_length < 2:
        raise ValueError("max_length must be >= 2")
    if not messages or messages[-1].get("role") != "assistant":
        raise ValueError("Expected one final assistant completion.")
    json.loads(messages[-1]["content"])
    prefix = tokenizer.apply_chat_template(
        messages[:-1], tokenize=True, add_generation_prompt=True,
        # Transformers 5.x changed this default to True and returns a
        # BatchEncoding. Keep the pinned 4.48 behavior explicit so token-boundary
        # checks work identically during local dry-runs and Kaggle training.
        return_dict=False,
    )
    full = tokenizer.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=False,
        return_dict=False,
    )
    if len(full) > max_length:
        return None
    if not prefix or full[: len(prefix)] != prefix:
        raise ValueError(
            "Chat-template prefix does not match full sequence; cannot safely mask prompt. "
            "Use the shipped Qwen chat template or adapt the template explicitly."
        )
    if len(full) <= len(prefix):
        raise ValueError("No assistant tokens remain for supervised learning.")
    return {
        "input_ids": full,
        "attention_mask": [1] * len(full),
        "labels": [-100] * len(prefix) + full[len(prefix) :],
    }


def prepare_examples(rows: list[Any], tokenizer: Any, max_length: int) -> tuple[list[dict], dict]:
    from .prompts import training_messages

    features: list[dict] = []
    dropped_tasks: Counter = Counter()
    kept_tasks: Counter = Counter()
    dropped_ids: list[str] = []
    for row in rows:
        encoded = encode_completion(training_messages(row), tokenizer, max_length)
        if encoded is None:
            dropped_tasks[row.task] += 1
            dropped_ids.append(row.example_id)
            continue
        features.append(encoded)
        kept_tasks[row.task] += 1
    if not features:
        raise ValueError("All examples exceed max_seq_length; no training/evaluation is possible.")
    return features, {
        "input_examples": len(rows),
        "kept_examples": len(features),
        "dropped_overlong": len(dropped_ids),
        "dropped_example_ids": dropped_ids,
        "kept_by_task": dict(kept_tasks),
        "dropped_by_task": dict(dropped_tasks),
        "input_tokens": sum(len(row["input_ids"]) for row in features),
        "supervised_tokens": sum(sum(token != -100 for token in row["labels"]) for row in features),
        "max_sequence_length": max(len(row["input_ids"]) for row in features),
    }


class CompletionCollator:
    """Dynamic right padding; EOS targets stay supervised even when EOS is PAD."""

    def __init__(self, pad_token_id: int, pad_to_multiple_of: int = 8):
        self.pad_token_id = pad_token_id
        self.pad_to_multiple_of = pad_to_multiple_of

    def __call__(self, features: list[dict]) -> dict:
        import torch

        width = max(len(row["input_ids"]) for row in features)
        width = ((width + self.pad_to_multiple_of - 1) // self.pad_to_multiple_of) * self.pad_to_multiple_of
        batch = {"input_ids": [], "attention_mask": [], "labels": []}
        for row in features:
            count = width - len(row["input_ids"])
            batch["input_ids"].append(row["input_ids"] + [self.pad_token_id] * count)
            batch["attention_mask"].append(row["attention_mask"] + [0] * count)
            batch["labels"].append(row["labels"] + [-100] * count)
        return {key: torch.tensor(value, dtype=torch.long) for key, value in batch.items()}
