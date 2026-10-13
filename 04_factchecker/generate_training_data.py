"""Build grounded Fact-Checker JSONL files from allenai/scifact.

SciFact exposes a corpus config and a flattened claims config. This script joins
them by document id, preserves rationale sentence indices, and never uses the
unlabelled public test split for supervised examples.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import config


LABEL_MAP = {
    "SUPPORT": "support",
    "CONTRADICT": "contradict",
}


def _load_scifact() -> tuple[Any, Any]:
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError("Install the 'datasets' package first") from exc
    corpus = load_dataset("allenai/scifact", "corpus", split="train", trust_remote_code=True)
    claims = load_dataset("allenai/scifact", "claims", trust_remote_code=True)
    return corpus, claims


def _normalize_doc_id(value: Any) -> str:
    return str(value).strip()


def _context(title: str, abstract: Iterable[str]) -> str:
    sentences = [str(sentence).strip() for sentence in abstract]
    body = "\n".join(f"[{i}] {sentence}" for i, sentence in enumerate(sentences))
    return f"Title: {str(title).strip()}\nAbstract:\n{body}"


def _reasoning_from_rationale(sentences: list[str]) -> str:
    quoted = " ".join(sentence.strip() for sentence in sentences if sentence.strip())
    return f'The annotated evidence states: "{quoted}"'


def build_examples(corpus_rows: Iterable[dict], claim_rows: Iterable[dict]) -> list[dict]:
    corpus = {
        _normalize_doc_id(row["doc_id"]): {
            "title": row["title"],
            "abstract": list(row["abstract"]),
        }
        for row in corpus_rows
    }
    grouped: dict[int, dict[str, Any]] = {}
    for row in claim_rows:
        claim_id = int(row["id"])
        item = grouped.setdefault(
            claim_id,
            {
                "claim": str(row["claim"]),
                "cited_doc_ids": set(),
                "evidences": [],
            },
        )
        item["cited_doc_ids"].update(
            _normalize_doc_id(doc_id) for doc_id in row.get("cited_doc_ids", [])
        )
        label = str(row.get("evidence_label", "")).strip().upper()
        doc_id = _normalize_doc_id(row.get("evidence_doc_id", ""))
        if label and doc_id:
            item["evidences"].append(
                {
                    "doc_id": doc_id,
                    "label": label,
                    "sentence_indices": [int(i) for i in row["evidence_sentences"]],
                }
            )

    examples: list[dict] = []
    for claim_id, item in sorted(grouped.items()):
        evidence_doc_ids: set[str] = set()
        seen_evidence: defaultdict[tuple[str, str], int] = defaultdict(int)
        for evidence in item["evidences"]:
            doc_id = evidence["doc_id"]
            evidence_doc_ids.add(doc_id)
            if evidence["label"] not in LABEL_MAP or doc_id not in corpus:
                continue
            doc = corpus[doc_id]
            indices = evidence["sentence_indices"]
            if any(i < 0 or i >= len(doc["abstract"]) for i in indices):
                continue
            key = (doc_id, evidence["label"])
            evidence_set = seen_evidence[key]
            seen_evidence[key] += 1
            rationale = [doc["abstract"][i] for i in indices]
            examples.append(
                {
                    "example_id": f"{claim_id}:{doc_id}:{evidence_set}",
                    "claim_id": claim_id,
                    "doc_id": doc_id,
                    "claim": item["claim"],
                    "context": _context(doc["title"], doc["abstract"]),
                    "label": LABEL_MAP[evidence["label"]],
                    "reasoning": _reasoning_from_rationale(rationale),
                    "evidence_sentence_indices": indices,
                    "evidence_sentences": rationale,
                    "source": "allenai/scifact",
                }
            )

        # In SciFact, cited documents without an annotated evidence set are the
        # document-level NOT_ENOUGH_INFO cases. Do not invent a document when a
        # claim has no cited_doc_ids.
        for doc_id in sorted(item["cited_doc_ids"] - evidence_doc_ids):
            if doc_id not in corpus:
                continue
            doc = corpus[doc_id]
            examples.append(
                {
                    "example_id": f"{claim_id}:{doc_id}:nei",
                    "claim_id": claim_id,
                    "doc_id": doc_id,
                    "claim": item["claim"],
                    "context": _context(doc["title"], doc["abstract"]),
                    "label": "not_enough_info",
                    "reasoning": (
                        "The cited context has no annotated evidence that supports "
                        "or contradicts the complete claim."
                    ),
                    "evidence_sentence_indices": [],
                    "evidence_sentences": [],
                    "source": "allenai/scifact",
                }
            )
    return examples


def write_jsonl(path: Path, rows: Iterable[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-output", type=Path, default=config.TRAIN_DATA_PATH)
    parser.add_argument("--dev-output", type=Path, default=config.DEV_DATA_PATH)
    args = parser.parse_args()

    corpus, claims = _load_scifact()
    train_rows = build_examples(corpus, claims["train"])
    dev_rows = build_examples(corpus, claims["validation"])
    train_count = write_jsonl(args.train_output, train_rows)
    dev_count = write_jsonl(args.dev_output, dev_rows)
    print(f"Wrote {train_count} train examples to {args.train_output}")
    print(f"Wrote {dev_count} dev examples to {args.dev_output}")
    print("Public test labels are absent and were not used.")


if __name__ == "__main__":
    main()
