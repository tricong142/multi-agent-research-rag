"""Check the embedded Kaggle demo on CPU with the real archive and simulated workers."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile
import pytest

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "artifacts/r8-v12-e2e-real-pdf"
CHECKPOINTS = ROOT / "artifacts/cellfix29-e2e-kaggle-checkpoints"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("variant", ["", "_table_context", "_table_proof"])
def test_real_pdf_demo_runtime_and_zip(variant):
    lock = json.loads((DEMO / "manifest.json").read_bytes())
    assert digest(DEMO / "inputs.json") == lock["inputs_sha256"]
    gold_path = DEMO / "gold.json"
    assert digest(gold_path) == lock["gold_sha256"]
    table_context = bool(variant)
    notebook = json.loads((ROOT / f"scripts/kaggle_r8_v12_e2e_real_pdf{variant}.ipynb").read_bytes())
    template = json.loads((ROOT / lock["notebook_template"]).read_bytes())
    if not table_context:
        assert notebook["cells"][2] == template["cells"][2]
    assert notebook["cells"][4] == template["cells"][4]
    boot, cuda, run, export = ["".join(c["source"]) for c in notebook["cells"] if c["cell_type"] == "code"]
    for step, source in enumerate((boot, cuda, run, export), 1):
        compile(source, f"demo cell {step}", "exec")
    embedded = {n.targets[0].id: ast.literal_eval(n.value) for n in ast.parse(run).body[:4]}
    assert set(embedded) == {"LOCK_JSON", "LOCK_SHA256", "INPUTS_JSON", "PDFS"}
    assert json.loads(embedded["INPUTS_JSON"]) == json.loads((DEMO / "inputs.json").read_bytes())
    assert gold_path.read_text(encoding="utf-8").strip() not in run
    run_lock = json.loads(embedded["LOCK_JSON"])
    if table_context:
        assert run_lock["base_runtime_sha256"] == lock["runtime_sha256"]
        assert run_lock["runtime_sha256"] != lock["runtime_sha256"]

    with TemporaryDirectory(prefix="r8-real-pdf-preflight-") as tmp:
        boot = boot.replace('subprocess.run(["nvidia-smi", "-L"], check=True)', "")
        boot = boot.replace('"/kaggle/input"', repr(str(CHECKPOINTS))).replace('"/tmp"', repr(tmp))
        scope = {}
        exec(compile(boot, "demo cell 1 CPU checkpoint", "exec"), scope)
        assert digest(scope["root"] / "artifacts/factcheck-verdict-r8-v12-holdout/candidate-lock.json") == lock["baseline_lock_sha256"]
        assert scope["RUNTIME_SHA256"] == run_lock["runtime_sha256"]
        for path, expected in run_lock.get("reader_runtime_members", {}).items():
            assert digest(scope["root"] / path) == expected
            if variant == "_table_proof":
                assert digest(ROOT / path) == expected
        if variant == "_table_proof":
            assert "research_rag/r8_adapter.py" in run_lock["reader_runtime_members"]
        scope["status_path"] = Path(tmp) / "status.json"
        scope["status_path"].write_text('{"state":"passed"}')
        scope["base_info"] = Path(tmp) / "base.json"
        scope["base_info"].write_text('{"simulated":true}')
        scope["python"] = sys.executable
        scope["env"] = {}
        calls = []

        def worker(command, *, cwd, env, stdout, stderr, timeout):
            assert command[command.index("--verifier") + 1] == "r8-v12"
            if table_context:
                assert command[command.index("--pdf-max-pages") + 1] == "26"
                coordinates = Path(command[command.index("--pdf-table-coordinates") + 1])
                assert digest(coordinates) == run_lock["reader_runtime_members"][coordinates.relative_to(cwd).as_posix()]
            path = Path(command[command.index("--pdf") + 1])
            assert digest(path) == lock["pdfs"][path.stem]["sha256"]
            calls.append(command[command.index("--question") + 1])
            if len(calls) == 2:
                stderr.write("injected worker failure")
                return SimpleNamespace(returncode=1)
            trace = Path(command[command.index("--trace-output") + 1])
            trace.write_text(json.dumps({"event":"graph_result","state":{
                "final_report":{"sentences":[]},"status":"completed"}}) + "\n")
            return SimpleNamespace(returncode=0)

        with patch.object(subprocess, "run", side_effect=worker):
            exec(compile(run.replace('"/kaggle/working"', repr(tmp)), "demo cell 3 simulated", "exec"), scope)
        assert calls == [case["question"] for case in scope["cases"]]
        exec(compile(export, "demo cell 4", "exec"), scope)
        with ZipFile(scope["archive"]) as result:
            assert result.testzip() is None
            review = json.loads(result.read("review.json"))
            assert review["complete_roster"] and review["returned_reports"] == 2
            assert review["quality_review"] == "pending"
            assert [r["id"] for r in review["cases"]] == [item["id"] for item in scope["cases"]]
            assert b"injected worker failure" in result.read(f"{scope['cases'][1]['id']}/stderr.log")
        (scope["out"] / scope["cases"][-1]["id"] / "process.json").unlink()
        exec(compile(export, "demo cell 4 partial data", "exec"), scope)
        assert scope["archive"].name.endswith("-incomplete.zip")
        with ZipFile(scope["archive"]) as result:
            assert not json.loads(result.read("review.json"))["complete_roster"]
