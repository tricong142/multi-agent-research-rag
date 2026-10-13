"""Kaggle cell: test the existing private PDF fixtures without loading the LLMs.

Select CPU, enable GEMINI_API_KEY, and attach the workspace/fixture datasets.
Requires PyMuPDF, pytesseract, google-genai and the Tesseract executable.
This cell has been syntax-checked locally; the full API test has not run yet.
"""

import os
import subprocess
import sys
from pathlib import Path

from kaggle_secrets import UserSecretsClient

workspace_manifests = list(Path('/kaggle/input').rglob('transfer-manifest.json'))
fixture_manifests = list(Path('/kaggle/input').rglob('evaluation-transfer-manifest.json'))
assert len(workspace_manifests) == len(fixture_manifests) == 1
root = workspace_manifests[0].parent
fixture_root = fixture_manifests[0].parent / 'research_rag/evaluation'
assert (fixture_root / 'reader_smoke.py').is_file()
output = Path('/kaggle/working/reader-api-result.json')
assert not output.exists(), 'Preserve the previous result before starting a new run'

reader_env = os.environ.copy()
reader_env['PYTHONPATH'] = str(root)
reader_env['GEMINI_API_KEY'] = UserSecretsClient().get_secret('GEMINI_API_KEY')
reader_env['GEMINI_MODEL'] = 'gemini-3.6-flash'
reader_env['READER_MANIFEST'] = str(fixture_root / 'reader_smoke_manifest.jsonl')

reader_code = r'''
import importlib.metadata as md
import json, os, runpy, time
from pathlib import Path

pages = []
started = time.perf_counter()
result = {'passed': False, 'model': os.environ['GEMINI_MODEL']}
try:
    from train_agent2_reader.reader_agent import ReaderAgent
    from research_rag.adapters import PdfReader

    manifest = Path(os.environ['READER_MANIFEST'])
    # The workspace v2 has no research_rag.evaluation package.
    score = runpy.run_path(str(manifest.parent / 'reader_smoke.py'))['score']

    class ObservedReader(ReaderAgent):
        def process_page(self, pdf_path, page_no=0):
            page_started = time.perf_counter()
            event = {'pdf': Path(pdf_path).name, 'page_no': page_no}
            try:
                page = super().process_page(pdf_path, page_no)
                event.update(success=page['success'], final_tool=page['final_tool'],
                             attempts=page['attempts'], block_count=len(page['blocks']))
                return page
            except Exception as exc:
                event.update(success=False, error_type=type(exc).__name__,
                             http_code=getattr(exc, 'code', None))
                raise
            finally:
                event['latency_ms'] = round((time.perf_counter()-page_started)*1000, 2)
                pages.append(event)
                Path('/kaggle/working/reader-api-pages.json').write_text(json.dumps(pages, indent=2))

    model_dir = Path.cwd() / 'train_agent2_reader/layoutlmv3_doclaynet_model'
    agent = ObservedReader(layoutlmv3_model_dir=str(model_dir))
    result.update(score(manifest, PdfReader(agent=agent)))
    result['passed'] = not result['failures'] and result['exact_span_rate'] == 1.0
    result['google_genai'] = md.version('google-genai')
    result['scorer_note'] = 'Existing fixture scorer uses substring matching; rerun with the updated scorer before final acceptance.'
except Exception as exc:
    result.update(error_type=type(exc).__name__, http_code=getattr(exc, 'code', None))
result.update(total_ms=round((time.perf_counter()-started)*1000, 2), pages=pages)
Path('/kaggle/working/reader-api-result.json').write_text(json.dumps(result, indent=2))
raise SystemExit(0 if result['passed'] else 1)
'''

try:
    completed = subprocess.run(
        [sys.executable, '-u', '-c', reader_code], cwd=root, env=reader_env,
        capture_output=True, text=True, timeout=240,
    )
    print({'process_exit_code': completed.returncode})
    if output.is_file():
        print(output.read_text())
    else:
        print({'result_written': False, 'stderr_present': bool(completed.stderr)})
except subprocess.TimeoutExpired:
    print({'reader_timeout_seconds': 240, 'passed': False})
finally:
    reader_env.pop('GEMINI_API_KEY', None)
