# Atomic verifier v5 — sửa bug 6, 8, 9, 10

Ngày kiểm tra: 2026-10-15. Mã phiên bản giữ theo candidate đã đặt tên:
`atomic-verifier-constrained-v5-20261013`. Đây là bản đóng băng offline;
chưa có kết quả inference Qwen/CUDA v5 hay duyệt ngữ nghĩa độc lập bằng người.

Cập nhật khi chạy Kaggle ngày 2026-10-15: setup phát hiện lỗi overlap hash ở
`test_summary_trace.py`, trước model loading. Builder đã bổ sung hash từ manifest
diagnostics đã xác minh; ba test đóng gói đạt sau khi thêm fixture file gốc có sẵn.
Giữ nguyên core/prompt/criteria v5, dựng lại notebook và manifest phát hành.
[Bằng chứng lỗi và bản sửa đóng gói](atomic-verifier-v5-kaggle-packaging-fix.json).

## Thay đổi và nguyên nhân

| Bug | Nguyên nhân | Cách sửa và file chính |
| --- | --- | --- |
| 6 | Parse JSON thành công không bảo đảm có đúng trường hoặc đúng kiểu dữ liệu. | `train_agent3_summarizer/node.py`: kiểm schema riêng cho Generator/Critic trước khi đọc trường; Generator lỗi bỏ qua Critic, đưa lỗi vào retry hiện có; hết 3 vòng trả unsupported/low confidence. Trace phân biệt `json_valid`, `schema_valid`, `schema_issue`. |
| 8 | Runner/builder đã dùng v5 nhưng criteria và notebook chưa được dựng. | Chạy `scripts/freeze_atomic_verifier.py` từ source/prompt/contract/data thực tế, rồi `scripts/build_atomic_verifier_notebook.py`. Builder gọi `load_frozen` trước đóng gói. Không chép criteria v4 hoặc bỏ kiểm hash. |
| 9 | Validator và schema lấy toàn bộ restriction trong claim rồi bắt mọi part giữ tất cả. | `04_factchecker/inference/atomic_verifier.py`, `atomic_decoding.py`: bind restriction theo vế AND; chỉ tiền tố time/dataset có dấu phẩy ở đầu câu được dùng chung. Schema dùng các object alternative gắn quote với scope tương ứng. Cấu trúc không biểu diễn được dừng `unsupported_scope_structure` trước backend call; replay kiểm lại cả trường hợp 0 call này. |
| 10 | Một phép so sánh đang bị yêu cầu bao phủ toàn bộ các số trong part. | `numeric_verifier.py`, `atomic_verifier.py`: code tạo `numeric_requirements` theo từng lần xuất hiện, gồm offset trong quote, số, unit/đối tượng và quote. Observation chấp nhận danh sách phép kiểm, kiểm từng bằng chứng và tổng hợp độ phủ. Thiếu một yêu cầu không thể support; số sai có bằng chứng có thể contradict. Không tái sử dụng một phép kiểm cho hai yêu cầu. |

Ví dụ `four models on two datasets` có hai yêu cầu độc lập: `four models`
và `two datasets`. Hai đối tượng có cùng số lượng cũng giữ hai record riêng.
Record số liệu dạng object đơn trước đây vẫn được chấp nhận; schema assessment
hiện chấp nhận null, object đơn hoặc danh sách 1–16 object.

## Kiểm chứng

- Regression/experiment/đóng gói: 83 test đạt; có token filter thật của
  lm-format-enforcer, tokenizer nhỏ và model giả lập. Test model không tải weights.
- Autonomy/E2E/graph safety/integration: 55 test đạt.
- `validate-only`: cả 39 ca verifier và 18 ca decomposition probe đạt freeze gate;
  không gọi model và không tạo thư mục inference output.
- Notebook có ba code cell, biên dịch được; test giải nén đúng payload vào runtime
  tạm, đối chiếu byte/hash với source, discover experiment tests và chạy freeze
  test/validate-only từ runtime đó. Test xác minh luôn manifest phát hành.
- Dữ liệu, model revision và ngân sách giữ nguyên: 39 ca/312 calls hoặc probe
  18 ca/36 calls; 1.536 token/call, tối đa 2 attempts. Không hạ quality gate.

Lệnh kiểm regression từ workspace root, dùng Python của `.venv`:

```powershell
# Sandbox Windows từ chối replace file trong TEMP mặc định; dùng thư mục workspace.
New-Item -ItemType Directory -Path research-runs/v5-test-tmp -Force | Out-Null
$env:TEMP = Join-Path (Get-Location) 'research-runs/v5-test-tmp'
$env:TMP = $env:TEMP
.venv/Scripts/python.exe -m unittest research_rag.tests.test_summary_schema research_rag.tests.test_summary_trace research_rag.tests.test_atomic_verifier research_rag.tests.test_atomic_decoding research_rag.tests.test_atomic_decomposition_v5 research_rag.tests.test_atomic_contract_v5 research_rag.tests.test_atomic_experiment scripts.test_atomic_notebook -q
.venv/Scripts/python.exe -m unittest research_rag.tests.test_autonomy research_rag.tests.test_e2e_regressions research_rag.tests.test_graph_safety research_rag.tests.test_integration -q
.venv/Scripts/python.exe -m research_rag.evaluation.evaluate_atomic_verifier --output-dir research-runs/v5-validate-only --validate-only
.venv/Scripts/python.exe -m research_rag.evaluation.evaluate_atomic_verifier --output-dir research-runs/v5-validate-only --decomposition-probe --validate-only
```

## Artifact và phạm vi

- [Notebook v5](../scripts/kaggle_decomposition_probe_v5.ipynb).
- [Criteria v5](../research_rag/evaluation/atomic_verifier_criteria_v5.json): hash
  source, hai prompt atomic, contract, dữ liệu, baseline và cấu hình model/decoder.
- [Contract v5](../research_rag/evaluation/atomic_verifier_contract_v5.json).
- [Manifest phát hành](atomic-verifier-v5-release.json): hash notebook, criteria,
  contract và hai script freeze/build.

Regression mới ở `research_rag/tests/test_summary_schema.py` và
`test_atomic_contract_v5.py`; cập nhật `test_summary_trace.py`,
`test_atomic_decoding.py`, `test_atomic_decomposition_v5.py`,
`test_atomic_experiment.py`, cùng `scripts/test_atomic_notebook.py`.
`research_rag/evaluation/evaluate_atomic_verifier.py` cập nhật replay cho preflight.
Không thêm dependency hay đổi kiến trúc serving.

Lần chạy experiment đầu gặp `WinError 5` khi replace checkpoint trong TEMP của
sandbox; chạy lại với TEMP/TMP nằm trong workspace đã đạt. Không thay cơ chế ghi
checkpoint để che lỗi quyền. Test deadline có chủ ý in dòng `process_timeout`;
kết quả test phải đọc theo exit code và tổng kết unittest.

Giới hạn: grammar vẫn là English AND và scope đơn giản. Unit/count noun được
gắn bằng từ ngay sau số; liên kết ngữ nghĩa phức tạp vẫn cần review. Arithmetic
và exact quote không tự chứng minh entailment hay population completeness.
Notebook Kaggle đã thử setup, rồi lỗi worker authentication trước model;
chưa có inference v5. Bản Colab giữ nguyên freeze, giải nén độc lập vượt qua
80 regression tests và cả hai validate-only local (2 test packaging Colab đạt).
Colab trong trình duyệt agent lỗi tải Monaco; người dùng chạy bằng Chrome/Edge.
ZIP run `20261015T103401Z-723b3e4a` đã kiểm: 80 regression tests trên T4 và hai
validate-only đạt; probe 18/18 cấu trúc, 18 calls, replay khớp. Review AI đủ 20
parts: 16/18 claim đạt, 007/008 còn bare metric `took`/`contained` trái prompt.
Human review và bộ 39 ca vẫn chờ; false support chưa đo.
Xem [review](DECOMPOSITION_PROBE_REVIEW_20261015T103401Z-723b3e4a.md) và
[trạng thái bước 2](ATOMIC_VERIFIER_V5_STEP2_20261015.md).
