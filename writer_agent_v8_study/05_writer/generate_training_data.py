"""Derive conservative Writer labels from QASPER evidence, without a teacher API.

QASPER is QA/evidence annotation, not verified-claim/report/critique ground truth.
Here ``verified`` means a verbatim match to the supplied paper text only. The
derived report target copies that evidence; it does not assert that an answer
annotation is entailed. Synthetic negative labels are explicitly identified.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "05_writer"

from .schemas import (
    CritiqueResult, ReportSchema, ReportSentence, SentenceCritique,
    TrainingExample, VerifiedClaim, WriterAction,
)

DATASET_ID = "allenai/qasper"
# Converted Parquet revision observed in the upstream repository. Pinning avoids
# executing its legacy dataset script and makes subsequent runs reproducible.
PARQUET_REVISION = "06806e4608976fc2fac0a090ac425d5b2b29caf4"
SPLITS = ("train", "validation", "test")
DATA_DIR = Path(__file__).resolve().parent / "data"
QUOTE_LIMITATION = "The available claims may not fully answer the intent."


def _strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple)):
        if any(not isinstance(item, str) for item in value):
            raise ValueError("Expected a list of text strings")
        return [item for item in value if item.strip()]
    raise ValueError("Expected text or a list of text strings")


def columnar_records(value: Any, key: str) -> list[dict[str, Any]]:
    """Normalize Arrow's dict-of-lists and original QASPER list-of-dicts.

    ``key`` identifies the *record* dimension; nested arrays such as evidence
    must not be flattened. Unequal column lengths are rejected, never zipped
    silently and truncated.
    """
    if value is None:
        return []
    if isinstance(value, list):
        if any(not isinstance(item, Mapping) for item in value):
            raise ValueError(f"{key}: expected records, not scalar values")
        return [dict(item) for item in value]
    if not isinstance(value, Mapping):
        raise ValueError(f"{key}: expected a record collection")
    primary = value.get(key)
    if not isinstance(primary, list):
        return [dict(value)]
    count = len(primary)
    for name, items in value.items():
        if isinstance(items, list) and len(items) != count:
            raise ValueError(f"{key}: column {name!r} has an inconsistent length")
    return [
        {name: items[index] if isinstance(items, list) else items for name, items in value.items()}
        for index in range(count)
    ]


def normalize_questions(paper: Mapping[str, Any]) -> list[dict[str, Any]]:
    return columnar_records(paper.get("qas"), "question")


def normalize_answers(question: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = question.get("answers", [])
    if isinstance(raw, Mapping) and isinstance(raw.get("answer"), Mapping):
        # Also accept Arrow readers that retain an inner struct-of-lists.
        nested = raw["answer"]
        if isinstance(nested.get("unanswerable"), list):
            records = columnar_records(nested, "unanswerable")
            return [dict(answer) for answer in records]
    wrappers = columnar_records(raw, "answer")
    result: list[dict[str, Any]] = []
    for wrapper in wrappers:
        answer = wrapper.get("answer", wrapper)
        if not isinstance(answer, Mapping):
            raise ValueError("Answer annotation must be an object")
        result.append(dict(answer))
    return result


def answer_metadata(answer: Mapping[str, Any]) -> dict[str, Any]:
    """Preserve ``False`` as a No answer; never use truthiness to classify it."""
    yes_no = answer.get("yes_no")
    if yes_no is not None and not isinstance(yes_no, bool):
        raise ValueError("QASPER yes_no must be true, false, or null")
    unanswerable = answer.get("unanswerable", False)
    if not isinstance(unanswerable, bool):
        raise ValueError("QASPER unanswerable must be a boolean")
    spans = _strings(answer.get("extractive_spans"))
    free_form = answer.get("free_form_answer") or ""
    if not isinstance(free_form, str):
        raise ValueError("QASPER free_form_answer must be text")
    return {
        "unanswerable": unanswerable,
        "yes_no": yes_no,
        "extractive_spans": spans,
        "free_form_answer": free_form,
    }


def _paragraphs(paper: Mapping[str, Any]) -> list[str]:
    sections = columnar_records(paper.get("full_text", []), "section_name")
    return [text for section in sections for text in _strings(section.get("paragraphs"))]


def _conflicting_answers(annotations: list[dict[str, Any]]) -> bool:
    answerability = {item["unanswerable"] for item in annotations}
    polarities = {item["yes_no"] for item in annotations if item["yes_no"] is not None}
    return len(answerability) > 1 or len(polarities) > 1


def extract_claims(
    paper: Mapping[str, Any], question: Mapping[str, Any], *,
    max_claims: int = 4, max_claim_chars: int = 900,
) -> tuple[list[VerifiedClaim], dict[str, Any]]:
    """Use textual evidence present verbatim in full_text; omit visual markers.

    Highlighted evidence is preferred when it is an exact substring of an
    annotated paragraph. Long snippets are omitted rather than truncated into
    potentially misleading fragments. Unanswerable/contradictory annotations
    produce an empty pool and an explicit limitation.
    """
    answers = normalize_answers(question)
    annotations = [answer_metadata(answer) for answer in answers]
    metadata: dict[str, Any] = {
        "answer_annotations": annotations,
        "contradictory_annotations": _conflicting_answers(annotations),
        "all_unanswerable": bool(annotations) and all(a["unanswerable"] for a in annotations),
        "dropped_visual_evidence": 0,
        "dropped_unmatched_evidence": 0,
        "dropped_long_snippets": 0,
    }
    if metadata["contradictory_annotations"] or metadata["all_unanswerable"]:
        return [], metadata
    paragraphs = _paragraphs(paper)
    claims: list[VerifiedClaim] = []
    seen: set[str] = set()
    paper_id = str(paper["id"])
    for answer in answers:
        if answer.get("unanswerable", False):
            continue
        highlights = _strings(answer.get("highlighted_evidence"))
        for evidence in _strings(answer.get("evidence")):
            if evidence.lstrip().startswith("FLOAT SELECTED"):
                metadata["dropped_visual_evidence"] += 1
                continue
            matches = [index for index, paragraph in enumerate(paragraphs) if evidence == paragraph]
            if not matches:
                metadata["dropped_unmatched_evidence"] += 1
                continue
            selected = [span for span in highlights if span in evidence and not span.lstrip().startswith("FLOAT SELECTED")]
            for text in selected or [evidence]:
                if text in seen:
                    continue
                if len(text) > max_claim_chars:
                    metadata["dropped_long_snippets"] += 1
                    continue
                seen.add(text)
                digest = hashlib.sha256(f"{paper_id}\0{text}".encode("utf-8")).hexdigest()[:16]
                claims.append(VerifiedClaim(
                    claim_id=f"qasper_{digest}", text=text, evidence=evidence,
                    source_id=f"qasper:{paper_id}:paragraph:{matches[0]}",
                    confidence=1.0, verification_status="verified",
                ))
                if len(claims) == max_claims:
                    metadata["claim_cap_reached"] = True
                    return claims, metadata
    return claims, metadata


def unsupported_text(marker: str) -> str:
    """Recognizable fabricated training corruption, never a real QASPER fact."""
    return f"The paper reports {marker} as an established finding."


def examples_for_paper(
    paper: Mapping[str, Any], split: str, *, max_claims: int = 4,
    max_claim_chars: int = 900, source_provenance: dict[str, Any] | None = None,
) -> Iterable[TrainingExample]:
    if split not in SPLITS:
        raise ValueError(f"Unknown native split: {split}")
    if not paper.get("id"):
        raise ValueError("Paper must include an id")
    paper_id = str(paper["id"])
    for question_index, question in enumerate(normalize_questions(paper)):
        original_question = question.get("question")
        if not isinstance(original_question, str) or not original_question.strip():
            raise ValueError(f"{paper_id}: missing question text")
        claims, metadata = extract_claims(paper, question, max_claims=max_claims, max_claim_chars=max_claim_chars)
        question_id = str(question.get("question_id") or question_index)
        key = hashlib.sha256(f"{paper_id}\0{question_id}".encode("utf-8")).hexdigest()[:20]
        provenance = {
            "dataset": DATASET_ID, "license": "CC-BY-4.0",
            "claim_verification": "verbatim_source_match",
            "question_id": question_id, "original_question": original_question,
            **(source_provenance or {}), **metadata,
        }
        intent = (
            "Provide only verbatim evidence excerpts relevant to this research question: "
            f"{original_question} Do not infer an answer beyond the supplied excerpts."
        )
        limitations = [QUOTE_LIMITATION]
        if not claims:
            limitations.append("Insufficient verified claims to answer the intent.")
        report = ReportSchema(
            title="Research report",
            sentences=[ReportSentence(sentence_id=f"s{index + 1}", text=claim.text, claim_ids=[claim.claim_id]) for index, claim in enumerate(claims[:2])],
            limitations=limitations,
        )
        critique = CritiqueResult(
            sentence_reviews=[SentenceCritique(sentence_id=sentence.sentence_id, verdict="supported", reason="The sentence exactly quotes its cited evidence claim.") for sentence in report.sentences],
            needs_more_evidence=not bool(claims),
            summary="Derived quote-consistency labels; no human semantic review.",
        )
        common = dict(paper_id=paper_id, split=split, verified_claims=claims, intent=intent, report=report, critique=critique, provenance=provenance, label_origin="derived_evidence_quote", human_reviewed=False)
        yield TrainingExample(example_id=f"{key}:report", task="report", **common)
        yield TrainingExample(example_id=f"{key}:critic_positive", task="critic", **common)
        if not claims:
            continue
        marker = f"WRITER_SYNTHETIC_UNSUPPORTED_{key.upper()}"
        if any(marker in claim.evidence for claim in claims) or marker in original_question:
            raise ValueError("Synthetic marker unexpectedly occurs in source material")
        corrupted = ReportSchema(
            title="Research report",
            sentences=[ReportSentence(sentence_id="s1", text=unsupported_text(marker), claim_ids=[claims[0].claim_id])],
            limitations=[QUOTE_LIMITATION],
        )
        negative_critique = CritiqueResult(
            sentence_reviews=[SentenceCritique(sentence_id="s1", verdict="unsupported", reason="The assertion introduces a synthetic result absent from the cited evidence.")],
            needs_more_evidence=False,
            summary="Synthetic unsupported candidate; an existing evidence claim can replace it.",
        )
        negative_provenance = {**provenance, "synthetic_corruption": {"kind": "unsupported_marker", "sentence_id": "s1", "marker": marker}}
        negative_common = {**common, "report": corrupted, "critique": negative_critique, "provenance": negative_provenance, "label_origin": "synthetic_unsupported"}
        yield TrainingExample(example_id=f"{key}:critic_negative", task="critic", **negative_common)
        if len(claims) > 1:
            # No request_new_claim, retrieval, external tool, or round-trip label.
            alternative = claims[1]
            action = WriterAction(action="reselect_claims", sentence_id="s1", claim_ids=[alternative.claim_id], replacement_text=alternative.text, reason="Replace the unsupported assertion using another claim already in the supplied pool.")
            yield TrainingExample(example_id=f"{key}:action_reselect", task="action", action=action, **{**negative_common, "label_origin": "synthetic_reselection"})


def load_local_papers(path: Path) -> list[dict[str, Any]]:
    """Read original {paper_id: paper} JSON, a paper array, or JSONL rows."""
    if path.suffix.lower() == ".jsonl":
        payload = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    else:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(payload, dict):
        if "qas" in payload:
            payload = [payload]
        else:
            payload = [{**paper, "id": str(paper_id)} for paper_id, paper in payload.items()]
    if not isinstance(payload, list) or any(not isinstance(paper, dict) for paper in payload):
        raise ValueError(f"{path}: expected QASPER paper records")
    return payload


def load_hf_splits(revision: str = PARQUET_REVISION) -> Any:
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError("Install datasets to load Parquet, or supply --local-json SPLIT=PATH.") from exc
    data_files = {
        split: f"https://huggingface.co/datasets/{DATASET_ID}/resolve/{revision}/qasper/{split}/0000.parquet"
        for split in SPLITS
    }
    return load_dataset("parquet", data_files=data_files)


def generate_dataset(
    split_records: Mapping[str, Iterable[Mapping[str, Any]]], output_dir: Path, *,
    max_papers_per_split: int | None = None, max_claims: int = 4,
    max_claim_chars: int = 900, manual_candidates: int = 100,
    provenance_by_split: Mapping[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if max_claims < 1 or max_claim_chars < 1 or manual_candidates < 0:
        raise ValueError("Claim limits must be positive and manual_candidates nonnegative")
    if max_papers_per_split is not None and max_papers_per_split < 1:
        raise ValueError("max_papers_per_split must be positive")
    seen_papers: dict[str, str] = {}
    counts: Counter[str] = Counter()
    training_rows: list[TrainingExample] = []
    test_rows: list[TrainingExample] = []
    for split in SPLITS:
        for index, paper in enumerate(split_records.get(split, [])):
            # Validate the partition before applying a debugging/subsample cap.
            if not paper.get("id"):
                raise ValueError(f"{split}: a paper is missing its id")
            paper_id = str(paper["id"])
            if paper_id in seen_papers:
                raise ValueError(f"Duplicate/leaked paper {paper_id!r}: {seen_papers[paper_id]} and {split}")
            seen_papers[paper_id] = split
            if max_papers_per_split is not None and index >= max_papers_per_split:
                continue
            counts[f"papers_{split}"] += 1
            for example in examples_for_paper(paper, split, max_claims=max_claims, max_claim_chars=max_claim_chars, source_provenance=(provenance_by_split or {}).get(split)):
                counts[f"{split}_{example.task}"] += 1
                if split == "test":
                    if example.task == "report" and len(test_rows) < manual_candidates:
                        test_rows.append(example)
                else:
                    training_rows.append(example)
    if not training_rows:
        raise ValueError("No training/validation examples produced; check input files and native split names")
    # All inputs and paper boundaries have been checked before any output writes.
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(output_dir / "writer_sft_raw.jsonl", training_rows)
    _write_jsonl(output_dir / "writer_eval_candidates.jsonl", test_rows)
    # Invalidate outputs from any previous corpus; preserve human annotations.
    for name in ("writer_sft_validated.jsonl", "writer_sft_rejected.jsonl"):
        (output_dir / name).write_text("", encoding="utf-8")
    (output_dir / "writer_eval_manual.jsonl").touch(exist_ok=True)
    result = {
        "dataset": DATASET_ID, "counts": dict(sorted(counts.items())),
        "training_examples": len(training_rows), "manual_review_candidates": len(test_rows),
        "human_reviewed_examples_generated": 0,
        "claim_verification": "verbatim_source_match, not independent semantic verification",
        "max_claims": max_claims, "max_claim_chars": max_claim_chars,
        "sources": dict(provenance_by_split or {}),
    }
    (output_dir / "generation_manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def _write_jsonl(path: Path, rows: Iterable[TrainingExample]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(row.model_dump_json() + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--local-json", action="append", default=[], metavar="SPLIT=PATH", help="Original local QASPER JSON/JSONL with its native split; repeat per split.")
    parser.add_argument("--revision", default=PARQUET_REVISION, help="Pinned Hugging Face Parquet revision")
    parser.add_argument("--max-papers-per-split", type=int)
    parser.add_argument("--max-claims", type=int, default=4)
    parser.add_argument("--max-claim-chars", type=int, default=900)
    parser.add_argument("--manual-candidates", type=int, default=100)
    args = parser.parse_args(argv)
    if args.local_json:
        records: dict[str, Any] = {}
        provenance: dict[str, dict[str, Any]] = {}
        for spec in args.local_json:
            split, separator, filename = spec.partition("=")
            if not separator or split not in SPLITS or split in records:
                parser.error("--local-json requires a unique train=PATH, validation=PATH, or test=PATH")
            path = Path(filename)
            records[split] = load_local_papers(path)
            provenance[split] = {"source_transport": "user_supplied_qasper_json", "source_file": path.name, "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    else:
        records = load_hf_splits(args.revision)
        provenance = {split: {"source_transport": "hf_parquet", "source_revision": args.revision} for split in SPLITS}
    result = generate_dataset(records, args.output_dir, max_papers_per_split=args.max_papers_per_split, max_claims=args.max_claims, max_claim_chars=args.max_claim_chars, manual_candidates=args.manual_candidates, provenance_by_split=provenance)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("Next: python 05_writer/validate_labels.py --data-dir", args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
