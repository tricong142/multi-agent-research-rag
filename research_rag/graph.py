"""Controller-driven research loop with grounded evidence and explicit termination."""

from __future__ import annotations

import re
import math
import logging
import time
import importlib
from dataclasses import asdict, is_dataclass
from collections.abc import Mapping
from typing import Any, Callable

from .state import EvidenceRef, ResearchState, SourceChunk, TableCell
from .pdf_table_cells import count_cell_claim, count_table_header, table_count_cells, table_percentage_cells
from .pdf_cell_context import relevant_coordinate_cells
from .r8_adapter import R8_POLICY_ID
from .controller import AgentResult, Decision, budget_config, choose_action, enforce_limits
from .planning import answer_coverage_gap, create_plan, plan_complete, task_question, update_plan
from train_agent3_summarizer.claim_contract import SENTENCE_BREAK, claim_contract_issues, split_claims

logger = logging.getLogger(__name__)


PDF_LIGATURES = str.maketrans({"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st"})


def source_evidence(span: str, text: str) -> str | None:
    """Recover an original substring, allowing only whitespace/PDF ligatures.

    Keep offsets into the source so downstream evidence is verbatim. Do not
    case-fold, alter punctuation/numbers, or use approximate similarity.
    """
    if span in text:
        return span
    target = " ".join(span.translate(PDF_LIGATURES).split())
    if not target:
        return None
    normalized = []
    offsets = []
    for index, char in enumerate(text):
        replacement = " " if char.isspace() else char.translate(PDF_LIGATURES)
        if replacement == " " and normalized and normalized[-1] == " ":
            offsets[-1] = (offsets[-1][0], index + 1)
            continue
        for letter in replacement:
            normalized.append(letter)
            offsets.append((index, index + 1))
    canonical = "".join(normalized)
    position = canonical.find(target)
    while position >= 0:
        original = text[offsets[position][0]:offsets[position + len(target) - 1][1]]
        if " ".join(original.translate(PDF_LIGATURES).split()) == target:
            return original
        position = canonical.find(target, position + 1)
    return None


def referenced_table_context(question: str, hits: list[SourceChunk],
                             pdf_chunks: list[SourceChunk]) -> list[SourceChunk]:
    """Keep nearby table blocks and the caption together, with original citations."""
    names = re.findall(r"\btable\s+(\d+[a-z]?)\b", question, re.I)
    if len(set(name.casefold() for name in names)) != 1:
        return []
    caption_pattern = re.compile(rf"^\s*table\s+{re.escape(names[0])}\s*[:.]", re.I)
    pdf_chunks = [c for c in pdf_chunks if c["metadata"].get("source_tool") != "pdf_coordinates"]
    captions = [c for c in pdf_chunks if caption_pattern.match(c["text"])
                and len(c["metadata"].get("bbox") or []) == 4]
    if len(captions) != 1:
        return []
    caption = captions[0]
    page = caption["source_id"].rsplit(":", 2)[0]
    if not any(c["source_id"].rsplit(":", 2)[0] == page for c in hits):
        return []
    left, top, right, bottom = caption["metadata"]["bbox"]
    # Bound the look-back to the local region above a bottom caption.
    nearby = []
    for chunk in pdf_chunks:
        box = chunk["metadata"].get("bbox") or []
        if (chunk["source_id"].rsplit(":", 2)[0] == page and len(box) == 4
                and 0 <= top - box[3] <= 180 and box[0] < right and box[2] > left):
            nearby.append(chunk)
    nearby.sort(key=lambda c: (c["metadata"]["bbox"][1], c["metadata"]["bbox"][0]))
    if not any(count_table_header(c["text"]) for c in nearby):
        below = [
            c for c in pdf_chunks if c["source_id"].rsplit(":", 2)[0] == page
            and len(box := c["metadata"].get("bbox") or []) == 4
            and 0 <= box[1] - bottom <= 110 and box[0] < right and box[2] > left
        ]
        headers = [c for c in below if count_table_header(c["text"])
                   and c["metadata"]["bbox"][1] - bottom <= 28]
        if len(headers) == 1:
            nearby = sorted(below, key=lambda c: c["metadata"]["bbox"][1])
    return [caption, *nearby]


def pdf_evidence_units(chunks: list[SourceChunk], table_ids: set[str]) -> dict[str, EvidenceRef]:
    units: dict[str, EvidenceRef] = {}
    for chunk in chunks:
        source_id = chunk["source_id"]
        # PDF extraction often splits the cells of a row across physical lines.
        spans = [chunk["text"]] if source_id in table_ids else SENTENCE_BREAK.split(chunk["text"])
        for span in spans:
            if text := span.strip():
                units[f"S{len(units) + 1}"] = {"source_id": source_id, "text": text}
    return units


def build_graph(
    *,
    retriever: Any,
    summarizer: Any,
    factchecker: Any,
    writer: Any,
    reader: Any = None,
    max_graph_retries: int = 1,
    initial_top_k: int = 5,
    max_context_chars: int = 6000,
    factcheck_threshold: float = 0.7,
    max_factcheck_calls: int = 120,
    verifier_policy: str | None = None,
    max_steps: int = 30,
    max_seconds: float = 600.0,
    max_cost_usd: float | None = None,
    action_cost_bounds: dict[str, float] | None = None,
    checkpointer: Any = None,
    on_event: Callable[[dict], None] | None = None,
    clock: Callable[[], float] = time.time,
) -> Any:
    """Compile a graph. Models/services are injected, so tests need no GPU or API key."""
    from langgraph.graph import END, START, StateGraph

    if not 0 <= max_graph_retries <= 5 or not 1 <= initial_top_k <= 25 or max_context_chars < 100:
        raise ValueError("Graph retry or top_k limit is invalid")
    if not 0 <= factcheck_threshold <= 1:
        raise ValueError("factcheck_threshold must be in [0, 1]")
    if max_factcheck_calls < 1:
        raise ValueError("max_factcheck_calls must be positive")
    budget = budget_config(max_steps=max_steps, max_seconds=max_seconds,
                           max_searches=max_graph_retries + 1, max_cost_usd=max_cost_usd,
                           action_cost_bounds=action_cost_bounds)
    budget["policy"] = {"initial_top_k": initial_top_k, "max_context_chars": max_context_chars,
                        "runtime_schema": 4, "claim_contract": "explicit-subject-relation-v1",
                        "retrieval_policy": getattr(retriever, "policy", None) if callable(getattr(retriever, "run", None)) else "service",
                        "factcheck_threshold": factcheck_threshold, "max_factcheck_calls": max_factcheck_calls}
    if verifier_policy is not None:
        budget["policy"]["verifier"] = verifier_policy

    def emit(event: dict) -> None:
        # Only counts, identifiers and reason codes; source/query text stays in private state.
        logger.info("research_event=%s", event)
        if on_event:
            on_event(dict(event))

    def prepare(state: ResearchState) -> ResearchState:
        question = state.get("question", "")
        valid = isinstance(question, str) and bool(question.strip()) and len(question) <= 4000
        now = clock()
        plan = {}
        plan_error = None
        if valid:
            try:
                plan = create_plan(question, state.get("research_plan"))
            except ValueError:
                valid, plan_error = False, "Invalid research plan"
        return {
            "question": question.strip() if valid else "", "intent": question.strip() if valid else "",
            "goal": question.strip() if valid else "", "current_task": "inspect_input",
            "active_query": question.strip() if valid else "",
            "research_plan": plan, "active_task_id": "", "plan_history": [], "agent_cycles": [],
            "retrieval_trace": [],
            "retrieval_autonomy": callable(getattr(retriever, "run", None)),
            "budget": budget, "started_at": now, "deadline_at": now + max_seconds,
            "steps_used": 0, "search_count": 0, "factcheck_calls_used": 0,
            "reserved_cost_usd": 0.0, "stop_reason": None, "action_history": [],
            "next_action": {}, "agent_result": {}, "read_pages": [], "remaining_pages": [],
            "reader_diagnostics": {}, "pdf_chunks": [], "retrieved_chunks": [],
            "draft_answer": "", "evidence_spans": [], "evidence_refs": [],
            "context_source_ids": [], "summary_diagnostics": {}, "summary_supported": False,
            "summary_confidence": "low", "final_report": {}, "writer_diagnostics": {},
            "retrieval_decision": "", "retrieval_warning": None,
            "retry_count": 0, "retrieval_history": [], "errors": [],
            "seen_chunks": [],
            "verified_claims": [], "fact_check_results": [],
            "low_confidence_warning": False, "status": "ready" if valid else "invalid_input",
            **({"errors": [plan_error or "question must be non-empty text of at most 4000 characters"]} if not valid else {}),
        }

    def control(state: ResearchState) -> ResearchState:
        if state["budget"] != budget:
            raise ValueError("Resume must use the same budget and evidence policy as the original run")
        plan_update = update_plan(state, split_claims)
        state = state | plan_update
        if plan_update.get("plan_history"):
            emit({"event": "plan_review", **plan_update["plan_history"][-1]})
        decision = Decision.model_validate(choose_action(state, initial_top_k=initial_top_k).model_dump())
        decision = enforce_limits(decision, state, now=clock())
        emit({"event": "decision", "action": decision.action, "reason": decision.reason,
              "step": state["steps_used"], "status": state["status"], "task_id": state.get("active_task_id"),
              "plan_revision": state.get("research_plan", {}).get("revision")})
        if decision.action == "stop":
            return plan_update | {"next_action": decision.model_dump(), "stop_reason": decision.reason}
        return plan_update | {"next_action": decision.model_dump(), "current_task": task_question(state),
                "steps_used": state["steps_used"] + 1,
                "reserved_cost_usd": state["reserved_cost_usd"] + state["budget"]["action_cost_bounds"].get(decision.action, 0.0)}

    def read_pdf(state: ResearchState) -> ResearchState:
        if reader is None:
            return {"pdf_chunks": [], "status": "reader_failed", "errors": state.get("errors", []) + ["PDF reader is not configured"]}
        try:
            result = reader.read_for_question(str(state["pdf_path"]), question=state.get("active_query") or task_question(state),
                                              excluded_pages=state["read_pages"])
            chunks = result["chunks"]
            return {"pdf_chunks": state["pdf_chunks"] + chunks,
                    "read_pages": state["read_pages"] + result["read_pages"],
                    "remaining_pages": result["remaining_pages"], "reader_diagnostics": result["diagnostics"],
                    "status": "read_ready" if chunks else "reader_failed",
                    "errors": state.get("errors", []) if chunks else state.get("errors", []) + ["reader:no_chunks"]}
        except Exception as exc:  # PDF/OCR/model boundary
            return {"pdf_chunks": state.get("pdf_chunks", []), "status": "reader_failed",
                    "reader_diagnostics": getattr(exc, "diagnostics", {"error_type": type(exc).__name__}),
                    "errors": state.get("errors", []) + [f"reader:{type(exc).__name__}"]}

    def retrieve(state: ResearchState) -> ResearchState:
        try:
            action = Decision.model_validate(state["next_action"])
            ordinary_chunks = [c for c in state.get("pdf_chunks", [])
                               if c["metadata"].get("source_tool") != "pdf_coordinates"]
            if callable(getattr(retriever, "run", None)):
                result = retriever.run(state={**state, "pdf_chunks": ordinary_chunks}
                                       if state.get("pdf_path") else state, top_k=action.top_k)
            else:
                result = retriever.search(
                    action.query, method=action.method,
                    pdf_chunks=ordinary_chunks if state.get("pdf_path") else None,
                    top_k=action.top_k, history=state.get("retrieval_history", []))
            chunks: list[SourceChunk] = result["chunks"]
            seen = list(state.get("seen_chunks", []))
            seen_keys = {(c["doc_id"], c["source_id"], c["text"]) for c in seen}
            for chunk in chunks:
                key = (chunk["doc_id"], chunk["source_id"], chunk["text"])
                if key not in seen_keys:
                    seen.append(chunk)
                    seen_keys.add(key)
            history = state["retrieval_history"] + [{"query": result.get("query", action.query),
                       "requested_method": result.get("requested_method", action.method),
                       "tool": str(result["decision"]), "top_k": action.top_k,
                       "doc_ids": [c["doc_id"] for c in chunks], "has_hits": bool(chunks),
                       "task_id": state.get("active_task_id"),
                       "reason": state["status"]}]
            has_new_evidence = len(seen) > len(state["seen_chunks"])
            return {
                "retrieved_chunks": chunks,
                "seen_chunks": seen,
                "retrieval_history": history, "search_count": state["search_count"] + 1,
                "retrieval_trace": state.get("retrieval_trace", []) + result.get("trace", []),
                **({"agent_result": result["agent_result"]} if result.get("agent_result") else {}),
                "retry_count": state["search_count"],
                # New evidence invalidates old verification; empty searches preserve a safe partial report.
                **({"verified_claims": [], "fact_check_results": [], "final_report": {}} if has_new_evidence else {}),
                "retrieval_decision": str(result["decision"]),
                "retrieval_warning": result.get("warning"),
                "status": "retrieved" if has_new_evidence else "no_hits",
            }
        except Exception as exc:  # search/model boundary
            return {"retrieved_chunks": [], "status": "retrieval_failed", "errors": state.get("errors", []) + [f"retrieval:{type(exc).__name__}"]}

    def summarize(state: ResearchState) -> ResearchState:
        try:
            selected: list[SourceChunk] = []
            used_chars = 0
            # Keep candidate evidence across retries, even if new hits fill the context window.
            retained_ids = {r["source_id"] for r in state.get("evidence_refs", [])}
            retained_ids.update(r["source_id"] for r in state.get("fact_check_results", [])
                                if r["label"] == "support" and r["status"] == "ok")
            retained = [c for c in state["seen_chunks"] if c["source_id"] in retained_ids]
            tables = referenced_table_context(task_question(state), state["retrieved_chunks"], state.get("pdf_chunks", []))
            cells = relevant_coordinate_cells(task_question(state), state.get("pdf_chunks", []))
            candidates = retained + [c for c in cells + tables if c not in retained]
            candidates += [c for c in state["retrieved_chunks"] if c not in candidates]
            candidates += [c for c in state["seen_chunks"] if c not in candidates]
            seen_ids = {c["source_id"] for c in state["seen_chunks"]}
            table_ids = {c["source_id"] for c in cells + tables}
            run_ids = getattr(summarizer, "run_with_source_ids", None) if state.get("pdf_path") else None
            id_mode = callable(run_ids)
            selected_ids = set()
            for chunk in candidates:
                if id_mode and chunk["source_id"] in selected_ids:
                    continue
                if used_chars + len(chunk["text"]) <= max_context_chars:
                    selected.append(chunk)
                    selected_ids.add(chunk["source_id"])
                    used_chars += len(chunk["text"])
            if not selected:
                raise ValueError("No retrieved chunk fits the context budget")
            units = pdf_evidence_units(selected, table_ids) if id_mode else {}
            table_cells = table_percentage_cells(state["pdf_path"], tables) if tables and id_mode else {}
            count_cells = table_count_cells(state["pdf_path"], tables) if tables and id_mode else {}
            if id_mode:
                source_units = {id_: ref["text"] for id_, ref in units.items()}
                table_text = {chunk["source_id"]: chunk["text"] for chunk in tables}
                table_scope = {}
                cells_by_unit = {}
                counts_by_unit = {}
                for id_, ref in units.items():
                    if cell := table_cells.get(ref["source_id"]):
                        table_scope[id_] = [table_text[cell["caption_source_id"]],
                                            table_text[cell["header_source_id"]]]
                        cells_by_unit[id_] = cell
                    elif counts := count_cells.get(ref["source_id"]):
                        table_scope[id_] = [table_text[counts[0]["caption_source_id"]],
                                            table_text[counts[0]["header_source_id"]]]
                        counts_by_unit[id_] = counts
                if tables:
                    options = {"table_scope": table_scope, "table_cells": cells_by_unit}
                    if counts_by_unit:
                        options["count_cells"] = counts_by_unit
                    result = run_ids(source_units, task_question(state), **options)
                else:
                    result = run_ids(source_units, task_question(state))
            else:
                context = "\n\n".join(f"[{chunk['source_id']}] {chunk['text']}" for chunk in selected)
                result = summarizer.run(context=context, question=task_question(state))
            if not isinstance(result.evidence_spans, list) or any(
                not isinstance(span, str) or not span.strip() for span in result.evidence_spans
            ):
                raise ValueError("Evidence spans must be a list of nonempty strings")
            spans = [span.strip() for span in result.evidence_spans]
            if not id_mode and len(spans) > 10:
                raise ValueError("Summarizer returned too many evidence spans")
            refs: list[EvidenceRef] = []
            matched_span_count = 0
            if id_mode:
                refs = [{**units[id_], "evidence_id": id_, "claim": claim}
                        for claim, ids in result.claim_sources.items() for id_ in ids]
                for ref in refs:
                    if cell := table_cells.get(ref["source_id"]):
                        ref["table_cell"] = cell
                    else:
                        match = next((c for c in count_cells.get(ref["source_id"], [])
                                      if count_cell_claim(c) == ref["claim"]), None)
                        if match:
                            ref["table_cell"] = match
                matched_span_count = len({ref["evidence_id"] for ref in refs})
            else:
                for span in spans:
                    matched = False
                    for chunk in selected:
                        original = source_evidence(span, chunk["text"])
                        if original is not None:
                            matched = True
                            ref = {"source_id": chunk["source_id"], "text": original}
                            if ref not in refs:
                                refs.append(ref)
                    matched_span_count += int(matched)
            gap = answer_coverage_gap(task_question(state), str(result.answer))
            structure_issues = claim_contract_issues(result.answer)
            supported = (not gap and not structure_issues and result.is_supported is True and result.confidence == "high"
                         and bool(refs) and matched_span_count == len(spans))
            reasons = []
            if structure_issues:
                reasons.append("incomplete_claim_structure")
            if gap:
                reasons.append("answer_coverage_missing")
            if result.is_supported is not True:
                reasons.append("critic_not_supported")
            if result.confidence != "high":
                reasons.append("summary_confidence_not_high")
            if not spans:
                reasons.append("no_evidence_spans")
            elif not refs:
                reasons.append("no_verbatim_evidence")
            elif matched_span_count != len(spans):
                reasons.append("unmatched_evidence_spans")
            missing = getattr(result, "missing_information", [])
            query = getattr(result, "suggested_query", None)
            outcome = AgentResult(agent="summarize", completed="summary_ready" if supported else "summary_unverified",
                                  evidence_source_ids=[r["source_id"] for r in refs],
                                  missing_information=([gap] if gap else missing) or ([] if supported else reasons),
                                  suggested_action="factcheck" if supported else "search", suggested_query=query)
            return {
                "draft_answer": str(result.answer), "evidence_spans": spans,
                "context_source_ids": [chunk["source_id"] for chunk in selected],
                "evidence_refs": refs, "summary_supported": supported,
                "seen_chunks": state["seen_chunks"] + [c for c in selected if c["source_id"] in table_ids - seen_ids],
                "summary_confidence": str(result.confidence),
                "agent_result": outcome.model_dump(),
                "summary_diagnostics": {"reasons": reasons, "span_count": len(spans),
                                        "evidence_mode": "source_ids" if id_mode else "verbatim_spans",
                                        "claim_contract_issues": structure_issues,
                                        "trials": [asdict(t) if is_dataclass(t) else t for t in getattr(result, "reasoning_trace", [])],
                                        "matched_span_count": matched_span_count,
                                        "selected_chunk_count": len(selected)},
                "low_confidence_warning": not supported or bool(state.get("retrieval_warning")) or len(selected) < len(candidates) or bool(state.get("remaining_pages")),
                "status": "summary_ready" if supported else "summary_unverified",
            }
        except Exception as exc:
            return {"draft_answer": "", "evidence_spans": [], "evidence_refs": [],
                    "summary_supported": False, "summary_confidence": "low", "status": "summary_failed",
                    "summary_diagnostics": {"reasons": ["summarizer_exception"], "exception_type": type(exc).__name__},
                    "low_confidence_warning": True,
                    "errors": state.get("errors", []) + [f"summarizer:{type(exc).__name__}"]}

    def factcheck(state: ResearchState) -> ResearchState:
        previous = [claim for task in state.get("research_plan", {}).get("tasks", []) for claim in task["claim_texts"]]
        audit_only = not state.get("summary_supported")
        proposed = ([r["text"] for r in state.get("evidence_refs", [])] if audit_only
                    else split_claims(state.get("draft_answer", "")))
        claims = list(dict.fromkeys(previous + proposed))
        invalid_claims = [issue for claim in claims for issue in claim_contract_issues(claim)]
        if invalid_claims:
            outcome = AgentResult(agent="factcheck", completed="insufficient_evidence", authority="advise",
                                  missing_information=["Complete claims with explicit entities and relations are required."],
                                  suggested_action="search", suggested_query=task_question(state))
            return {"fact_check_results": [], "verified_claims": [], "low_confidence_warning": True,
                    "status": "insufficient_evidence", "agent_result": outcome.model_dump(),
                    "errors": state.get("errors", []) + ["factchecker:incomplete_claim_structure"]}
        reviews: list[dict[str, Any]] = []
        errors = list(state.get("errors", []))
        verified: list[dict[str, Any]] = []
        calls_started = 0
        if (state.get("summary_supported") or len(state.get("evidence_refs", [])) >= 2) and claims and len(claims) <= 24:
            refs = list(state.get("evidence_refs", []))
            bound_claims = {r["claim"] for r in refs if "claim" in r}
            # Prior task claims must be supported again, not merely checked for contradiction.
            if previous:
                for chunk in state.get("seen_chunks", []):
                    ref = {"source_id": chunk["source_id"], "text": chunk["text"]}
                    if ref not in refs:
                        refs.append(ref)
            ref_keys = {(ref["source_id"], ref["text"]) for ref in refs}
            pdf_sources = {c["source_id"]: c["text"] for c in state.get("pdf_chunks", [])}
            coordinate_cells = [c for c in state.get("pdf_chunks", [])
                                if c["metadata"].get("source_tool") == "pdf_coordinates"]
            coordinate_ids = {c["source_id"] for c in coordinate_cells}
            # A new retrieval round must not erase a previously observed conflict.
            other_chunks = [chunk for chunk in state.get("seen_chunks", [])
                            if (chunk["source_id"], chunk["text"]) not in ref_keys]
            if state["factcheck_calls_used"] + len(claims) * (len(refs) + len(other_chunks)) > max_factcheck_calls:
                return {"fact_check_results": [], "verified_claims": [],
                        "errors": errors + ["factchecker:call_budget_exceeded"],
                        "low_confidence_warning": True, "status": "insufficient_evidence"}

            def review(claim: str, source_id: str, evidence: str, scope: str,
                       table_cell: TableCell | None = None, source_context: str | None = None,
                       coordinate: bool = False) -> tuple[Any, Any, Any, Any]:
                nonlocal calls_started
                started = clock()
                try:
                    if clock() >= state["deadline_at"]:
                        raise TimeoutError("Research deadline reached")
                    calls_started += 1
                    request = {"claim": claim, "context": evidence, "deadline_at": state["deadline_at"]}
                    if table_cell is not None:
                        request["source_id"] = source_id
                        request["table_cell"] = table_cell
                    elif source_context is not None:
                        request["source_id"] = source_id
                        request["pdf_source_context"] = source_context
                    if coordinate:
                        request.update(source_id=source_id, question=task_question(state),
                                       pdf_coordinate_cells=coordinate_cells)
                    decision = factchecker(request)
                    if not isinstance(decision, Mapping):
                        raise ValueError("Fact-check response must be a mapping")
                    label = decision.get("fact_check_label")
                    score = decision.get("confidence_score")
                    status = decision.get("fact_check_status")
                    if (label not in ("support", "contradict", "not_enough_info")
                            or not isinstance(status, str) or not status
                            or type(score) not in (int, float)
                            or not math.isfinite(score) or not 0 <= score <= 1):
                        raise ValueError("Malformed fact-check label, score or status")
                except Exception as exc:  # external model/service boundary
                    errors.append(f"factchecker:{type(exc).__name__}")
                    decision = {"fact_check_label": "not_enough_info", "confidence_score": 0.0,
                                "fact_check_status": "backend_failed", "fact_check_reasoning": "Fact-check service failed."}
                label = decision.get("fact_check_label")
                score = decision.get("confidence_score", 0.0)
                status = decision.get("fact_check_status")
                action = decision.get("recommended_action")
                if action not in (None, "expand_context", "other_source", "ask_clarify"):
                    action = None
                reviews.append({"claim": claim, "source_id": source_id, "evidence": evidence,
                                "scope": scope, "label": label, "confidence_score": score,
                                "status": status, "reasoning": decision.get("fact_check_reasoning"),
                                "confidence_reasoning": decision.get("confidence_reasoning"),
                                "verification_method": decision.get("verification_method"),
                                "attempts": [{k: a[k] for k in ("stage", "attempt", "ok", "error_type") if k in a}
                                             for a in decision.get("fact_check_attempts", [])],
                                "recommended_action": action})
                emit({"event": "tool_result", "action": "factcheck", "call": state["factcheck_calls_used"] + calls_started,
                      "status": "ok" if status == "ok" else "failed", "elapsed_ms": round((clock() - started) * 1000, 2)})
                return label, score, status, decision.get("verification_method")

            for claim_no, claim in enumerate(claims, 1):
                candidates = []
                require_binding = claim in bound_claims
                conflict = False
                failed_review = False
                coordinate_checked = False
                for ref in refs:
                    source_context = pdf_sources.get(ref["source_id"]) if ref.get("claim") == claim else None
                    coordinate = (verifier_policy == R8_POLICY_ID and not previous and not audit_only
                                  and len(refs) == len(claims) == 1 and source_context == ref["text"]
                                  and ref["source_id"] in coordinate_ids)
                    label, score, status, method = review(claim, ref["source_id"], ref["text"], "evidence",
                                                          ref.get("table_cell"), source_context, coordinate)
                    coordinate_checked = coordinate and status == "ok" and method == "pdf_coordinate_cell"
                    if label == "contradict" and status == "ok":
                        conflict = True
                    if (label == "support" and status == "ok" and type(score) in (float, int)
                            and factcheck_threshold <= score <= 1 and (not require_binding or ref.get("claim") == claim)):
                        candidates.append((float(score), ref))
                    if status != "ok":
                        failed_review = True
                # The scoped check has already compared all cells for this exact table coordinate.
                for chunk in [] if coordinate_checked else other_chunks:
                    label, score, status, _ = review(claim, chunk["source_id"], chunk["text"], "chunk")
                    if label == "contradict" and status == "ok":
                        conflict = True
                    if label == "support" and status == "ok" and factcheck_threshold <= score <= 1 and not require_binding:
                        candidates.append((float(score), {"source_id": chunk["source_id"], "text": chunk["text"]}))
                    if status != "ok":
                        failed_review = True
                if candidates and not conflict and not failed_review and not audit_only:
                    score, ref = max(candidates, key=lambda pair: pair[0])
                    verified.append({"claim_id": f"claim:{claim_no}", "text": claim,
                                     "evidence": ref["text"], "source_id": ref["source_id"],
                                     "confidence": score, "verification_status": "verified"})
        complete = bool(claims) and len(verified) == len(claims)
        unresolved = [claim for claim in claims if claim not in {v["text"] for v in verified}]
        advice = "ask_clarify" if any(r["recommended_action"] == "ask_clarify" for r in reviews) else "search"
        outcome = AgentResult(agent="factcheck", completed="verified" if complete else "insufficient_evidence",
                              authority="advise",
                              evidence_source_ids=[v["source_id"] for v in verified], missing_information=unresolved,
                              suggested_action="write" if complete else advice,
                              suggested_query=(task_question(state) + " " + unresolved[0])[:4000] if unresolved else None)
        return {"fact_check_results": reviews, "verified_claims": verified, "errors": errors,
                "factcheck_calls_used": state["factcheck_calls_used"] + calls_started,
                "agent_result": outcome.model_dump(),
                "low_confidence_warning": state.get("low_confidence_warning", False) or not complete,
                "status": "verified" if complete else "insufficient_evidence"}

    def write(state: ResearchState) -> ResearchState:
        try:
            output = writer({"intent": state.get("intent", ""),
                             "verified_claims": state.get("verified_claims", []),
                             "low_confidence_warning": state.get("low_confidence_warning", True)})
            report = output["final_report"]
            validator = importlib.import_module("05_writer.report_schema_validator")
            report_model = validator.validate_report(report, validator.parse_claims(state["verified_claims"]))
            report = report_model.model_dump(mode="json")
            warning = output["low_confidence_warning"] is not False or state["low_confidence_warning"] or not plan_complete(state)
            diagnostics = output.get("writer_diagnostics", {})
            critique = validator.parse_critique(diagnostics.get("critique"), report_model)
            accepted = {r.sentence_id for r in critique.sentence_reviews if r.verdict == "supported"}
            sentences = [s for s in report["sentences"] if s["sentence_id"] in accepted]
            if len(sentences) != len(report["sentences"]):
                warning = True
                report = dict(report, sentences=sentences,
                              limitations=report["limitations"] + ["Unverified writer sentences were excluded."])
            needs_more = critique.needs_more_evidence
            warning = warning or needs_more
            outcome = AgentResult(agent="write", completed="report_written",
                                  evidence_source_ids=[c["source_id"] for c in state["verified_claims"]],
                                  missing_information=["Research question not fully covered"] if needs_more else [],
                                  suggested_action="search" if needs_more else "stop",
                                  suggested_query=state["question"] if needs_more else None)
            return {"final_report": report, "writer_diagnostics": output.get("writer_diagnostics", {}),
                    "agent_result": outcome.model_dump(),
                    "low_confidence_warning": warning,
                    "status": "completed" if report.get("sentences") and not warning else
                              "partial" if report.get("sentences") else "insufficient_evidence"}
        except Exception as exc:
            return {"final_report": {"title": "Research report", "sentences": [], "limitations": ["Writer failed."]},
                    "low_confidence_warning": True, "status": "writer_failed",
                    "errors": state.get("errors", []) + [f"writer:{type(exc).__name__}"]}

    def execute_agent(state: ResearchState, expected_action: str, handler: Callable) -> ResearchState:
        if state["budget"] != budget:
            raise ValueError("Resume must use the original budget and evidence policy")
        action = Decision.model_validate(state["next_action"])
        if action.action != expected_action:
            raise ValueError("Agent node received an unauthorized action")
        started = clock()
        if started >= state["deadline_at"]:
            return {"status": "timed_out", "stop_reason": "time_budget_exhausted"}
        emit({"event": "tool_start", "action": action.action, "step": state["steps_used"]})
        update = handler(state)
        outcome = update.get("agent_result") or AgentResult(
            agent=action.action, completed=update["status"],
            authority="advise" if action.action == "factcheck" else "execute",
            evidence_source_ids=[c["source_id"] for c in update.get("retrieved_chunks", update.get("pdf_chunks", []))],
            missing_information=[] if update["status"] in {"read_ready", "retrieved"} else [update["status"]],
            suggested_action="search" if action.action == "read" else "summarize" if update["status"] == "retrieved" else "search",
        ).model_dump()
        update["agent_result"] = AgentResult.model_validate(outcome).model_dump()
        if outcome.get("suggested_query"):
            update["active_query"] = outcome["suggested_query"]
        elapsed = round((clock() - started) * 1000, 2)
        event = {"event": "agent_result", "step": state["steps_used"], "action": action.action,
                 "task_id": state.get("active_task_id"), "authority": outcome.get("authority", "execute"),
                 "status": update["status"], "elapsed_ms": elapsed,
                 "evidence_count": len(outcome["evidence_source_ids"])}
        update["action_history"] = state["action_history"] + [event | {"decision": action.model_dump()}]
        # Private, checkpointed trace of observation -> local execution -> evaluation -> handoff.
        local_trace = (update.get("retrieval_trace", [])[len(state.get("retrieval_trace", [])):] if action.action == "search"
                       else update.get("reader_diagnostics") if action.action == "read"
                       else update.get("summary_diagnostics") if action.action == "summarize"
                       else update.get("fact_check_results") if action.action == "factcheck"
                       else update.get("writer_diagnostics"))
        update["agent_cycles"] = state.get("agent_cycles", []) + [{
            "step": state["steps_used"], "agent": action.action, "task_id": state.get("active_task_id"),
            "observation": {"question": task_question(state), "evidence_source_ids": [c["source_id"] for c in state["seen_chunks"]],
                            "missing_information": state.get("agent_result", {}).get("missing_information", [])},
            "delegation": action.model_dump(), "local_execution": local_trace,
            "evaluation": outcome, "handoff_to": "controller", "elapsed_ms": elapsed,
        }]
        if clock() >= state["deadline_at"]:
            update.update(status="timed_out", stop_reason="time_budget_exhausted", low_confidence_warning=True)
        emit(event)
        return update

    def stop(state: ResearchState) -> ResearchState:
        reason = state["stop_reason"] or "insufficient_evidence"
        report = state.get("final_report")
        if not report:
            generator = importlib.import_module("05_writer.inference.report_generator").ReportGenerator()
            # A budget exit does not make another model call. Copy verified claims only.
            report = generator.generate(state["verified_claims"], state["intent"]).model_dump(mode="json")
        if reason != "task_completed":
            report = dict(report, limitations=list(report.get("limitations", [])) + [reason])
        status = "completed" if reason == "task_completed" else "partial" if report.get("sentences") else "insufficient_evidence"
        if reason == "invalid_input":
            status = "invalid_input"
        elif reason == "needs_clarification":
            status = "needs_input"
        return {"final_report": report, "status": status, "current_task": "finished",
                "low_confidence_warning": reason != "task_completed" or state["low_confidence_warning"]}

    graph = StateGraph(ResearchState)
    for name, node in (("prepare", prepare), ("controller", control), ("stop", stop)):
        graph.add_node(name, node)
    nodes = {"read": "reader", "search": "retrieval", "summarize": "summarizer", "factcheck": "factchecker", "write": "writer"}
    handlers = {"read": read_pdf, "search": retrieve, "summarize": summarize, "factcheck": factcheck, "write": write}
    def agent_node(action_name: str):
        def run(state: ResearchState) -> ResearchState:
            return execute_agent(state, action_name, handlers[action_name])
        return run
    for action_name, node_name in nodes.items():
        graph.add_node(node_name, agent_node(action_name))
        graph.add_edge(node_name, "controller")
    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "controller")
    graph.add_conditional_edges("controller", lambda s: s["next_action"]["action"], nodes | {"stop": "stop"})
    graph.add_edge("stop", END)
    return graph.compile(checkpointer=checkpointer).with_config({"recursion_limit": 2 * max_steps + 6})
