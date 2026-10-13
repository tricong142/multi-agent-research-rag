"""Measure Reader extraction against page-level PDF fixtures with known text."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

from research_rag.adapters import PdfReader


TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(unicodedata.normalize("NFKC", text).lower())


def score(manifest: Path, reader: PdfReader | None = None, *, page_no: int | None = None) -> dict:
    reader = reader or PdfReader()
    rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    if page_no is not None:
        if type(page_no) is not int or page_no < 0:
            raise ValueError("page_no must be a nonnegative integer")
        rows = [{**row, "expected_spans": [span for span in row["expected_spans"]
                                         if span["page_no"] == page_no]} for row in rows]
    if not rows:
        raise ValueError("Reader manifest is empty")
    if any(not isinstance(row.get("expected_spans"), list) or not row["expected_spans"] for row in rows):
        raise ValueError("Each PDF must have expected_spans before evaluation")
    extractions = []
    for row in rows:
        relative = Path(row["pdf_path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("PDF paths must be relative to the manifest directory")
        path = (manifest.parent / relative).resolve()
        if not path.is_file():
            extractions.append({"pdf_path": relative.as_posix(), "error_type": "FileNotFoundError"})
            continue
        if row.get("source_sha256") and hashlib.sha256(path.read_bytes()).hexdigest() != row["source_sha256"]:
            extractions.append({"pdf_path": relative.as_posix(), "error_type": "SourceHashMismatch"})
            continue
        try:
            chunks = reader.read(str(path))
        except Exception as exc:
            extractions.append({"pdf_path": relative.as_posix(), "error_type": type(exc).__name__})
            continue
        extractions.append({"pdf_path": relative.as_posix(), "chunks": chunks})
    return score_extractions(rows, extractions)


def score_extractions(rows: list[dict], extractions: list[dict]) -> dict:
    """Same scorer for live and saved chunks; no model/API/PDF needed for replay."""
    if not rows or any(not row.get("expected_spans") for row in rows):
        raise ValueError("Each PDF must have expected_spans before evaluation")
    records = {record["pdf_path"]: record for record in extractions}
    expected_paths = [Path(row["pdf_path"]).as_posix() for row in rows]
    if len(records) != len(extractions) or len(set(expected_paths)) != len(rows) or set(records) != set(expected_paths):
        raise ValueError("Need exactly one extraction record per manifest PDF")
    expected_span_count = sum(len(row["expected_spans"]) for row in rows)
    scores: list[float] = []
    exact = 0
    failed: list[dict[str, str]] = []
    by_layout: dict[str, dict[str, int]] = {}
    for row in rows:
        name = Path(row["pdf_path"]).as_posix()
        record = records[name]
        if record.get("error_type"):
            failed.append({"pdf_path": name, "error_type": record["error_type"]})
            continue
        chunks = record["chunks"]
        pages: dict[int, str] = {}
        for chunk in chunks:
            page_no = int(chunk["metadata"]["page_no"])
            pages[page_no] = pages.get(page_no, "") + " " + chunk["text"]
        layout = str(row.get("layout", "unknown"))
        layout_stats = by_layout.setdefault(layout, {"spans": 0, "exact_matches": 0})
        for span in row["expected_spans"]:
            expected = tokens(span["text"])
            actual = tokens(pages.get(int(span["page_no"]), ""))
            if not expected:
                raise ValueError("Expected span must contain searchable text")
            wanted, found = Counter(expected), Counter(actual)
            scores.append(sum((wanted & found).values()) / sum(wanted.values()))
            matched = f" {' '.join(expected)} " in f" {' '.join(actual)} "
            exact += matched
            layout_stats["spans"] += 1
            layout_stats["exact_matches"] += matched
    return {"pdf_count": len(rows), "evaluated_pdf_count": len(rows) - len(failed),
            "expected_span_count": expected_span_count, "span_coverage": len(scores) / expected_span_count,
            "overall_exact_span_rate": exact / expected_span_count,
            "span_count": len(scores), "exact_span_rate": exact / len(scores) if scores else None,
            "mean_token_recall": sum(scores) / len(scores) if scores else None,
            "by_layout": by_layout, "failures": failed,
            "annotation_origins": sorted({row.get("annotation_origin", "Project-authored fixture; see manifest provenance") for row in rows}),
            "note": "exact_span_rate is conditional on readable PDFs; overall_exact_span_rate includes failed PDFs as zero matches. Phrase/page presence only, not reading order, tables, or representative production quality."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path(__file__).resolve().parent / "reader_smoke_manifest.jsonl")
    args = parser.parse_args()
    result = score(args.manifest.resolve())
    result["passed"] = not result["failures"] and result["overall_exact_span_rate"] == 1.0
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
