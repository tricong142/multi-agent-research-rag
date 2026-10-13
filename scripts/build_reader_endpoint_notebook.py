"""Build a CPU-only, two-cell diagnostic with frozen actual Reader request inputs."""
import base64
import hashlib
import json
from pathlib import Path
from pprint import pformat
import zlib

from train_agent2_reader.reader_agent import ReaderAgent


ROOT = Path(__file__).resolve().parents[1]
pdf = ROOT / 'research_rag/evaluation/pdfs/qasper_2021.pdf'
features = ReaderAgent()._extract_heuristic_features(str(pdf), 3)
blocks_file = ROOT / 'research-runs/kaggle-20261012T024449Z/reader-failed-page/page_blocks.jsonl'
row = json.loads(blocks_file.read_text(encoding='utf-8').splitlines()[0])
assert row['accepted'] is True and row['page_no'] == 3
assert row['source_sha256'] == hashlib.sha256(pdf.read_bytes()).hexdigest()
confidences = [b['confidence'] for b in row['blocks'] if b['confidence'] is not None]
inputs = {'pdf_sha256': row['source_sha256'], 'page_no': 3, 'router_features': features,
          'critique_summary': {'source_tool': row['final_tool'], 'num_blocks': len(row['blocks']),
              'avg_confidence': sum(confidences) / len(confidences),
              'sample_texts': [b['text'] for b in row['blocks'][:5]],
              'page_width': features['page_width'], 'page_height': features['page_height']},
          'critique_fixture_origin': 'Accepted extraction from development run 20261012T024449Z; not new extraction or independently reviewed ground truth.',
          'source_url': 'https://aclanthology.org/2021.naacl-main.365.pdf', 'license': 'CC-BY-4.0'}
files = {name: (ROOT / name).read_bytes() for name in (
    'scripts/kaggle_reader_endpoint_probe.py', 'scripts/kaggle_gemini_probe.py',
    'train_agent2_reader/reader_policy.py')}
files['train_agent2_reader/__init__.py'] = b''
files['inputs.json'] = json.dumps(inputs, ensure_ascii=False, indent=2).encode()
payload = [{'path': name, 'sha256': hashlib.sha256(data).hexdigest(),
            'payload': base64.b64encode(zlib.compress(data)).decode()} for name, data in files.items()]
setup = '''from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
from uuid import uuid4
import base64, hashlib, json, os, shutil, subprocess, sys, time, zipfile, zlib

out = Path('/kaggle/working') / ('reader-endpoint-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:8])
out.mkdir(exist_ok=False)
code_dir = out / 'code'
code_dir.mkdir()
entries = __PAYLOAD__
for item in entries:
    relative = PurePosixPath(item['path'])
    assert not relative.is_absolute() and '..' not in relative.parts
    data = zlib.decompress(base64.b64decode(item['payload'], validate=True))
    assert hashlib.sha256(data).hexdigest() == item['sha256']
    target = code_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as handle: handle.write(data)
(out / 'code-manifest.json').write_text(json.dumps([{k: v for k, v in item.items() if k != 'payload'} for item in entries], indent=2))

def bundle_endpoint():
    items = [{'path': str(p.relative_to(out)), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'size': p.stat().st_size}
             for p in sorted(out.rglob('*')) if p.is_file() and p.name != 'output-manifest.json']
    (out / 'output-manifest.json').write_text(json.dumps({'files': items}, indent=2))
    with zipfile.ZipFile(out.with_suffix('.zip'), 'w', zipfile.ZIP_DEFLATED) as archive:
        for p in sorted(out.rglob('*')):
            if p.is_file(): archive.write(p, str(p.relative_to(out)))
    print('ZIP:', out.with_suffix('.zip'))

venv = Path('/tmp') / out.name
python = str(venv / 'bin/python')
setup_status = {'state': 'running', 'stage': 'create_venv', 'base_python': sys.version.split()[0]}

def find_bootstrap_pip():
    # CPU images can expose pip on PATH rather than through the kernel interpreter.
    candidates = [[sys.executable, '-m', 'pip']]
    pip_binary = shutil.which('pip') or shutil.which('pip3')
    if pip_binary: candidates.append([pip_binary])
    for candidate in candidates:
        try:
            result = subprocess.run(candidate + ['--help'], capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode == 0 and '--python' in result.stdout:
            return candidate
    raise RuntimeError('No existing pip supporting --python was found. Preserve the setup ZIP.')

try:
    with (out / 'setup.stdout.log').open('x') as stdout, (out / 'setup.stderr.log').open('x') as stderr:
        subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(venv)],
                       stdout=stdout, stderr=stderr, check=True, timeout=120)
        setup_status['stage'] = 'find_bootstrap_pip'
        bootstrap_pip = find_bootstrap_pip()
        setup_status['stage'] = 'install_sdk'
        subprocess.run(bootstrap_pip + ['--python', python, 'install', '--disable-pip-version-check',
                        'pip==26.2.1', 'wrapt==2.1.2', 'google-genai==2.22.0', 'httpx==0.28.1', 'pydantic==2.13.5'],
                       stdout=stdout, stderr=stderr, check=True, timeout=300)
    setup_status['stage'] = 'freeze'
    with (out / 'freeze.stdout.log').open('x') as handle:
        subprocess.run([python, '-m', 'pip', 'freeze'], stdout=handle, check=True, timeout=30)
    # Compile the portable source without calling a model.
    setup_status['stage'] = 'compile_sources'
    subprocess.run([python, '-m', 'compileall', '-q', str(code_dir)], check=True, timeout=30)
    setup_status['stage'] = 'validate_sdk'
    sdk_check = """from importlib.metadata import version
from google import genai
import httpx, pydantic, wrapt
assert version('google-genai') == '2.22.0'
assert version('httpx') == '0.28.1'
assert version('pydantic') == '2.13.5'
assert version('wrapt') == '2.1.2'
"""
    sdk_result = subprocess.run([python, '-c', sdk_check], capture_output=True, text=True, timeout=60)
    with (out / 'setup.stdout.log').open('a') as stdout, (out / 'setup.stderr.log').open('a') as stderr:
        stdout.write(sdk_result.stdout)
        stderr.write(sdk_result.stderr)
    sdk_result.check_returncode()
    if 'Error in sitecustomize' in sdk_result.stderr:
        raise RuntimeError('Python startup failed in sitecustomize; preserve setup.stderr.log in the ZIP.')
    setup_status['stage'] = 'read_secret'
    from kaggle_secrets import UserSecretsClient
    try:
        secret_check = UserSecretsClient().get_secret('GEMINI_API_KEY')
        assert isinstance(secret_check, str) and secret_check
    except Exception:
        raise RuntimeError('Enable the existing GEMINI_API_KEY Secret for this notebook.') from None
    finally:
        secret_check = None
    setup_status.update(state='completed', stage='complete', sdk='2.22.0')
except BaseException as exc:
    setup_status.update(state='failed', error_type=type(exc).__name__)
    if isinstance(exc, subprocess.CalledProcessError): setup_status['exit_code'] = exc.returncode
    raise
finally:
    (out / 'setup-status.json').write_text(json.dumps(setup_status, indent=2))
    bundle_endpoint()
print('SETUP_OK: no live Gemini requests yet. Run cell 2 once.')
'''.replace('__PAYLOAD__', pformat(payload, width=100))
run = '''assert 'python' in globals() and Path(python).is_file(), 'Complete cell 1 first'
assert (out / 'setup-status.json').exists() and json.loads((out / 'setup-status.json').read_text()).get('state') == 'completed', 'Cell 1 did not complete; preserve its ZIP and resolve setup first'
assert not (out / 'status.json').exists() and not (out / 'probe').exists(), 'Already attempted; preserve the ZIP and stop'
model = 'gemini-3.6-flash'
status = {'state': 'running', 'model': model}
with (out / 'status.json').open('x') as handle: json.dump(status, handle, indent=2)
child_env = os.environ.copy()
child_env.update(PYTHONPATH=str(code_dir), GEMINI_MODEL=model, GOOGLE_GENAI_USE_VERTEXAI='false')
started = time.monotonic()
try:
    child_env['GEMINI_API_KEY'] = UserSecretsClient().get_secret('GEMINI_API_KEY')
    with (out / 'probe.stdout.log').open('x') as stdout, (out / 'probe.stderr.log').open('x') as stderr:
        process = subprocess.Popen([python, '-u', str(code_dir / 'scripts/kaggle_reader_endpoint_probe.py'),
            '--inputs', str(code_dir / 'inputs.json'), '--output-dir', str(out / 'probe')],
            env=child_env, stdout=stdout, stderr=stderr, start_new_session=True)
        try:
            while True:
                try:
                    code = process.wait(timeout=15)
                    break
                except subprocess.TimeoutExpired:
                    elapsed = time.monotonic() - started
                    print('Endpoint comparison running:', round(elapsed), 'seconds', flush=True)
                    if elapsed >= 600: raise TimeoutError('Endpoint comparison exceeded 600 seconds')
        except BaseException:
            import signal
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
    child_env.pop('GEMINI_API_KEY', None)
    status['elapsed_ms'] = round((time.monotonic() - started) * 1000, 3)
    (out / 'status.json').write_text(json.dumps(status, indent=2))
    bundle_endpoint()
summary = out / 'probe/summary.json'
print(summary.read_text(encoding='utf-8') if summary.exists() else 'No summary; preserve status/stderr in the ZIP.')
print('Stop here. Contract success is not the Reader quality gate; preserve the ZIP for review.')
'''
for body in (setup, run):
    compile(body, 'reader-endpoint-notebook', 'exec')
notebook = {'cells': [{'cell_type': 'markdown', 'metadata': {}, 'source':
    '# Reader request comparison — CPU, two cells\n\n'
    'Use a NEW private Kaggle notebook; Internet ON; Accelerator None; enable the existing GEMINI_API_KEY Secret. '
    'No dataset attachment, GPU or model weight download. Cell 1 installs a small isolated SDK environment matching the audited run and checks Secret access. '
    'Cell 2 makes at most FOUR live requests, no retry, starts at least 61 seconds apart: router SDK/REST, critique SDK/REST. '
    'Payloads are serialized by the installed SDK and matched byte-for-byte. Stops early on HTTP 400/401/403/404/429. '
    'Frozen router features come from QASPER page 4; critique input uses a historical extraction from development evidence. '
    'This checks API contracts, not extraction quality or independent E2E. Do not rerun cell 2 or change keys/models within this run. '
    'Keep the Output ZIP even when the probe fails. Do not run Reader A/B based only on this contract result.\n'}]
    + [{'cell_type': 'code', 'metadata': {}, 'source': body, 'execution_count': None, 'outputs': []} for body in (setup, run)],
    'metadata': {'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'}},
    'nbformat': 4, 'nbformat_minor': 4}
path = ROOT / 'scripts/kaggle_reader_endpoint_comparison.ipynb'
path.write_text(json.dumps(notebook, ensure_ascii=False, indent=2), encoding='utf-8')
print(path.name, 'SHA256:', hashlib.sha256(path.read_bytes()).hexdigest())
