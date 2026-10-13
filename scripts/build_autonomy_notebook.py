"""Build a private Kaggle runner using the frozen local benchmark, without secrets."""
import base64
import hashlib
import json
from pathlib import Path
from pprint import pformat
import zlib

ROOT = Path(__file__).resolve().parents[1]
source = json.loads((ROOT / "scripts/kaggle_resume_validation.ipynb").read_text(encoding="utf-8"))
setup = next(c["source"] for c in source["cells"] if c["cell_type"] == "code")
mount = '''import kagglehub
from pathlib import Path
for dataset in ('trcng23/research-rag-five-agents-workspace', 'trcng23/research-rag-runtime-diagnostics'):
    mounted = kagglehub.dataset_download(dataset)
    print(dataset, '->', mounted)
print('Data manifests:', [p.name for p in Path('/kaggle/input').rglob('*manifest.json')])
'''
frozen = ROOT / "research-runs/autonomy-v1-20260930"
manifest = json.loads((frozen / "frozen-manifest.json").read_text(encoding="utf-8"))
payload = []
for name in [*manifest["files"], "frozen-manifest.json"]:
    data = (frozen / name).read_bytes()
    if name in manifest["files"]:
        assert hashlib.sha256(data).hexdigest() == manifest["files"][name]
    payload.append({"name": name, "sha256": hashlib.sha256(data).hexdigest(), "data": base64.b64encode(zlib.compress(data, 9)).decode()})
unpack = '''
suite = out / 'autonomy-v1'
suite.mkdir(exist_ok=True)
for item in __PAYLOAD__:
    assert Path(item['name']).name == item['name']
    content = zlib.decompress(base64.b64decode(item['data'], validate=True))
    assert hashlib.sha256(content).hexdigest() == item['sha256']
    target = suite / item['name']
    if target.exists():
        assert target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == item['sha256'], 'Existing frozen file differs: ' + item['name']
    else:
        assert not (suite/'results').exists() and 'autonomy-e2e' not in statuses, 'Frozen file missing after E2E started: ' + item['name']
        with target.open('xb') as handle:
            handle.write(content)
print('Frozen criteria SHA256:', hashlib.sha256((suite/'criteria.json').read_bytes()).hexdigest())
print((suite/'criteria.json').read_text())
bundle()
print('This is a regression rerun of an inspected benchmark, not a new independent test.')
print('Frozen suite verified; existing files preserved.')
if (suite/'results').exists() or 'autonomy-e2e' in statuses:
    print('An E2E attempt already exists. Inspect and save its results before starting a new run.')
'''.replace("__PAYLOAD__", pformat(payload, width=100))
execute = '''
from kaggle_secrets import UserSecretsClient
runtime_env = env.copy()
try:
    runtime_env['GEMINI_API_KEY'] = UserSecretsClient().get_secret('GEMINI_API_KEY')
except Exception:
    print('Reader secret unavailable; PDF scenario will be reported as failed, never simulated.')
runtime_env['GEMINI_REQUEST_INTERVAL_SECONDS'] = '61'
run('autonomy-e2e', [python, '-u', '-m', 'research_rag.evaluation.autonomy', 'run',
    '--directory', str(suite), '--online-model-downloads'], child_env=runtime_env, timeout=5400, required=False)
summary = suite/'results/summary.json'
print(summary.read_text() if summary.exists() else 'Run did not finish. Inspect status and stderr; no success claim.')
bundle()
print('Save Version with Output, verify saved, then Stop session to release GPU quota.')
'''
cells = [{"cell_type": "markdown", "metadata": {}, "source":
    "# Research RAG — bounded autonomy validation\nKeep Private. Attach the existing workspace and diagnostics v2 datasets. "
    "Use the existing GPU and GEMINI_API_KEY secret. Run these four cells in order. "
    "Runtime revision 2026-10-09: confidence repair retry added; model validation is pending. "
    "Criteria and eight cases remain unchanged. These inspected cases are now regression data, not an independent final test. "
    "Five controlled cases and three QASPER held-out candidates are reported separately; semantic overlap remains unaudited.\n"}]
for body in (mount, setup, unpack, execute):
    compile(body, "autonomy-notebook", "exec")
    cells.append({"cell_type": "code", "metadata": {}, "source": body, "execution_count": None, "outputs": []})
target = ROOT / "scripts/kaggle_autonomy_validation.ipynb"
target.write_text(json.dumps(dict(cells=cells, metadata=source["metadata"], nbformat=4, nbformat_minor=4), ensure_ascii=False, indent=2), encoding="utf-8")
print(target)
print("Bytes:", target.stat().st_size, "SHA256:", hashlib.sha256(target.read_bytes()).hexdigest())
