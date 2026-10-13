"""Search the existing aligned BM25/FAISS artifacts or a PDF's transient chunks."""

from __future__ import annotations

import heapq
import json
import pickle
import re
import time
from pathlib import Path
from typing import Any, Callable

from .state import SourceChunk
from .controller import AgentResult
from .planning import active_task, task_question
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal


ROOT = Path(__file__).resolve().parents[1]
INDEX_DIR = ROOT / "kb_indexing" / "indices"
CORPUS_PATH = ROOT / "kb_indexing" / "data" / "corpus.jsonl"
EMBEDDING_MODEL = "BAAI/bge-large-en-v1.5"  # model used by 03_build_faiss.py
EMBEDDING_REVISION = "d4aa6901d3a41ba39fb536a557fa166f842b0e09"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")  # exactly the tokenizer used to build BM25


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


class IndexMismatchError(ValueError):
    """The stored indices cannot safely be mapped back to the corpus."""


class RetrievalService:
    def __init__(
        self,
        corpus_path: Path = CORPUS_PATH,
        index_dir: Path = INDEX_DIR,
        *,
        encoder: Any = None,
        offline: bool = True,
        policy: Callable[[str, list[dict[str, Any]]], str] | None = None,
    ) -> None:
        self.corpus_path = Path(corpus_path)
        self.index_dir = Path(index_dir)
        self.encoder = encoder
        self.offline = offline
        # Runtime exposes implemented tools only. Training-router labels are separate.
        self.policy = policy or (lambda query, history: "dense" if history and history[-1].get("tool") == "bm25" else "bm25")
        self._rows: list[dict[str, Any]] | None = None
        self._bm25: Any = None
        self._faiss_index: Any = None

    def _load_static(self) -> None:
        if self._rows is not None:
            return
        with self.corpus_path.open(encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream if line.strip()]
        ids = [row.get("doc_id") for row in rows]
        if not rows or len(set(ids)) != len(ids) or any(not row.get("text") for row in rows):
            raise IndexMismatchError("Corpus has missing, duplicate, or empty chunks")
        # Only load this pickle from the local trusted build pipeline, never user uploads.
        with (self.index_dir / "bm25_index.pkl").open("rb") as stream:
            saved = pickle.load(stream)
        with (self.index_dir / "faiss_doc_ids.json").open(encoding="utf-8") as stream:
            faiss_ids = json.load(stream)
        if (
            not isinstance(saved, dict)
            or saved.get("doc_ids") != ids
            or saved.get("corpus") != [row["text"] for row in rows]
            or faiss_ids != ids
        ):
            raise IndexMismatchError("Corpus, BM25, and FAISS ID mapping disagree")
        self._bm25 = saved["bm25"]
        self._rows = rows

    def _get_encoder(self) -> Any:
        if self.encoder is None:
            from sentence_transformers import SentenceTransformer

            self.encoder = SentenceTransformer(EMBEDDING_MODEL, revision=EMBEDDING_REVISION,
                                               local_files_only=self.offline)
        return self.encoder

    def _get_faiss_index(self) -> Any:
        if self._faiss_index is None:
            import faiss

            index = faiss.read_index(str(self.index_dir / "faiss_arxiv.index"))
            if index.ntotal != len(self._rows or []):
                raise IndexMismatchError("FAISS vector count differs from corpus")
            self._faiss_index = index
        return self._faiss_index

    @staticmethod
    def _format(row: dict[str, Any], score: float, method: str) -> SourceChunk:
        doc_id = str(row["doc_id"])
        return {
            "doc_id": doc_id,
            "source_id": str(row.get("source_id") or doc_id),
            "text": str(row["text"]),
            "metadata": dict(row.get("metadata") or {}),
            "score": float(score),
            "method": method,
        }

    @staticmethod
    def _bm25_search(query: str, rows: list[dict[str, Any]], index: Any, top_k: int, *, pdf: bool = False) -> list[SourceChunk]:
        tokens = tokenize(query)
        if not tokens:
            return []
        scores = index.get_scores(tokens)
        query_terms = set(tokens)
        # rank_bm25 can assign zero/negative IDF to matching terms in small corpora.
        # Keep lexical matches even then; an empty token intersection is not a hit.
        frequencies = getattr(index, "doc_freqs", None)
        candidates = ((i, score) for i, score in enumerate(scores)
                      if score > 0 or query_terms.intersection(
                          frequencies[i] if frequencies is not None else tokenize(rows[i]["text"])
                      ))
        top = heapq.nlargest(top_k, candidates, key=lambda pair: float(pair[1]))
        return [RetrievalService._format(rows[i], float(score), "bm25") for i, score in top]

    def _dense_search(self, query: str, rows: list[dict[str, Any]], top_k: int, *, pdf: bool) -> list[SourceChunk]:
        import faiss
        import numpy as np

        encoder = self._get_encoder()
        if pdf:
            vectors = np.asarray(encoder.encode([r["text"] for r in rows], normalize_embeddings=True), dtype="float32")
            if vectors.ndim != 2 or len(vectors) != len(rows):
                raise ValueError("PDF embedding output has the wrong shape")
            index = faiss.IndexFlatIP(vectors.shape[1])
            index.add(vectors)
        else:
            index = self._get_faiss_index()
        vector = np.asarray(encoder.encode(QUERY_PREFIX + query, normalize_embeddings=True), dtype="float32").reshape(1, -1)
        if vector.shape[1] != index.d:
            raise IndexMismatchError("Query embedding dimension differs from FAISS index")
        scores, positions = index.search(vector, min(top_k, len(rows)))
        return [self._format(rows[int(i)], float(score), "dense") for score, i in zip(scores[0], positions[0]) if i >= 0]

    def search(
        self,
        query: str,
        *,
        pdf_chunks: list[SourceChunk] | None = None,
        top_k: int = 5,
        history: list[dict[str, Any]] | None = None,
        method: str | None = None,
    ) -> dict[str, Any]:
        if not query.strip() or not 1 <= top_k <= 50:
            raise ValueError("Non-empty query and top_k in [1, 50] are required")
        selected = method if method is not None else self.policy(query, history or [])
        if selected not in {"bm25", "dense"}:
            raise ValueError(f"Unimplemented retrieval action: {selected}; available: bm25, dense")
        seen_ids = {doc_id for trial in (history or []) for doc_id in trial.get("doc_ids", [])}
        search_k = min(50, top_k + len(seen_ids))
        pdf = pdf_chunks is not None
        if pdf:
            rows = list(pdf_chunks or [])
            if not rows:
                return {"chunks": [], "decision": selected, "warning": "empty_pdf_index"}
            from rank_bm25 import BM25Okapi

            bm25 = BM25Okapi([tokenize(row["text"]) for row in rows])
        else:
            self._load_static()
            rows, bm25 = self._rows or [], self._bm25
        warning = None
        mode = selected
        if mode == "dense":
            try:
                chunks = self._dense_search(query, rows, search_k, pdf=pdf)
            except IndexMismatchError:
                raise
            except Exception as exc:  # model availability is an external boundary
                chunks = self._bm25_search(query, rows, bm25, search_k, pdf=pdf)
                mode = "bm25"
                warning = f"dense_unavailable:{type(exc).__name__};used_bm25" if warning is None else warning + f";dense_unavailable:{type(exc).__name__};used_bm25"
        else:
            chunks = self._bm25_search(query, rows, bm25, search_k, pdf=pdf)
        chunks = [chunk for chunk in chunks if chunk["doc_id"] not in seen_ids][:top_k]
        return {"chunks": chunks, "decision": mode, "requested_method": selected, "warning": warning}


class RetrievalChoice(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    query: str = Field(min_length=1, max_length=4000)
    method: Literal["bm25", "dense"]
    reason: Literal["target_missing_information", "exact_terms_first", "semantic_expansion", "untried_tool"]


class RetrievalAgent:
    """Own query/tool policy; one search per delegation, sharing the task's global budget.

    A hit is a candidate, never proof of relevance or factual support. The controller
    decides whether to grant another search after the summarizer/checker feedback.
    """
    def __init__(self, service: RetrievalService, *, policy: str = "adaptive"):
        if policy not in {"adaptive", "bm25", "dense"}:
            raise ValueError("Unknown retrieval policy")
        self.service, self.policy = service, policy

    def choose(self, state: dict, top_k: int) -> RetrievalChoice | None:
        task = active_task(state)
        feedback = state.get("agent_result", {})
        query = (feedback.get("suggested_query") or task.get("query") or state.get("active_query") or task_question(state)).strip()[:4000]
        history = state.get("retrieval_history", [])
        own_history = [h for h in history if h.get("task_id") == state.get("active_task_id")]
        reason = "target_missing_information" if feedback.get("suggested_query") else "exact_terms_first"
        method = self.policy if self.policy != "adaptive" else "bm25"
        if self.policy == "adaptive" and own_history and (feedback.get("missing_information") or not own_history[-1].get("has_hits")):
            method, reason = "dense", "semantic_expansion"
        methods = [method, "dense" if method == "bm25" else "bm25"] if self.policy == "adaptive" else [method]
        for index, candidate in enumerate(methods):
            # Excluding newly seen documents changes the search space. Stop repeating
            # an identical search only when its latest attempt made no progress.
            matching = [h for h in history if (h.get("query"), h.get("requested_method"), h.get("top_k")) == (query, candidate, top_k)]
            if not matching or matching[-1].get("doc_ids"):
                return RetrievalChoice(query=query, method=candidate, reason="untried_tool" if index else reason)
        return None

    def run(self, *, state: dict, top_k: int) -> dict:
        if state["search_count"] >= state["budget"]["max_searches"]:
            raise TimeoutError("Retrieval permission expired")
        choice = self.choose(state, top_k)
        if choice is None:
            return {"chunks": [], "decision": "none", "warning": "no_untried_search", "trace": [],
                    "agent_result": AgentResult(agent="search", completed="no_untried_search",
                                                missing_information=[task_question(state)], suggested_action="stop").model_dump()}
        started = time.perf_counter()
        result = self.service.search(choice.query, method=choice.method, top_k=top_k,
                                     pdf_chunks=state.get("pdf_chunks") if state.get("pdf_path") else None,
                                     history=state.get("retrieval_history", []))
        chunks = result["chunks"]
        sources = [c["source_id"] for c in chunks]
        outcome = AgentResult(agent="search", completed="candidates_found" if chunks else "no_new_candidates",
                              evidence_source_ids=sources, missing_information=[] if chunks else [task_question(state)],
                              suggested_action="summarize" if chunks else "search",
                              suggested_query=None if chunks else choice.query)
        trace = {"task_id": state.get("active_task_id"), "policy": self.policy,
                 "observation": {"previous_searches": len(state.get("retrieval_history", [])),
                                 "missing_information": state.get("agent_result", {}).get("missing_information", [])},
                 "choice": choice.model_dump(), "actual_tool": result["decision"], "source_ids": sources,
                 "evaluation": {"new_candidates": len(chunks), "relevance_verified": False, "warning": result.get("warning")},
                 "elapsed_ms": round((time.perf_counter() - started) * 1000, 2), "handoff_to": "controller"}
        return result | {"query": choice.query, "requested_method": choice.method,
                         "trace": [trace], "agent_result": outcome.model_dump()}
