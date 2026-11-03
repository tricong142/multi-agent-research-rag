"""Port the immutable Colab notebook I/O to Kaggle without changing its payload."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'scripts/colab_atomic_verifier_cellfix17.ipynb'
TARGET = ROOT / 'scripts/kaggle_atomic_verifier_cellfix17.ipynb'

HELPERS = '''
def show_file(filename):
    path = Path(filename).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    path.relative_to(Path('/kaggle/working').resolve())
    print('Saved output:', path, flush=True)
    display(FileLink(os.path.relpath(path, Path.cwd())))

def read_review(filename):
    if not filename or not str(filename).strip():
        raise ValueError('Attach the human JSON as a private Kaggle input, then set the review path in this cell.')
    path = Path(filename)
    if not path.is_absolute() or not path.is_file():
        raise ValueError('Review path must be an existing absolute Kaggle path: '+str(path))
    raw = path.read_bytes()
    if not isinstance(json.loads(raw), dict):
        raise ValueError('Review must be a JSON object. The frozen human gate checks its content and hashes.')
    return {path.name: raw}

'''

INTRO = '# Cellfix17 — Kaggle, development30-v1\n\nCandidate mới sửa coverage enum rỗng do loại dấu câu khỏi member hợp lệ.\nChưa có inference GPU hoặc kết quả 30/30 cho Cellfix17. Bộ30-v1 đã dùng để sửa,\nchỉ được ghi là development. Cần holdout khác paper để đo độc lập.\nImport notebook private, bật GPU T4 và Internet. Chạy cells1–5, trực tiếp review\nprobe mới trước cell6, rồi review full39 mới trước cell7. Đặt PROBE_REVIEW_PATH\nvà FULL39_REVIEW_PATH bằng đường dẫn JSON review thực tế của run mới trên Kaggle.\nCells6/7 mặc định tắt. Không sửa hash, tự ký human review hoặc bỏ ca lỗi.\nLưu ZIP trong /kaggle/working trước khi dừng runtime. Không chạy lại cell1 để resume.\n'


def replace_once(code, before, after):
    if code.count(before) != 1:
        raise ValueError('Upstream notebook changed at: ' + before[:100])
    return code.replace(before, after, 1)


def build():
    catalog=ROOT/'docs/atomic-verifier-cellfix17-release.json'
    if not catalog.exists():catalog=ROOT/'research-runs/cellfix17-notebook-draft.json'
    release=json.loads(catalog.read_bytes())
    source_bytes = SOURCE.read_bytes()
    assert hashlib.sha256(source_bytes).hexdigest() == release['files'][SOURCE.relative_to(ROOT).as_posix()]
    book = json.loads(source_bytes)
    codes = [cell for cell in book['cells'] if cell['cell_type'] == 'code']
    assert len(codes) == 7
    for cell in codes:
        cell['source'] = ''.join(cell['source'])
        cell['execution_count'], cell['outputs'] = None, []
    code = codes[0]['source']
    code = replace_once(code, 'from google.colab import files', 'from IPython.display import display, FileLink')
    code = replace_once(code, "run_root = Path('/content')/('atomic-cellfix17-fresh-'+run_id)",
                        "run_root = Path('/tmp')/('atomic-cellfix17-kaggle-'+run_id)")
    code = replace_once(code, "out = run_root/('output-cellfix17-fresh-'+run_id)",
                        "out = Path('/kaggle/working')/('output-cellfix17-kaggle-'+run_id)")
    code = replace_once(code, 'env = os.environ.copy()', "env = os.environ.copy()\nenv['CUDA_VISIBLE_DEVICES'] = '0'")
    code = replace_once(code, 'def download_archive():', HELPERS + '\ndef download_archive():')
    code = replace_once(code, "'startup':'fresh embedded inputs; no previous session required',",
                        "'startup':'Kaggle fresh embedded inputs; no previous session required',\n        'platform':'kaggle',")
    codes[0]['source'] = code
    codes[5]['source'] = 'PROBE_REVIEW_PATH = ""  # Absolute path to the new probe human review JSON.\n' + codes[5]['source'].replace(
        '# Replace ONLY cell 6 in the existing cellfix17 Colab runtime.', '# Kaggle: review the current probe before enabling full39.').replace(
        'files.upload()', 'read_review(PROBE_REVIEW_PATH)')
    codes[6]['source'] = 'FULL39_REVIEW_PATH = ""  # Absolute path to the new full39 human review JSON.\n' + codes[6]['source'].replace(
        'files.upload()', 'read_review(FULL39_REVIEW_PATH)')
    for index, cell in enumerate(codes, 1):
        cell['source'] = cell['source'].replace('files.download(', 'show_file(')
        assert 'google.colab' not in cell['source'] and 'files.upload(' not in cell['source']
        compile(cell['source'], 'kaggle-cell-' + str(index), 'exec')
    book['cells'][0]['source'] = INTRO
    book['metadata'].pop('colab', None)
    book['metadata']['kernelspec'] = {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'}
    book['metadata']['kaggle'] = {'isGpuEnabled': True, 'isInternetEnabled': True, 'language': 'python', 'sourceType': 'notebook'}
    book['metadata']['cellfix17_port'] = {'source_notebook_sha256': hashlib.sha256(source_bytes).hexdigest(),
                                         'payload_sha256': release['payload_sha256'], 'gpu_inference_tested': False}
    TARGET.write_text(json.dumps(book, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    assert SOURCE.read_bytes() == source_bytes
    print(TARGET)


if __name__ == '__main__':
    build()
