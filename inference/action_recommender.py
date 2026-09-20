"""Recommend, but never execute, a next action for uncertain decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    import config
    from prompts import ACTION_SYSTEM_PROMPT, build_action_user_prompt
    from inference.judge import JSONBackend
except ImportError:
    from .. import config  # type: ignore
    from ..prompts import ACTION_SYSTEM_PROMPT, build_action_user_prompt  # type: ignore
    from .judge import JSONBackend


@dataclass(frozen=True)
class ActionRecommendation:
    recommended_action: str
    reasoning: str
    raw: dict[str, Any]


class ActionRecommender:
    def __init__(self, backend: JSONBackend) -> None:
        self.backend = backend

    def recommend(
        self,
        claim: str,
        context: str | list[str],
        label: str,
        confidence_score: float,
        uncertainty_reasoning: str,
    ) -> ActionRecommendation:
        messages = [
            {"role": "system", "content": ACTION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_action_user_prompt(
                    claim,
                    context,
                    label,
                    confidence_score,
                    uncertainty_reasoning,
                ),
            },
        ]
        raw = self.backend.generate_json(
            messages, max_new_tokens=config.MAX_NEW_TOKENS_ACTION
        )
        action = str(raw.get("recommended_action", "")).strip().lower()
        reasoning = str(raw.get("reasoning", "")).strip()
        if action not in config.RECOMMENDED_ACTIONS:
            raise ValueError(f"Invalid recommended_action: {action!r}")
        if not reasoning:
            raise ValueError("Action reasoning must not be empty")
        return ActionRecommendation(action, reasoning, raw)
