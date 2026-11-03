"""Offline packaging and review-input checks; no GPU inference or human signature."""
import ast
import base64
import hashlib
import io
import json
from pathlib import Path
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def assignments(code):
    return {n.targets[0].id: ast.literal_eval(n.value) for n in ast.parse(code).body
            if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
            and n.targets[0].id in ('payload', 'payload_sha256', 'manifest', 'criteria_sha256',
                                     'RUN_FULL39', 'RUN_VALIDATION30')}


def main():
    source = ROOT / 'scripts/colab_atomic_verifier_cellfix15.ipynb'
    target = ROOT / 'scripts/kaggle_atomic_verifier_cellfix15.ipynb'
    colab = [''.join(c['source']) for c in json.loads(source.read_bytes())['cells'] if c['cell_type'] == 'code']
    book = json.loads(target.read_bytes())
    cells = [c for c in book['cells'] if c['cell_type'] == 'code']
    codes = [''.join(c['source']) for c in cells]
    assert len(codes) == 7 and all(c['outputs'] == [] and c['execution_count'] is None for c in cells)
    for code in codes:
        compile(code, 'kaggle-packaging-check', 'exec')
        assert 'google.colab' not in code and 'files.upload(' not in code and 'files.download(' not in code
    assert assignments(codes[0]) == assignments(colab[0])
    inputs = assignments(codes[0])
    blob = base64.b64decode(inputs['payload'], validate=True)
    assert hashlib.sha256(blob).hexdigest() == inputs['payload_sha256']
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        assert z.testzip() is None and set(z.namelist()) == set(inputs['manifest'])
        for name, item in inputs['manifest'].items():
            raw = z.read(name)
            assert len(raw) == item['size'] and hashlib.sha256(raw).hexdigest() == item['sha256']
    assert codes[1:4] == colab[1:4]
    assert codes[4].replace('show_file(', 'files.download(') == colab[4]
    reverse6 = codes[5].split('\n', 1)[1].replace(
        '# Kaggle: review the current probe before enabling full39.', '# Replace ONLY cell 6 in the existing cellfix15 Colab runtime.').replace(
        'read_review(PROBE_REVIEW_PATH)', 'files.upload()').replace('show_file(', 'files.download(')
    reverse7 = codes[6].split('\n', 1)[1].replace('read_review(FULL39_REVIEW_PATH)', 'files.upload()').replace('show_file(', 'files.download(')
    assert reverse6 == colab[5] and reverse7 == colab[6]
    assert assignments(codes[5])['RUN_FULL39'] is False
    assert assignments(codes[6])['RUN_VALIDATION30'] is False
    function = next(n for n in ast.parse(codes[0]).body if isinstance(n, ast.FunctionDef) and n.name == 'read_review')
    namespace = {'Path': Path, 'json': json}
    exec(compile(ast.Module(body=[function], type_ignores=[]), 'kaggle-review-input', 'exec'), namespace)
    read_review = namespace['read_review']
    with tempfile.TemporaryDirectory(prefix='kaggle-review-check-', dir=str(ROOT / 'research-runs')) as temp:
        path = Path(temp) / 'human review.json'
        path.write_bytes(b'{"reviewer_kind":"assistant"}')
        assert read_review(str(path)) == {path.name: path.read_bytes()}
        # The adapter does not upgrade metadata or authorize the record; the frozen gate remains unchanged.
        for invalid in ('', 'relative.json', str(Path(temp) / 'absent.json')):
            try:
                read_review(invalid)
            except ValueError:
                pass
            else:
                raise AssertionError('Invalid review path accepted')
        path.write_text('[]', encoding='utf-8')
        try:
            read_review(str(path))
        except ValueError:
            pass
        else:
            raise AssertionError('Non-object review accepted')
    catalog=ROOT/'docs/atomic-verifier-cellfix15-release.json'
    if not catalog.exists():catalog=ROOT/'research-runs/cellfix15-notebook-draft.json'
    release=json.loads(catalog.read_bytes())
    for name, expected in release['files'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    report = {'notebook': str(target), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
              'code_cells_compile': 7, 'payload_inputs_match_colab': len(inputs['manifest']),
              'payload_sha256': inputs['payload_sha256'], 'criteria_sha256': inputs['criteria_sha256'],
              'runtime_and_evaluation_cells_unchanged_except_io': True, 'invalid_review_inputs_rejected': 4,
              'human_review_metadata_not_modified_by_adapter': True, 'full39_and_validation_default_disabled': True,
              'original_release_files_unchanged': len(release['files']), 'gpu_inference_tested': False,
              'kaggle_browser_download_tested': False}
    (ROOT / 'docs/atomic-verifier-cellfix15-kaggle-validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
