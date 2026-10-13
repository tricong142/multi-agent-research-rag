"""Strict label prediction with validated structured output."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Protocol, Sequence

if __package__ and "." in __package__:
    from .. import config
    from ..prompts import JUDGE_SYSTEM_PROMPT, build_judge_user_prompt
else:
    import config
    from prompts import JUDGE_SYSTEM_PROMPT, build_judge_user_prompt


class JSONBackend(Protocol):
    def generate_json(
        self, messages: Sequence[dict[str, str]], *, max_new_tokens: int
    ) -> dict[str, Any]: ...


class ModelOutputError(ValueError):
    """A repairable output error; keep the output separate from public error text."""

    def __init__(self, message: str, raw_output: str) -> None:
        super().__init__(message)
        self.raw_output = raw_output


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

    def __init__(self, model: Any, tokenizer: Any, *, on_generation: Callable[[dict], None] | None = None) -> None:
        self.model = model
        self.tokenizer = tokenizer
        self.on_generation = on_generation

    def generation_options(self, messages: Sequence[dict[str, str]]) -> dict[str, Any]:
        """Experimental subclasses can constrain decoding; serving uses defaults."""
        return {}

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
        options = self.generation_options(messages)
        with torch.inference_mode():
            output_ids = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                pad_token_id=self.tokenizer.eos_token_id,
                **options,
            )
        prompt_length = inputs["input_ids"].shape[1]
        text = self.tokenizer.decode(
            output_ids[0][prompt_length:], skip_special_tokens=True
        )
        parsed = None
        error_type = None
        try:
            parsed = extract_json_object(text)
            return parsed
        except ValueError as exc:
            error_type = type(exc).__name__
            raise ModelOutputError(str(exc), text) from exc
        finally:
            # Opt-in private diagnostic output, never emitted by default.
            if self.on_generation is not None:
                self.on_generation({"event": "factchecker_generation", "raw_output": text,
                                    "json_valid": parsed is not None, "parse_error_type": error_type,
                                    "parsed_keys": sorted(parsed) if parsed is not None else [],
                                    "prompt_tokens": prompt_length,
                                    "generated_tokens": len(output_ids[0]) - prompt_length,
                                    "max_new_tokens": max_new_tokens,
                                    **getattr(self, "decoding_metadata", {})})


@dataclass(frozen=True)
class FactCheckDecision:
    fact_check_label: str
    reasoning: str
    raw: dict[str, Any]


class FactCheckJudge:
    def __init__(self, backend: JSONBackend, *, system_prompt: str = JUDGE_SYSTEM_PROMPT) -> None:
        self.backend = backend
        self.system_prompt = system_prompt

    def judge(self, claim: str, context: str | list[str]) -> FactCheckDecision:
        if not claim.strip():
            raise ValueError("claim must not be empty")
        messages = [
            {"role": "system", "content": self.system_prompt},
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
