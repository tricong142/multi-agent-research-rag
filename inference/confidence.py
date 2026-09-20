"""Self-assessed confidence, kept separate from the label decision."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

try:
    import config
    from prompts import CONFIDENCE_SYSTEM_PROMPT, build_confidence_user_prompt
    from inference.judge import JSONBackend
except ImportError:
    from .. import config  # type: ignore
    from ..prompts import CONFIDENCE_SYSTEM_PROMPT, build_confidence_user_prompt  # type: ignore
    from .judge import JSONBackend


@dataclass(frozen=True)
class ConfidenceEstimate:
    confidence_score: float
    reasoning: str
    raw: dict[str, Any]


class ConfidenceEstimator:
    def __init__(self, backend: JSONBackend) -> None:
        self.backend = backend

    def estimate(
        self, claim: str, context: str | list[str], label: str, judge_reasoning: str
    ) -> ConfidenceEstimate:
        messages = [
            {"role": "system", "content": CONFIDENCE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_confidence_user_prompt(
                    claim, context, label, judge_reasoning
                ),
            },
        ]
        raw = self.backend.generate_json(
            messages, max_new_tokens=config.MAX_NEW_TOKENS_CONFIDENCE
        )
        try:
            score = float(raw["confidence_score"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("confidence_score must be numeric") from exc
        reasoning = str(raw.get("reasoning", "")).strip()
        if not math.isfinite(score) or not 0.0 <= score <= 1.0:
            raise ValueError("confidence_score must be finite and in [0, 1]")
        if not reasoning:
            raise ValueError("Confidence reasoning must not be empty")
        return ConfidenceEstimate(score, reasoning, raw)
