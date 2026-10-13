# Hướng dẫn hoàn thiện Research RAG trên Kaggle

Đối chiếu với code local ngày 2026-09-27. Đây là hướng dẫn thực hiện, không phải
báo cáo rằng các lượt GPU/API bên dưới đã chạy hoặc đã đạt.

## 0. Chọn đúng phạm vi và thứ tự

Mục tiêu trước mắt: bản research/portfolio phi thương mại, trả lời từ corpus
được chọn và PDF, có bằng chứng/citation, biết từ chối khi thiếu bằng chứng.
Chỉ công bố các layout, ngôn ngữ, kích thước PDF và tải đồng thời đã được đo.

Thứ tự: môi trường → Fact-Checker A/B → Reader → retrieval dev → đóng băng
cấu hình/dữ liệu → calibration → E2E dev → final test → đóng gói/demo.
API và lưu checkpoint bền vững là phần triển khai sau các gate chất lượng.

Notebook hiện có bốn cell code: setup, A/B, Reader, QASPER dev. Nó chưa có
calibration fitting, bộ E2E adverse chạy model thật, API hoặc persistence.
Các bước ghi “cần bổ sung code” bên dưới chưa phải chức năng CLI sẵn có.

## 1. Mở notebook bằng Chrome thông thường

1. Mở https://www.kaggle.com/code/trcng23/research-rag-gpu-validation/edit.
2. Nếu draft cũ có kết quả chưa lưu, Save Version → Quick Save → Advanced
   Settings → Save output for this version → Save; kiểm phiên bản hoàn thành.
3. Nhập file local `scripts/kaggle_resume_validation.ipynb` bằng chức năng
   Import Notebook. Nếu menu của editor không có, dùng chức năng Import
   Notebook ở trang Code; notebook mới phải được cấu hình lại Input/Secrets.
4. Xác nhận notebook **Private** và đúng bốn cell code, không trộn cell lịch sử.
5. Attach đúng **Research RAG Five Agents Workspace** và **Research RAG Runtime
   Diagnostics version 2**. Bộ Evaluation Fixtures cũ có thể vẫn được attach;
   notebook mới dùng manifest trong workspace đã overlay.
6. Bật Internet, T4 x2 nếu còn quota miễn phí, bật Secret `GEMINI_API_KEY` cho
   notebook này. Không ghi giá trị key vào cell, output hoặc file.
7. Chạy từng cell theo thứ tự, chưa dùng Run All trên notebook lịch sử.

Không cần tạo Kaggle API token. Timeout CDP của công cụ điều khiển khác với
timeout Python/Gemini. Dùng Chrome thủ công bỏ được lớp điều khiển đang lỗi,
nhưng không bảo đảm Kaggle/network/API không còn lỗi riêng.

Nếu quota GPU hết, dừng; không chạy các LLM trên laptop đang thiếu RAM.

## 2. Chạy cell setup và kiểm kết quả thật

Cell đầu kiểm manifest 49 payload, áp dụng 10 file vá có hash, tạo workspace và
venv mới trong `/tmp`, cài bộ serving, chạy `pip check`, unit tests, preflight.
Không cài thêm requirements training của từng agent vào venv serving.

Các biến dùng trong những cell thêm ở tài liệu này:

| Biến | Nghĩa |
|---|---|
| `root` | Workspace trên Kaggle, các agent nằm cạnh `research_rag/` |
| `python` | Python của venv serving; không thay bằng `!python` mặc định |
| `env` | Môi trường subprocess, gồm PYTHONPATH và HF_HOME |
| `out` | Thư mục diagnostic riêng trong `/kaggle/working` |
| `run(...)` | Helper chạy subprocess có deadline, status và log |
| `bundle()` | Gói diagnostic thành ZIP; chưa thay thế thao tác lưu Output |

Đọc báo cáo ngay sau setup:

```python
preflight = json.loads((out / 'preflight.stdout.log').read_text())
print(json.dumps(preflight, indent=2))
assert preflight['host']['cuda_available']
assert preflight['models']['factchecker']['checkpoint']['weights_complete']
assert preflight['models']['factchecker']['base_matches_adapter']
assert preflight['faiss']['readable']
assert preflight['faiss']['ids_aligned']
```

`preflight` hiện chỉ in báo cáo; exit code 0 không có nghĩa mọi weights đều đủ.
Thiếu base Summarizer/Writer/BGE ở đây có thể xảy ra và phải bổ sung ở bước sau.
Fact-Checker dùng merged Qwen2.5-3B, không tải 7B để thay vào checkpoint đó.
FAISS ở preflight là index arXiv cũ; benchmark QASPER dùng index riêng ở bước 5.

**Đạt:** hash đúng, pip check không lỗi, tests không lỗi, CUDA hoạt động,
Fact-Checker merged đủ weights và base khớp metadata adapter.

### Khi một stage lỗi hoặc timeout

```python
print(json.dumps(json.loads((out / 'status.json').read_text()), indent=2))
# Thay bằng đúng tên stage thất bại, ví dụ serving, factchecker, reader-real.
stage = 'factchecker'
path = out / (stage + '.stderr.log')
if path.exists():
    print(path.read_text()[-6000:])
```

Chỉ xem log trong notebook Private; rà/redact trước khi chia sẻ ra ngoài.
Không in toàn bộ `env` hoặc đối tượng credential để debug.

Helper không cho chạy lại cùng tên stage để bảo vệ kết quả cũ. Khi đã xác định
nguyên nhân và sửa, chạy lệnh riêng với tên mới, ví dụ `factchecker-r2` và thư
mục kết quả mới. Chạy lại nguyên cell thường vẫn dùng tên cũ và sẽ bị chặn.

Nếu session đã mất, `/tmp`, venv và biến Python có thể không còn. Bắt đầu setup
mới rồi chạy stage cần thiết; attach/tải Output cũ để đối chiếu, không ghi đè.

## 3. Fact-Checker A/B bằng checkpoint thật

Chạy cell “Paired Fact-Checker diagnostic”. Script dùng cùng checkpoint 3B
NF4 cho hai profile, tổng 84 prediction: 2 × (30 dev + 12 synthetic contracts).
Không có bước train trong cell này.

File cần đọc trong `out/factchecker/`:

- `baseline-dev30.jsonl`, `coverage-dev30.jsonl`.
- `baseline-contracts.jsonl`, `coverage-contracts.jsonl`.
- `metrics.json`, `resources.json`, `provenance.json`.

```python
fc = json.loads((out / 'factchecker/metrics.json').read_text())
for profile, datasets in fc.items():
    for dataset, m in datasets.items():
        print(profile, dataset, {
            'n': m['n'], 'macro_f1': m['macro_f1'],
            'false_support': m['false_support'],
            'runtime_failed_rows': m['runtime_failed_rows'],
            'support_precision': m['per_label']['support']['precision'],
            'contradict_recall': m['per_label']['contradict']['recall'],
        })
```

Ưu tiên đọc trực tiếp mọi false support: claim có nhiều mệnh đề nhưng context
chỉ chứng minh một phần, sai số liệu, thiếu qualifier, nhầm causal relation.
Phân biệt NEI với contradict: thiếu thông tin không tự chứng minh claim sai.

**Gate development đề xuất:** không có runtime failure và không false support
trên các contract cố định; chọn profile dựa cả support precision, recall nhãn
contradict, macro-F1 và latency. Một model từ chối tất cả không đạt yêu cầu trả
lời. Không coi 30 dev/12 synthetic là bằng chứng tổng quát hóa.

Nếu coverage không giải quyết lỗi: giữ baseline, bổ sung các ca khó vào dev /
training có nhãn đúng, sửa prompt hoặc fine-tune lại rồi lặp A/B. Không hạ
threshold để che false support; claim sai nhưng score cao vẫn có thể lọt.

### Đưa profile đã chọn vào graph — cần bổ sung code

`research_rag.local` hiện luôn khởi tạo prompt baseline. Tham số
`--prompt-profile` chỉ tồn tại ở `04_factchecker/eval_factchecker.py`.

Trong `research_rag/local.py`:

1. Thêm `factchecker_profile: str = 'baseline'` vào `build_local_graph`.
2. Validate giá trị chỉ là `baseline` hoặc `coverage`.
3. Khi khởi tạo Fact-Checker, dùng cùng cặp prompt như A/B:

```python
prompts = importlib.import_module('04_factchecker.prompts')
judge_options = ({'system_prompt': prompts.COVERAGE_JUDGE_SYSTEM_PROMPT}
                 if factchecker_profile == 'coverage' else {})
confidence_options = ({'system_prompt': prompts.LABEL_CONFIDENCE_SYSTEM_PROMPT}
                      if factchecker_profile == 'coverage' else {})
factchecker = factchecker_module.FactCheckerNode(
    fact_inference.FactCheckJudge(fact_backend, **judge_options),
    fact_inference.ConfidenceEstimator(fact_backend, **confidence_options),
    fact_inference.ActionRecommender(fact_backend),
)
```

4. Thêm argument CLI `--factchecker-profile` với hai choices trên; truyền
   `args.factchecker_profile` vào `build_local_graph`.
5. Test baseline mặc định không đổi, coverage nhận đúng cả hai prompt.
6. Đồng bộ file đã sửa lên Kaggle, lưu hash file/prompt cùng run. Notebook hiện
   không tự tải sửa local mới: generator chỉ nhúng danh sách 10 file, chưa có
   `local.py`; phải đồng bộ file này rõ ràng hoặc mở rộng generator/manifest.

Đừng thêm một option vào lệnh chạy trước khi đã thêm parser của option đó.

## 4. Reader API sau sửa và dữ liệu PDF

Trong cell Reader, Secret được đưa vào subprocess, không in ra. Model ID của
run trước là `gemini-3.5-flash-lite`; đây là cấu hình đã lưu, không bảo đảm
endpoint đó luôn còn phục vụ tài khoản.

Có thể thêm cell kiểm danh sách model trước Reader, dùng đúng venv:

```python
from kaggle_secrets import UserSecretsClient
probe_env = env.copy()
probe_env['GEMINI_API_KEY'] = UserSecretsClient().get_secret('GEMINI_API_KEY')
try:
    run('gemini-models', [python, '-u', '-c', '''
from google import genai
client = genai.Client(http_options={'timeout': 30000})
for model in client.models.list():
    if 'generateContent' in (model.supported_actions or []):
        print(model.name)
'''], child_env=probe_env, timeout=120)
finally:
    probe_env.pop('GEMINI_API_KEY', None)
print((out / 'gemini-models.stdout.log').read_text())
```

Nếu model ID cũ không có, chọn ID hỗ trợ generateContent từ danh sách của
tài khoản, cập nhật `GEMINI_MODEL` trong cell Reader và ghi ID/version đã dùng.
Đổi model là đổi cấu hình cần đánh giá lại; không tự giả định quota/giá giống cũ.
Xem [Google Models API](https://ai.google.dev/api/models).

Chạy cell Reader:

1. Kiểm có binary Tesseract. Thiếu thì cài Tesseract bằng package manager của
   host; `pip install pytesseract` chỉ cài Python wrapper, không cài binary.
2. Smoke: 3 PDF synthetic, 9 spans.
3. Real: PDF QASPER 12 trang, 9 spans đã ghi ở trang 0/3/8.
4. Giữ `GEMINI_REQUEST_INTERVAL_SECONDS=61` như cấu hình diagnostic trước.
   Đây chỉ là pacing, không bảo đảm miễn lỗi 429/quota. Chạy full PDF có thể lâu.

**Đạt cho hai fixture manifest:** `passed=true`, `failures=[]`,
`span_coverage=1`, `overall_exact_span_rate=1`. Cell notebook có thể kết thúc
bình thường sau khi in “Reader gate failed”; phải xem JSON và status của
`reader-smoke` lẫn `reader-real`, không nhìn riêng dấu tick xanh của cell.

| Lỗi | Cách xử lý đúng |
|---|---|
| 401/403 | Kiểm Secret đã bật và quyền API; không retry mãi |
| Model 404 | Kiểm danh sách model và ID cấu hình |
| 429 | Đọc quota/RPM/TPM/daily limit; chờ hoặc giảm tải. Daily quota hết thì dừng |
| 503 / network timeout | Retry hữu hạn; giữ log, không coi response thiếu là đạt |
| API thành công nhưng mất span | Kiểm extraction, overflow windows, page_no và normalization |
| SourceHashMismatch | Kiểm đúng PDF đã gán nhãn; không bỏ kiểm hash để pass |

### Bổ sung benchmark Reader thật

Hai manifest sẵn có chỉ đủ diagnostic. Chuẩn bị riêng nhóm nhiều cột/bảng và
scan thực tế, có quyền xử lý bằng API. Khởi đầu 12–20 PDF đại diện là đề xuất
thực dụng, không phải kích thước bảo đảm chất lượng thống kê.

1. Chọn tài liệu trước khi xem model output; giữ hash và license mỗi PDF.
2. Người gán nhãn mở PDF và chép spans/trang chuẩn; người khác rà các ca khó.
3. `page_no` đếm từ 0. `pdf_path` phải tương đối với thư mục manifest.
4. Mỗi PDF hiện bị giới hạn 20 trang bởi `PdfReader`; nếu tăng, đo lại tài
   nguyên và kiểm test. Không đánh giá subset trang rồi gọi là toàn PDF.
5. Tạo JSONL cùng schema `reader_real_manifest.jsonl`, mỗi PDF ít nhất một
   `expected_spans`. Tốt hơn phủ các trang/đoạn dễ lỗi và số liệu quan trọng.
6. Chạy scorer bằng manifest mới. Nếu cần chứng minh bảng/reading order, phải
   thêm nhãn cell/thứ tự và scorer tương ứng; scorer span hiện chưa đo chúng.

Người tự gán nhãn có thể tạo held-out trước inference, nhưng không ghi là
“đã được người thứ hai adjudicate” nếu chưa có bước đó.

## 5. Dense QASPER và lựa chọn corpus

Chạy cell “BGE and QASPER dev”. Nó tải đúng revision BGE, dựng index riêng rồi
so BM25/dense/policy trên cùng 393 dev queries, top-k=5.

**Kiểm tra kỹ thuật:** corpus 18.587 paragraphs; index và ID mapping cùng thứ
tự; `dense_fallback_queries == 0`. FAISS query dùng CPU với `faiss-cpu`; GPU
được dùng cho encoder. Đừng gọi kết quả này là FAISS GPU benchmark.

**Đọc chất lượng:** hit@5 khác recall@5. Hit chỉ yêu cầu tìm được một paragraph
dương tính; recall tính tỷ lệ paragraph được annotate đã tìm thấy. Đo thêm
top-k=10 trên dev nếu cần và cân nhắc context/token/Fact-Checker budget.

Nếu dense kém, kiểm prefix query BGE, normalization, passage/query dùng cùng
encoder và revision, paragraph quá dài bị truncation, scope query có title.
Phân tích lỗi trên dev rồi mới đổi chunking/reranking. Đổi chunking thì phải
map lại qrels, không giữ nguyên ID của chunks khác nội dung.

Policy hiện có hyde/rewrite/decompose nhưng chưa thực hiện transformation;
`unsupported_policy_queries > 0` nghĩa là chưa thể tuyên bố các kỹ thuật đó đã
được benchmark. Chọn một mode thật đã có (bm25/dense) sau so sánh là phương án
đơn giản. Để ép mode đó cho E2E phải truyền `policy` vào `RetrievalService`
trong loader; hiện CLI `research_rag.local` chưa có `--retrieval-mode`.

Chưa chạy 417 test candidate để chọn top-k, mode, prompt hoặc threshold.

### Quyền corpus: đóng dependency cũ bằng thay thế

`jamescalam/ai-arxiv-chunked` vẫn chưa có bằng chứng quyền phân phối đủ cho
bản copy hiện tại. Private không tự tạo ra quyền sử dụng/phân phối. [Trang
nguồn](https://huggingface.co/datasets/jamescalam/ai-arxiv-chunked/tree/main)
và [hướng dẫn reuse arXiv](https://info.arxiv.org/help/license/reuse.html).

Hướng đề xuất để hoàn thiện bản phát hành: dùng QASPER đã chuẩn bị, giữ
attribution và manifest; [dataset card nguồn công bố CC BY 4.0](https://huggingface.co/datasets/allenai/qasper/blob/main/README.md).

1. Mọi lệnh demo/E2E phải truyền cả `--corpus` và `--index-dir` tương ứng QASPER.
2. Bỏ corpus/index arXiv cũ khỏi artifact phát hành mới. Không xóa checkpoint
   hay dữ liệu huấn luyện không liên quan.
3. Cập nhật default loader/deployment config để không vô tình quay lại corpus cũ.
4. Tạo gói Private mới chỉ chứa code/checkpoint cần thiết và nguồn thay thế;
   kiểm manifest/secret/license trước upload. Gói workspace cũ đang có corpus
   arXiv nên việc đổi CLI chưa tự loại nó khỏi lịch sử Kaggle dataset.
5. Ghi “corpus cũ không thuộc release; quyền chưa xác minh”, không ghi “đã được
   cấp phép”. Nếu giữ lại để phân phối, phải có căn cứ quyền từ rightsholder.

Không mặc định rằng xử lý corpus đã giải quyết mọi license của model/dữ liệu
train. Giữ `THIRD_PARTY_NOTICES.md`, `NOTICE.txt` và license Qwen 3B; phạm vi
dự án vẫn phi thương mại như đã chọn.

## 6. Calibration và tập test độc lập

### 6.1 Tạo/đóng băng dữ liệu đúng

Không dùng lại dev30/466 dev để công bố final test. Qrels retrieval cũng không
phải nhãn Fact-Checker. Cần các cặp claim/context với 3 nhãn:

- `support`: context chứng minh toàn bộ claim.
- `contradict`: context phủ định một phần có ý nghĩa của claim.
- `not_enough_info`: chưa đủ để kết luận, không có mâu thuẫn rõ.

Mỗi JSONL tối thiểu có `example_id`, `claim`, `context`, `label`. Thêm
`claim_id`, `paper_id`, `source_id`, nguồn/license, người gán nhãn, ngày chốt và
trạng thái review để audit. Không gán confidence ground truth bằng LLM.

Quy trình:

1. Lấy nguồn có nhãn người hoặc gán nhãn thủ công trên tài liệu được phép dùng.
2. So trùng với train, dev và mọi case đã dùng debug của từng agent liên quan;
   kiểm claim/context chuẩn hóa, paper IDs và review trùng ngữ nghĩa.
3. Gom cùng claim và paper vào một nhóm. Nếu một claim liên quan nhiều paper,
   các paper nối với nhau phải ở cùng nhóm, tránh lọt qua hai split.
4. Tách nhóm thành calibration và final trước inference; có đủ 3 nhãn và ca
   hỗ trợ một phần/mâu thuẫn. Ghi phân bố; không chỉ tuyển ca dễ/nhãn support.
5. Dùng calibration để fit map/chọn threshold. Final chỉ chấm sau khi khóa.
6. Lưu manifest hashes và protocol. Khởi đầu vài trăm cặp là đề xuất pilot;
   báo số mẫu, số claim/paper và độ bất định, không gọi kích thước nhỏ là chứng
   nhận production.

417 QASPER candidate chỉ thành final đúng phạm vi sau audit provenance.
“Độc lập với fine-tuning/prompt selection đã biết” khác với “chưa từng xuất
hiện trong pretraining”; hiện không có bằng chứng để khẳng định vế sau.

### 6.2 Thu prediction có confidence thật

Sau khi upload dữ liệu có nhãn vào Private Input, đặt đúng đường dẫn thực tế
cho `calibration_data`. Không có file đó thì chưa chạy phần này.

```python
from pathlib import Path
profile = 'coverage'  # Chỉ đặt sau quyết định A/B; có thể vẫn là baseline.
calibration_data = Path('/kaggle/input/YOUR_PRIVATE_DATA/factchecker_calibration.jsonl')
assert calibration_data.is_file(), 'Thay bằng đường dẫn dữ liệu đã gán nhãn/chốt'
calibration_predictions = out / 'factchecker-calibration-predictions.jsonl'
assert not calibration_predictions.exists()
run('fc-calibration-inference', [
    python, '-u', '-m', '04_factchecker.eval_factchecker',
    '--runtime-contract', '--prompt-profile', profile,
    '--data', str(calibration_data), '--output', str(calibration_predictions),
], timeout=7200)
run('fc-calibration-metrics', [
    python, '-m', 'research_rag.evaluate', 'confidence',
    '--predictions', str(calibration_predictions), '--threshold', '0.7',
])
```

Collector hiện giữ prediction trong RAM và ghi cuối lượt; nó chưa có resume
theo từng dòng như A/B. Nếu muốn chạy nhiều trăm mẫu lâu, bổ sung ghi/flush mỗi
dòng và resume kiểm hash trước khi chạy; không chạy lại vô hạn khi hết timeout.

`confidence` chỉ tính ECE/Brier/reliability/support precision; **chưa fit map**.
Confidence đo tính đúng của nhãn dự đoán, không phải xác suất claim đúng.
Nhãn contradict/NEI có thể rất chắc chắn. Prediction lỗi không được thay score
bằng 0 để đưa vào calibration.

### 6.3 Nếu cần score được hiệu chỉnh — cần bổ sung code

Có thể dùng `sklearn.isotonic.IsotonicRegression(out_of_bounds='clip')`:

1. `x` = confidence thô; `y` = 1 nếu predicted label bằng gold, ngược lại 0.
2. Fit chỉ trên calibration; lưu `X_thresholds_`, `y_thresholds_`, prompt /
   checkpoint hashes, source split hash, sklearn version và ý nghĩa score.
3. Chọn ngưỡng support trên calibration theo precision/coverage mong muốn đã
   công bố trước; tránh cách từ chối tất cả để đạt precision đẹp.
4. Áp dụng cùng map trước graph threshold và khi tạo prediction final. Giữ cả
   raw score và calibrated score để audit; lỗi runtime tiếp tục fail closed.
5. Truyền threshold vào `build_graph(factcheck_threshold=...)` qua loader.
   Đổi `FACTCHECKER_CONFIDENCE_THRESHOLD` đơn lẻ **không** đổi threshold graph.
6. So ECE/Brier và precision/coverage trên final sau khi khóa map/threshold.
   Map có thể không cải thiện; không sửa map dựa trên final rồi báo cùng final
   đó như dữ liệu chưa từng sử dụng.

Isotonic chỉ là một lựa chọn, dễ overfit khi ít mẫu; không bảo đảm chữa được
score chỉ có 0/1 hoặc confidence không mang tín hiệu. [API chính thức](https://scikit-learn.org/stable/modules/generated/sklearn.isotonic.IsotonicRegression.html).
Repo hiện chưa có fitter/wrapper này, nên đây là công việc implementation cụ
thể còn phải làm nếu yêu cầu calibrated score, không phải lệnh đã có.

## 7. Tải base và chạy E2E thật

Sau cell QASPER, thêm cell tải base theo đúng adapter config. Dùng cache chung
của subprocess; không tải vào Python/environment khác.

```python
base_code = r'''
import json
from pathlib import Path
from huggingface_hub import snapshot_download
from research_rag.local import ROOT
configs = [
    ROOT/'train_agent3_summarizer/checkpoints/generator_qlora/final/adapter_config.json',
    ROOT/'train_agent3_summarizer/checkpoints/critic_qlora/final/adapter_config.json',
    ROOT/'05_writer/checkpoints/writer_qlora/adapter_config.json',
]
names = sorted({json.loads(p.read_text())['base_model_name_or_path'] for p in configs})
for name in names:
    folder = snapshot_download(name, token=False, max_workers=2,
        allow_patterns=['*.json', '*.safetensors', '*.txt', '*.model', '*.jinja', 'LICENSE', 'README.md'])
    print(json.dumps({'model': name, 'resolved_revision': Path(folder).name}), flush=True)
'''
run('base-downloads', [python, '-u', '-c', base_code], timeout=7200)
run('preflight-after-download', [python, '-m', 'research_rag.preflight', '--faiss'])
p = json.loads((out/'preflight-after-download.stdout.log').read_text())
for name in ('summarizer_generator', 'summarizer_critic', 'writer'):
    assert p['models'][name]['adapter_present']
    assert p['models'][name]['base_cache']['weights_complete'], name
assert p['models']['retrieval_encoder']['base_cache']['weights_complete']
```

Snapshot revision được ghi trong log. Loader Qwen hiện dùng model name/ref
`main`; khi đóng release, cần khóa resolved revision trong loader/config và
đảm bảo downloader, preflight, loader dùng cùng revision. BGE đã pin riêng.
[Hugging Face download/caching](https://huggingface.co/docs/huggingface_hub/guides/download).

### 7.1 Một positive case trên code hiện tại

Cell sau dùng đúng CLI đang có; **baseline FC và heuristic retrieval hiện tại**.
Sau khi thêm profile/mode/threshold/calibration options ở các bước trên, phải
truyền chúng vào lệnh và lưu cấu hình cùng output. Không đánh giá coverage
ngoài graph rồi ngầm coi graph baseline là cùng hệ thống.

```python
corpus = root / 'kb_indexing/data/qasper_eval_20260926/corpus.jsonl'
index = out / 'qasper-index'
dev_path = corpus.parent / 'qrels_dev.jsonl'
dev = [json.loads(line) for line in dev_path.read_text().splitlines() if line.strip()]
question = dev[0]['query']  # Dev case; không thay bằng final để debug.
run('e2e-dev-one', [
    python, '-u', '-m', 'research_rag.local',
    '--question', question,
    '--corpus', str(corpus), '--index-dir', str(index),
    '--quantize-4bit', '--profile-resources', '--max-graph-retries', '1',
    '--metrics-output', str(out/'e2e-dev-one.metrics.json'),
    '--trace-output', str(out/'e2e-dev-one.private-trace.jsonl'),
], timeout=3600)
```

Trace chứa văn bản nguồn/raw generation; giữ Private. Đừng xem exit code 0
của CLI là quality pass: graph có thể trả `insufficient_evidence` hoặc `partial`.

### 7.2 Kiểm citation bằng cấu trúc thực tế

Writer hiện liên kết `sentence.claim_ids → verified_claims → source_id`.
Không giả định report có trường `citations` hoặc citation Markdown.

```python
events = [json.loads(line) for line in
          (out/'e2e-dev-one.private-trace.jsonl').read_text().splitlines() if line.strip()]
state = next(event['state'] for event in reversed(events) if event.get('event') == 'graph_result')
claims = {c['claim_id']: c for c in state.get('verified_claims', [])}
sources = {}
for chunk in state.get('seen_chunks', []):
    sources.setdefault(chunk['source_id'], []).append(chunk['text'])
sentences = state.get('final_report', {}).get('sentences', [])
for sentence in sentences:
    assert sentence['claim_ids'] and set(sentence['claim_ids']) <= claims.keys()
for claim in claims.values():
    assert claim['evidence'], 'Empty evidence'
    assert any(claim['evidence'] in text for text in sources.get(claim['source_id'], []))
print({'status': state.get('status'), 'sentences': len(sentences),
       'verified_claims': len(claims), 'errors': state.get('errors')})
```

Đây là kiểm cấu trúc/span. Người rà phải kiểm câu report có thực sự suy ra từ
claim và context không; citation hợp lệ không tự chứng minh answer đúng.
Positive case phải có trả lời hữu ích; zero sentences không được coi là pass
chỉ vì các vòng assert không chạy.

### 7.3 Chạy ma trận ca lỗi bằng model thật — cần harness bổ sung

Giữ model thật ở các thành phần không bị chủ động gây lỗi. Chỉ thay boundary
cần fault injection; ghi rõ case nào injected, không gọi toàn bộ là API outage
tự nhiên. `build_graph` đã nhận dependency injection để làm việc này.

| Ca | Dữ liệu/thao tác | Điều kiện cần kiểm |
|---|---|---|
| Có đủ bằng chứng | Câu hỏi dev có nhãn, nhiều mức khó | Trả lời đúng và citation đủ, không chỉ có JSON |
| Không có bằng chứng | Câu hỏi ngoài nội dung corpus, người rà trước | Không bịa; không đưa claim không có evidence vào report |
| Nhiều claim | Có cả mệnh đề được hỗ trợ và thiếu dữ liệu | Mệnh đề thiếu không được đưa vào verified_claims |
| Hai nguồn mâu thuẫn | Nguồn đồng ý và phủ định đã gán nhãn | Không bỏ nguồn đối lập vì Summarizer không chọn nó |
| Mâu thuẫn qua retry | Retrieval lượt 1 có nguồn phản bác, lượt 2 chỉ nguồn thuận | `seen_chunks` giữ nguồn cũ, conflict không biến mất |
| Reader hỏng | PDF hỏng/không đọc được; một case API timeout injected | Lỗi có cấu trúc; không sinh bằng chứng giả |
| JSON model lỗi | Inject output sai tại boundary trong một ca riêng | Retry hữu hạn và fail closed |
| Hết retry budget | Evidence vẫn thiếu sau các lượt | Kết thúc trong budget đã cấu hình |
| Citation sai | Report tham chiếu claim/source không tồn tại | Validator chặn và không phát hành report sai |

Không sửa corpus chuẩn để tạo test mâu thuẫn; tạo fixture riêng, có provenance.
Không chạy từng ca bằng cách nạp lại toàn bộ model nếu không cần; harness nên
nạp một lần, dùng câu hỏi/trạng thái riêng, ghi result sau từng ca.

Nếu CUDA OOM: xem memory snapshot xác định model nào/thiết bị nào đầy. T4 x2
là hai vùng VRAM riêng, không tự thành một vùng 32 GB. `device_map='auto'` chưa
phải bằng chứng placement tối ưu. Nạp sequential để xác nhận từng model, sau
đó chỉnh placement/lifecycle nếu cần; giảm context/new tokens trong phạm vi
đã đánh giá. Không ép nạp CPU trên máy thiếu RAM hoặc tăng timeout để chữa OOM.

## 8. Final test, latency và chi phí

1. Khóa prompt/profile, models/revisions, corpus/index, top-k/context,
   calibration/threshold, retry budget và dependency freeze.
2. Chạy độc lập final của retrieval, Fact-Checker, Reader và toàn graph theo
   phạm vi nhãn từng tập. Một test thành phần không chứng nhận toàn pipeline.
3. Ghi mọi failure, không lọc ca lỗi ra rồi chỉ báo điểm trên ca thành công.
4. Báo precision/recall theo nhãn, false support, support coverage, ECE/Brier,
   citation validity và semantic correctness, abstention và answer quality.
5. Báo cold start riêng; warm latency mean/p50/p95 cần đủ lượt lặp, không tính
   p95 từ một câu. Tách thời gian deliberate API pacing khỏi inference thuần.
6. Metrics hiện có RSS snapshots, CUDA allocated peaks và node latency;
   chưa đo mọi RAM peak / utilization / token / billing. `token_usage=null`
   và `estimated_cost=null` nghĩa là chưa có dữ liệu, không phải 0.
7. Nếu cần token/cost: bổ sung thu `usage_metadata` của API và input/output
   token IDs ở local backend; ghi giá theo model/ngày/đơn vị từ nhà cung cấp.
   Giờ GPU Kaggle là tài nguyên/quota; không suy ra hóa đơn trả phí khi không có.

Threshold chất lượng cần chốt trước final theo yêu cầu ứng dụng. Ví dụ
support precision cao cùng coverage tối thiểu, không false support ở bộ
adverse cố định, không citation ID sai. Không có ngưỡng recall/ECE phổ quát
bảo đảm mọi RAG đã “production-ready”. Final fail thì sửa trên development,
ghi nhận final đã bị dùng và tạo vòng kiểm chứng mới phù hợp.

## 9. API/checkpoint nếu phạm vi release yêu cầu — chưa có code

Khi quality gates đạt, bổ sung tối thiểu:

1. API private với request question, tham chiếu PDF hợp lệ; validate độ dài,
   loại/kích thước/số trang. Không nhận đường dẫn filesystem tùy ý từ client.
2. Nạp model một lần trong lifecycle, giới hạn concurrency/queue theo VRAM,
   timeout/cancellation và error response có cấu trúc.
3. Auth khi mở ra ngoài máy; request ID, latency/error metrics không log secrets
   hoặc toàn bộ tài liệu mặc định. Không dùng public tunnel như production.
4. Persistence: cho `build_graph` nhận checkpointer rồi truyền vào `compile`;
   truyền `thread_id` ở invocation. SQLite dùng thử single-process, PostgreSQL
   khi triển khai phù hợp. Thư mục `/tmp` và saver RAM không bền qua restart.
5. `run_with_metrics` hiện chưa nhận config/thread_id: phải cập nhật đường
   stream này cùng loader, không chỉ thêm checkpointer vào `compile`.
6. Test restart/resume, hai người dùng khác thread không lẫn dữ liệu, API retry
   không nhân đôi chi phí. State có thể chứa text nguồn nên cần retention và
   access phù hợp, không chỉ quan tâm table schema.

LangGraph cung cấp persistence qua checkpointer; repo hiện gọi `compile()`
không tham số nên chưa có persistence đó. [Tài liệu chính thức](https://docs.langchain.com/oss/python/langgraph/persistence).
Kaggle phù hợp chạy benchmark/demo theo session; triển khai phục vụ liên tục
cần host và lưu trữ được quản lý cho vòng đời đó.

## 10. Lưu bằng chứng và chốt bản phát hành

Sau mỗi stage tốn thời gian:

1. Chạy `bundle()` khi không có subprocess ghi file.
2. Save Version → Quick Save → Advanced Settings → Save output for this
   version → Save.
3. Mở version vừa lưu, kiểm có ZIP/status/metrics cần thiết và trạng thái thành
   công. Chỉ thấy file notebook source chưa phải đã lưu đủ diagnostic.
4. Tải ZIP về máy, kiểm checksum và giữ phiên bản.
5. Khi kết thúc công việc, More settings → Stop session; xác nhận Session off.
   Nếu editor không mở được, dùng Active Events để dừng đúng session.

Nếu dùng Save & Run All để chạy background, chỉ dùng notebook sạch đã kiểm,
đã bỏ các bước cần quyết định giữa chừng hoặc đã khóa quyết định trước đó.
Chạy background có thể tạo thêm session; kiểm Active Events để không để cả
interactive lẫn background tiêu hao GPU ngoài ý muốn.

Release evidence tối thiểu gồm: source/config hashes, dependency freeze,
model revisions, data/license manifests, split audit, A/B decision, calibration
artifact nếu dùng, final predictions/metrics, Reader results, E2E case table,
latency/resource records, giới hạn đã biết và lệnh tái tạo.

README phải phân biệt test giả với model thật, dev với final và schema citation
với semantic correctness. Bản research demo có thể mô tả giới hạn thành thật;
không gắn nhãn production-ready khi các gate tương ứng chưa đạt.

## Bảng xử lý nhanh

| Hiện tượng | Việc cần làm |
|---|---|
| Tool CDP timeout | Dùng Chrome trực tiếp; không chỉnh timeout Gemini vì khác lớp |
| Manifest/hash fail | Attach đúng diagnostics v2/base; không bỏ assert |
| `name not in statuses` fail | Tên stage đã dùng; dùng tên/thư mục mới cho lượt đã sửa |
| `weights_complete=false` | Tải đúng base vào cùng HF_HOME, kiểm lại shard/ref |
| Dense fallback | Kiểm BGE cache/revision, dimension/index/ID/RAM; không báo dense pass |
| `insufficient_evidence` | Đọc trace: summary reasons, fact-check labels, conflict, call budget |
| `unmatched_evidence_spans` | So span với nguồn; không bỏ kiểm verbatim để answer đi qua |
| `call_budget_exceeded` | Số claim × số evidence/chunk vượt budget; giảm claim/context hoặc tăng budget sau đo tài nguyên |
| Reader API ok nhưng quality fail | Debug extraction/page mapping/layout; API ok chỉ chứng minh kết nối |
| ECE/Brier xấu | Kiểm ý nghĩa score rồi fit/đánh giá; không đổi gold hoặc xóa lỗi |

Các cell bổ sung trong tài liệu được kiểm cú pháp local; không coi đó là
kiểm thử thành công bằng GPU/API. Khi sửa runtime, cần regression tương ứng
và đồng bộ đúng bản lên Kaggle trước khi chạy lại.
