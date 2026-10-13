# Reader: tiếp tục sau lỗi critique 503

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
import hashlib
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
```

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
probe_stage = ('reader-failed-page-retry-1' if 'reader-failed-page-retry-1' in statuses else 'reader-failed-page')
probe_status = statuses.get(probe_stage, {})
print('Full PDF prerequisite:', probe_stage, probe_status)
assert probe_status.get('state') == 'completed' and probe_status.get('exit_code') == 0, 'Resolve the selected page-4 stage first: ' + probe_stage
probe_summary = json.loads((out / probe_stage / 'summary.json').read_text())
assert probe_summary.get('automated_gate_pass') is True, 'The original Reader probe must pass before the full PDF'
run_reader_component('reader-real', timeout=5400)
bundle()
print('Review page_blocks.jsonl and extractions.jsonl against the PDF; pending review is not a pass.')
print('Save Version WITH Output, download the ZIP, then stop the GPU session.')
```

Lưu Output và tải ZIP được in ở cuối. Nếu cell B thất bại, giữ kết quả và dừng.
Đây là một lượt phục hồi có kiểm soát, không phải xác nhận dịch vụ Gemini đã ổn
định hoặc dự án đã nghiệm thu. Các lần thất bại trước vẫn thuộc báo cáo đánh giá.
