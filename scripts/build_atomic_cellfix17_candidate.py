"""Build a narrow coverage-decoder fix from immutable Cellfix16 inputs."""
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "research-runs/atomic-cellfix17-candidate/workspace"


def sha(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            result.update(chunk)
    return result.hexdigest()


def build():
    if (ROOT / "docs/atomic-verifier-cellfix17-release.json").exists():
        raise ValueError("Released candidate is immutable")
    parent = json.loads((ROOT / "docs/atomic-verifier-cellfix16-candidate.json").read_bytes())
    release = json.loads((ROOT / "docs/atomic-verifier-cellfix16-release.json").read_bytes())
    for name, expected in release["files"].items():
        assert sha(ROOT / name) == expected, name
    before = Path(parent["source_root"])
    for name, item in parent["input_manifest"].items():
        assert sha(before / name) == item["sha256"], name
        target = SOURCE / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(before / name, target)
    extra = {
        "04_factchecker/inference/cellfix17_coverage.py": "scripts/atomic_cellfix17_coverage.py",
        "research_rag/tests/test_atomic_cellfix17.py": "scripts/test_atomic_cellfix17.py",
        "research_rag/tests/fixtures/cellfix16_full39_failure.json": "scripts/fixtures/cellfix16_full39_failure.json",
    }
    for name, original in extra.items():
        target = SOURCE / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / original, target)
    atomic = SOURCE / "04_factchecker/inference/atomic_verifier.py"
    atomic.write_bytes(atomic.read_bytes() + b"\nPOLICY='atomic-verifier-constrained-v8-cellfix17'\n")
    decoding = SOURCE / "04_factchecker/inference/atomic_decoding.py"
    decoding.write_bytes(decoding.read_bytes() + b'''
_cf16_final_assessment_schema=assessment_schema
from .cellfix17_coverage import bind_coverage
def assessment_schema(claim,part,context):
    witness=count_witness(part,context)
    if witness:return count_schema(witness)
    return bind_coverage(_cf15_assessment_schema(claim,part,context),context)
DECODER.update(policy='atomic-schema-decoding-v5-cellfix17',coverage_members='exact_source_observation_spans',empty_coverage_enum='never_unconstrained')
''')
    sys.path.insert(0, str(SOURCE))
    a = importlib.import_module("04_factchecker.inference.atomic_verifier")
    d = importlib.import_module("04_factchecker.inference.atomic_decoding")
    path = SOURCE / "research_rag/evaluation/atomic_verifier_criteria_v8.json"
    old = json.loads(path.read_bytes())
    criteria = {**old, "version": a.POLICY, "policy": a.POLICY, "structured_decoder": d.DECODER}
    criteria["source_sha256"] = {name: sha(SOURCE / name) for name in list(old["source_sha256"]) + list(extra)}
    contract = json.loads((path.parent / old["contract_file"]).read_bytes())
    contract.update(version="atomic-contract-constrained-v8-cellfix17",
                    cellfix17="Coverage uses exact source/observation spans including punctuation; impossible required enums fail closed.")
    contract_path = path.parent / "atomic_verifier_contract_v8_cellfix17.json"
    contract_path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    criteria.update(contract_file=contract_path.name, contract_sha256=sha(contract_path))
    path.write_text(json.dumps(criteria, indent=2) + "\n", encoding="utf-8")
    assert criteria["prompt_sha256"] == old["prompt_sha256"]
    names = sorted(set(parent["input_manifest"]) | set(extra) | {contract_path.relative_to(SOURCE).as_posix()})
    report = {"candidate": a.POLICY, "source_root": str(SOURCE), "parent_criteria_sha256": parent["criteria_sha256"],
        "criteria_sha256": sha(path), "input_manifest": {name: {"size": (SOURCE / name).stat().st_size, "sha256": sha(SOURCE / name)} for name in names},
        "validation30_used_for_tuning": True, "evaluation_role": "development", "new_model_inference_completed": False,
        "independent_validation_completed": False, "promoted_to_serving": False,
        "parent_release_files": release["files"], "model_budget_gold_gate_unchanged": True, "prompts_unchanged": True,
        "validator_logic_unchanged": True, "holdout_used_for_fix": False}
    (ROOT / "docs/atomic-verifier-cellfix17-candidate.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(report["criteria_sha256"], flush=True)


if __name__ == "__main__":
    if "--no-torch" in sys.argv:
        sys.modules["torch"] = None
    build()
