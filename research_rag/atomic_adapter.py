"""Opt-in graph adapter for the frozen Cellfix29 candidate."""
from __future__ import annotations

import hashlib
import importlib
import importlib.machinery
from io import BytesIO
import json
from pathlib import Path
import sys
import time
from types import ModuleType, SimpleNamespace
from typing import Any, Mapping
from zipfile import ZipFile

from .pdf_count_evidence import check_pdf_count_claim
from .pdf_table_cells import check_count_claim, check_percentage_claim


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "research-runs/atomic-cellfix29-candidate/workspace"
PAYLOAD = ROOT / "artifacts/atomic-cellfix29-six-suite-inputs.zip"
PAYLOAD_SHA256 = "83c4c54562d3a68049328b635dc30d1feac5fa0409f9dfe234d3cd0f6fd1baa0"
CRITERIA_FILE = "research_rag/evaluation/atomic_verifier_criteria_v8.json"
CRITERIA_SHA256 = "fa01c12d0fd0373082defc78d2f68e950567537c92ea35366cf3db583a6c25d1"
POLICY_ID = "atomic:" + CRITERIA_SHA256 + ":ledger-eligibility-v1"
STRUCTURED_POLICY_ID = "atomic-structured:" + CRITERIA_SHA256 + ":v1"


def verifier_policy(verifier):
    if verifier == "r8-v12":
        from .r8_adapter import R8_POLICY_ID
        return R8_POLICY_ID
    return {"legacy": None, "atomic": POLICY_ID, "atomic-structured": STRUCTURED_POLICY_ID}[verifier]


def _frozen_inputs(workspace: Path):
    payload = PAYLOAD.read_bytes()
    if hashlib.sha256(payload).hexdigest() != PAYLOAD_SHA256:
        raise ValueError("Atomic adapter requires the frozen Cellfix29 payload")
    with ZipFile(BytesIO(payload)) as archive:
        required = {name for name in archive.namelist() if name.startswith("04_factchecker/")}
        required.add(CRITERIA_FILE)
        for name in sorted(required):
            path = (workspace / name).resolve()
            if not path.is_relative_to(workspace) or not path.is_file():
                raise ValueError("Missing frozen Cellfix29 input: " + name)
            if path.read_bytes() != archive.read(name):
                raise ValueError("Changed frozen Cellfix29 input: " + name)
        criteria_bytes = archive.read(CRITERIA_FILE)
    if hashlib.sha256(criteria_bytes).hexdigest() != CRITERIA_SHA256:
        raise ValueError("Cellfix29 criteria hash mismatch")
    criteria = json.loads(criteria_bytes)
    package_path = workspace / "04_factchecker"
    expected = {name for name in required if name.startswith("04_factchecker/inference/") and name.endswith(".py")}
    if {p.relative_to(workspace).as_posix() for p in (package_path / "inference").rglob("*.py")} != expected:
        raise ValueError("Unexpected Cellfix29 inference module")
    return criteria, package_path


def cellfix29_runtime(workspace: Path = WORKSPACE) -> SimpleNamespace:
    """Load verified candidate modules without replacing serving's import cache."""
    workspace = workspace.resolve()
    criteria, package_path = _frozen_inputs(workspace)
    # Relative imports stay in this candidate, even if legacy modules were imported first.
    name = "_research_rag_cellfix29_" + hashlib.sha256(str(workspace).encode()).hexdigest()[:16]
    if name not in sys.modules:
        package = ModuleType(name)
        package.__path__ = [str(package_path)]
        package.__spec__ = importlib.machinery.ModuleSpec(name, loader=None, is_package=True)
        sys.modules[name] = package
    atomic = importlib.import_module(name + ".inference.atomic_verifier")
    decoding = importlib.import_module(name + ".inference.atomic_decoding")
    if atomic.POLICY != criteria["policy"] or decoding.DECODER != criteria["structured_decoder"]:
        raise ValueError("Imported atomic policy differs from Cellfix29")
    return SimpleNamespace(atomic=atomic, decoding=decoding, criteria=criteria, workspace=workspace)


class AtomicFactCheckerNode:
    """Translate a completed ledger to the existing graph's fact-check contract.

    confidence_score is binary ledger eligibility, NOT a calibrated probability.
    Incomplete/failed checks never authorize a claim or fall back to the legacy judge.
    """

    policy_id = POLICY_ID

    def __init__(self, backend: Any, runtime: SimpleNamespace, *, on_trace=None):
        self.backend, self.runtime, self.on_trace = backend, runtime, on_trace
        self.structured = getattr(runtime, "structured", False)
        if self.structured:
            self.policy_id = STRUCTURED_POLICY_ID

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
        if (cell := state.get("table_cell")) is not None:
            args = (claim, context, state.get("source_id"), cell)
            checked = check_percentage_claim(*args) or check_count_claim(*args)
            if checked is not None:
                label, reason = checked
                if self.on_trace:
                    self.on_trace({"event": "table_cell_verification", "claim": claim, "label": label,
                                   "reason": reason, "table_cell": cell})
                response = self._response(None, "ok", reason, assessed_label=label)
                response["confidence_reasoning"] = "Exact PDF row, column and numeric value comparison."
                return response
        source_id, paragraph = state.get("source_id"), state.get("pdf_source_context")
        if isinstance(source_id, str) and source_id.startswith("pdf:") and isinstance(paragraph, str):
            reason = check_pdf_count_claim(claim, context, paragraph, self.runtime.atomic.numeric_requirements)
            if reason is not None:
                if self.on_trace:
                    self.on_trace({"event": "pdf_count_verification", "claim": claim, "label": "support",
                                   "reason": reason, "source_id": source_id, "evidence": context})
                response = self._response(None, "ok", reason, assessed_label="support")
                response["confidence_reasoning"] = "Explicit PDF count with matching relation, scope and unit."
                return response
        verifier = self.runtime.atomic.AtomicVerifier(
            self.backend, max_calls=criteria["max_calls_per_case"], max_attempts=criteria["max_attempts"],
            max_new_tokens=criteria["max_new_tokens"], timeout_seconds=timeout,
        )
        options = {"structured": True} if self.structured else {}
        result = verifier.verify(claim, context, **options)
        if self.on_trace:
            event = {"event": "atomic_verifier_result", "verifier_policy": self.policy_id, "result": result}
            if "table_cell" in state:
                event["table_cell"] = state["table_cell"]
            self.on_trace(event)
        if result["status"] != "completed" or result["stop_reason"] != "completed":
            return self._response(result, "incomplete", result["explanation"])
        if result["assessed_label"] not in ("support", "contradict", "not_enough_info"):
            raise ValueError("Atomic verifier returned an invalid completed label")
        return self._response(result, "ok", result["explanation"])

    def _response(self, result, status, reasoning, *, assessed_label=None):
        label = (assessed_label or result["assessed_label"]) if status == "ok" else "not_enough_info"
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
            "fact_check_raw": {"atomic": result}, "verifier_policy": self.policy_id,
        }


def load_atomic_factchecker(*, offline: bool, on_generation=None, on_event=None, on_model_loaded=None,
                           runtime: SimpleNamespace | None = None):
    """Use the candidate's pinned base Qwen/NF4 settings, never fine-tuned weights."""
    runtime = runtime if runtime is not None else cellfix29_runtime()
    import torch
    from huggingface_hub import snapshot_download
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, GenerationConfig

    if not torch.cuda.is_available():
        raise RuntimeError("Atomic loading requires CUDA/NF4, including with --allow-cpu")
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
        on_model_loaded("atomic_base_instruct_structured_v1" if getattr(runtime, "structured", False)
                        else "atomic_base_instruct_cellfix29")
    return AtomicFactCheckerNode(backend, runtime, on_trace=on_generation)


def structured_runtime() -> SimpleNamespace:
    """Use the pinned baseline model and tokenizer with the structured protocol."""
    workspace = WORKSPACE.resolve()
    criteria, _ = _frozen_inputs(workspace)
    return SimpleNamespace(
        atomic=importlib.import_module("04_factchecker.inference.atomic_verifier"),
        decoding=importlib.import_module("04_factchecker.inference.atomic_decoding"),
        criteria=criteria, workspace=workspace, structured=True,
    )
