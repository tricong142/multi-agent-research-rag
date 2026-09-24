from typing import TypedDict, Annotated, Optional, Any
import operator

class AgentState(TypedDict, total=False):
    """
    AgentState dùng chung cho toàn bộ StateGraph của Multi-Agent RAG.
    Đọc/ghi qua reducer của LangGraph.
    """
    query: str
    intent: str
    pdf_path: Optional[str]
    sub_queries: list[str]
    retrieved_docs: list[dict[str, Any]]
    document_schema: dict[str, Any]
    answer: str
    evidence_spans: list[str]
    claims: list[str]
    verified_claims: list[dict[str, Any]]
    fact_check_label: str  # "support" | "contradict" | "not_enough_info"
    final_report: str
    retry_count: int  # Tầng ngoài Orchestrator (giới hạn 3 lần)
    confidence: str   # "high" | "low"
    reasoning_trace: Annotated[list[dict[str, Any]], operator.add]
