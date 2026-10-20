"""Package the frozen v7 verifier for an isolated Colab CUDA runtime."""
import ast
import base64
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]
CRITERIA = 'research_rag/evaluation/atomic_verifier_criteria_v7.json'
TARGET = 'scripts/colab_decomposition_probe_v7.ipynb'


def package(*, criteria_path=CRITERIA):
    sys.path.insert(0, str(ROOT))
    from research_rag.evaluation.evaluate_atomic_verifier import load_frozen
    frozen, *_ = load_frozen(ROOT / criteria_path)
    names = set(frozen['source_sha256']) | {criteria_path}
    for folder in ('research_rag', '04_factchecker', '04_factchecker/inference',
                   'train_agent3_summarizer', 'train_agent3_summarizer/generator',
                   'train_agent3_summarizer/critic'):
        names.update(p.relative_to(ROOT).as_posix() for p in (ROOT / folder).glob('*.py'))
    names.update('research_rag/evaluation/' + name for name in (
        '__init__.py', 'factchecker_contract_cases.jsonl', frozen['supplemental_cases_file'],
        frozen['contract_file'], frozen['baseline_file'], frozen['decomposition_probe']['cases_file']))
    names.update('04_factchecker/checkpoints/factchecker_merged/' + name for name in (
        'config.json', 'generation_config.json', 'tokenizer.json', 'tokenizer_config.json',
        'chat_template.jinja'))
    manifest = {}
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(names):
            data = (ROOT / name).read_bytes()
            manifest[name] = {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
            entry = zipfile.ZipInfo(name, date_time=(2026, 10, 15, 0, 0, 0))
            archive.writestr(entry, data, compress_type=zipfile.ZIP_DEFLATED)
    return frozen, manifest, stream.getvalue()


def build():
    frozen, manifest, payload = package()
    template = json.loads((ROOT / 'scripts/kaggle_decomposition_probe_v7.ipynb').read_text(encoding='utf-8'))
    setup = template['cells'][2]['source']
    if not isinstance(setup, str):
        setup = ''.join(setup)
    # Reuse the exercised log, process-group deadline and archive handling.
    helpers = '\n\n'.join(ast.get_source_segment(setup, node) for node in ast.parse(setup).body
                          if isinstance(node, ast.FunctionDef) and node.name in ('bundle', 'run'))
    helpers = helpers.replace("if required and code: raise RuntimeError(name + ' failed; inspect its saved stderr')",
        "if required and code:\n        print((out / (name + '.stderr.log')).read_text()[-12000:], flush=True)\n        raise RuntimeError(name + ' failed; inspect its saved stderr')")
    unpack = '''from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
import base64, hashlib, io, json, os, signal, subprocess, sys, time, uuid, zipfile

run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
run_root = Path('/content') / ('atomic-v7-' + run_id)
root, out = run_root / 'workspace', run_root / 'output'
root.mkdir(parents=True, exist_ok=False)
out.mkdir(exist_ok=False)
'''
    unpack += 'payload = ' + repr(base64.b64encode(payload).decode()) + '\n'
    unpack += 'payload_sha256 = ' + repr(hashlib.sha256(payload).hexdigest()) + '\n'
    unpack += 'manifest = ' + repr(manifest) + '\n'
    unpack += '''data = base64.b64decode(payload, validate=True)
assert hashlib.sha256(data).hexdigest() == payload_sha256
with zipfile.ZipFile(io.BytesIO(data)) as archive:
    assert len(archive.namelist()) == len(manifest) and set(archive.namelist()) == set(manifest)
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
env.update(PYTHONPATH=str(root), HF_HOME=str(run_root / 'hf'), HF_HUB_DISABLE_PROGRESS_BARS='1')
env.pop('HF_HUB_OFFLINE', None)
env.pop('TRANSFORMERS_OFFLINE', None)
venv = run_root / 'venv'
python = str(venv / 'bin/python')
statuses = {}
'''
    unpack += helpers + '\n'
    unpack += "run('gpu-host', ['nvidia-smi'])\nprint('Run directory:', run_root)\n"
    install = '''run('venv', [sys.executable, '-m', 'venv', '--without-pip', str(venv)])
run('bootstrap', [sys.executable, '-m', 'pip', '--python', python, 'install', '--no-cache-dir', 'pip==26.2.1', 'wrapt==2.1.2'])
run('torch', [python, '-m', 'pip', 'install', '--no-cache-dir', 'torch==2.10.0', 'torchvision==0.25.0', '--index-url', 'https://download.pytorch.org/whl/cu128'])
run('runtime', [python, '-m', 'pip', 'install', '--no-cache-dir', '-r', 'requirements-orchestrator.txt', '-r', 'requirements-atomic-verifier.txt'])
run('pip-check', [python, '-m', 'pip', 'check'])
run('pip-freeze', [python, '-m', 'pip', 'freeze'])
'''
    tests = [Path(name).with_suffix('').as_posix().replace('/', '.') for name in frozen['source_sha256']
             if name.startswith('research_rag/tests/')]
    validate = "run('regression', [python, '-m', 'unittest', " + ', '.join(map(repr, tests)) + ", '-v'])\n"
    validate += '''run('cuda-preflight', [python, '-c', "import json, torch; assert torch.cuda.is_available(); print(json.dumps({'cuda': torch.version.cuda, 'torch': torch.__version__, 'device': torch.cuda.get_device_name(0)}))"])
run('probe-validate-only', [python, '-m', 'research_rag.evaluation.evaluate_atomic_verifier', '--output-dir', str(out / 'decomposition-probe'), '--decomposition-probe', '--validate-only'])
run('verifier-validate-only', [python, '-m', 'research_rag.evaluation.evaluate_atomic_verifier', '--output-dir', str(out / 'verifier39'), '--validate-only'])
print('Frozen verifier checks passed. Full five-agent/FAISS preflight is outside this minimal package.')
'''
    probe = '''assert all(statuses.get(name, {}).get('exit_code') == 0 for name in ('regression', 'cuda-preflight', 'probe-validate-only', 'verifier-validate-only'))
code = run('decomposition-probe', [python, '-u', '-m', 'research_rag.evaluation.evaluate_atomic_verifier', '--output-dir', str(out / 'decomposition-probe'), '--decomposition-probe', '--online-model-downloads'], timeout=2520, required=False)
for filename in ('summary.json', 'metrics.json'):
    path = out / 'decomposition-probe' / filename
    print(filename, path.read_text() if path.exists() else 'Incomplete; inspect saved logs.')
bundle()
print('Download:', out.with_suffix('.zip'))
print('Review all 18 actual decompositions before admission of the 39 cases. Stop the GPU after preserving output.')
from google.colab import files
files.download(str(out.with_suffix('.zip')))
'''
    intro = '''# Atomic verifier v7: Colab GPU, 18-claim probe

Select a CUDA GPU runtime before running these four code cells. This package
contains exact frozen v7 source/data plus the shared local tokenizer/config;
base weights download from the pinned Qwen revision. No Drive mount, secrets,
fine-tuned weights, retrieval indices or serving requests are needed.

The isolated venv uses the same pinned runtime as the Kaggle artifact.
Regression, CUDA preflight and BOTH validate-only modes precede inference.
V7 applies the same clause-local metric requirement in validation and decoder
enums for supported positive duration/count predicates. Named properties remain
accepted. Base prompts, model revision, input data and budgets match v6.
Budgets remain 2 calls/claim, 1536 tokens/call, 180 seconds/claim,
36 calls total and 2400 seconds for the probe process (2520 outer watchdog).
Do not rerun a completed stage; start a new run and preserve failed output.

A structural pass does not establish semantic correctness. Human review must
cover all five frozen rubric fields for all 18 predictions and bind the exact
prediction/criteria hashes before the unchanged runner admits the 39 cases.
No automatic 39-case execution, fabricated review or serving promotion.
These are inspected synthetic development cases, not independent held-out data.
'''
    cells = [{'cell_type': 'markdown', 'metadata': {}, 'source': intro}]
    for i, source in enumerate((unpack, install, validate, probe), 1):
        compile(source, 'colab-atomic-cell-' + str(i), 'exec')
        cells.append({'cell_type': 'code', 'metadata': {}, 'source': source, 'execution_count': None, 'outputs': []})
    cells.append({'cell_type': 'markdown', 'metadata': {}, 'source':
        'After reviewing the probe, preserve `semantic-review.json` with the real human reviewer and individual notes. '
        'The full runner command is `python -m research_rag.evaluation.evaluate_atomic_verifier '
        '--output-dir <new-output-dir> --probe-dir <reviewed-probe-dir> --online-model-downloads` '
        'using the isolated venv and workspace above. The admission gate validates the review; no skip flag is provided.'})
    notebook = {'cells': cells, 'metadata': {'kernelspec': {'display_name': 'Python 3', 'name': 'python3'},
                 'language_info': {'name': 'python'}, 'accelerator': 'GPU', 'colab': {'name': Path(TARGET).name}},
                'nbformat': 4, 'nbformat_minor': 4}
    target = ROOT / TARGET
    target.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    release = {'version': frozen['version'], 'platform': 'Google Colab CUDA',
        'criteria_sha256': hashlib.sha256((ROOT / CRITERIA).read_bytes()).hexdigest(),
        'payload_sha256': hashlib.sha256(payload).hexdigest(), 'payload_files': manifest,
        'files': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in
                  (TARGET, 'scripts/build_colab_atomic_probe.py', 'scripts/freeze_atomic_verifier_v7.py',
                   CRITERIA, 'research_rag/evaluation/atomic_verifier_contract_v7.json')},
        'validation_scope': 'Isolated verifier only; full five-agent/FAISS preflight not included.',
        'model_inference_completed': False}
    (ROOT / 'docs/atomic-verifier-v7-colab-release.json').write_text(json.dumps(release, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'notebook': str(target), 'bytes': target.stat().st_size,
                      'payload_files': len(manifest), 'criteria_sha256': release['criteria_sha256']}))
    return target


if __name__ == '__main__':
    build()
