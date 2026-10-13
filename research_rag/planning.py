"""Bounded, inspectable task planning. This is a code policy, not an LLM planner."""
from __future__ import annotations

import re
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal


class ResearchTask(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    task_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,40}$")
    question: str = Field(min_length=1, max_length=4000)
    kind: Literal["research", "synthesis"] = "research"
    depends_on: list[str] = Field(default_factory=list, max_length=6)
    focus_terms: list[str] = Field(default_factory=list, max_length=4)
    completion_criteria: list[str] = Field(default_factory=lambda: [
        "Answer the task question with verbatim source evidence.",
        "Every answer claim passes fact-checking against all observed sources.",
    ], min_length=1, max_length=6)
    status: Literal["pending", "active", "complete"] = "pending"
    query: str = Field(default="", max_length=4000)
    missing_questions: list[str] = Field(default_factory=list, max_length=16)
    claim_texts: list[str] = Field(default_factory=list, max_length=24)
    evidence_source_ids: list[str] = Field(default_factory=list)


class ResearchPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    tasks: list[ResearchTask] = Field(min_length=1, max_length=6)
    revision: int = Field(default=1, ge=1)
    last_observed_step: int = Field(default=0, ge=0)
    policy: Literal["bounded_code_v1", "provided"] = "bounded_code_v1"

    @model_validator(mode="after")
    def validate_dependencies(self):
        previous = set()
        for task in self.tasks:
            if task.task_id in previous or not set(task.depends_on) <= previous:
                raise ValueError("Tasks must have unique IDs and depend only on earlier tasks")
            if task.kind == "synthesis" and not task.depends_on:
                raise ValueError("Synthesis requires evidence tasks")
            previous.add(task.task_id)
        return self


def create_plan(question: str, provided: dict | None = None) -> dict:
    if provided is not None:
        plan = ResearchPlan.model_validate(provided)
        # Supplied plans are task specifications, never trusted completion assertions.
        for task in plan.tasks:
            task.status, task.claim_texts, task.evidence_source_ids = "pending", [], []
            task.missing_questions = []
        plan.revision, plan.last_observed_step, plan.policy = 1, 0, "provided"
        return plan.model_dump()
    pair = re.search(r"(?:compare|so sánh)\s+(.+?)\s+(?:and|versus|vs\.?|với|và)\s+(.+?)(?:[?.!]|$)", question, re.I)
    tasks = []
    if pair:
        left, right = [part.strip() for part in pair.groups()]
        # Keep the comparison dimension in the goal, not in the second entity name.
        right = re.split(r"\s+(?:in terms of|with respect to|on|về|theo)\s+", right, maxsplit=1, flags=re.I)[0]
        for index, subject in enumerate((left, right), 1):
            tasks.append(ResearchTask(task_id=f"t{index}", question=f"Evidence about {subject}. Research goal: {question}",
                                      query=subject, focus_terms=[subject]))
        tasks.append(ResearchTask(task_id="synthesis", question=question, kind="synthesis",
                                  depends_on=["t1", "t2"], focus_terms=[left, right],
                                  completion_criteria=["Cover both named methods using verified evidence.",
                                                       "Verify all comparison claims before writing."]))
    else:
        questions = [q.strip() + "?" for q in question.split("?") if q.strip()]
        questions = questions if 1 < len(questions) <= 4 else [question]
        tasks = [ResearchTask(task_id=f"t{i}", question=q, query=q) for i, q in enumerate(questions, 1)]
    return ResearchPlan(tasks=tasks).model_dump()


def active_task(state: dict) -> dict:
    return next((t for t in state.get("research_plan", {}).get("tasks", [])
                 if t["task_id"] == state.get("active_task_id")), {})


def task_question(state: dict) -> str:
    return active_task(state).get("question", state["question"])


def answer_coverage_gap(question: str, answer: str) -> str | None:
    """Reject obvious non-answers; passing is not a semantic completeness proof."""
    if not answer.strip():
        return "The answer is empty."
    if re.fullmatch(r"[\d\s.,%+\-]+", answer.strip()):
        return "Restate the answer as a complete factual sentence with its subject and quantity."
    # A location is an answer to a 'where' question, but a bare section pointer
    # cannot answer a request for a value, method or result.
    location_question = re.search(r"\bwhere\b|ở đâu|phần nào|mục nào", question, re.I)
    pointer = re.search(
        r"(?:\b(?:reported|provided|described|found|available)\s+in\s+(?:the\s+)?|\bsee\s+(?:the\s+)?)"
        r"(?:appendix|supplement|table|section)\b", answer, re.I)
    if not location_question and pointer and len(answer.split()) <= 18 and not re.search(r"\d", answer):
        return "The answer only points to another section; the requested fact is still missing."
    return None


def update_plan(state: dict, split_claims) -> dict:
    """Reconcile evidence, revise missing questions, and select a dependency-ready task."""
    if not state.get("research_plan") or state.get("stop_reason"):
        return {}
    plan = ResearchPlan.model_validate(state["research_plan"])
    task = next((t for t in plan.tasks if t.task_id == state.get("active_task_id")), None)
    outcome = state.get("agent_result", {})
    event = "keep"
    reason = "await_agent_result"
    changed = False
    observed = state["steps_used"] > plan.last_observed_step
    status = state["status"]
    update = {}
    if task and observed:
        plan.last_observed_step = state["steps_used"]
        reason = "evidence_not_yet_verified"
        if outcome.get("agent") == "factcheck":
            verified = {c["text"]: c for c in state.get("verified_claims", [])}
            # A new source can invalidate a previously completed task.
            for old in plan.tasks:
                if old.claim_texts and not set(old.claim_texts) <= verified.keys():
                    old.status = "pending"
                    old.missing_questions = [text for text in old.claim_texts if text not in verified]
                    changed, reason = True, "previous_evidence_invalidated"
            claims = split_claims(state.get("draft_answer", ""))
            coverage = " ".join(claims).casefold()
            missing_focus = [term for term in task.focus_terms if term.casefold() not in coverage]
            gap = answer_coverage_gap(task.question, state.get("draft_answer", ""))
            if claims and set(claims) <= verified.keys() and not missing_focus and not gap:
                task.status, task.claim_texts, task.missing_questions = "complete", claims, []
                task.evidence_source_ids = sorted({verified[c]["source_id"] for c in claims})
                changed, event, reason = True, "advance", "task_claims_verified"
            elif missing_focus or gap:
                task.missing_questions = ([gap] if gap else []) + [f"Evidence answering the question about {term}" for term in missing_focus]
                task.query = task.question
                update.update(status="insufficient_evidence", active_query=task.query,
                              agent_result=dict(outcome, suggested_action="search", suggested_query=task.query,
                                                missing_information=task.missing_questions))
                changed, reason = True, "task_coverage_missing"
        if outcome.get("missing_information") and task.status != "complete":
            missing = outcome["missing_information"][:16]
            query = outcome.get("suggested_query") or task.query or task.question
            if task.missing_questions != missing or task.query != query:
                task.missing_questions, task.query = missing, query
                changed, reason = True, "repair_missing_questions"
        if outcome.get("agent") == "write" and outcome.get("suggested_action") == "search":
            task.status = "active"
            task.missing_questions = outcome.get("missing_information", [])[:16]
            task.query = outcome.get("suggested_query") or task.question
            changed, reason = True, "writer_requested_more_evidence"
    if task is None or task.status == "complete":
        completed = {t.task_id for t in plan.tasks if t.status == "complete"}
        next_task = next((t for t in plan.tasks if t.status != "complete" and set(t.depends_on) <= completed), None)
        if next_task is not None:
            next_task.status = "active"
            update.update(active_task_id=next_task.task_id, active_query=next_task.query or next_task.question,
                          agent_result={})
            if task is not None:
                # Reuse collected evidence for synthesis; research tasks get their own search.
                update["status"] = "retrieved" if next_task.kind == "synthesis" else "task_ready"
            changed, event, reason = True, "advance", "activate_dependency_ready_task"
    if changed:
        plan.revision += 1
        if event == "keep":
            event = "revise"
    history = list(state.get("plan_history", []))
    if observed or changed:
        history.append({"step": state["steps_used"], "revision": plan.revision, "event": event,
                        "reason": reason, "task_id": update.get("active_task_id", state.get("active_task_id"))})
    return update | {"research_plan": plan.model_dump(), "plan_history": history}


def plan_complete(state: dict) -> bool:
    tasks = state.get("research_plan", {}).get("tasks", [])
    return bool(tasks) and all(t["status"] == "complete" for t in tasks)
