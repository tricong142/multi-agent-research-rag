"""LangGraph-compatible Fact-Checker node.

The node returns a partial state update. It never routes the graph and never
executes a recommended action. Internal retries only recover invalid LLM JSON.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import config
from inference import ActionRecommender, ConfidenceEstimator, FactCheckJudge


class FactCheckerNode:
    def __init__(
        self,
        judge: FactCheckJudge,
        confidence: ConfidenceEstimator,
        action_recommender: ActionRecommender,
        *,
        claim_keys: Sequence[str] = ("claim", "answer", "final_answer"),
        context_keys: Sequence[str] = ("context", "evidence_context", "retrieved_context"),
        max_internal_retry: int = config.MAX_INTERNAL_RETRY,
        confidence_threshold: float = config.CONFIDENCE_THRESHOLD,
    ) -> None:
        if max_internal_retry < 1:
            raise ValueError("max_internal_retry must be >= 1")
        if not 0.0 <= confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be in [0, 1]")
        self.judge = judge
        self.confidence = confidence
        self.action_recommender = action_recommender
        self.claim_keys = tuple(claim_keys)
        self.context_keys = tuple(context_keys)
        self.max_internal_retry = max_internal_retry
        self.confidence_threshold = confidence_threshold

    @staticmethod
    def _first_present(state: Mapping[str, Any], keys: Sequence[str]) -> Any:
        for key in keys:
            value = state.get(key)
            if value is not None and value != "" and value != []:
                return value
        return None

    @staticmethod
    def _normalize_context(value: Any) -> str | list[str]:
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            normalized: list[str] = []
            for item in value:
                if isinstance(item, str):
                    normalized.append(item)
                elif isinstance(item, Mapping):
                    text = item.get("text") or item.get("content") or item.get("page_content")
                    if text:
                        normalized.append(str(text))
                else:
                    normalized.append(str(item))
            return normalized
        if isinstance(value, Mapping):
            text = value.get("text") or value.get("content") or value.get("page_content")
            return str(text) if text else str(dict(value))
        return str(value)

    def _retry(self, name: str, function: Any, attempts: list[dict]) -> Any | None:
        for attempt in range(1, self.max_internal_retry + 1):
            try:
                result = function()
                attempts.append({"stage": name, "attempt": attempt, "ok": True})
                return result
            except Exception as exc:  # boundary: convert backend failure to state
                attempts.append(
                    {
                        "stage": name,
                        "attempt": attempt,
                        "ok": False,
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:500],
                    }
                )
        return None

    def __call__(self, state: Mapping[str, Any]) -> dict[str, Any]:
        attempts: list[dict] = []
        claim_value = self._first_present(state, self.claim_keys)
        context_value = self._first_present(state, self.context_keys)
        if claim_value is None or context_value is None:
            missing = "claim" if claim_value is None else "context"
            return {
                "fact_check_label": "not_enough_info",
                "confidence_score": 0.0,
                "recommended_action": "expand_context" if missing == "context" else "ask_clarify",
                "fact_check_reasoning": f"Fact-Checker input is missing required {missing}.",
                "confidence_reasoning": "The decision cannot be assessed without complete input.",
                "action_reasoning": f"Provide the missing {missing} before relying on the decision.",
                "fact_check_attempts": attempts,
                "fact_check_status": "invalid_input",
            }

        claim = str(claim_value).strip()
        context = self._normalize_context(context_value)
        decision = self._retry("judge", lambda: self.judge.judge(claim, context), attempts)
        if decision is None:
            return {
                "fact_check_label": "not_enough_info",
                "confidence_score": 0.0,
                "recommended_action": "expand_context",
                "fact_check_reasoning": "Judge failed to produce valid structured output.",
                "confidence_reasoning": "No valid judge decision was available.",
                "action_reasoning": "More context is the conservative fallback; no action was executed.",
                "fact_check_attempts": attempts,
                "fact_check_status": "judge_failed",
            }

        estimate = self._retry(
            "confidence",
            lambda: self.confidence.estimate(
                claim, context, decision.fact_check_label, decision.reasoning
            ),
            attempts,
        )
        if estimate is None:
            confidence_score = 0.0
            confidence_reasoning = "Confidence estimator failed to produce valid structured output."
            confidence_raw: dict[str, Any] = {}
        else:
            confidence_score = estimate.confidence_score
            confidence_reasoning = estimate.reasoning
            confidence_raw = estimate.raw

        action = None
        action_was_required = confidence_score < self.confidence_threshold
        if action_was_required:
            action = self._retry(
                "action_recommender",
                lambda: self.action_recommender.recommend(
                    claim,
                    context,
                    decision.fact_check_label,
                    confidence_score,
                    confidence_reasoning,
                ),
                attempts,
            )

        if estimate is None:
            status = "confidence_failed"
        elif action_was_required and action is None:
            status = "action_failed"
        else:
            status = "ok"

        return {
            "fact_check_label": decision.fact_check_label,
            "confidence_score": confidence_score,
            "recommended_action": action.recommended_action if action else None,
            "fact_check_reasoning": decision.reasoning,
            "confidence_reasoning": confidence_reasoning,
            "action_reasoning": (
                action.reasoning
                if action
                else (
                    "Action recommender failed to produce valid structured output; no action was executed."
                    if action_was_required
                    else None
                )
            ),
            "fact_check_attempts": attempts,
            "fact_check_raw": {
                "judge": decision.raw,
                "confidence": confidence_raw,
                "action": action.raw if action else {},
            },
            "fact_check_status": status,
        }

    def run(self, state: Mapping[str, Any]) -> dict[str, Any]:
        return self(state)
