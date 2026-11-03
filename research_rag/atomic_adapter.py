"""Opt-in graph adapter for the frozen Cellfix16 candidate; no model loaded on import."""
from __future__ import annotations

import hashlib
import importlib
import importlib.machinery
import json
from pathlib import Path
import sys
import time
from types import ModuleType, SimpleNamespace
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "research-runs/atomic-cellfix16-candidate/workspace"
CRITERIA_FILE = "research_rag/evaluation/atomic_verifier_criteria_v8.json"
CRITERIA_SHA256 = "c025247428698d892e549fb12ad22e19561020b034a2a2276c9dfcaf0cbdc966"
POLICY_ID = "atomic:" + CRITERIA_SHA256 + ":ledger-eligibility-v1"


def cellfix16_runtime(workspace: Path = WORKSPACE) -> SimpleNamespace:
    """Load verified candidate modules without replacing serving's import cache."""
    workspace = workspace.resolve()
    release = json.loads((ROOT / "docs/atomic-verifier-cellfix16-release.json").read_bytes())
    if release["criteria_sha256"] != CRITERIA_SHA256:
        raise ValueError("Atomic adapter requires the frozen Cellfix16 release")
    manifest = release["payload_files"]
    required = {name for name in manifest if name.startswith("04_factchecker/")}
    required.add(CRITERIA_FILE)
    for name in sorted(required):
        path = (workspace / name).resolve()
        if not path.is_relative_to(workspace) or not path.is_file():
            raise ValueError("Missing frozen Cellfix16 input: " + name)
        raw = path.read_bytes()
        if len(raw) != manifest[name]["size"] or hashlib.sha256(raw).hexdigest() != manifest[name]["sha256"]:
            raise ValueError("Changed frozen Cellfix16 input: " + name)
    criteria = json.loads((workspace / CRITERIA_FILE).read_bytes())
    if hashlib.sha256((workspace / CRITERIA_FILE).read_bytes()).hexdigest() != CRITERIA_SHA256:
        raise ValueError("Cellfix16 criteria hash mismatch")
    package_path = workspace / "04_factchecker"
    expected = {name for name in required if name.startswith("04_factchecker/inference/") and name.endswith(".py")}
    if {p.relative_to(workspace).as_posix() for p in (package_path / "inference").rglob("*.py")} != expected:
        raise ValueError("Unexpected Cellfix16 inference module")
    # Relative imports stay in this candidate, even if legacy modules were imported first.
    name = "_research_rag_cellfix16_" + hashlib.sha256(str(workspace).encode()).hexdigest()[:16]
    if name not in sys.modules:
        package = ModuleType(name)
        package.__path__ = [str(package_path)]
        package.__spec__ = importlib.machinery.ModuleSpec(name, loader=None, is_package=True)
        sys.modules[name] = package
    atomic = importlib.import_module(name + ".inference.atomic_verifier")
    decoding = importlib.import_module(name + ".inference.atomic_decoding")
    if atomic.POLICY != criteria["policy"] or decoding.DECODER != criteria["structured_decoder"]:
        raise ValueError("Imported atomic policy differs from Cellfix16")
    return SimpleNamespace(atomic=atomic, decoding=decoding, criteria=criteria, workspace=workspace)


class AtomicFactCheckerNode:
    """Translate a completed ledger to the existing graph's fact-check contract.

    confidence_score is binary ledger eligibility, NOT a calibrated probability.
    Incomplete/failed checks never authorize a claim or fall back to the legacy judge.
    """

    policy_id = POLICY_ID

    def __init__(self, backend: Any, runtime: SimpleNamespace, *, on_trace=None):
        self.backend, self.runtime, self.on_trace = backend, runtime, on_trace

    def __call__(self, state: Mapping[str, Any]) -> dict[str, Any]:
        claim, context = state.get("claim"), state.get("context")
        if not isinstance(claim, str) or not claim.strip() or not isinstance(context, str) or not context.strip():
            return self._response(None, "invalid_input", "Atomic verification requires claim and context text.")
        criteria = self.runtime.criteria
        timeout = criteria["case_deadline_seconds"]
        if state.get("deadline_at") is not None:
            timeout = min(timeout, state["deadline_at"] - time.time())
        if timeout <= 0:
            return self._response(None, "deadline_exceeded", "Research deadline reached before atomic verification.")
        verifier = self.runtime.atomic.AtomicVerifier(
            self.backend, max_calls=criteria["max_calls_per_case"], max_attempts=criteria["max_attempts"],
            max_new_tokens=criteria["max_new_tokens"], timeout_seconds=timeout,
        )
        result = verifier.verify(claim, context)
        if self.on_trace:
            self.on_trace({"event": "atomic_verifier_result", "verifier_policy": self.policy_id, "result": result})
        if result["status"] != "completed" or result["stop_reason"] != "completed":
            return self._response(result, "incomplete", result["explanation"])
        if result["assessed_label"] not in ("support", "contradict", "not_enough_info"):
            raise ValueError("Atomic verifier returned an invalid completed label")
        return self._response(result, "ok", result["explanation"])

    @staticmethod
    def _response(result, status, reasoning):
        label = result["assessed_label"] if status == "ok" else "not_enough_info"
        eligible = status == "ok" and label == "support"
        trace = result["trace"] if result else []
        return {
            "fact_check_label": label, "fact_check_status": status,
            "confidence_score": float(eligible),
            "confidence_reasoning": "Binary completed-ledger eligibility; not a calibrated probability.",
            "fact_check_reasoning": reasoning,
            "recommended_action": None if eligible else "expand_context",
            "fact_check_attempts": [{"stage": call["stage"], "attempt": call["attempt"],
                                     "ok": call.get("valid") is True,
                                     **({"error_type": call["error_type"]} if "error_type" in call else {})}
                                    for call in trace],
            "fact_check_raw": {"atomic": result}, "verifier_policy": POLICY_ID,
        }


def load_atomic_factchecker(*, offline: bool, on_generation=None, on_event=None, on_model_loaded=None,
                           runtime: SimpleNamespace | None = None):
    """Use the candidate's pinned base Qwen/NF4 settings, never fine-tuned weights."""
    runtime = runtime if runtime is not None else cellfix16_runtime()
    import torch
    from huggingface_hub import snapshot_download
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, GenerationConfig

    if not torch.cuda.is_available():
        raise RuntimeError("Cellfix16 atomic loading requires CUDA/NF4, including with --allow-cpu")
    criteria = runtime.criteria
    model_path = snapshot_download(criteria["base_model"], revision=criteria["base_revision"],
                                   local_files_only=offline,
                                   allow_patterns=["*.json", "*.safetensors", "*.txt", "LICENSE"])
    shared = runtime.workspace / "04_factchecker/checkpoints/factchecker_merged"
    tokenizer = AutoTokenizer.from_pretrained(shared, local_files_only=True)
    generation = GenerationConfig.from_pretrained(shared, local_files_only=True)
    torch.manual_seed(criteria["seed"])
    model = AutoModelForCausalLM.from_pretrained(
        model_path, local_files_only=True, device_map={"": 0}, dtype=torch.float16,
        quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.float16),
    ).eval()
    expected = json.loads((shared / "config.json").read_bytes())
    if any(getattr(model.config, key) != expected[key] for key in
           ("model_type", "vocab_size", "hidden_size", "num_hidden_layers")):
        raise ValueError("Atomic base model is incompatible with the frozen tokenizer")
    model.generation_config = generation
    backend = runtime.decoding.ConstrainedAtomicBackend(model, tokenizer)
    backend.on_generation = on_generation
    from .observe import observe_call
    backend.generate_json = observe_call(backend.generate_json, "atomic_verifier", on_event)
    if on_model_loaded:
        on_model_loaded("atomic_base_instruct_cellfix16")
    return AtomicFactCheckerNode(backend, runtime, on_trace=on_generation)
