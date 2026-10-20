"""Package only QASPER dev/corpus and the real BM25/FAISS runtime for Colab."""
import ast
import base64
import hashlib
import io
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "scripts/colab_qasper_bm25_dense_dev.ipynb"


def package():
    names = ["research_rag/" + name for name in (
        "__init__.py", "graph.py", "state.py", "controller.py", "planning.py", "retrieval.py", "indexing.py",
        "evaluation/__init__.py", "evaluation/qasper_benchmark.py", "tests/test_qasper_benchmark.py")]
    names += ["kb_indexing/data/qasper_eval_20260926/" + name for name in (
        "corpus.jsonl", "qrels_dev.jsonl", "manifest.json")]
    manifest, stream = {}, io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(names):
            raw = (ROOT / name).read_bytes()
            manifest[name] = {"size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
            entry = zipfile.ZipInfo(name, date_time=(2026, 10, 16, 0, 0, 0))
            archive.writestr(entry, raw, compress_type=zipfile.ZIP_DEFLATED)
    return manifest, stream.getvalue()


def build():
    manifest, payload = package()
    # Keep the already exercised process timeout, stage logs and failure ZIP export.
    template = json.loads((ROOT / "scripts/colab_decomposition_probe_v7.ipynb").read_text(encoding="utf-8"))
    helpers = []
    for cell in template["cells"]:
        if cell["cell_type"] == "code":
            source = ''.join(cell["source"]) if isinstance(cell["source"], list) else cell["source"]
            helpers += [ast.get_source_segment(source, n) for n in ast.parse(source).body
                        if isinstance(n, ast.FunctionDef) and n.name in ("run", "bundle")]
    assert len(helpers) == 2
    setup = '''from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
import base64, hashlib, io, json, os, signal, subprocess, sys, time, uuid, zipfile
run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
run_root = Path('/content') / ('qasper-dev-' + run_id)
root, out = run_root / 'workspace', run_root / 'output'
root.mkdir(parents=True, exist_ok=False)
out.mkdir(exist_ok=False)
'''
    setup += 'payload = ' + repr(base64.b64encode(payload).decode()) + '\n'
    setup += 'payload_sha256 = ' + repr(hashlib.sha256(payload).hexdigest()) + '\n'
    setup += 'manifest = ' + repr(manifest) + '\n'
    setup += '''data = base64.b64decode(payload, validate=True)
assert hashlib.sha256(data).hexdigest() == payload_sha256
with zipfile.ZipFile(io.BytesIO(data)) as archive:
    assert archive.testzip() is None and set(archive.namelist()) == set(manifest)
    for name in archive.namelist():
        relative = PurePosixPath(name)
        assert not relative.is_absolute() and '..' not in relative.parts and '\\\\' not in name
        raw = archive.read(name)
        assert len(raw) == manifest[name]['size'] and hashlib.sha256(raw).hexdigest() == manifest[name]['sha256']
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
(out / 'input-manifest.json').write_text(json.dumps(manifest, indent=2))
env = os.environ.copy()
env.update(PYTHONPATH=str(root), HF_HOME=str(run_root / 'hf'), OMP_NUM_THREADS='4', TOKENIZERS_PARALLELISM='false')
env.pop('HF_HUB_OFFLINE', None)
env.pop('TRANSFORMERS_OFFLINE', None)
venv = run_root / 'venv'
python = str(venv / 'bin/python')
statuses = {}
'''
    setup += '\n\n'.join(helpers) + "\nrun('gpu-host', ['nvidia-smi'])\nprint('Run:', run_root)\n"
    install = '''run('venv', [sys.executable, '-m', 'venv', '--without-pip', str(venv)])
run('bootstrap', [sys.executable, '-m', 'pip', '--python', python, 'install', '--no-cache-dir', 'pip==26.2.1'])
run('torch', [python, '-m', 'pip', 'install', '--no-cache-dir', 'torch==2.10.0', 'torchvision==0.25.0', '--index-url', 'https://download.pytorch.org/whl/cu128'])
run('runtime', [python, '-m', 'pip', 'install', '--no-cache-dir', 'rank-bm25==0.2.2', 'faiss-cpu==1.15.0', 'sentence-transformers==6.0.0', 'transformers==5.16.1', 'pydantic==2.13.5'])
run('pip-check', [python, '-m', 'pip', 'check'])
run('pip-freeze', [python, '-m', 'pip', 'freeze'])
run('regression', [python, '-m', 'unittest', 'research_rag.tests.test_qasper_benchmark', '-v'])
run('cuda-check', [python, '-c', "import torch; assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0))"])
'''
    build_index = '''run('download-pinned-bge', [python, '-c', "from huggingface_hub import snapshot_download; from research_rag.retrieval import EMBEDDING_MODEL,EMBEDDING_REVISION; print(snapshot_download(EMBEDDING_MODEL, revision=EMBEDDING_REVISION, ignore_patterns=['*.bin','onnx/*','openvino/*']))"], timeout=1800)
data_dir = root / 'kb_indexing/data/qasper_eval_20260926'
index_dir = out / 'qasper-index'
run('build-qasper-faiss', [python, '-u', '-m', 'research_rag.indexing', '--corpus', str(data_dir / 'corpus.jsonl'), '--output-dir', str(index_dir), '--dense', '--device', 'cuda:0', '--batch-size', '8'], timeout=5400)
'''
    benchmark = '''assert all(statuses.get(name, {}).get('exit_code') == 0 for name in ('regression','cuda-check','build-qasper-faiss'))
code = run('paired-dev-benchmark', [python, '-u', '-m', 'research_rag.evaluation.qasper_benchmark', '--data-dir', str(data_dir), '--index-dir', str(index_dir), '--output-dir', str(out / 'benchmark'), '--mode', 'paired', '--top-k', '5'], timeout=3600, required=False)
summary = out / 'benchmark/summary.json'
print(summary.read_text() if summary.exists() else 'Incomplete; inspect saved logs.')
bundle()
print('A valid paired result requires 393 BM25 + 393 Dense queries, no fallback, matching hashes. No test candidate or verifier/E2E evaluation here.')
from google.colab import files
files.download(str(out.with_suffix('.zip')))
assert code == 0, 'Do not report Dense metrics from a failed or fallback run.'
'''
    intro = '''# QASPER dev: BM25 vs real BGE Dense

Select T4 GPU, then run the four code cells in order. This isolated package
contains 18,587 original paragraph chunks and 393 development qrels. It excludes
the 417 test-candidate qrels, verifier datasets, model adapters and credentials.
It builds a NEW FAISS IndexFlatIP with normalized BGE-Large embeddings at the
pinned revision and verifies corpus/ID mapping/artifact hashes before scoring.
BM25 and Dense use the same dev questions, corpus, k=5 and no retrieval history.
Every query records the requested/actual backend; any fallback invalidates the
entire Dense score. A missing/invalid FAISS stops before loading the encoder.

This is QASPER-derived global paragraph retrieval with paper-title-prefixed
questions, not the official QASPER answer metric. Recall does not measure false
support or answer quality. Download the ZIP even if a stage fails. It includes
the index (~76 MB uncompressed), logs, dependencies, input hashes and traces.
Stop the GPU after download. Do not rerun stages in the same run directory.
'''
    cells = [{"cell_type": "markdown", "metadata": {}, "source": intro}]
    cells += [{"cell_type": "code", "metadata": {}, "execution_count": None,
               "outputs": [], "source": code} for code in (setup, install, build_index, benchmark)]
    notebook = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                                            "accelerator": "GPU"}, "nbformat": 4, "nbformat_minor": 5}
    TARGET.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + '\n', encoding="utf-8")
    release = {"notebook": TARGET.relative_to(ROOT).as_posix(), "notebook_sha256": hashlib.sha256(TARGET.read_bytes()).hexdigest(),
               "payload_sha256": hashlib.sha256(payload).hexdigest(), "payload_files": manifest,
               "gpu_executed": False, "test_candidate_included": False}
    (ROOT / "docs/qasper-benchmark-colab-release.json").write_text(json.dumps(release, indent=2) + '\n', encoding="utf-8")
    return release


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
