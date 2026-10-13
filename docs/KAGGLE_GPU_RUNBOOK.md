# Chạy research RAG trên Kaggle GPU

Tài liệu này là checklist thực thi. Các số đo GPU, recall và chất lượng PDF chỉ được ghi sau khi chạy trên notebook thật. Dataset và notebook phải để **Private**. `THIRD_PARTY_NOTICES.md` ghi rõ corpus arXiv chưa có bằng chứng cấp quyền phân phối; không đổi dataset sang Public.

## 1. Nhận đúng workspace

Workspace hiện dùng gói `kaggle_transfer/research-rag-kaggle-v2.zip` đã upload vào dataset Private `trcng23/research-rag-five-agents-workspace`. Gắn thêm dataset Private `trcng23/research-rag-runtime-diagnostics` và áp dụng [overlay đã kiểm hash](KAGGLE_RUNTIME_UPDATE.md) để nhận code mới. Không có gói v3 hoàn chỉnh trong thư mục transfer tại thời điểm cập nhật này. Gói v2 có script chuyển ở thư mục gốc; Kaggle giải nén ZIP và giữ cây thư mục. Chạy cell sau trong notebook:

```python
from pathlib import Path
import os, sys, subprocess, shutil

matches = list(Path('/kaggle/input').rglob('transfer-manifest.json'))
assert len(matches) == 1, f'Expected one transfer manifest, found {len(matches)}: {matches}'
root = matches[0].parent.resolve()
os.chdir(root)
sys.path.insert(0, str(root))
required = ['research_rag', 'train_agent1_retrieval', 'train_agent2_reader',
            'train_agent3_summarizer', '04_factchecker', '05_writer',
            'kb_indexing', 'requirements-orchestrator.txt']
assert all((root / item).exists() for item in required)
script = root / 'scripts/transfer_kaggle.py'
if not script.is_file():
    script = root / 'transfer_kaggle.py'
subprocess.run([sys.executable, str(script), 'verify-dir',
                '--root', str(root), '--full'], check=True)
print('Workspace:', root)
print('Working disk GiB:', round(shutil.disk_usage('/kaggle/working').free / 2**30, 2))
```

Nếu không tìm thấy manifest, kiểm tra dataset đã upload xong và đã Add Input; không đoán một path khác. Không đưa `.env` lên Kaggle. Đặt `GEMINI_API_KEY` trong Kaggle Notebook Secrets khi test Reader API; không in giá trị.

## 2. Chốt môi trường serving và kiểm tra GPU

Trong notebook mới, bật GPU ở Settings. Kaggle runtime là môi trường mới, không chuyển `.venv` từ Windows. Ngày 2026-09-26 đã kiểm được T4 x2, Python 3.12.13 và PyTorch 2.10.0+cu128. Image gốc có conflict của các package không thuộc dự án, nên dùng venv riêng và gọi qua `serving_python`. File `requirements-orchestrator.txt` là bộ pin **serving**; không cài chung `05_writer/requirements-train.txt` vào môi trường này.

```python
import torch, platform, subprocess, sys
print({'python': platform.python_version(), 'torch': torch.__version__,
       'torch_cuda': torch.version.cuda, 'gpu_count': torch.cuda.device_count(),
       'gpu_names': [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]})
assert torch.cuda.is_available(), 'Enable GPU in Kaggle Settings before model inference'
print('Temporary disk free GiB:', round(shutil.disk_usage('/tmp').free / 2**30, 2))
serving_dir = Path('/tmp/research-rag-serving')
# ensurepip của image Kaggle thất bại; pip --python quản lý venv chưa có pip.
subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(serving_dir)], check=True)
serving_python = str(serving_dir / 'bin/python')
run_env = os.environ.copy()
run_env['PYTHONPATH'] = str(root)
run_env['HF_HOME'] = '/tmp/research-rag-hf'
subprocess.run([sys.executable, '-m', 'pip', '--python', serving_python,
                'install', '--no-cache-dir', 'pip==26.2.1', 'wrapt==2.1.2'], check=True)
# wrapt phục vụ sitecustomize có sẵn của Kaggle, không phải dependency AI mới.
subprocess.run([serving_python, '-m', 'pip', 'install', '--no-cache-dir',
                'torch==2.10.0', 'torchvision==0.25.0', '--index-url',
                'https://download.pytorch.org/whl/cu128'], env=run_env, check=True)
subprocess.run([serving_python, '-m', 'pip', 'install', '--no-cache-dir',
                '-r', str(root / 'requirements-orchestrator.txt')], env=run_env, check=True)
subprocess.run([serving_python, '-m', 'pip', 'check'], env=run_env, check=True)
freeze = subprocess.run([serving_python, '-m', 'pip', 'freeze'],
                        capture_output=True, text=True, check=True)
Path('/kaggle/working/requirements-serving-kaggle.lock.txt').write_text(freeze.stdout)
```

Các lệnh inference/evaluation phía dưới dùng venv, không dùng package của kernel notebook. Venv và cache trong `/tmp` chỉ sống theo session; tạo lại khi session bị thay mới. Output nhỏ được ghi trong `/kaggle/working`. Nếu `pip check` trong venv lỗi, giải quyết conflict trước khi nạp model. Kiểm tra trước model load:

```python
subprocess.run([serving_python, '-m', 'research_rag.preflight', '--faiss'],
                cwd=root, env=run_env, check=True)
```

`preflight` phải cho thấy FAISS đọc được, 41.549 vector, chiều 1024, ID cùng số lượng; Fact-Checker merged đủ shard và `base_matches_adapter=true`. Đó là kiểm tra artifact, chưa phải truy vấn dense hay inference.

## 3. Bổ sung base weights và đo RAM/VRAM

Summarizer generator và critic cùng dùng Qwen2.5-7B-Instruct; Writer dùng Qwen2.5-1.5B-Instruct; dense search dùng BGE-Large-en-v1.5. Các weights này không nằm trong ZIP. Đảm bảo notebook có Internet và đủ disk trước khi tải. Tải từ model repo gốc bằng `huggingface_hub` (chỉ một bản 7B cho hai adapter):

```python
download_code = '''
import json
from pathlib import Path
from huggingface_hub import snapshot_download
records = []
for model_id in ('BAAI/bge-large-en-v1.5', 'Qwen/Qwen2.5-7B-Instruct',
                 'Qwen/Qwen2.5-1.5B-Instruct'):
    path = Path(snapshot_download(repo_id=model_id, token=False,
        allow_patterns=['*.json', '*.safetensors', '*.txt', '*.model',
                        '*.tiktoken', '*.jinja', 'LICENSE', 'README.md']))
    records.append({'repo': model_id, 'revision': path.name})
    Path('/kaggle/working/base-weights.json').write_text(json.dumps(records, indent=2))
    print(model_id, path.name, flush=True)
'''
subprocess.run([serving_python, '-u', '-c', download_code], env=run_env, check=True)
```

Nếu disk/cache không đủ, dừng và ghi dung lượng còn trống; không tiếp tục nạp model với cache thiếu. Chạy lại `preflight` để kiểm tra `weights_complete` của cả ba base. Sau đó dùng đúng một câu hỏi, ghi số đo và trạng thái:

```python
metrics_path = Path('/kaggle/working/first-run-metrics.json')
command = [serving_python, '-m', 'research_rag.local',
           '--question', 'What does the corpus say about knowledge distillation?',
           '--quantize-4bit', '--profile-resources',
           '--metrics-output', str(metrics_path)]
subprocess.run(command, cwd=root, env=run_env, check=True)
```

`--quantize-4bit` dùng NF4 cho Summarizer/Fact-Checker; Writer tự nạp 4-bit khi đến node Writer. Ghi `nvidia-smi` trước/sau, RSS/peak CUDA trong stderr và `total_ms` cùng thời gian từng node trong metrics. `peak_allocated_bytes` là bộ nhớ PyTorch cấp phát đỉnh, không phải toàn bộ VRAM tiến trình; `nvidia-smi` là kiểm tra bổ sung. Nếu OOM, ghi stage đang load, GPU/dung lượng trống, stack trace rồi mới điều chỉnh cấu hình. Không hạ `max_context_chars` hay bỏ Fact-Checker mà chưa đo ảnh hưởng chất lượng.

## 4. Dense search và qrels có nhãn

### Chẩn đoán lần chạy `summary_unverified`

Bản code local cập nhật ngày 2026-09-26 có `--trace-output`; **dataset v2 chưa có cờ này**. Đồng bộ các file runtime mới trước khi dùng. Giữ nguyên layout tương đối để `research_rag.local.ROOT` tìm đúng checkpoint/index. Không chạy lệnh mới trên bản v2 rồi hiểu lỗi `unrecognized arguments` là lỗi model.

```python
diagnostic_command = [serving_python, '-m', 'research_rag.local',
    '--question', 'How much smaller is DistilBERT than BERT, and how much language understanding performance does it retain?',
    '--quantize-4bit', '--profile-resources', '--max-graph-retries', '1',
    '--trace-output', '/kaggle/working/distilbert-trace.private.jsonl',
    '--metrics-output', '/kaggle/working/distilbert-metrics.json']
with open('/kaggle/working/distilbert-result.json', 'w') as out, open('/kaggle/working/distilbert-stderr.log', 'w') as err:
    subprocess.run(diagnostic_command, cwd=root, env=run_env, stdout=out, stderr=err, check=True)
```

Trace là tùy chọn, chứa nội dung model và nguồn nên phải giữ Private; metrics vẫn chỉ có thời gian/trạng thái/số lượng. File trace phải là file mới, không ghi đè lần trước. Đọc từng event `summarizer_generation`: `role`, `raw_output`, `json_valid`, `parse_error`, `generated_tokens`, `max_new_tokens`. `json_valid=true` chỉ có nghĩa parse được JSON, chưa chứng minh đúng schema. Số token chạm giới hạn chỉ là dấu hiệu cần kiểm tra truncation, chưa phải kết luận.

Event cuối `graph_result` giữ state để đối chiếu draft, span, nguồn và Fact-Checker. `summary_diagnostics.reasons` phân biệt `critic_not_supported`, `summary_confidence_not_high`, `no_evidence_spans`, `no_verbatim_evidence`, hoặc `summarizer_exception`. Không bỏ kiểm evidence hoặc hạ threshold để làm test pass. Chỉ gọi lần chạy này là end-to-end có báo cáo khi thực sự có Fact-Checker inference, Writer inference và citation đã được đối chiếu.

### Đánh giá truy xuất

Để xác nhận BGE + FAISS thật, chạy một truy vấn bắt buộc đi qua `dense` và kiểm tra `method`, `warning`:

```python
probe_code = '''
import time
from research_rag.retrieval import RetrievalService
service = RetrievalService(offline=True, policy=lambda query, history: 'dense')
start = time.perf_counter()
result = service.search('knowledge distillation for language models', top_k=5)
print({'latency_ms': round((time.perf_counter() - start) * 1000, 1),
       'methods': [c['method'] for c in result['chunks']],
       'warning': result['warning'],
       'doc_ids': [c['doc_id'] for c in result['chunks']]})
assert result['chunks'] and all(c['method'] == 'dense' for c in result['chunks'])
assert result['warning'] is None
'''
subprocess.run([serving_python, '-c', probe_code], cwd=root, env=run_env, check=True)
```

`qrels.jsonl` phải do người đánh giá gán trên câu hỏi **giữ lại**, mỗi dòng có `query` và `relevant_doc_ids` thật từ `corpus.jsonl`. Không dùng `retrieval_eval_manual.jsonl` vì file đó chỉ có nhãn tool. Không tự gán nhãn bằng kết quả top-k của hệ thống.

Bộ dataset Private `trcng23/research-rag-evaluation-fixtures` đã có `retrieval_smoke_qrels.jsonl` gồm 10 câu và một chunk dương tính đã xác nhận cho mỗi câu. Dùng nó để kiểm tra đường chạy trước khi thu thập qrels giữ lại; kết quả **không phải recall tổng quát** vì nhãn chưa đầy đủ và câu hỏi được viết từ corpus:

```python
eval_manifests = list(Path('/kaggle/input').rglob('evaluation-transfer-manifest.json'))
assert len(eval_manifests) == 1
pilot_qrels = eval_manifests[0].parent / 'research_rag/evaluation/retrieval_smoke_qrels.jsonl'
for mode in ('bm25', 'dense', 'policy'):
    subprocess.run([serving_python, '-m', 'research_rag.evaluate', 'retrieval',
                    '--qrels', str(pilot_qrels), '--mode', mode, '--top-k', '5'],
                   cwd=root, env=run_env, check=True)
```

Sau smoke test, dùng bộ qrels giữ lại có nhãn đầy đủ cho gate chất lượng:

```python
qrels = Path('/kaggle/working/qrels.jsonl')
assert qrels.is_file()
for mode in ('bm25', 'dense', 'policy'):
    subprocess.run([serving_python, '-m', 'research_rag.evaluate', 'retrieval',
                    '--qrels', str(qrels), '--mode', mode, '--top-k', '5'],
                   cwd=root, env=run_env, check=True)
```

Chỉ coi phép đo dense hợp lệ nếu `dense_fallback_queries=0`. So sánh recall@5, hit@5, p95 latency và số `unsupported_policy_queries` trên cùng qrels; sau đó mới quyết định giữ hay bỏ `hyde/rewrite/decompose`.

## 5. Reader PDF, OCR và Gemini API thật

Ngày 2026-09-26 đã xác nhận Secret hoạt động và `models.list()` trả về `gemini-3.6-flash`. Chưa chạy inference Reader. Khi chỉ kiểm fixture/API, có thể chọn CPU; không cần tải Qwen/BGE. Cell độc lập ở `docs/KAGGLE_READER_CELL.py` lấy scorer từ dataset fixture, ghi lỗi/latency từng trang, giới hạn process 240 giây và không in credential. Cell mới chỉ được kiểm cú pháp local. Kernel hiện có `google-genai==1.68.0`; phải ghi nhận version khi chạy và kiểm lại với bộ serving pin trước khi chốt môi trường. Không `import research_rag.evaluation.reader_smoke` từ dataset workspace v2 vì gói đó chưa chứa module đánh giá.

Chuẩn bị manifest PDF giữ lại gồm text PDF đơn giản, nhiều cột/bảng và scan; với mỗi file cần nhãn trang và các câu/đoạn quan trọng do người đọc xác nhận. File PDF này là dữ liệu riêng, không tự đưa vào ZIP workspace. Trên notebook:

Dataset Private đánh giá ở trên cũng có ba PDF **tự tạo** và `reader_smoke_manifest.jsonl`. Trước tiên nạp key từ Kaggle Notebook Secrets rồi chạy smoke test qua Reader. Reader gửi mẫu text tới Gemini để critique; chỉ dùng PDF được phép xử lý qua API, không in key hoặc nội dung tài liệu riêng vào output:

```python
from kaggle_secrets import UserSecretsClient
import os, shutil
assert shutil.which('tesseract'), 'Tesseract binary is required for scanned PDFs'
run_env['GEMINI_API_KEY'] = UserSecretsClient().get_secret('GEMINI_API_KEY')
```

```python
eval_root = eval_manifests[0].parent
reader_manifest = eval_root / 'research_rag/evaluation/reader_smoke_manifest.jsonl'
import json
env = run_env.copy()
# Gói v2 chưa có research_rag/evaluation; gọi script trong dataset fixture.
reader_script = eval_root / 'research_rag/evaluation/reader_smoke.py'
run = subprocess.run([serving_python, str(reader_script),
                      '--manifest', str(reader_manifest)], cwd=root, env=env,
                     check=True, capture_output=True, text=True)
metrics = json.loads(run.stdout)
print(metrics)
# Dataset fixture cũ chỉ in metrics, không trả exit code lỗi khi thiếu span.
assert not metrics['failures'] and metrics['exact_span_rate'] == 1.0, 'Reader smoke gate failed'
```

Với PDF thật có nhãn, kiểm tra cùng đường Reader và chỉ in metadata cần thiết:

```python
pdf_path = Path('/kaggle/working/reader_eval/sample.pdf')  # thay bằng file thật
assert pdf_path.is_file()
reader_code = '''
import sys
from research_rag.adapters import PdfReader
chunks = PdfReader().read(sys.argv[1])
print({'chunks': len(chunks),
       'pages_0_based': sorted({c['metadata']['page_no'] for c in chunks}),
       'tools': sorted({c['metadata']['source_tool'] for c in chunks})})
'''
subprocess.run([serving_python, '-c', reader_code, str(pdf_path)],
                cwd=root, env=run_env, check=True)
```

Đối chiếu text, trang (zero-based), bbox và tool với manifest có nhãn; kiểm tra riêng scan/OCR và lỗi API/quota. Không in nội dung PDF hoặc key vào log được chia sẻ. `GEMINI_API_KEY` cần được gắn vào Notebook Secrets; nếu `get_secret` lỗi, kiểm tra Secret đã attach và quyền Internet/API trước khi chạy lại.

## 6. End-to-end và gate hoàn thiện

Nạp graph **một lần** rồi chạy các ca giữ lại: có bằng chứng, không có bằng chứng, nhiều claim, hai nguồn mâu thuẫn, PDF scan/layout, lỗi Reader/API, Fact-Checker lỗi và retry hết budget. Dùng `run_with_metrics(graph, state)` và lưu JSON metrics vào `/kaggle/working`; chỉ lưu báo cáo/claim ra file riêng nếu dữ liệu được phép lưu và review. Với mỗi ca, người gán nhãn kiểm tra: claim có đúng không, evidence có hỗ trợ claim không, `source_id` có trỏ đúng chunk/trang không, mâu thuẫn có bị chặn không, status/retry có hợp lý không. Chạy thêm `research_rag.evaluate confidence` khi có prediction kèm `confidence_score` và nhãn vàng; ngưỡng 0,7 hiện chưa calibration.

Chỉ đánh dấu hoàn thiện khi: manifest/checksum pass; GPU model load và dense không fallback; qrels/PDF manifest có nhãn; test end-to-end bằng model thật cho kết quả được review; p95 latency và chi phí phù hợp ngân sách bạn đặt; log không chứa prompt, key hoặc tài liệu nhạy cảm. `token_usage` và `estimated_cost` hiện là `null`, nên phải bổ sung đo usage từ backend hoặc ghi chi phí API thực tế trước khi đặt gate cost. Nếu thiếu qrels/PDF/rights, ghi rõ **chưa đánh giá**, không suy từ mock test.
