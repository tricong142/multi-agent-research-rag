"""Build separate, hashed Reader and confidence backend diagnostics for manual Kaggle runs."""
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
source = json.loads((ROOT / "scripts/kaggle_autonomy_validation.ipynb").read_text(encoding="utf-8"))
setup = [cell for cell in source["cells"] if cell["cell_type"] == "code"][:2]


def save(name, title, instructions, bodies, *, mount_prefix=""):
    mount = {**setup[0], "source": mount_prefix + setup[0]["source"]}
    cells = [{"cell_type": "markdown", "metadata": {}, "source": "# " + title + "\n\n" + instructions}, mount, setup[1]]
    for body in bodies:
        compile(body, name, "exec")
        cells.append({"cell_type": "code", "metadata": {}, "source": body, "execution_count": None, "outputs": []})
    path = ROOT / "scripts" / name
    path.write_text(json.dumps({"cells": cells, "metadata": source["metadata"], "nbformat": 4,
                               "nbformat_minor": 4}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path.name, "code_cells:", len(setup) + len(bodies), "SHA256:", hashlib.sha256(path.read_bytes()).hexdigest())


confidence = '''diagnostic_env = env.copy()
diagnostic_env.pop('HF_HUB_OFFLINE', None)
diagnostic_env.pop('TRANSFORMERS_OFFLINE', None)
run('confidence-backends', [python, '-u', '-m', 'research_rag.evaluation.compare_confidence_backends',
    '--output-dir', str(out / 'confidence-backends'), '--online-model-downloads'],
    child_env=diagnostic_env, timeout=5400, required=False)
for filename in ('summary.json', 'metrics.json'):
    path = out / 'confidence-backends' / filename
    print(filename, path.read_text() if path.exists() else 'Incomplete: inspect saved status/stderr.')
bundle()
print('Keep serving repair. No prompt/backend promotion. Human review remains pending.')
print('Save Version WITH Output, download the ZIP, and stop the GPU session.')
'''
save("kaggle_confidence_backends.ipynb", "Confidence backend comparison — 2026-10-10",
     "Private notebook; T4 GPU and Internet; existing workspace + diagnostics v2 datasets. "
     "THREE code cells: 1 mount; 2 fresh setup/tests; 3 confidence-only 2 backends x 2 prompts x 24 cases. "
     "No Gemini key or API calls. Downloads pinned Qwen2.5-3B-Instruct weights if absent (about 6.2 GB), "
     "and loads only one model at a time. The audited merged checkpoint is not replaced. "
     "Criteria are saved before inference. Exit 1 means the required candidate gate failed; preserve the evidence. "
     "This is a development intervention, not calibration or final E2E. Do not overwrite a previous run.\n", [confidence])

probe_report = (ROOT / 'scripts/kaggle_gemini_probe.py').read_text(encoding='utf-8') + '''
import os
from pathlib import Path
from uuid import uuid4

gemini_availability = check_gemini_endpoint(os.environ.get('GEMINI_MODEL', 'gemini-3.6-flash'))
gemini_probe_finished_at = time.monotonic()
gemini_probe_path = Path('/kaggle/working') / ('gemini-availability-' + uuid4().hex + '.json')
with gemini_probe_path.open('x', encoding='utf-8') as handle:
    json.dump(gemini_availability, handle, indent=2)
print(json.dumps(gemini_availability, indent=2))
print('Saved:', gemini_probe_path)
'''

# This single cell runs before workspace setup and shares the Reader's exact probe.
access_check = probe_report + '''
print('PROBE_PASS: this request succeeded; full Reader quota is not confirmed.'
      if gemini_availability['endpoint_available'] is True else
      'PROBE_FAILED: stop here. Review error_message_redacted in the JSON above; do not run Reader cells 2-4.')
'''
compile(access_check, 'kaggle_gemini_access_check', 'exec')
access_notebook = {
    'cells': [
        {'cell_type': 'markdown', 'metadata': {}, 'source':
         '# Gemini access diagnostic — one cell\n\n'
         'Copy this code cell into the existing private Kaggle notebook with Internet and its GEMINI_API_KEY Secret enabled. '
         'No GPU, dataset mount, package install or Reader run. One metadata GET and at most one generation POST; no retries. '
         'Keep the JSON, including error_message_redacted. PROBE_FAILED is a failure even without an AssertionError. '
         'Credentials and common account identifiers are filtered; check the remaining text before sharing.\n'},
        {'cell_type': 'code', 'metadata': {}, 'source': access_check, 'execution_count': None, 'outputs': []}],
    'metadata': source['metadata'], 'nbformat': 4, 'nbformat_minor': 4}
access_path = ROOT / 'scripts/kaggle_gemini_access_check.ipynb'
access_path.write_text(json.dumps(access_notebook, ensure_ascii=False, indent=2), encoding='utf-8')
print(access_path.name, 'code_cells:', 1, 'SHA256:', hashlib.sha256(access_path.read_bytes()).hexdigest())

reader_probe = probe_report + '''
probe_last_request = (gemini_availability['requests'] or [{}])[-1]
assert gemini_availability['endpoint_available'] is True, (
    'Preflight failed: stage=' + gemini_availability.get('failure_stage', 'unknown')
    + '; HTTP=' + str(probe_last_request.get('http_status', 'not received'))
    + '; API=' + probe_last_request.get('api_status', 'not available')
    + '; reason=' + gemini_availability.get('failure_reason', gemini_availability.get('error_type', 'unknown'))
    + '. Preserve the JSON; do not run cells 2-4.')

'''

reader = '''from kaggle_secrets import UserSecretsClient
assert gemini_availability['endpoint_available'] is True, 'Run cell 1 successfully in this session first'
assert env.get('GEMINI_MODEL', 'gemini-3.6-flash') == gemini_availability['model'], 'Model changed after availability check'
with (out / 'gemini-availability.json').open('x', encoding='utf-8') as handle:
    json.dump(gemini_availability, handle, indent=2)
bundle()
assert shutil.which('tesseract'), 'Install the Tesseract binary before Reader diagnostics'
last_reader_finished_at = gemini_probe_finished_at

def run_reader_component(name, *, page=None, timeout=5400):
    global last_reader_finished_at
    reader_env = env.copy()
    reader_env.setdefault('GEMINI_MODEL', 'gemini-3.6-flash')
    reader_env.update(GEMINI_REQUEST_INTERVAL_SECONDS='61', GEMINI_CALL_BUDGET_SECONDS='240')
    reader_env['GEMINI_API_KEY'] = UserSecretsClient().get_secret('GEMINI_API_KEY')
    print('Configured Reader model:', reader_env['GEMINI_MODEL'])
    destination = out / name
    command = [python, '-u', '-m', 'research_rag.evaluation.reader_reliability',
               '--manifest', str(root / 'research_rag/evaluation/reader_real_manifest.jsonl'),
               '--output-dir', str(destination)]
    if page is not None: command.extend(['--page', str(page)])
    try:
        if last_reader_finished_at is not None:
            while time.monotonic() - last_reader_finished_at < 61:
                time.sleep(min(15, max(0, 61 - (time.monotonic() - last_reader_finished_at))))
        code = run(name, command, child_env=reader_env, timeout=timeout, required=False)
    finally:
        reader_env.pop('GEMINI_API_KEY', None)
        last_reader_finished_at = time.monotonic()
        bundle()
    summary = destination / 'summary.json'
    print(summary.read_text() if summary.exists() else 'Missing summary: inspect saved status/stderr.')
    if summary.exists():
        run(name + '-replay', [python, '-u', '-m', 'research_rag.evaluation.reader_reliability',
            '--replay-dir', str(destination), '--output-dir', str(out / (name + '-replay'))], timeout=300)
        print('Replay verified. The ORIGINAL Reader gate still determines pass/fail.')
    return code

run_reader_component('reader-failed-page', page=3, timeout=900)
print('page_no=3 is PDF page 4. If quota still fails, save the ZIP and resolve quota before continuing.')
'''
reader_full = '''probe_stage = ('reader-failed-page-retry-1' if 'reader-failed-page-retry-1' in statuses else 'reader-failed-page')
probe_status = statuses.get(probe_stage, {})
print('Full PDF prerequisite:', probe_stage, probe_status)
assert probe_status.get('state') == 'completed' and probe_status.get('exit_code') == 0, 'Resolve the selected page-4 stage first: ' + probe_stage
probe_summary = json.loads((out / probe_stage / 'summary.json').read_text())
assert probe_summary.get('automated_gate_pass') is True, 'The original Reader probe must pass before the full PDF'
run_reader_component('reader-real', timeout=5400)
bundle()
print('Review page_blocks.jsonl and extractions.jsonl against the PDF; pending review is not a pass.')
print('Save Version WITH Output, download the ZIP, then stop the GPU session.')
'''
save("kaggle_reader_diagnostics.ipynb", "Reader availability + text export — 2026-10-11",
     "Private notebook; existing workspace + diagnostics v2; GPU and Internet; enable the existing GEMINI_API_KEY Secret. "
     "FOUR code cells: 1 check Gemini (one metadata GET + one tiny generation, no retries) then mount; 2 fresh setup/tests; "
     "3 retry exactly the formerly failing page 4 (index 3); 4 the full real PDF, only after the probe passes. "
     "No confidence or smoke inference. Each Reader stage exports page blocks, exact scored chunks, safe quota metadata "
     "and runs a model-free offline replay. Failed PDFs remain failed even if earlier pages were extracted. "
     "Cell 1 saves a sanitized availability JSON even on failure; stop if it fails. A passing probe only confirms that request. "
     "Do not rerun a stage into existing results; preserve the ZIP and use a fresh run.\n", [reader, reader_full],
     mount_prefix=reader_probe)

reader_retry = '''import hashlib
import json
from pathlib import Path

assert all(name in globals() for name in ('out', 'statuses', 'python', 'root', 'env', 'run_reader_component')), (
    'Copy this cell into the EXISTING Reader notebook session. If that session ended, use Reader cells 1-3 in a fresh run.')
assert Path(python).is_file(), 'The installed runtime is missing; use Reader cells 1-3 in a fresh run.'
original_stage = 'reader-failed-page'
retry_stage = 'reader-failed-page-retry-1'
original_status = statuses.get(original_stage, {})
assert original_status.get('state') == 'failed' and original_status.get('exit_code') == 1, 'Expected a failed original page probe'
original_summary = json.loads((out / original_stage / 'summary.json').read_text())
original_criteria = json.loads((out / original_stage / 'criteria.json').read_text())
http_counts = original_summary.get('api', {}).get('http_status_counts', {})
assert original_summary.get('automated_gate_pass') is False, 'This cell is only for a failed probe'
assert set(http_counts) - {'not_available'} == {'503'} and http_counts.get('503', 0) > 0, 'This retry is only for HTTP 503; resolve other failures first'
assert original_criteria.get('selected_page') == 3, 'Expected page index 3'
assert original_criteria.get('configured_model') == env.get('GEMINI_MODEL', 'gemini-3.6-flash'), 'Model changed; use a fresh evaluation'
current_manifest = root / 'research_rag/evaluation/reader_real_manifest.jsonl'
assert hashlib.sha256(current_manifest.read_bytes()).hexdigest() == original_criteria['manifest_sha256'], 'Evaluation manifest changed'
assert retry_stage not in statuses and not (out / retry_stage).exists(), 'One manual retry already attempted; preserve both results and stop'
assert not any((out / (retry_stage + suffix)).exists() for suffix in ('.stdout.log', '.stderr.log')), 'Retry logs already exist; preserve them'
print('Retrying PDF page 4 once in a separate stage; original evidence remains failed:', out / original_stage)
run_reader_component(retry_stage, page=3, timeout=900)
retry_status = statuses.get(retry_stage, {})
retry_summary_path = out / retry_stage / 'summary.json'
retry_summary = json.loads(retry_summary_path.read_text()) if retry_summary_path.exists() else {}
retry_passed = (retry_status.get('state') == 'completed' and retry_status.get('exit_code') == 0
                and retry_summary.get('automated_gate_pass') is True)
print('READER_PROBE_PASS: check available quota before running the full-PDF cell.' if retry_passed else
      'READER_PROBE_FAILED: stop here; download the ZIP. Do not repeat or run the full PDF.')
print('ZIP:', out.with_suffix('.zip'))
'''
retry_cells = [{'cell_type': 'markdown', 'metadata': {}, 'source':
    '# Reader: one controlled retry after HTTP 503\n\n'
    'Copy these TWO cells, in order, below the cells in the EXISTING Reader notebook. '
    'Keep its GPU session, Internet, Secret and installed environment. Do not import this as a new session. '
    'Cell A retries only PDF page 4 under reader-failed-page-retry-1; original failed results are preserved. '
    'It allows one manual retry stage, using the existing API retry/deadline policy, model and criteria. '
    'If it fails again, save the ZIP and stop; do not rerun cells or rename stages. '
    'Cell B replaces the OLD cell 4 and checks the latest stage plus its original quality gate. '
    'Run B only after READER_PROBE_PASS and checking actual quota with headroom for the full PDF. '
    'No package reinstall or extra availability request. If the session was lost, run Reader cells 1-3 in a fresh run instead.\n'}]
for body in (reader_retry, reader_full):
    compile(body, 'kaggle_reader_retry_503', 'exec')
    retry_cells.append({'cell_type': 'code', 'metadata': {}, 'source': body, 'execution_count': None, 'outputs': []})
retry_path = ROOT / 'scripts/kaggle_reader_retry_503.ipynb'
retry_path.write_text(json.dumps({'cells': retry_cells, 'metadata': source['metadata'], 'nbformat': 4,
                                 'nbformat_minor': 4}, ensure_ascii=False, indent=2), encoding='utf-8')
print(retry_path.name, 'code_cells:', 2, 'SHA256:', hashlib.sha256(retry_path.read_bytes()).hexdigest())

retry_guide = '''# Reader: tiếp tục sau lỗi critique 503

## Điều kiện sử dụng

Dùng trong **notebook Reader cũ, cùng phiên Kaggle còn hoạt động**, đã chạy cell 1–3
và có `reader-failed-page` failed do HTTP 503. Giữ GPU, Internet và quyền Secret.
Hai cell dưới dùng lại môi trường đã cài; không cần chạy lại setup hoặc availability.

Nếu phiên cũ đã mất, hai cell này sẽ dừng trước khi gọi model. Khi đó dùng
`scripts/kaggle_reader_diagnostics.ipynb` để chạy cell 1–3 trong run mới.

## Cell A — thử lại trang 4 đúng một lần

Thêm một code cell dưới các cell hiện có, sao chép khối dưới và chạy. Stage mới
là `reader-failed-page-retry-1`. Model, prompt, tiêu chí và retry policy giữ nguyên.
Lần chạy lỗi trước vẫn được lưu và vẫn được tính là thất bại.

```python
''' + reader_retry + '''```

- `READER_PROBE_PASS`: trang thử đạt gate tự động; vẫn cần review bằng người.
- `READER_PROBE_FAILED` hoặc exception: dừng; tải ZIP được in ra. Không bấm lại,
  không đổi tên stage để tạo vòng retry mới, không chạy cell B.
- Script chạy lại trang 4 gồm router/extraction/critique. ZIP cũ không lưu candidate
  blocks chưa được critique chấp nhận nên chưa thể chạy lại riêng critique từ ZIP đó.

## Cell B — đọc toàn PDF sau khi trang thử đạt

Kiểm tra quota thực tế còn đủ nhu cầu và dự phòng trước khi chạy B. Lượt audit
trước ước tính đường chạy thuận lợi cho PDF này cần ít nhất 17 lần sinh nội dung;
retry/fallback có thể cần thêm. Probe đạt không xác nhận quota cho toàn PDF.

Thêm code cell tiếp theo với nội dung dưới. **Dùng cell B này thay cell 4 cũ**:
cell 4 cũ chỉ nhìn stage ban đầu nên sẽ tiếp tục chặn dù retry đã đạt.

```python
''' + reader_full + '''```

Lưu Output và tải ZIP được in ở cuối. Nếu cell B thất bại, giữ kết quả và dừng.
Đây là một lượt phục hồi có kiểm soát, không phải xác nhận dịch vụ Gemini đã ổn
định hoặc dự án đã nghiệm thu. Các lần thất bại trước vẫn thuộc báo cáo đánh giá.
'''
(ROOT / 'docs/READER_RETRY_503.md').write_text(retry_guide, encoding='utf-8')
