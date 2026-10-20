"""Package frozen v7 plus a verified passed probe; human admission stays mandatory."""
import ast
import base64
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RUN = '20261016T024708Z-a57ee72a'
PROBE_ZIP = ROOT / 'research-runs/colab-atomic-v7' / RUN / 'original-output.zip'
PROBE_SHA = '9501567f9efe425c9d8ed61a416f58a92ccac75bc44afef7c04e71b1eead590f'
TARGET = ROOT / 'scripts/colab_atomic_verifier39_v7.ipynb'
REVIEW = ROOT / 'docs' / ('semantic-review-v7-' + RUN + '.json')


def build():
    sys.path.insert(0, str(ROOT))
    from research_rag.evaluation import evaluate_atomic_verifier as d
    criteria, *_ = d.load_frozen(d.CRITERIA)
    assert criteria['version'] == 'atomic-verifier-constrained-v7-20261016'
    record = json.loads((ROOT / 'docs' / ('atomic-verifier-v7-human-admission-' + RUN + '.json')).read_text(encoding='utf-8'))
    assert record['human_review_completed'] is True and record['admission_verified'] is True
    admission_record = d.require_probe_review(Path(record['reviewed_probe_directory']))
    human_data = REVIEW.read_bytes()
    assert hashlib.sha256(human_data).hexdigest() == admission_record['semantic_review_sha256']
    release = json.loads((ROOT / 'docs/atomic-verifier-v7-colab-release.json').read_text())
    source = ROOT / 'scripts/colab_decomposition_probe_v7.ipynb'
    assert hashlib.sha256(source.read_bytes()).hexdigest() == release['files'][source.relative_to(ROOT).as_posix()]
    raw_probe = PROBE_ZIP.read_bytes()
    assert hashlib.sha256(raw_probe).hexdigest() == PROBE_SHA
    with zipfile.ZipFile(PROBE_ZIP) as archive:
        assert archive.testzip() is None
        summary = json.loads(archive.read('decomposition-probe/summary.json'))
        assert summary['automated_gate_pass'] is True and summary['prediction_count'] == 18
        assert archive.read('decomposition-probe/criteria.json') == d.CRITERIA.read_bytes()
    original = json.loads(source.read_text(encoding='utf-8'))
    code = [cell['source'] for cell in original['cells'] if cell['cell_type'] == 'code']
    assert len(code) == 4
    unpack = code[0].replace("('atomic-v7-' + run_id)", "('atomic-v7-full39-' + run_id)")
    assert unpack != code[0]
    unpack += '\nimport shutil\n'
    unpack += 'probe_zip_b64 = ' + repr(base64.b64encode(raw_probe).decode()) + '\n'
    unpack += 'probe_zip_sha256 = ' + repr(PROBE_SHA) + '\n'
    unpack += '''probe_data = base64.b64decode(probe_zip_b64, validate=True)
assert hashlib.sha256(probe_data).hexdigest() == probe_zip_sha256
(out / 'probe-original.zip').write_bytes(probe_data)
probe_original = run_root / 'probe-original'
probe_original.mkdir(exist_ok=False)
with zipfile.ZipFile(io.BytesIO(probe_data)) as archive:
    assert archive.testzip() is None
    records = json.loads(archive.read('output-manifest.json'))['files']
    assert len(records) == len({item['path'] for item in records})
    assert set(archive.namelist()) == {item['path'] for item in records} | {'output-manifest.json'}
    for item in records:
        name = item['path']
        relative = PurePosixPath(name)
        assert not relative.is_absolute() and '..' not in relative.parts and '\\\\' not in name and ':' not in name
        raw = archive.read(name)
        assert len(raw) == item['size'] and hashlib.sha256(raw).hexdigest() == item['sha256']
        target = probe_original / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
reviewed_probe = out / 'reviewed-probe'
shutil.copytree(probe_original / 'decomposition-probe', reviewed_probe)
bundle()
print('Original probe preserved; reviewed copy starts with the original pending human form.')
'''
    admission = code[2] + '\nreview_b64 = ' + repr(base64.b64encode(human_data).decode()) + '\n'
    admission += 'review_sha256 = ' + repr(admission_record['semantic_review_sha256']) + '\n'
    admission += '''review_data = base64.b64decode(review_b64, validate=True)
assert hashlib.sha256(review_data).hexdigest() == review_sha256
review = json.loads(review_data)
assert isinstance(review, dict), 'Human review must be a JSON object'
(reviewed_probe / 'semantic-review.json').write_bytes(review_data)
admission_code = "import json; from pathlib import Path; from research_rag.evaluation.evaluate_atomic_verifier import require_probe_review; print(json.dumps(require_probe_review(Path(" + repr(str(reviewed_probe)) + "))))"
run('probe-admission', [python, '-c', admission_code], timeout=120)
print('Admission passed for this exact probe, criteria, human reviewer and review hash. No model has been loaded yet.')
'''
    run39 = '''assert all(statuses.get(name, {}).get('exit_code') == 0 for name in ('regression', 'cuda-preflight', 'probe-validate-only', 'verifier-validate-only', 'probe-admission')), 'Finish validation and human admission first'
code = run('verifier39', [python, '-u', '-m', 'research_rag.evaluation.evaluate_atomic_verifier', '--output-dir', str(out / 'verifier39'), '--probe-dir', str(reviewed_probe), '--online-model-downloads'], timeout=5520, required=False)
for filename in ('summary.json', 'metrics.json'):
    path = out / 'verifier39' / filename
    print(filename, path.read_text() if path.exists() else 'Incomplete; inspect saved logs.')
bundle()
print('Download:', out.with_suffix('.zip'))
print('Preserve all output, including failures, and stop GPU after download. Evidence review is still required.')
from google.colab import files
files.download(str(out.with_suffix('.zip')))
'''
    intro = '''# Atomic verifier v7 — 39 development cases after human admission

Use a fresh Colab T4 runtime. Four code cells: unpack verified v7 and original
passed probe; install pinned runtime; run 101 regression tests and both
validate-only modes, then verify the human-confirmed semantic-review JSON; finally
run39 only after admission succeeds. No new probe inference is needed.

Embedded probe run: ''' + RUN + '''. Original ZIP/predictions remain unchanged.
The embedded review replaces only the review file in a separate reviewed copy.
Human reviewer tricong explicitly confirmed all18/fivecriteria in chat after
reading the review form, including metric caveats010/014/018. This completed
review is bound to the exact prediction/criteria hashes and rechecked before
model loading. Missing/tampered/failed review stops; no skip flag is provided.

Same model/revision/NF4/dtype/seed/data and frozen budgets: max8 calls/case,
two attempts, 1536 tokens/call, 180 seconds/case, 312 calls and479232 generated
tokens overall. Hard worker deadline5400 seconds, notebook watchdog5520.
Passing requires39/39 labels, zero false support and runtime failures, and
review of evidence/coverage/numeric bindings/missing information for every case.
These inspected development cases do not establish held-out generalization.
Preserve output from failed runs. Do not rerun completed cells in the same run.
'''
    cells = [{'cell_type': 'markdown', 'metadata': {}, 'source': intro}]
    for index, text in enumerate((unpack, code[1], admission, run39), 1):
        compile(text, 'colab-full39-cell-' + str(index), 'exec')
        cells.append({'cell_type': 'code', 'metadata': {}, 'source': text,
                      'execution_count': None, 'outputs': []})
    notebook = {**original, 'cells': cells}
    notebook['metadata'] = {**original['metadata'], 'colab': {'name': TARGET.name}}
    TARGET.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    record = {'version': criteria['version'], 'purpose': 'Full39 notebook; human admission required before model loading',
              'criteria_sha256': hashlib.sha256(d.CRITERIA.read_bytes()).hexdigest(),
              'embedded_probe_run': RUN, 'embedded_original_probe_zip_sha256': PROBE_SHA,
              'files': {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in (TARGET, Path(__file__), source, REVIEW)},
              'human_review_embedded': True, 'human_review': admission_record,
              'verifier39_inference_completed': False}
    (ROOT / 'docs/atomic-verifier-v7-full39-colab-release.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({'notebook': str(TARGET), 'bytes': TARGET.stat().st_size, **record}))
    return TARGET


if __name__ == '__main__':
    build()
