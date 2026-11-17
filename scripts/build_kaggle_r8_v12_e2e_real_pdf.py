"""Build the real-PDF Kaggle demo with the exact runtime from the successful R8 v12 smoke."""
import ast
import base64
import hashlib
import json
import sys
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "artifacts/r8-v12-e2e-real-pdf"
OUTPUT = ROOT / "scripts/kaggle_r8_v12_e2e_real_pdf.ipynb"
TABLE_OUTPUT = ROOT / "scripts/kaggle_r8_v12_e2e_real_pdf_table_context.ipynb"
PROOF_OUTPUT = ROOT / "scripts/kaggle_r8_v12_e2e_real_pdf_table_proof.ipynb"
COORDINATES = "artifacts/r8-v12-e2e-real-pdf/table-coordinates.json"
READER_FILES = ("research_rag/adapters.py", "research_rag/graph.py", "research_rag/local.py",
                "research_rag/pdf_cell_context.py", COORDINATES)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


RUN = '''
import json

assert json.loads(status_path.read_text())["state"] == "passed", "Run Cell 2 first."

def check_bytes(raw, expected, what):
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError(f"{what}: SHA-256 mismatch")

lock_bytes = LOCK_JSON.encode("utf-8")
input_bytes = INPUTS_JSON.encode("utf-8")
check_bytes(lock_bytes, LOCK_SHA256, "Demo manifest")
lock = json.loads(lock_bytes)
check_bytes(input_bytes, lock["inputs_sha256"], "Questions")
assert lock["runtime_sha256"] == RUNTIME_SHA256
check_bytes((root / "artifacts/factcheck-verdict-r8-v12-holdout/candidate-lock.json").read_bytes(),
            lock["baseline_lock_sha256"], "R8 verifier lock")
cases = json.loads(input_bytes)
assert len(cases) == len({case["id"] for case in cases}) == 3
assert set(PDFS) == set(lock["pdfs"]) == {case["paper"] for case in cases}
input_dir = root / "real_pdf_inputs"
input_dir.mkdir(exist_ok=True)
pdf_paths = {}
for paper, encoded in PDFS.items():
    raw = base64.b64decode(encoded, validate=True)
    check_bytes(raw, lock["pdfs"][paper]["sha256"], paper)
    pdf_paths[paper] = input_dir / (paper + ".pdf")
    pdf_paths[paper].write_bytes(raw)

out = Path(tempfile.mkdtemp(prefix="r8-v12-e2e-real-pdf-", dir="/kaggle/working"))
(out / "manifest.json").write_bytes(lock_bytes)
(out / "inputs.json").write_bytes(input_bytes)
(out / "provenance.json").write_text(json.dumps({
    "manifest_sha256": LOCK_SHA256,
    "runtime_sha256": RUNTIME_SHA256,
    "verifier_lock_sha256": lock["baseline_lock_sha256"],
    "checkpoint_members": ASSETS,
    "environment": json.loads(base_info.read_text()),
}, indent=2), encoding="utf-8")

for case in cases:
    case_dir = out / case["id"]
    case_dir.mkdir()
    command = [
        python, "-u", "-m", "research_rag.local",
        "--verifier", "r8-v12", "--question", case["question"], "--pdf", str(pdf_paths[case["paper"]]),
        "--retrieval-policy", lock["retrieval"], "--initial-top-k", str(lock["initial_top_k"]),
        "--quantize-4bit", "--online-model-downloads", "--profile-resources",
        "--process-timeout", "3600", "--metrics-output", str(case_dir / "metrics.json"),
        "--events-output", str(case_dir / "events.jsonl"), "--trace-output", str(case_dir / "trace.private.jsonl"),
    ]
    result = {"id": case["id"], "exit_code": None, "error_type": None}
    try:
        with (case_dir / "stdout.log").open("w", encoding="utf-8") as stdout, \
             (case_dir / "stderr.log").open("w", encoding="utf-8") as stderr:
            proc = subprocess.run(command, cwd=root, env=env, stdout=stdout, stderr=stderr, timeout=3720)
        result["exit_code"] = proc.returncode
    except (OSError, subprocess.TimeoutExpired) as error:
        result["error_type"] = type(error).__name__
    pending = case_dir / "process.tmp"
    pending.write_text(json.dumps(result, indent=2), encoding="utf-8")
    pending.replace(case_dir / "process.json")
    print(case["id"], result["exit_code"], result["error_type"], flush=True)
'''

EXPORT = '''
def read_json(path, *, lines=False):
    if not path.is_file():
        return [] if lines else {}
    raw = path.read_text(encoding="utf-8")
    return [json.loads(line) for line in raw.splitlines() if line.strip()] if lines else json.loads(raw)

reports = []
for case in cases:
    case_dir = out / case["id"]
    error = None
    try:
        process = read_json(case_dir / "process.json")
        trace = read_json(case_dir / "trace.private.jsonl", lines=True)
    except (OSError, ValueError) as exc:
        process, trace, error = {}, [], type(exc).__name__
    state = next((e["state"] for e in reversed(trace) if e.get("event") == "graph_result"), {})
    report = state.get("final_report")
    claims = state.get("verified_claims", [])
    chunks = {item["source_id"]: item for item in state.get("pdf_chunks", [])}
    cited = []
    for claim in claims:
        source = chunks.get(claim["source_id"], {})
        p0 = source.get("metadata", {}).get("page_no")
        cited.append({**claim, "pdf_page": p0 + 1 if isinstance(p0, int) else None,
                      "pdf_source": source.get("text")})
    status = "returned" if process.get("exit_code") == 0 and report else "failed_or_missing"
    reports.append({"id": case["id"], "paper": case["paper"], "question": case["question"], "run_status": status,
                    "process": process, "graph_status": state.get("status"), "errors": state.get("errors", []),
                    "export_error": error, "report": report, "citations": cited,
                    "r8_reviews": [e for e in trace if e.get("event") == "r8_verifier_result"]})

complete = len(reports) == 3 and all(
    row["process"].get("id") == row["id"] and
    (isinstance(row["process"].get("exit_code"), int) or row["process"].get("error_type"))
    for row in reports
)
summary = {"case_count": len(reports), "complete_roster": complete,
           "returned_reports": sum(r["run_status"] == "returned" for r in reports),
           "quality_review": "pending", "cases": reports}
(out / "review.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
archive = out.with_name(out.name + (".zip" if complete else "-incomplete.zip"))
temporary_archive = archive.with_suffix(".zip.tmp")
with ZipFile(temporary_archive, "w", compression=8) as bundle:
    for path in sorted(out.rglob("*")):
        if path.is_file():
            bundle.write(path, path.relative_to(out).as_posix())
temporary_archive.replace(archive)
print("ZIP to send:", archive)
print("Returned reports:", summary["returned_reports"], "/ 3")
'''


def table_runtime(boot, expected, *, table_proof=False):
    old_encoded = next(ast.literal_eval(node.value) for node in ast.parse(boot).body
                       if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                       and node.targets[0].id == "RUNTIME_B64")
    original = base64.b64decode(old_encoded, validate=True)
    assert digest(original) == expected
    paths = (*READER_FILES, "research_rag/r8_adapter.py") if table_proof else READER_FILES
    new_members = {name: (ROOT / name).read_bytes() for name in paths}
    target = BytesIO()
    with ZipFile(BytesIO(original)) as old, ZipFile(target, "w", compression=ZIP_DEFLATED) as new:
        for name in old.namelist():
            if name not in new_members:
                new.writestr(ZipInfo(name), old.read(name), compress_type=ZIP_DEFLATED)
        for name, content in new_members.items():
            new.writestr(ZipInfo(name), content, compress_type=ZIP_DEFLATED)
    runtime = target.getvalue()
    encoded = base64.b64encode(runtime).decode("ascii")
    boot = boot.replace(repr(old_encoded), repr(encoded), 1).replace(expected, digest(runtime), 1)
    return boot, digest(runtime), {name: digest(raw) for name, raw in new_members.items()}


def build(*, table_context=False, table_proof=False):
    lock_bytes = (DATA / "manifest.json").read_bytes()
    lock = json.loads(lock_bytes)
    inputs = (DATA / "inputs.json").read_bytes()
    assert digest(inputs) == lock["inputs_sha256"]
    assert digest((DATA / "gold.json").read_bytes()) == lock["gold_sha256"]
    parent = (ROOT / lock["notebook_template"]).read_bytes()
    assert digest(parent) == lock["notebook_template_sha256"]
    notebook = json.loads(parent)
    cells = notebook["cells"]
    setup = ast.parse("".join(cells[2]["source"]))
    expected_runtime = next(ast.literal_eval(node.value) for node in setup.body if isinstance(node, ast.Assign)
                            and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "RUNTIME_SHA256")
    assert expected_runtime == lock["runtime_sha256"]
    pdfs = {}
    for name, entry in lock["pdfs"].items():
        data = (ROOT / entry["path"]).read_bytes()
        assert digest(data) == entry["sha256"]
        pdfs[name] = base64.b64encode(data).decode("ascii")

    def write(index, text):
        cells[index]["source"] = text.splitlines(keepends=True)
        if cells[index]["cell_type"] == "code":
            cells[index].update(execution_count=None, outputs=[])

    output = OUTPUT
    run = RUN
    export = EXPORT
    detail = "This uses the original R8 v12 runtime."
    if table_context or table_proof:
        output = PROOF_OUTPUT if table_proof else TABLE_OUTPUT
        variant = "proof" if table_proof else "context"
        boot, runtime_sha, members = table_runtime("".join(cells[2]["source"]), expected_runtime,
                                                   table_proof=table_proof)
        write(2, boot)
        lock.update(role=f"r8_v12_real_pdf_demo_table_{variant}", base_runtime_sha256=expected_runtime,
                    runtime_sha256=runtime_sha, reader_max_pages=26, reader_runtime_members=members)
        lock_bytes = (json.dumps(lock, indent=2) + "\n").encode("utf-8")
        run = run.replace("cases = json.loads(input_bytes)", """for name, expected in lock["reader_runtime_members"].items():
    check_bytes((root / name).read_bytes(), expected, name)
cases = json.loads(input_bytes)""").replace(
            'prefix="r8-v12-e2e-real-pdf-"', f'prefix="r8-v12-e2e-real-pdf-table-{variant}-"').replace(
            '        "--retrieval-policy"', '        "--pdf-max-pages", str(lock["reader_max_pages"]),\n'
            f'        "--pdf-table-coordinates", str(root / {COORDINATES!r}),\n'
            '        "--retrieval-policy"')
        export = export.replace('"pdf_source": source.get("text")', '"pdf_source": source.get("text"),\n'
                                '                      "pdf_source_metadata": source.get("metadata")')
        detail = "This uses the locked R8 v12 verifier and audited table coordinates for the two input PDFs."
        if table_proof:
            detail += " Single-cell claims have a coordinate-based evidence check inside the R8 adapter."

    write(0, "# R8 v12 | Demo on two real PDFs\n\nPrivate Kaggle notebook. Enable GPU T4 x2 and Internet. "
             "Attach the private dataset containing research-rag-kaggle-v2.zip. Run Cells 1 to 4. "
             f"{detail} Gold is kept outside this notebook.\n")
    write(5, "## 3. Run three PDF questions\n")
    write(6, f"LOCK_JSON = {lock_bytes.decode()!r}\nLOCK_SHA256 = {digest(lock_bytes)!r}\n"
             f"INPUTS_JSON = {inputs.decode()!r}\nPDFS = {pdfs!r}\n" + run)
    write(7, "## 4. Package the three cases for review\n")
    write(8, export)
    for index, cell in enumerate(cells):
        if cell["cell_type"] == "code":
            compile("".join(cell["source"]), f"{output.name}: cell {index}", "exec")
    output.write_text(json.dumps(notebook, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(output, digest(output.read_bytes()))


if __name__ == "__main__":
    build(table_context="--table-context" in sys.argv[1:], table_proof="--table-proof" in sys.argv[1:])
