"""Build a sequential notebook with a hashed code patch over uploaded dataset v2."""
import base64
import hashlib
import json
from pathlib import Path
import re
import textwrap
import zlib
from pprint import pformat


cells = []


def add(kind, source):
    cell = {"cell_type": kind, "metadata": {}, "source": textwrap.dedent(source).strip() + "\n"}
    if kind == "code":
        compile(cell["source"], f"cell-{len(cells)}", "exec")
        cell.update(execution_count=None, outputs=[])
    cells.append(cell)


add("markdown", """
# Research RAG — resume validation

Keep this notebook **Private**, enable T4 x2 and Internet, attach **Research RAG
Five Agents Workspace** and **Research RAG Runtime Diagnostics version 2**.
Enable the existing `GEMINI_API_KEY` Secret. Never paste a key into a cell.

Run cells **one at a time in order**. The subprocess stays attached to its cell;
each stage has a timeout, saves logs/status, and packages diagnostic outputs.
Do not infer completion from a start message. No prompt promotion, threshold
tuning, API serving or final-test evaluation happens here.

The first cell verifies the exact approved manifest and uses a fresh workspace.
This notebook also contains the controller and source/test files from the current local runtime,
with before/after hashes checked over that workspace. The previously uploaded
ZIP is unchanged; import this updated notebook to use the fixes.
If a session is lost, inspect saved Output first; `/tmp` is disposable. Quick
Save **with Output** after each completed expensive stage, then stop the Draft
Session when done. The ZIP on `/kaggle/working` is not durable until saved.
""")

add("code", r'''
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
import base64, hashlib, json, os, shutil, signal, subprocess, sys, time, zipfile, zlib
import torch

assert torch.cuda.is_available(), "Enable an authorized GPU before this validation"
base_files = list(Path('/kaggle/input').rglob('transfer-manifest.json'))
update_files = list(Path('/kaggle/input').rglob('validation-update-manifest.json'))
assert len(base_files) == len(update_files) == 1, "Attach workspace and diagnostics v2"
base, update = base_files[0].parent, update_files[0].parent
manifest = json.loads(update_files[0].read_text())
assert len(manifest['files']) == 49
expected_manifest_sha = '__MANIFEST_SHA__'
assert hashlib.sha256(update_files[0].read_bytes()).hexdigest() == expected_manifest_sha
for item in manifest['files']:
    relative = PurePosixPath(item['path'])
    assert not relative.is_absolute() and '..' not in relative.parts
    data = (update / relative).read_bytes()
    assert len(data) == item['size'] and hashlib.sha256(data).hexdigest() == item['sha256']
    if item['base_sha256'] is not None:
        assert hashlib.sha256((base / relative).read_bytes()).hexdigest() == item['base_sha256']

run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
out = Path('/kaggle/working') / ('rag-validation-' + run_id)
out.mkdir(exist_ok=False)
root = Path('/tmp') / ('rag-workspace-' + run_id)
assert shutil.disk_usage('/tmp').free > 35 * 2**30
shutil.copytree(base, root)
for item in manifest['files']:
    target = root / item['path']
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(update / item['path'], target)
shutil.copy2(update_files[0], out / 'applied-manifest.json')
runtime_patch = __RUNTIME_PATCH__
for item in runtime_patch:
    relative = PurePosixPath(item['path'])
    assert not relative.is_absolute() and '..' not in relative.parts
    target = root / relative
    if item['base_sha256'] is None:
        assert not target.exists(), 'Unexpected existing file: ' + item['path']
    else:
        assert hashlib.sha256(target.read_bytes()).hexdigest() == item['base_sha256']
    payload = zlib.decompress(base64.b64decode(item['payload'], validate=True))
    assert len(payload) == item['size'] and hashlib.sha256(payload).hexdigest() == item['sha256']
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
(out/'runtime-patch-manifest.json').write_text(json.dumps(
    [{k:v for k,v in item.items() if k != 'payload'} for item in runtime_patch], indent=2))
env = os.environ.copy()
env.update(PYTHONPATH=str(root), HF_HOME='/tmp/rag-validation-hf', HF_HUB_DISABLE_PROGRESS_BARS='1')
venv = Path('/tmp') / ('rag-serving-' + run_id)
python = str(venv / 'bin/python')
statuses = {}

def bundle():
    # This dedicated directory contains only diagnostics produced by these cells.
    entries = [{'path':str(p.relative_to(out)), 'size':p.stat().st_size,
                'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
               for p in sorted(out.rglob('*')) if p.is_file() and p.name != 'output-manifest.json']
    (out/'output-manifest.json').write_text(json.dumps({'run_id':run_id,'files':entries},indent=2))
    archive = out.with_suffix('.zip')
    pending = archive.with_suffix('.zip.partial')
    with zipfile.ZipFile(pending, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob('*')):
            if p.is_file(): z.write(p, str(p.relative_to(out)))
    pending.replace(archive)
    print('Diagnostic archive:', archive.name, flush=True)

def run(name, command, *, timeout=1800, child_env=None, required=True):
    assert name not in statuses, 'Preserve the previous stage; start a fresh run for retries'
    started = time.perf_counter()
    status = {'state':'running'}
    statuses[name] = status
    (out/'status.json').write_text(json.dumps(statuses,indent=2))
    try:
        with (out/(name+'.stdout.log')).open('x') as stdout, (out/(name+'.stderr.log')).open('x') as stderr:
            process = subprocess.Popen(command, cwd=root, env=child_env or env,
                                       stdout=stdout, stderr=stderr, start_new_session=True)
            try:
                while True:
                    try:
                        code = process.wait(timeout=15)
                        break
                    except subprocess.TimeoutExpired:
                        elapsed = time.perf_counter()-started
                        print(name, 'running', round(elapsed), 'seconds', flush=True)
                        if elapsed > timeout: raise TimeoutError(name)
            except BaseException:
                os.killpg(process.pid, signal.SIGTERM)
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                raise
        status.update(state='completed' if code == 0 else 'failed', exit_code=code)
    except BaseException as exc:
        status.update(state='interrupted', error_type=type(exc).__name__)
        raise
    finally:
        status['elapsed_ms'] = round((time.perf_counter()-started)*1000,2)
        (out/'status.json').write_text(json.dumps(statuses,indent=2))
        bundle()
    print(name, status, flush=True)
    if required and code: raise RuntimeError(name + ' failed; inspect its saved stderr')
    return code

run('venv', [sys.executable,'-m','venv','--without-pip',str(venv)])
run('bootstrap', [sys.executable,'-m','pip','--python',python,'install','--no-cache-dir','pip==26.2.1','wrapt==2.1.2'])
run('torch', [python,'-m','pip','install','--no-cache-dir','torch==2.10.0','torchvision==0.25.0','--index-url','https://download.pytorch.org/whl/cu128'])
run('serving', [python,'-m','pip','install','--no-cache-dir','-r',str(root/'requirements-orchestrator.txt')])
run('pip-check', [python,'-m','pip','check'])
run('freeze', [python,'-m','pip','freeze'])
run('contract-tests', [python,'-m','unittest','discover','-s','research_rag/tests','-q'])
run('preflight', [python,'-m','research_rag.preflight','--faiss'])
print('SETUP COMPLETE; inspect preflight before running the next cell')
''')

add("markdown", """
## 1. Paired Fact-Checker diagnostic
84 predictions: baseline/coverage × (30 dev + 12 synthetic contracts).
Read `metrics.json`, false-support examples and label-confidence reasoning.
This is prompt development, **not** independent calibration or a final test.
""")
add("code", r'''
offline = env.copy()
offline.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
fc_dir = out/'factchecker'
run('factchecker', [python,'-u','-m','research_rag.evaluation.compare_factchecker',
                   '--output-dir',str(fc_dir)], child_env=offline, timeout=3600)
metrics = json.loads((fc_dir/'metrics.json').read_text())
for profile, datasets in metrics.items():
    for dataset, result in datasets.items():
        print(profile, dataset, {k:result[k] for k in ('n','accuracy','macro_f1','false_support','runtime_failed_rows')})
print('No profile promoted. Quick Save WITH Output now.')
''')

add("markdown", """
## 2. Reader API and complete real PDF
Use the existing Secret; do not print environment variables or key values.
The real PDF has 12 pages; only nine spans on pages 0/3/8 have labels.
At 61 seconds between API request starts this cell can take over 25 minutes.
The scorer checks phrase/page presence; it does not certify tables, reading order,
or independently labelled real scans. API failure remains a failed gate.
""")
add("code", r'''
from kaggle_secrets import UserSecretsClient
assert shutil.which('tesseract'), 'Tesseract must be installed on this host'
reader_env = env.copy()
reader_env.update(GEMINI_API_KEY=UserSecretsClient().get_secret('GEMINI_API_KEY'),
                  GEMINI_MODEL='gemini-3.5-flash-lite', GEMINI_REQUEST_INTERVAL_SECONDS='61')
for label, filename in [('reader-smoke','reader_smoke_manifest.jsonl'), ('reader-real','reader_real_manifest.jsonl')]:
    code = run(label, [python,'-u','-m','research_rag.evaluation.reader_smoke',
                      '--manifest',str(root/'research_rag/evaluation'/filename)],
               child_env=reader_env, timeout=3600, required=False)
    print((out/(label+'.stdout.log')).read_text()[-5000:])
    if code:
        print('Reader gate failed; inspect saved results before retrying. Retrieval is independently testable.')
        break
reader_env.pop('GEMINI_API_KEY', None)
print('Quick Save WITH Output now. API token usage/billing is not supplied by this CLI.')
''')

add("markdown", """
## 3. BGE and QASPER dev
Download the pinned public BGE snapshot, build a separate index, compare the same
393 dev queries. The 417 test candidates remain unscored. BM25/dense/policy logs
must report zero dense fallback before calling a result a dense score.
Quality decisions require these measured results; no default corpus is changed.
""")
add("code", r'''
bge_code = """
from huggingface_hub import snapshot_download
from research_rag.retrieval import EMBEDDING_MODEL, EMBEDDING_REVISION
path = snapshot_download(EMBEDDING_MODEL, revision=EMBEDDING_REVISION,
    token=False, allow_patterns=['*.json','*.safetensors','*.txt','*.model','README.md','LICENSE'])
print(path)
"""
run('bge-download', [python,'-u','-c',bge_code])
corpus = root/'kb_indexing/data/qasper_eval_20260926/corpus.jsonl'
qrels = corpus.parent/'qrels_dev.jsonl'
index = out/'qasper-index'
run('qasper-index', [python,'-u','-m','research_rag.indexing','--corpus',str(corpus),
                    '--output-dir',str(index),'--dense','--device','cuda:0','--batch-size','16'], timeout=3600)
for mode in ('bm25','dense','policy'):
    run('retrieval-'+mode, [python,'-u','-m','research_rag.evaluate','retrieval','--qrels',str(qrels),
        '--corpus',str(corpus),'--index-dir',str(index),'--mode',mode,'--top-k','5'], timeout=1800)
    result = json.loads((out/('retrieval-'+mode+'.stdout.log')).read_text())
    print(mode, result)
    assert result['dense_fallback_queries'] == 0, 'Fallback occurred: this is not a pure dense score'
print('Development diagnostics complete; final quality gates require review, calibration and adverse E2E.')
bundle()
print('Quick Save WITH Output, verify complete, then Stop session. Do not leave idle GPU running.')
''')

root = Path(__file__).resolve().parents[1]
import zipfile
with zipfile.ZipFile(root/'kaggle_transfer/validation-update-20260927.zip') as archive, \
        zipfile.ZipFile(root/'kaggle_transfer/research-rag-kaggle-v2.zip') as base:
    manifest_sha = hashlib.sha256(archive.read('validation-update-manifest.json')).hexdigest()
    base_hashes = {item['path']:item['sha256'] for item in json.loads(base.read('transfer-manifest.json'))['files']}
    paths = ['research_rag/graph.py', 'research_rag/state.py', 'research_rag/retrieval.py', 'research_rag/preflight.py',
             'research_rag/indexing.py', 'research_rag/evaluate.py', 'research_rag/evaluation/reader_smoke.py',
             'research_rag/tests/test_graph_safety.py', 'research_rag/tests/test_evaluation_contracts.py',
             'research_rag/tests/test_indexing.py', 'research_rag/controller.py',
             'research_rag/adapters.py', 'research_rag/local.py', 'research_rag/observe.py',
             'requirements-orchestrator.txt', 'train_agent3_summarizer/node.py',
             'train_agent3_summarizer/critic/prompts.py', 'research_rag/tests/test_integration.py',
             'research_rag/tests/test_autonomy.py', 'research_rag/planning.py', 'research_rag/tests/test_planning.py',
             'research_rag/evaluation/autonomy.py', 'research_rag/evaluation/autonomy_criteria.json',
             'research_rag/tests/test_autonomy_evaluation.py',
             '04_factchecker/inference/judge.py', 'train_agent2_reader/reader_agent.py',
             'train_agent2_reader/tools/tool_ocr_fallback.py', 'research_rag/tests/test_reader_local.py',
             'research_rag/tests/test_e2e_regressions.py',
             '04_factchecker/inference/confidence.py', '04_factchecker/node.py',
             '04_factchecker/prompts.py', '04_factchecker/eval_factchecker.py',
             'research_rag/evaluation/compare_factchecker.py',
             'research_rag/evaluation/confidence_criteria.json',
             'research_rag/evaluation/confidence_failures_20261009.jsonl',
             'research_rag/tests/test_confidence_repair.py',
             'research_rag/tests/test_confidence_diagnostic.py',
             'research_rag/evaluation/confidence_explanation_criteria.json',
             'research_rag/tests/test_confidence_explanations.py',
             'train_agent2_reader/reader_policy.py',
             'research_rag/tests/test_reader_api_retry.py',
             'research_rag/evaluation/reader_reliability.py',
             'research_rag/tests/test_reader_reliability.py',
             'research_rag/evaluation/confidence_backend_criteria.json',
             'research_rag/evaluation/compare_confidence_backends.py',
             'research_rag/tests/test_confidence_backends.py']
    secret = re.compile(rb'AIza[0-9A-Za-z_-]{35}|hf_[0-9A-Za-z]{25,}|gh[pousr]_[0-9A-Za-z]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')
    runtime_patch = []
    for relative in paths:
        data = (root/relative).read_bytes()
        assert not secret.search(data), 'Credential pattern in ' + relative + '; value withheld'
        original_sha = hashlib.sha256(archive.read(relative)).hexdigest() if relative in archive.namelist() else base_hashes.get(relative)
        runtime_patch.append({'path':relative, 'size':len(data), 'sha256':hashlib.sha256(data).hexdigest(),
                              'base_sha256':original_sha, 'payload':base64.b64encode(zlib.compress(data, 9)).decode('ascii')})
for cell in cells:
    cell['source'] = cell['source'].replace('__MANIFEST_SHA__', manifest_sha)
    cell['source'] = cell['source'].replace('__RUNTIME_PATCH__', pformat(runtime_patch, width=100))
    if cell['cell_type'] == 'code':
        compile(cell['source'], 'generated-notebook', 'exec')
target = root/'scripts/kaggle_resume_validation.ipynb'
target.write_text(json.dumps({'cells':cells, 'metadata':{'kernelspec':{'display_name':'Python 3',
    'language':'python','name':'python3'}}, 'nbformat':4,'nbformat_minor':4}, ensure_ascii=False, indent=2), encoding='utf-8')
print(target)
