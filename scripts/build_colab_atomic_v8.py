"""Build isolated v8 assessment smoke + probe; human admission still gates full39."""
import ast
import base64
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_colab_atomic_probe import package

CRITERIA = 'research_rag/evaluation/atomic_verifier_criteria_v8.json'
TARGET = 'scripts/colab_atomic_verifier_v8_smoke_probe.ipynb'


def build():
    frozen, manifest, payload = package(criteria_path=CRITERIA)
    previous = json.loads((ROOT / 'scripts/colab_decomposition_probe_v7.ipynb').read_text(encoding='utf-8'))
    helpers = []
    for cell in previous['cells']:
        if cell['cell_type'] != 'code':
            continue
        source = ''.join(cell['source']) if isinstance(cell['source'], list) else cell['source']
        helpers += [ast.get_source_segment(source, node) for node in ast.parse(source).body
                    if isinstance(node, ast.FunctionDef) and node.name in ('bundle', 'run')]
    assert len(helpers) == 2
    setup = '''from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
import base64, hashlib, io, json, os, signal, subprocess, sys, time, uuid, zipfile
run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
run_root = Path('/content') / ('atomic-v8-' + run_id)
root, out = run_root / 'workspace', run_root / 'output'
root.mkdir(parents=True, exist_ok=False)
out.mkdir(exist_ok=False)
'''
    setup += 'payload = ' + repr(base64.b64encode(payload).decode()) + '\n'
    setup += 'payload_sha256 = ' + repr(hashlib.sha256(payload).hexdigest()) + '\n'
    setup += 'manifest = ' + repr(manifest) + '\n'
    setup += '''raw = base64.b64decode(payload, validate=True)
assert hashlib.sha256(raw).hexdigest() == payload_sha256
with zipfile.ZipFile(io.BytesIO(raw)) as archive:
    assert archive.testzip() is None and set(archive.namelist()) == set(manifest)
    for name, item in manifest.items():
        relative = PurePosixPath(name)
        assert not relative.is_absolute() and '..' not in relative.parts and '\\\\' not in name
        data = archive.read(name)
        assert len(data) == item['size'] and hashlib.sha256(data).hexdigest() == item['sha256']
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
(out / 'input-manifest.json').write_text(json.dumps(manifest, indent=2))
env = os.environ.copy()
env.update(PYTHONPATH=str(root), HF_HOME=str(run_root / 'hf'), HF_HUB_DISABLE_PROGRESS_BARS='1', TOKENIZERS_PARALLELISM='false')
env.pop('HF_HUB_OFFLINE', None)
env.pop('TRANSFORMERS_OFFLINE', None)
venv = run_root / 'venv'
python = str(venv / 'bin/python')
statuses = {}
'''
    setup += '\n\n'.join(helpers) + "\nrun('gpu-host', ['nvidia-smi'])\nprint('Run directory:', run_root)\n"
    install = '''run('venv', [sys.executable, '-m', 'venv', '--without-pip', str(venv)])
run('bootstrap', [sys.executable, '-m', 'pip', '--python', python, 'install', '--no-cache-dir', 'pip==26.2.1', 'wrapt==2.1.2'])
run('torch', [python, '-m', 'pip', 'install', '--no-cache-dir', 'torch==2.10.0', 'torchvision==0.25.0', '--index-url', 'https://download.pytorch.org/whl/cu128'])
run('runtime', [python, '-m', 'pip', 'install', '--no-cache-dir', '-r', 'requirements-orchestrator.txt', '-r', 'requirements-atomic-verifier.txt'])
run('pip-check', [python, '-m', 'pip', 'check'])
run('pip-freeze', [python, '-m', 'pip', 'freeze'])
'''
    modules = [Path(name).with_suffix('').as_posix().replace('/', '.') for name in frozen['source_sha256']
               if name.startswith('research_rag/tests/') and name.endswith('.py')]
    validate = 'run("regression", [python, "-m", "unittest", ' + ', '.join(repr(m) for m in modules) + ', "-v"], timeout=900)\n'
    validate += '''run('cuda-preflight', [python, '-c', "import json,torch; assert torch.cuda.is_available(); print(json.dumps({'torch':torch.__version__,'cuda':torch.version.cuda,'gpu':torch.cuda.get_device_name(0)}))"])
for name, flag in (('probe-validate-only','--decomposition-probe'), ('smoke-validate-only','--assessment-smoke'), ('verifier-validate-only',None)):
    command = [python, '-m', 'research_rag.evaluation.evaluate_atomic_verifier', '--output-dir', str(out / 'unused'), '--validate-only']
    if flag: command.append(flag)
    run(name, command)
run('pinned-model-cache', [python, '-c', "from huggingface_hub import snapshot_download; print(snapshot_download('Qwen/Qwen2.5-3B-Instruct',revision='aa8e72537993ba99e69dfaafa59ed015b17504d1',ignore_patterns=['*.bin','*.gguf','original/*']))"], timeout=1800)
'''
    smoke = '''assert all(statuses.get(name, {}).get('exit_code') == 0 for name in ('regression','cuda-preflight','probe-validate-only','smoke-validate-only','verifier-validate-only','pinned-model-cache'))
code = run('assessment-smoke', [python, '-u', '-m', 'research_rag.evaluation.evaluate_atomic_verifier', '--output-dir', str(out / 'assessment-smoke'), '--assessment-smoke', '--online-model-downloads'], timeout=2520, required=False)
path = out / 'assessment-smoke/metrics.json'
smoke_passed = code == 0 and path.exists() and json.loads(path.read_text())['automated_gate_pass'] is True
print(path.read_text() if path.exists() else 'Incomplete smoke; inspect logs.')
bundle()
from google.colab import files
files.download(str(out.with_suffix('.zip')))
assert smoke_passed, 'Preserve this ZIP and stop; failed smoke is not permission to run probe/full39.'
'''
    probe = '''assert smoke_passed, 'Complete a passing assessment smoke first.'
code = run('decomposition-probe', [python, '-u', '-m', 'research_rag.evaluation.evaluate_atomic_verifier', '--output-dir', str(out / 'decomposition-probe'), '--decomposition-probe', '--online-model-downloads'], timeout=2520, required=False)
for filename in ('summary.json','metrics.json'):
    path = out / 'decomposition-probe' / filename
    print(path.read_text() if path.exists() else 'Incomplete; inspect logs.')
bundle()
from google.colab import files
files.download(str(out.with_suffix('.zip')))
print('Send the final ZIP for provenance/replay/evidence review. New human review must bind the exact v8 probe before full39. No full39 or serving promotion ran here.')
'''
    intro = '''# Atomic verifier v8: assessment smoke, then probe18

Select Colab T4 GPU. Run the FIVE code cells in order in a fresh session.
The ZIP contains frozen isolated source/data/tokenizer; Qwen weights download
at the same pinned revision, NF4/float16/seed42 and unchanged per-case budgets.
V8 constrains source evidence/operands and prose, repairs missing numeric checks,
binds supported predicates with exactly, checks explicit quantity denial and
passes an absolute deadline into Transformers decoding. A hung CUDA call still
requires the outer process watchdog. No Reader/Gemini/FAISS or serving requests.

The 12-case smoke uses ALL original inspected development contracts. It is not
held-out evaluation, human review or admission to full39. It must pass all labels,
no false support/failures and complete decoder/deadline traces before probe18.
Both stages preserve their own outputs and pending review, including failures.
The fifth cell runs only probe18; full39 remains gated by a fresh human review.
Do not sign the review with an assistant identity or reuse the v7 signature.

Download the latest output ZIP even on failure; do not overwrite/retry a stage
in the same directory. Stop the GPU after preserving the output.
'''
    cells = [{'cell_type': 'markdown', 'metadata': {}, 'source': intro}]
    for index, source in enumerate((setup, install, validate, smoke, probe)):
        compile(source, f'v8-cell-{index}', 'exec')
        cells.append({'cell_type': 'code', 'metadata': {}, 'execution_count': None, 'outputs': [], 'source': source})
    notebook = {'cells': cells, 'metadata': {'kernelspec': {'display_name': 'Python 3', 'name': 'python3'}, 'accelerator': 'GPU'},
                'nbformat': 4, 'nbformat_minor': 4}
    target = ROOT / TARGET
    raw = (json.dumps(notebook, ensure_ascii=False, indent=1) + '\n').encode()
    release_path = ROOT / 'docs/atomic-verifier-v8-colab-release.json'
    if release_path.exists() and target.read_bytes() != raw:
        raise ValueError('Released v8 notebook is immutable; create another candidate')
    target.write_bytes(raw)
    release = {'version': frozen['version'], 'criteria_sha256': hashlib.sha256((ROOT / CRITERIA).read_bytes()).hexdigest(),
        'payload_sha256': hashlib.sha256(payload).hexdigest(), 'payload_files': manifest,
        'files': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in (
            TARGET, CRITERIA, 'research_rag/evaluation/atomic_verifier_contract_v8.json',
            'scripts/build_colab_atomic_v8.py', 'scripts/build_colab_atomic_probe.py',
            'scripts/colab_decomposition_probe_v7.ipynb', 'scripts/freeze_atomic_verifier_v8.py')},
        'assessment_smoke_cases': 12, 'probe_claims': 18, 'full39_runs_automatically': False,
        'fresh_gpu_inference_completed': False, 'human_review': 'pending', 'promoted_to_serving': False}
    if release_path.exists() and json.loads(release_path.read_text()) != release:
        raise ValueError('Released v8 metadata is immutable; create another candidate')
    # Emit a release only after --release; draft payload is exercised in isolation first.
    if '--release' in sys.argv:
        release_path.write_text(json.dumps(release, indent=2) + '\n', encoding='utf-8')
    else:
        (ROOT / 'research-runs/atomic-v8-draft-colab-release.json').write_text(json.dumps(release, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'notebook': str(target), 'payload_files': len(manifest), 'criteria_sha256': release['criteria_sha256']}))


if __name__ == '__main__':
    build()
