"""Small adapters around the existing agents; no model is loaded on import."""

from __future__ import annotations

import hashlib
import importlib
import re
from pathlib import Path
from typing import Any

from .state import SourceChunk


class ReaderBatchError(RuntimeError):
    """Keep page decisions when a batch fails, without publishing rejected text."""
    def __init__(self, diagnostics: dict):
        super().__init__("Reader did not accept the selected page batch")
        self.diagnostics = diagnostics


class PdfReader:
    def __init__(self, agent: Any = None, *, max_pages: int = 20, max_chunk_chars: int = 2000) -> None:
        if max_pages < 1 or max_chunk_chars < 1:
            raise ValueError("Reader limits must be positive")
        self.agent = agent
        self.max_pages = max_pages
        self.max_chunk_chars = max_chunk_chars

    def read(self, pdf_path: str) -> list[SourceChunk]:
        """Compatibility entry point for extraction evaluations: read every permitted page."""
        return self._read(pdf_path, question="", excluded_pages=[], page_batch=None)["chunks"]

    def read_for_question(self, pdf_path: str, *, question: str, excluded_pages: list[int],
                          page_batch: int = 3) -> dict:
        return self._read(pdf_path, question=question, excluded_pages=excluded_pages, page_batch=page_batch)

    def _read(self, pdf_path: str, *, question: str, excluded_pages: list[int], page_batch: int | None) -> dict:
        import fitz

        path = Path(pdf_path).resolve()
        if not path.is_file() or path.suffix.lower() != ".pdf":
            raise ValueError("pdf_path must point to an existing PDF")
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for part in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(part)
        document_hash = digest.hexdigest()[:16]
        with fitz.open(path) as document:
            page_count = len(document)
            if page_count > self.max_pages:
                raise ValueError(f"PDF has {page_count} pages, above max_pages={self.max_pages}")
            candidates = [i for i in range(page_count) if i not in excluded_pages]
            terms = set(re.findall(r"\w+", question.casefold()))
            # Cheap lexical preview selects expensive OCR/layout work. Empty/scanned pages
            # remain candidates and are visited on subsequent requests, never deemed irrelevant.
            scores = {i: len(terms.intersection(re.findall(r"\w+", document[i].get_text().casefold()))) for i in candidates}
            ranked = sorted(candidates, key=lambda i: (-scores[i], i))
            selected = ranked if page_batch is None else ranked[:page_batch]
        if page_count > self.max_pages:
            raise ValueError(f"PDF has {page_count} pages, above max_pages={self.max_pages}")
        if self.agent is None:
            agent_class = importlib.import_module("train_agent2_reader.reader_agent").ReaderAgent
            model_dir = Path(__file__).resolve().parents[1] / "train_agent2_reader" / "layoutlmv3_doclaynet_model"
            self.agent = agent_class(layoutlmv3_model_dir=str(model_dir))

        chunks: list[SourceChunk] = []
        page_trials = []
        diagnostics = {"page_count": page_count, "selected_pages": selected,
                       "page_trials": page_trials,
                       "selection_method": "lexical_preview" if question else "all_pages"}
        for page_no in selected:
            try:
                result = self.agent.process_page(str(path), page_no)
            except Exception as exc:
                page_trials.append({"page_no": page_no, "accepted": False,
                                    "error_type": type(exc).__name__})
                raise ReaderBatchError(diagnostics) from exc
            page_trials.append({"page_no": page_no, "attempts": result.get("attempts", []),
                                "final_tool": result.get("final_tool"), "accepted": result.get("success") is True})
            if result.get("success") is not True:
                raise ReaderBatchError(diagnostics)
            for block_no, block in enumerate(result.get("blocks", [])):
                text = str(block.text).strip()
                if not text:
                    continue
                for part_no, start in enumerate(range(0, len(text), self.max_chunk_chars)):
                    part = text[start:start + self.max_chunk_chars]
                    source_id = f"pdf:{document_hash}:p{page_no}:b{block_no}:c{part_no}"
                    chunks.append({
                        "doc_id": source_id,
                        "source_id": source_id,
                        "text": part,
                        "metadata": {
                            "page_no": page_no,
                            "bbox": list(block.bbox),
                            "label": block.label,
                            "source_tool": block.source_tool,
                        },
                        "score": 0.0,
                        "method": "reader",
                    })
        return {"chunks": chunks, "read_pages": selected,
                "remaining_pages": [i for i in candidates if i not in selected],
                "diagnostics": diagnostics}
