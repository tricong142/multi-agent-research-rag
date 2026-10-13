# Đồng bộ bản sửa runtime nhỏ (2026-09-26)

Gói `kaggle_transfer/runtime-update-20260926.zip` chỉ chứa các file sửa và dữ liệu dev đã loại trùng. Không có checkpoint, corpus, `.env` hoặc API key. Gói được kiểm SHA-256 từng file. Dataset workspace v2 vẫn giữ nguyên. **Đã upload Private và Add Input** tại [Research RAG Runtime Diagnostics](https://www.kaggle.com/datasets/trcng23/research-rag-runtime-diagnostics). Các cell CPU/GPU ngày 2026-09-26 đã kiểm đủ hash nguồn/đích và áp dụng 12 file thành công. Graph GPU có raw trace đã chạy; sau sửa định dạng evidence, một ca DistilBERT đạt luồng Retrieval → Summarizer → Fact-Checker → Writer có citation. Xem `KAGGLE_VALIDATION_STATUS.md` để phân biệt ca chạy này với các gate chất lượng còn thiếu.

**Hai sửa mới chưa nằm trong ZIP 12 file:** timeout/retry của `train_agent2_reader/reader_policy.py` và đối chiếu whitespace/ligature trong `research_rag/graph.py`. Bản graph đã thực thi nằm trong Output notebook `validated-runtime/research_rag/graph.py` và cell patch trong notebook. Khi dựng session mới phải áp dụng các sửa mới từ workspace local hoặc source Output đã kiểm chứng; không coi riêng overlay 12 file là phiên bản cuối. Không thay checkpoint/index hay ghi đè ZIP đã upload.

Dataset đã attach thì không upload lại. Khi session mới đã thiết lập `root` trỏ tới workspace v2 và `run_env`, chạy cell dưới bằng kernel notebook. Cell kiểm patch khớp đúng bản nguồn, sao chép workspace sang `/tmp` rồi áp dụng file mới; không ghi lên dataset read-only hoặc xóa workspace cũ. Bản sửa retry mới ở `train_agent2_reader/reader_policy.py` được tạo sau gói này và chưa nằm trong dataset; không suy ra đồng bộ 12 file đã bao gồm sửa đó.

```python
import hashlib, json, shutil
from pathlib import Path, PurePosixPath

manifests = list(Path('/kaggle/input').rglob('runtime-update-manifest.json'))
assert len(manifests) == 1, 'Attach exactly one runtime update dataset'
update_root = manifests[0].parent
manifest = json.loads(manifests[0].read_text())
for entry in manifest['files']:
    relative = PurePosixPath(entry['path'])
    assert not relative.is_absolute() and '..' not in relative.parts
    source = update_root / relative
    assert hashlib.sha256(source.read_bytes()).hexdigest() == entry['sha256']
    if entry['base_sha256'] is not None:
        assert hashlib.sha256((root / relative).read_bytes()).hexdigest() == entry['base_sha256'], entry['path']

runtime_root = Path('/tmp/research-rag-workspace-diagnostics')
assert not runtime_root.exists(), 'Use a fresh directory; do not overwrite a prior run'
assert shutil.disk_usage('/tmp').free > 10 * 2**30, 'Need space to copy the 7.57 GB workspace'
shutil.copytree(root, runtime_root)
for entry in manifest['files']:
    target = runtime_root / entry['path']
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(update_root / entry['path'], target)
root = runtime_root
run_env['PYTHONPATH'] = str(root)
print('Updated runtime files:', len(manifest['files']))
```

Sau đó chạy ca chẩn đoán trong `KAGGLE_GPU_RUNBOOK.md` bằng **process Python mới** từ `serving_python`, `cwd=root`, `env=run_env`. Process mới tránh giữ module cũ đã import trong kernel. Thu raw Summarizer, kiểm span, rồi mới xác nhận Fact-Checker và Writer được gọi thật. Giữ trace trong Output Private; metrics riêng không có nội dung.

Để thu confidence, dùng `04_factchecker/eval_factchecker.py --runtime-contract` với `research_rag/evaluation/scifact_dev_deduplicated.jsonl`. Đánh giá dev/calibration này không thay thế qrels/PDF giữ lại và không chứng minh end-to-end hoàn thiện.

Cuối session: **Save Version → Quick Save → Advanced Settings → Save output for this version → Save**. Đợi `Successful`, sau đó **More settings → Stop session**, xác nhận `Session stopped` hoặc `Draft Session off`. Quick Save mặc định có thể không lưu Output; phải kiểm tra lựa chọn này.
