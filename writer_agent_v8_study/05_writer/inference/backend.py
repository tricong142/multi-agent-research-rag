"""One-call JSON generation with optional, lazily loaded Hugging Face models.

All retries belong to the loop controller. A context overflow raises an error;
dropping claim text to make a prompt fit would change the evidence available.
"""

from __future__ import annotations

import json
import math
from typing import Any, Protocol


class JsonGenerationBackend(Protocol):
    def generate(self, messages: list[dict[str, str]]) -> str:
        """Generate a single completion, without retries or external routing."""
        ...


def parse_json_object(text: str) -> dict[str, Any]:
    """Reject prose, fences, duplicate JSON keys, and NaN/Infinity values."""
    if not isinstance(text, str):
        raise ValueError("The generation backend must return a JSON string.")

    def reject_constant(value: str) -> Any:
        raise ValueError(f"Invalid JSON constant: {value}")

    def finite_float(value: str) -> float:
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError("JSON numeric value exceeds the finite floating-point range.")
        return parsed

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        parsed = json.loads(
            text, object_pairs_hook=unique_object, parse_constant=reject_constant, parse_float=finite_float
        )
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model output is not a complete JSON object: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Model output must be a JSON object.")
    return parsed


class HFJsonBackend:
    """Greedy local inference for an instruct/chat model or its LoRA adapter.

    Model artifacts may be downloaded by ``from_pretrained`` during loading.
    Generation itself never retrieves evidence. ``local_files_only=True`` also
    disables model downloads for fully offline deployments.
    """

    def __init__(
        self,
        model_name_or_path: str,
        *,
        adapter_path: str | None = None,
        load_in_4bit: bool = False,
        max_new_tokens: int = 1024,
        max_input_tokens: int | None = None,
        trust_remote_code: bool = False,
        device_map: str | dict[str, Any] | None = "auto",
        attention_implementation: str | None = None,
        local_files_only: bool = False,
    ) -> None:
        if not model_name_or_path.strip():
            raise ValueError("model_name_or_path must be non-empty.")
        if type(max_new_tokens) is not int or max_new_tokens < 1:
            raise ValueError("max_new_tokens must be a positive integer.")
        if max_input_tokens is not None and (type(max_input_tokens) is not int or max_input_tokens < 1):
            raise ValueError("max_input_tokens must be a positive integer or None.")
        self.model_name_or_path = model_name_or_path
        self.adapter_path = adapter_path
        self.load_in_4bit = load_in_4bit
        self.max_new_tokens = max_new_tokens
        self.max_input_tokens = max_input_tokens
        self.trust_remote_code = trust_remote_code
        self.device_map = device_map
        self.attention_implementation = attention_implementation
        self.local_files_only = local_files_only
        self._model: Any = None
        self._tokenizer: Any = None
        self._torch: Any = None

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        except ImportError as exc:
            raise RuntimeError("Install the inference dependencies before using HFJsonBackend.") from exc
        if self.load_in_4bit and not torch.cuda.is_available():
            raise RuntimeError("This NF4 backend requires a CUDA GPU; disable load_in_4bit on CPU.")
        dtype = torch.float32
        if torch.cuda.is_available():
            dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        common = {
            "trust_remote_code": self.trust_remote_code,
            "local_files_only": self.local_files_only,
        }
        tokenizer = AutoTokenizer.from_pretrained(self.model_name_or_path, **common)
        if not tokenizer.chat_template:
            raise ValueError("Choose an instruct/chat tokenizer with an explicit chat_template.")
        kwargs: dict[str, Any] = {
            **common,
            "torch_dtype": dtype,
            "device_map": self.device_map,
        }
        if self.attention_implementation:
            kwargs["attn_implementation"] = self.attention_implementation
        if self.load_in_4bit:
            kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
                bnb_4bit_compute_dtype=dtype,
            )
        model = AutoModelForCausalLM.from_pretrained(self.model_name_or_path, **kwargs)
        if self.adapter_path:
            try:
                from peft import PeftModel
            except ImportError as exc:
                raise RuntimeError("Install peft to load a LoRA adapter.") from exc
            model = PeftModel.from_pretrained(model, self.adapter_path, **common)
        model.eval()
        self._torch, self._tokenizer, self._model = torch, tokenizer, model

    def generate(self, messages: list[dict[str, str]]) -> str:
        self._load()
        rendered = self._tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self._tokenizer(rendered, return_tensors="pt", add_special_tokens=False, truncation=False)
        input_length = int(inputs["input_ids"].shape[-1])
        if self.max_input_tokens is not None and input_length > self.max_input_tokens:
            raise ValueError(
                f"Prompt has {input_length} tokens, exceeding max_input_tokens={self.max_input_tokens}; "
                "claims were not truncated."
            )
        limits = [
            getattr(self._model.config, "max_position_embeddings", None),
            getattr(self._tokenizer, "model_max_length", None),
        ]
        finite_limits = [int(limit) for limit in limits if isinstance(limit, (int, float)) and 0 < limit < 10**9]
        if not finite_limits:
            raise ValueError("Cannot establish this model's context limit safely.")
        context_limit = min(finite_limits)
        if input_length + self.max_new_tokens > context_limit:
            raise ValueError(
                f"Prompt ({input_length}) + output budget ({self.max_new_tokens}) exceeds "
                f"context window ({context_limit}); reduce the explicit budgets or input."
            )
        device = self._model.get_input_embeddings().weight.device
        inputs = {key: value.to(device) for key, value in inputs.items()}
        pad_token_id = self._tokenizer.pad_token_id
        if pad_token_id is None:
            pad_token_id = self._tokenizer.eos_token_id
        with self._torch.inference_mode():
            output = self._model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                do_sample=False,
                num_beams=1,
                use_cache=True,
                pad_token_id=pad_token_id,
            )
        return self._tokenizer.decode(output[0, input_length:], skip_special_tokens=True).strip()
