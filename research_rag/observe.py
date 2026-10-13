"""Run a compiled graph and collect content-free timing/status telemetry."""

from __future__ import annotations

import time
from collections import Counter
from functools import wraps
from typing import Any


def observe_call(function, component: str, callback):
    """Count backend attempts, including failures; do not log prompts or infer billing."""
    @wraps(function)
    def call(*args, **kwargs):
        started = time.perf_counter()
        status = "failed"
        try:
            result = function(*args, **kwargs)
            status = "ok"
            return result
        finally:
            if callback:
                callback({"event": "backend_call", "component": component, "status": status,
                          "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                          "cost_usd": None})
    return call


def run_with_metrics(graph: Any, state: dict[str, Any] | None, config: dict | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Stream one graph run. Timings include routing/stream overhead between nodes."""
    final_state = dict(state or {})
    if state is None and config:
        final_state = dict(graph.get_state(config).values)
    events: list[dict[str, Any]] = []
    started = previous = time.perf_counter()
    for update in graph.stream(state, config, stream_mode="updates"):
        now = time.perf_counter()
        for node, fields in update.items():
            if not isinstance(fields, dict):
                continue
            final_state.update(fields)
            events.append({
                "node": node, "elapsed_ms": round((now - previous) * 1000, 2),
                "status": fields.get("status"),
                "retrieved_count": len(final_state.get("retrieved_chunks") or []),
                "verified_claim_count": len(final_state.get("verified_claims") or []),
                "retry_count": final_state.get("retry_count", 0),
                "action": final_state.get("next_action", {}).get("action"),
                "steps_used": final_state.get("steps_used", 0),
            })
        previous = now
    metrics = {"total_ms": round((time.perf_counter() - started) * 1000, 2),
               "events": events, "final_status": final_state.get("status"),
               "error_count": len(final_state.get("errors") or []),
               "token_usage": None, "estimated_cost": None,
               "reserved_cost_usd": final_state.get("reserved_cost_usd", 0.0),
               "stop_reason": final_state.get("stop_reason"),
               "factcheck_calls_used": final_state.get("factcheck_calls_used", 0)}
    metrics["agent_calls"] = dict(Counter(h["action"] for h in final_state.get("action_history", [])))
    metrics["plan_revisions"] = final_state.get("research_plan", {}).get("revision")
    return final_state, metrics
