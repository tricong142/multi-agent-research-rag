"""Evidence-driven controller; no model loading, invented tools, or free-form routing."""
from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .state import ResearchState
from .planning import plan_complete

Action = Literal["read", "search", "summarize", "factcheck", "write", "stop"]
EXECUTABLE_ACTIONS = ("read", "search", "summarize", "factcheck", "write")


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    action: Action
    reason: str = Field(min_length=1, max_length=500)
    query: str | None = Field(default=None, min_length=1, max_length=4000)
    method: Literal["bm25", "dense", "auto"] | None = None
    top_k: int | None = Field(default=None, ge=1, le=50)

    @model_validator(mode="after")
    def check_arguments(self):
        if self.action == "search":
            if not self.query or not self.query.strip() or self.method is None or self.top_k is None:
                raise ValueError("search requires query, method and top_k")
        elif any(value is not None for value in (self.query, self.method, self.top_k)):
            raise ValueError("Only search accepts query, method and top_k")
        return self


class AgentResult(BaseModel):
    """One contract at the graph boundary, independent of each model's JSON format."""
    model_config = ConfigDict(extra="forbid", strict=True)
    agent: Action
    completed: str
    evidence_source_ids: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    suggested_action: Literal["search", "summarize", "factcheck", "write", "stop", "ask_clarify"] | None = None
    suggested_query: str | None = Field(default=None, max_length=4000)
    authority: Literal["execute", "advise"] = "execute"


def budget_config(*, max_steps: int, max_seconds: float, max_searches: int,
                  max_cost_usd: float | None, action_cost_bounds: dict[str, float] | None) -> dict:
    if type(max_steps) is not int or not 1 <= max_steps <= 200:
        raise ValueError("max_steps must be an integer in [1, 200]")
    if type(max_seconds) not in (int, float) or not math.isfinite(max_seconds) or max_seconds <= 0:
        raise ValueError("max_seconds must be finite and positive")
    if max_cost_usd is not None and (type(max_cost_usd) not in (int, float)
            or not math.isfinite(max_cost_usd) or max_cost_usd < 0):
        raise ValueError("max_cost_usd must be finite and non-negative")
    bounds = dict(action_cost_bounds or {})
    if set(bounds) - set(EXECUTABLE_ACTIONS) or any(
        type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in bounds.values()
    ):
        raise ValueError("Invalid action cost bounds")
    if max_cost_usd is not None and set(bounds) != set(EXECUTABLE_ACTIONS):
        raise ValueError("Cost cap requires an upper bound for every action, including internal retries")
    return {"max_steps": max_steps, "max_seconds": max_seconds, "max_searches": max_searches,
            "max_cost_usd": max_cost_usd, "action_cost_bounds": bounds}


def choose_action(state: ResearchState, *, initial_top_k: int = 5) -> Decision:
    """Select a useful next step from observations, not a precomputed sequence."""
    status = state["status"]
    result = state.get("agent_result", {})
    if state.get("stop_reason"):
        return Decision(action="stop", reason=state["stop_reason"])
    if status == "invalid_input":
        return Decision(action="stop", reason="invalid_input")
    if status == "ready" and state.get("pdf_path") and not state.get("read_pages"):
        return Decision(action="read", reason="inspect_question_relevant_pages")
    if status == "retrieved":
        return Decision(action="summarize", reason="synthesize_available_evidence")
    if status == "summary_ready":
        return Decision(action="factcheck", reason="verify_claims_and_observed_conflicts")
    if (status == "summary_unverified" and len(state.get("evidence_refs", [])) >= 2
            and "unmatched_evidence_spans" not in state.get("summary_diagnostics", {}).get("reasons", [])):
        return Decision(action="factcheck", reason="audit_unverified_source_statements")
    if status == "verified" and plan_complete(state):
        return Decision(action="write", reason="write_from_verified_claims")
    if status == "completed" and plan_complete(state):
        return Decision(action="stop", reason="task_completed")
    if result.get("suggested_action") == "ask_clarify":
        return Decision(action="stop", reason="needs_clarification")
    if status in {"reader_failed", "retrieval_failed", "summary_failed", "writer_failed"}:
        return Decision(action="stop", reason=status)
    if "factchecker:call_budget_exceeded" in state.get("errors", []):
        return Decision(action="stop", reason="factcheck_budget_exhausted")
    if any(review.get("status") != "ok" for review in state.get("fact_check_results", [])):
        return Decision(action="stop", reason="factchecker_failed")
    if result.get("agent") == "write" and result.get("suggested_action") != "search":
        return Decision(action="stop", reason="partial_report")
    if state.get("search_count", 0) >= state["budget"]["max_searches"]:
        return Decision(action="stop", reason="search_budget_exhausted")
    if state.get("pdf_path") and state.get("remaining_pages") and status not in {"ready", "read_ready"}:
        return Decision(action="read", reason="inspect_unread_pages_for_missing_evidence")
    query = result.get("suggested_query") or state.get("active_query") or state["question"]
    history = state.get("retrieval_history", [])
    # Alternate real methods, increasing coverage; no unimplemented query transforms.
    # This is a service-only compatibility hint. RetrievalAgent selects its own tool.
    method = "dense" if history and history[-1]["tool"] == "bm25" else "bm25"
    if state.get("retrieval_autonomy"):
        method = "auto"
    return Decision(action="search", reason="retrieve_missing_evidence" if history else "initial_evidence_search",
                    query=query, method=method,
                    top_k=min(50, initial_top_k * (state.get("search_count", 0) + 1)))


def enforce_limits(decision: Decision, state: ResearchState, *, now: float) -> Decision:
    """Limits are enforced independently of planner choices and cannot be overridden by agents."""
    if decision.action == "stop":
        return decision
    budget = state["budget"]
    reason = None
    if now >= state["deadline_at"]:
        reason = "time_budget_exhausted"
    elif state["steps_used"] >= budget["max_steps"]:
        reason = "step_budget_exhausted"
    elif (budget["max_cost_usd"] is not None and state["reserved_cost_usd"]
          + budget["action_cost_bounds"][decision.action] > budget["max_cost_usd"]):
        reason = "cost_budget_exhausted"
    elif decision.action == "search":
        if state["search_count"] >= budget["max_searches"]:
            reason = "search_budget_exhausted"
        elif any((h.get("query"), h.get("requested_method"), h.get("top_k")) ==
                 (decision.query, decision.method, decision.top_k) for h in state["retrieval_history"]):
            reason = "repeated_search_without_progress"
    return Decision(action="stop", reason=reason) if reason else decision
