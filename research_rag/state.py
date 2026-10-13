"""Fields exchanged between graph nodes; each node returns a partial update."""

from __future__ import annotations

from typing import Any, TypedDict


class SourceChunk(TypedDict):
    doc_id: str
    source_id: str
    text: str
    metadata: dict[str, Any]
    score: float
    method: str


class EvidenceRef(TypedDict):
    source_id: str
    text: str


class ResearchState(TypedDict, total=False):
    # Runtime control belongs to one research task and is checkpoint-serializable.
    goal: str
    current_task: str
    research_plan: dict[str, Any]
    active_task_id: str
    plan_history: list[dict[str, Any]]
    agent_cycles: list[dict[str, Any]]
    retrieval_trace: list[dict[str, Any]]
    retrieval_autonomy: bool
    active_query: str
    next_action: dict[str, Any]
    agent_result: dict[str, Any]
    action_history: list[dict[str, Any]]
    budget: dict[str, Any]
    started_at: float
    deadline_at: float
    steps_used: int
    search_count: int
    factcheck_calls_used: int
    reserved_cost_usd: float
    stop_reason: str | None
    read_pages: list[int]
    remaining_pages: list[int]
    reader_diagnostics: dict[str, Any]
    question: str
    intent: str
    pdf_path: str | None
    pdf_chunks: list[SourceChunk]
    retrieved_chunks: list[SourceChunk]
    seen_chunks: list[SourceChunk]
    context_source_ids: list[str]
    retrieval_decision: str
    retrieval_warning: str | None
    retrieval_history: list[dict[str, Any]]
    draft_answer: str
    evidence_spans: list[str]
    evidence_refs: list[EvidenceRef]
    summary_supported: bool
    summary_confidence: str
    summary_diagnostics: dict[str, Any]
    fact_check_results: list[dict[str, Any]]
    verified_claims: list[dict[str, Any]]
    final_report: dict[str, Any]
    writer_diagnostics: dict[str, Any]
    low_confidence_warning: bool
    retry_count: int
    status: str
    errors: list[str]
