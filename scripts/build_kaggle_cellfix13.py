"""Port the immutable Colab notebook I/O to Kaggle without changing its payload."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'scripts/colab_atomic_verifier_cellfix13.ipynb'
TARGET = ROOT / 'scripts/kaggle_atomic_verifier_cellfix13.ipynb'

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

INTRO = '''# Cellfix13 — Kaggle, payload giữ nguyên từ bản Colab

Đây là bản chuyển môi trường, **không phải candidate sửa lỗi mới**. Cellfix13 đã
trượt Validation30 ở run Colab `20261027T151114Z-20ea1926`: 10/30 nhãn đúng,
false support=0, bốn runtime failures. Không dùng bản chuyển này để coi candidate
đã đạt hoặc chạy lặp Validation30 mong đổi kết quả. Giữ ZIP thất bại để audit.

- Import notebook này vào một notebook Kaggle riêng tư. Chọn GPU T4 và bật
  Internet để cài các dependency và tải đúng revision model. Notebook kiểm CUDA
  ở cell 3; chưa có kiểm chứng inference trên Kaggle cho bản chuyển này.
- Payload, source, prompts, criteria, model/revision, dependencies, budget và
  human gates giữ nguyên bytes của bản Colab đã đóng băng. Chỉ đổi đường dẫn,
  cách nhận review và cách tải output; chỉ dùng GPU 0 nếu runtime có nhiều GPU.
- Chạy **từng cell**, cells 1–5 là run mới: setup → regression/validate-only →
  smoke → probe. Không tự phục hồi kết quả Colab. Review của run cũ không mở gate
  cho predictions mới; không sửa hash trong review.
- Tải form HTML qua link output, trực tiếp review trên máy và xuất JSON. Đưa
  JSON vào một Kaggle input riêng tư, copy đường dẫn đầy đủ của file rồi đặt
  `PROBE_REVIEW_PATH` ở cell 6 hoặc `FULL39_REVIEW_PATH` ở cell 7. Có thể đặt
  đường dẫn file đã có trong `/kaggle/working`. Không tự tìm hoặc chọn review cũ.
- Cells 6/7 mặc định tắt. Chỉ bật sau khi automated gate và human review tương
  ứng thực sự đạt. Nếu bộ30 đã được dùng sửa/tune, coi nó là development và dùng
  một holdout mới để đo generalization.
- ZIP và forms được lưu trong `/kaggle/working`, có link tải sau mỗi stage.
  Workspace, venv và model cache ở `/tmp`, không đưa weights vào ZIP. Tải ZIP
  trước khi dừng session; không chạy lại cell 1 để tiếp tục một run đang có.

Thiết lập GPU/Internet của Kaggle được mô tả trong
[tài liệu chính thức](https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels_metadata.md).
'''


def replace_once(code, before, after):
    if code.count(before) != 1:
        raise ValueError('Upstream notebook changed at: ' + before[:100])
    return code.replace(before, after, 1)


def build():
    release = json.loads((ROOT / 'docs/atomic-verifier-cellfix13-release.json').read_bytes())
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
    code = replace_once(code, "run_root = Path('/content')/('atomic-cellfix13-fresh-'+run_id)",
                        "run_root = Path('/tmp')/('atomic-cellfix13-kaggle-'+run_id)")
    code = replace_once(code, "out = run_root/('output-cellfix13-fresh-'+run_id)",
                        "out = Path('/kaggle/working')/('output-cellfix13-kaggle-'+run_id)")
    code = replace_once(code, 'env = os.environ.copy()', "env = os.environ.copy()\nenv['CUDA_VISIBLE_DEVICES'] = '0'")
    code = replace_once(code, 'def download_archive():', HELPERS + '\ndef download_archive():')
    code = replace_once(code, "'startup':'fresh embedded inputs; no previous session required',",
                        "'startup':'Kaggle fresh embedded inputs; no previous session required',\n        'platform':'kaggle',")
    codes[0]['source'] = code
    codes[5]['source'] = 'PROBE_REVIEW_PATH = ""  # Absolute path to the new probe human review JSON.\n' + codes[5]['source'].replace(
        '# Replace ONLY cell 6 in the existing cellfix13 Colab runtime.', '# Kaggle: review the current probe before enabling full39.').replace(
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
    book['metadata']['cellfix13_port'] = {'source_notebook_sha256': hashlib.sha256(source_bytes).hexdigest(),
                                         'payload_sha256': release['payload_sha256'], 'gpu_inference_tested': False}
    TARGET.write_text(json.dumps(book, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    assert SOURCE.read_bytes() == source_bytes
    print(TARGET)


if __name__ == '__main__':
    build()
