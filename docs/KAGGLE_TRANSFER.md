# Chuyển research RAG lên Kaggle — Bước 0

Lệnh `build` bên dưới tạo gói `kaggle_transfer/research-rag-kaggle-v3.zip` chứa các thư mục runtime ở gốc workspace,
checkpoint của các agent và bốn artifact corpus/index. Không chứa `.venv`, `.git`,
`.env`, `_archive` hoặc cache Python. File `transfer-manifest.json` bên trong ZIP
ghi kích thước và SHA-256 của từng file.

## Tại máy này

```powershell
.venv\Scripts\python.exe -B scripts\transfer_kaggle.py build
.venv\Scripts\python.exe -B scripts\transfer_kaggle.py verify-zip --archive kaggle_transfer\research-rag-kaggle-v3.zip --full
```

Giữ dataset ở chế độ **Private**. Quyền phân phối corpus và index dẫn xuất
vẫn **chưa xác minh**: nguồn `jamescalam/ai-arxiv-chunked` hiện không công bố
license trên trang dataset. Không đổi sang Public. Vào Kaggle → Datasets → New Dataset, upload
`kaggle_transfer/research-rag-kaggle-v3.zip`, chọn tên/slug do bạn sở hữu rồi tạo
dataset. Notebook có thể thấy các file đã giải nén hoặc chỉ thấy ZIP; xem
[runbook GPU](KAGGLE_GPU_RUNBOOK.md) để xử lý cả hai. Không đưa ZIP vào Git.

## Trong Kaggle Notebook

Thêm dataset vừa tạo bằng **Add Input**. Trong cell đầu tiên:

```python
from pathlib import Path
import os
import sys

matches = list(Path("/kaggle/input").rglob("transfer-manifest.json"))
assert len(matches) == 1, f"Chọn đúng dataset chứa manifest: {matches}"
root = matches[0].parent.resolve()
assert (root / "research_rag/local.py").is_file()
assert (root / "transfer-manifest.json").is_file()
os.chdir(root)
sys.path.insert(0, str(root))
```

Kiểm tra toàn bộ file. Lần đầu nên dùng `--full` (đọc cả các checkpoint lớn):

```python
import subprocess
script = root / "scripts/transfer_kaggle.py"
if not script.is_file():  # gói v2 đã tạo trước khi sắp xếp lại workspace
    script = root / "transfer_kaggle.py"
subprocess.run([sys.executable, str(script), "verify-dir", "--root", str(root), "--full"], check=True)
```

Sau đó kiểm tra layout runtime:

```python
from research_rag.local import ROOT
print(ROOT)
assert ROOT == root
```

Nếu notebook có nhiều dataset chứa `transfer-manifest.json`, chọn đúng manifest
của gói này trong danh sách `matches` rồi đặt `root = matches[i].parent.resolve()`.
`/kaggle/input` là vùng chỉ đọc; mọi output như metrics/model cache phải ghi
vào `/kaggle/working`. Bước này chỉ chuyển và kiểm tra artifact, chưa chạy
inference hoặc tải base model.
