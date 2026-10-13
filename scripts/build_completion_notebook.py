"""Package the pending confidence explanation and Reader validation, without promoting prompts."""
import base64
import hashlib
import json
from pathlib import Path
import zlib


ROOT = Path(__file__).resolve().parents[1]
source = json.loads((ROOT / "scripts/kaggle_autonomy_validation.ipynb").read_text(encoding="utf-8"))
setup = [c for c in source["cells"] if c["cell_type"] == "code"][:2]
pdf = ROOT / "research-runs/autonomy-v1-20260930/extra-pages.pdf"
frozen = json.loads((pdf.parent / "frozen-manifest.json").read_text(encoding="utf-8"))
pdf_hash = hashlib.sha256(pdf.read_bytes()).hexdigest()
assert pdf_hash == frozen["files"][pdf.name]
fixture = {"sha256": pdf_hash, "payload": base64.b64encode(zlib.compress(pdf.read_bytes(), 9)).decode()}

confidence = '''offline = env.copy()
offline.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
diagnostic = out / 'confidence-explanation-v2'
run('confidence-explanation-v2', [python, '-u', '-m', 'research_rag.evaluation.compare_factchecker',
    '--comparison', 'explanation', '--output-dir', str(diagnostic)],
    child_env=offline, timeout=5400, required=False)
for filename in ('gate-results.json', 'metrics.json'):
    path = diagnostic / filename
    print(filename, path.read_text() if path.exists() else 'Missing; inspect saved status/stderr.')
print('Read explanation-review.jsonl against claim/context. No human judgment is pre-filled.')
print('Keep repair as serving default. Reader stages are independent of this candidate gate.')
bundle()
'''

reader_setup = '''from kaggle_secrets import UserSecretsClient
assert shutil.which('tesseract'), 'Tesseract is required for Reader smoke cases'
fixture = __FIXTURE__
fixture_dir = out / 'reader-fixture'
fixture_dir.mkdir(exist_ok=True)
pdf_data = zlib.decompress(base64.b64decode(fixture['payload'], validate=True))
assert hashlib.sha256(pdf_data).hexdigest() == fixture['sha256']
pdf_path = fixture_dir / 'extra-pages.pdf'
if pdf_path.exists():
    assert pdf_path.read_bytes() == pdf_data, 'Existing fixture changed; preserve the previous run'
else:
    with pdf_path.open('xb') as handle: handle.write(pdf_data)
manifest = fixture_dir / 'page0.jsonl'
row = {'pdf_path': 'extra-pages.pdf', 'layout': 'controlled_e2e_page0',
       'source_sha256': fixture['sha256'], 'annotation_origin': 'Original controlled E2E fixture; development regression',
       'expected_spans': [{'page_no': 0, 'text': 'Orion trial sample size: see the appendix for the final count.'}]}
manifest_data = (json.dumps(row) + '\\n').encode()
if manifest.exists():
    assert manifest.read_bytes() == manifest_data, 'Existing Reader manifest changed'
else:
    with manifest.open('xb') as handle: handle.write(manifest_data)
reader_env = env.copy()
reader_env['GEMINI_API_KEY'] = UserSecretsClient().get_secret('GEMINI_API_KEY')
# Keep the configured Reader default; an existing explicit environment override wins.
# This records the requested model ID, not a promise of endpoint availability.
reader_env.setdefault('GEMINI_MODEL', 'gemini-3.6-flash')
reader_env.update(GEMINI_REQUEST_INTERVAL_SECONDS='61', GEMINI_CALL_BUDGET_SECONDS='240')
print('Configured Reader model:', reader_env['GEMINI_MODEL'])
last_reader_finished_at = None

def run_reader_stage(name, manifest_path, *, page=None, timeout=3600):
    global last_reader_finished_at
    # Pacing in reader_policy is per process; preserve it across these CLI stages too.
    if last_reader_finished_at is not None:
        while time.monotonic() - last_reader_finished_at < 61:
            time.sleep(min(15, max(0, 61 - (time.monotonic() - last_reader_finished_at))))
    command = [python, '-u', '-m', 'research_rag.evaluation.reader_reliability',
               '--manifest', str(manifest_path), '--output-dir', str(out / name)]
    if page is not None: command.extend(['--page', str(page)])
    code = run(name, command, child_env=reader_env, timeout=timeout, required=False)
    last_reader_finished_at = time.monotonic()
    summary = out / name / 'summary.json'
    print(summary.read_text() if summary.exists() else 'Missing summary; inspect status/stderr.')
    bundle()
    return code

run_reader_stage('reader-page0', manifest, page=0, timeout=900)
print('Continue to Reader smoke only after reader-page0 completes with exit_code 0. Save Output now.')
'''.replace("__FIXTURE__", repr(fixture))

reader_smoke = '''assert statuses.get('reader-page0', {}).get('state') == 'completed', 'Resolve the saved page0 failure first'
run_reader_stage('reader-smoke', root / 'research_rag/evaluation/reader_smoke_manifest.jsonl', timeout=3600)
print('Continue to the real PDF only after smoke passes. Save Output now.')
'''
reader_real = '''assert statuses.get('reader-smoke', {}).get('state') == 'completed', 'Resolve the saved smoke failure first'
try:
    run_reader_stage('reader-real', root / 'research_rag/evaluation/reader_real_manifest.jsonl', timeout=5400)
finally:
    reader_env.pop('GEMINI_API_KEY', None)
    bundle()
print('Save Version WITH Output, verify the ZIP, then stop the GPU session.')
print('These are component diagnostics. Final E2E and independent human review remain separate gates.')
'''

cells = [{"cell_type": "markdown", "metadata": {}, "source":
    "# Confidence explanation + Reader reliability — 2026-10-10\n"
    "Private notebook. GPU T4, Internet, existing workspace + diagnostics v2 datasets. "
    "Enable the existing GEMINI_API_KEY Secret for cells 4–6; never paste its value. "
    "Run the SIX code cells in order, one at a time. 1 mount; 2 setup/tests; "
    "3 confidence explanation (142 predictions: two profiles × 47 original + 24 controlled label cases); "
    "4 exact E2E page0; 5 Reader smoke; 6 real 12-page PDF. "
    "The audited repair profile remains serving default; the new explanation profile is candidate-only. "
    "A deliberately wrong proposed label must not automatically get high confidence. "
    "Criteria are saved before inference, with version v2 for the new confidence experiment. "
    "Reader allows at most 3 transport attempts per logical API call, SDK retries disabled, "
    "240s logical-call budget including pacing and 30s per HTTP phase maximum; outer process timeouts still apply. "
    "The Reader model ID is printed in cell 4 and recorded per request; no automatic model switch. "
    "Cell completion is not a pass: read each gate. Save each completed stage with Output. "
    "Do not rerun a stage over its prior results; preserve the ZIP and start a fresh run.\n"}, *setup]
for body in (confidence, reader_setup, reader_smoke, reader_real):
    compile(body, "completion-notebook", "exec")
    cells.append({"cell_type": "code", "metadata": {}, "source": body, "execution_count": None, "outputs": []})
target = ROOT / "scripts/kaggle_completion_validation.ipynb"
target.write_text(json.dumps(dict(cells=cells, metadata=source["metadata"], nbformat=4, nbformat_minor=4),
                            ensure_ascii=False, indent=2), encoding="utf-8")
print(target)
print("Bytes:", target.stat().st_size, "SHA256:", hashlib.sha256(target.read_bytes()).hexdigest())
