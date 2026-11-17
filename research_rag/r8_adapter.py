"""Run the locked R8 v12 verdict policy through the graph's Fact-Checker contract."""

import ast
from functools import lru_cache
from hashlib import sha256
from importlib import import_module
from importlib.machinery import ModuleSpec
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
from zipfile import ZipFile
import json
import sys
import time

from .observe import observe_call
from .pdf_cell_context import check_coordinate_claim


ROOT = Path(__file__).resolve().parents[1]
R8_LOCK = ROOT / "artifacts/factcheck-verdict-r8-v12-holdout/candidate-lock.json"
R8_LOCK_SHA256 = "9adedbb5eb5269a41afb4a0f3a66275e079f49a0772090138c20124858279edd"
R8_POLICY_ID = "r8-v12:" + R8_LOCK_SHA256


@lru_cache(maxsize=1)
def load_r8_runtime():
    raw = R8_LOCK.read_bytes()
    if sha256(raw).hexdigest() != R8_LOCK_SHA256:
        raise ValueError("R8 v12 candidate lock hash mismatch")
    lock = json.loads(raw)
    source = ROOT / lock["source_bundle"]["path"]
    if sha256(source.read_bytes()).hexdigest() != lock["source_bundle"]["sha256"]:
        raise ValueError("R8 v12 source ZIP hash mismatch")
    with ZipFile(source) as bundle:
        members = lock["source_members"]
        if (len(bundle.namelist()) != len(members) or set(bundle.namelist()) != set(members)
                or any(sha256(bundle.read(n)).hexdigest() != h for n, h in members.items())):
            raise ValueError("R8 v12 source members differ from the candidate lock")
        temporary = TemporaryDirectory(prefix="r8-v12-frozen-")
        for name in members:
            if name.startswith("04_factchecker/"):
                bundle.extract(name, temporary.name)
        runner = bundle.read("scripts/run_factcheck_verdict.py")
    name = "_research_rag_locked_r8_v12"
    package = ModuleType(name)
    package.__path__ = [str(Path(temporary.name) / "04_factchecker")]
    package.__spec__ = ModuleSpec(name, loader=None, is_package=True)
    sys.modules[name] = package
    # The locked CLI uses absolute imports. Bind its unchanged assessment function
    # to isolated modules so the current development tree cannot change its policy.
    namespace = {
        key: import_module(f"{name}.inference.{module}") for key, module in (
            ("verdict", "semantic_verdict"), ("ledger", "source_ledger"), ("comparison", "source_comparison"),
        )
    }
    assessment = next(n for n in ast.parse(runner).body if isinstance(n, ast.FunctionDef) and n.name == "assess_case")
    exec(compile(ast.Module(body=[assessment], type_ignores=[]), "locked_r8_v12_assess_case.py", "exec"), namespace)
    config = lock["provenance"]
    if namespace["comparison"].POLICY != config["source_id_check_policy"]:
        raise ValueError("R8 v12 policy differs from the candidate lock")
    return SimpleNamespace(assess=namespace["assess_case"], config=config, temporary=temporary,
                           decoder=import_module(f"{name}.inference.atomic_decoding"),
                           verifier=import_module(f"{name}.inference.atomic_verifier"))


class R8FactCheckerNode:
    def __init__(self, backend, runtime, on_trace=None):
        self.backend, self.runtime, self.on_trace = backend, runtime, on_trace

    def __call__(self, state):
        claim, context = state.get("claim"), state.get("context")
        cfg = self.runtime.config
        label, status, reason, final = "not_enough_info", "invalid_input", "Missing claim or context.", None
        if isinstance(claim, str) and claim.strip() and isinstance(context, str) and context.strip():
            now = time.monotonic()
            seconds = cfg["timeout_seconds"]
            if state.get("deadline_at") is not None:
                seconds = min(seconds, state["deadline_at"] - time.time())
            deadline = now + seconds
            try:
                if seconds <= 0:
                    raise self.runtime.verifier.CaseDeadlineExceeded()
                if cells := state.get("pdf_coordinate_cells"):
                    label, reason = check_coordinate_claim(
                        claim, context, state["source_id"], state["question"], cells)
                    final = {"label": label, "reasoning": reason, "method": "pdf_coordinate_cell",
                             "evidence": [context] if label != "not_enough_info" else [],
                             "source_spans": [{"source_id": state["source_id"], "start": 0, "end": len(context)}]
                             if label != "not_enough_info" else []}
                else:
                    with self.backend.generation_deadline(deadline):
                        _, final, _ = self.runtime.assess(
                            {"claim": claim, "context": context},
                            lambda messages: self.backend.generate_json(messages, max_new_tokens=cfg["max_new_tokens"]),
                            evidence_format=cfg["evidence_format"], source_id_policy=cfg["source_id_check_policy"],
                        )
                if time.monotonic() >= deadline:
                    raise self.runtime.verifier.CaseDeadlineExceeded()
                if final["label"] in {"support", "contradict"} and (
                    not final["evidence"] or any(not quote or quote not in context for quote in final["evidence"])
                ):
                    raise ValueError("Decisive R8 verdict requires original evidence.")
                label, status, reason = final["label"], "ok", final["reasoning"]
            except (ValueError, self.runtime.verifier.CaseDeadlineExceeded) as exc:
                status, reason = "incomplete", type(exc).__name__
        if self.on_trace:
            self.on_trace({"event": "r8_verifier_result", "verifier_policy": R8_POLICY_ID, "label": label,
                           "claim": claim, "status": status, "verdict": final})
        return {"fact_check_label": label, "fact_check_status": status, "fact_check_reasoning": reason,
                "confidence_score": float(label == "support" and status == "ok"),
                "verification_method": final.get("method") if status == "ok" else None,
                "confidence_reasoning": "Binary eligibility of the completed locked R8 verdict.",
                "verifier_policy": R8_POLICY_ID}


def load_r8_factchecker(*, offline, on_generation=None, on_event=None, on_model_loaded=None):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    runtime = load_r8_runtime()
    cfg = runtime.config
    options = dict(revision=cfg["revision"], local_files_only=offline, trust_remote_code=False)
    torch.manual_seed(cfg["seed"])
    tokenizer = AutoTokenizer.from_pretrained(cfg["model"], **options)
    model = AutoModelForCausalLM.from_pretrained(
        cfg["model"], device_map={"": 0}, dtype=torch.float16, use_safetensors=True,
        quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                              bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.float16),
        **options,
    ).eval()
    backend = runtime.decoder.ConstrainedAtomicBackend(model, tokenizer)
    backend.on_generation = on_generation
    backend.generate_json = observe_call(backend.generate_json, "r8_verifier", on_event)
    if on_model_loaded:
        on_model_loaded("r8_v12_nf4")
    return R8FactCheckerNode(backend, runtime, on_trace=on_generation)
