"""Strict label prediction with validated structured output."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol, Sequence

try:
    import config
    from prompts import JUDGE_SYSTEM_PROMPT, build_judge_user_prompt
except ImportError:  # package-style import in tests/tools
    from .. import config  # type: ignore
    from ..prompts import JUDGE_SYSTEM_PROMPT, build_judge_user_prompt  # type: ignore


class JSONBackend(Protocol):
    def generate_json(
        self, messages: Sequence[dict[str, str]], *, max_new_tokens: int
    ) -> dict[str, Any]: ...


def extract_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object, tolerating a fenced wrapper but not invalid JSON."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        start = text.find("{")
        if start < 0:
            raise ValueError("Model output contains no JSON object")
        try:
            value, _ = decoder.raw_decode(text[start:])
        except json.JSONDecodeError as exc:
            raise ValueError("Model output is not valid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("Model output must be a JSON object")
    return value


class TransformersJSONBackend:
    """Small adapter around a transformers causal LM; no model is loaded here."""

    def __init__(self, model: Any, tokenizer: Any) -> None:
        self.model = model
        self.tokenizer = tokenizer

    def generate_json(
        self, messages: Sequence[dict[str, str]], *, max_new_tokens: int
    ) -> dict[str, Any]:
        import torch

        rendered = self.tokenizer.apply_chat_template(
            list(messages), tokenize=False, add_generation_prompt=True
        )
        inputs = self.tokenizer(rendered, return_tensors="pt")
        device = getattr(self.model, "device", None)
        if device is not None:
            inputs = {key: value.to(device) for key, value in inputs.items()}
        with torch.inference_mode():
            output_ids = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        prompt_length = inputs["input_ids"].shape[1]
        text = self.tokenizer.decode(
            output_ids[0][prompt_length:], skip_special_tokens=True
        )
        return extract_json_object(text)


@dataclass(frozen=True)
class FactCheckDecision:
    fact_check_label: str
    reasoning: str
    raw: dict[str, Any]


class FactCheckJudge:
    def __init__(self, backend: JSONBackend) -> None:
        self.backend = backend

    def judge(self, claim: str, context: str | list[str]) -> FactCheckDecision:
        if not claim.strip():
            raise ValueError("claim must not be empty")
        messages = [
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": build_judge_user_prompt(claim, context)},
        ]
        raw = self.backend.generate_json(
            messages, max_new_tokens=config.MAX_NEW_TOKENS_JUDGE
        )
        label = str(raw.get("fact_check_label", "")).strip().lower()
        reasoning = str(raw.get("reasoning", "")).strip()
        if label not in config.LABELS:
            raise ValueError(f"Invalid fact_check_label: {label!r}")
        if not reasoning:
            raise ValueError("Judge reasoning must not be empty")
        return FactCheckDecision(label, reasoning, raw)
