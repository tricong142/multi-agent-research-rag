# Candidate v6 — metric validation và repair hữu hạn

Ngày: 2026-10-15. Version: `atomic-verifier-constrained-v6-20261015`.
Hoàn thiện ba phần: bảo toàn v5, sửa validator/repair, regression và đóng gói
candidate mới. Đây là báo cáo kiểm tra lúc chuẩn bị artifact. Sau đó đã audit
[probe T4 v6](DECOMPOSITION_PROBE_REVIEW_20261015T155608Z-9262cfd5.md): 17/18
decomposition hợp lệ, gate false; **chưa hoàn thành bước 2 đánh giá 18/39 ca**.

## Bảo toàn v5

Snapshot có **127 file**: source/prompt/criteria/contract, tokenizer/config,
notebook/build scripts, report và ZIP/output gốc của run
`20261015T103401Z-723b3e4a`. Mỗi file có size/SHA256; ZIP snapshot qua CRC và
kiểm từng entry. Đã chạy `load_frozen()` và replay đủ 18 predictions bằng
source trong snapshot sau khi working tree chuyển sang v6.

- Snapshot: `research-runs/atomic-verifier-v5-source-snapshot-20261015T103401Z-723b3e4a/`.
- ZIP snapshot SHA256:
  `337583ca37fc017e164023dab462540c758906539349d10cdc64de39e00196af`.
- [Đường dẫn đầy đủ và manifest digest](atomic-verifier-v5-preserved-before-v6.json).

Các file criteria, contract và notebook v5 ở workspace vẫn được giữ. Shared
source đang là v6, nên muốn replay v5 phải dùng snapshot, không dùng source v6
với criteria v5. Runner v6 từ chối admission probe v5 vì khác criteria.
Không sửa predictions hoặc điền phiếu human review gốc.

## Thay đổi nhỏ trong shared validator

`metric_predicate_requirement()` kiểm metric chỉ còn một động từ thuộc nhóm
use/take/contain/evaluate, bao gồm một số dạng biến thể. Khi quote còn đối tượng
hoặc đại lượng theo sau, `scope_issues()` trả `metric_predicate_incomplete`.

Validation details ghi rõ `parts[i].scope.metric` và một `required_source` là
span nguyên văn trong **quote của part đó**. Span kết thúc trước time/condition
đã khai báo; từ nằm trong entity/time/condition không bị coi nhầm là predicate.
Các named property như accuracy, latency, pressure, memory vẫn hợp lệ.

Lỗi đi vào repair hiện có, tối đa hai attempts và trong call/time budget cũ.
Hết attempts thì trả incomplete, không gán label support và không gọi assessment
cho plan chưa hợp lệ. Không tự thay metric của model bằng code hậu xử lý.

Ví dụ mới trong regression: `Compilation took seven minutes.` với metric `took`
bị từ chối; metric đầy đủ `took seven minutes` được chấp nhận. Test repair dùng
backend giả và kiểm cả replay; đây không phải bằng chứng model thật đã sửa được.

## Freeze giữ nguyên thiết lập thí nghiệm

- Model/revision, NF4/float16, seed/sampling, dữ liệu và baseline giữ nguyên v5.
- Hai base prompt và JSON decoder enums giữ nguyên. Decoder policy vẫn là
  `atomic-schema-decoding-v3`; không sửa `atomic_decoding.py` trong lượt v6.
- Probe vẫn 18 claim, 36 calls tối đa, 1.536 token/call, hai attempts,
  180 giây/claim, 2.400 giây/process; outer watchdog 2.520 giây.
- Full verifier vẫn 39 ca, tối đa 312 calls; gate 39/39 nhãn đúng, false support
  bằng 0, runtime failures bằng 0; human review vẫn bắt buộc.
- **25 source files** được hash, thêm `test_atomic_metric_v6.py`.
- Criteria SHA256:
  `69b9d45d071d1c4627189f8eeecf3387a3b32b8357b8161ca417f82efc0047ae`.
- Contract SHA256:
  `914f4fb7e7ac492d93c9850981e9194abbe1c48b079c22bee5e44ff3884728cf`.

Script freeze kiểm criteria v5 với release/snapshot, tính lại toàn bộ hash
source, contract và prompt của v6, rồi chạy `load_frozen()`. Không tái sử dụng
hash v5 để bỏ qua kiểm tra. File đã freeze khác bytes sẽ bị từ chối ghi đè.

## Kiểm chứng

- **7 regression mới đạt**, dùng claim mới: generic predicate thiếu object/count,
  named properties, từ trùng trong entity/condition, repair thành công và hết
  attempts, lỗi scope đi cùng lỗi metric, binding riêng cho hai vế AND.
- **87/87 test verifier/summarizer đạt** trong một lượt, 20,454 giây.
- **7/7 test đóng gói đạt**, 59,813 giây: compile notebook, hash/payload,
  giải nén Colab sang runtime độc lập, chạy đủ 87 regression từ payload,
  cả hai validate-only, replay v5 từ snapshot và chặn v5 admission vào v6.
- Hai `validate-only` trực tiếp đạt: probe 18 claim/36 calls và verifier
  39 ca/312 calls. Không tạo output directory hoặc tải model ở chế độ này.
- Revalidate wire plans v5 bằng validator v6: 16 plan qua; 007/008 bị chặn đúng
  lỗi metric với spans `took 12 seconds` và `contained 240 documents`.
  Đây là kiểm offline output cũ, **không phải 18 predictions v6 mới**.
- **285/285 test trong `research_rag/tests` đạt** ở lượt cuối, 72,571 giây;
  cộng 7 test script đóng gói là **292 test cases riêng biệt**. Nhóm 87 test
  verifier/summarizer và 24 test notebook là tập con, không cộng thêm lần nữa.
  [Log suite cuối](atomic-verifier-v6-full-tests.log),
  [log packaging](atomic-verifier-v6-packaging-tests.log),
  [validation JSON](atomic-verifier-v6-validation.json).

Suite toàn repository đầu tiên phát hiện notebook resume validation cũ nhúng
Summarizer và Judge cũ. Hai source hiện tại đều trùng source đã freeze v5,
không phải thay đổi v6. Đã sao lưu notebook cũ và dùng builder hiện có dựng lại,
kiểm toàn bộ 45 payload khớp source. Không sửa assertion hoặc chất lượng gate.
Các notebook phụ thuộc resume/autonomy cũng được dựng lại theo chuỗi builder
sẵn có; giữ bản cũ/hash trước sửa. Sau đó cả 24 test validation-notebook đạt.
[Chi tiết và hash trước/sau](atomic-verifier-v6-legacy-packaging.json).

## Artifact và file thay đổi

| Phần | File |
| --- | --- |
| Metric guard, error và hint repair; policy v6 | `04_factchecker/inference/atomic_verifier.py` |
| Runner mặc định v6 | `research_rag/evaluation/evaluate_atomic_verifier.py` |
| Regression mới | `research_rag/tests/test_atomic_metric_v6.py` |
| Contract tampering test theo candidate đang chạy | `research_rag/tests/test_atomic_experiment.py` |
| Freeze prospective v6 | `scripts/freeze_atomic_verifier_v6.py` |
| Build/kiểm Kaggle và Colab v6 | `scripts/build_atomic_verifier_notebook.py`, `build_colab_atomic_probe.py`, `test_atomic_notebook.py`, `test_colab_atomic_probe.py` |
| Artifact cũ được đồng bộ qua builder | Resume, autonomy, confidence, confidence backends, reader diagnostics, completion, blind verifier mặc định; xem manifest backup bên dưới |

- [Notebook Colab v6 bốn code cell](../scripts/colab_decomposition_probe_v6.ipynb).
- [Notebook Kaggle v6 ba code cell](../scripts/kaggle_decomposition_probe_v6.ipynb).
- [Criteria v6](../research_rag/evaluation/atomic_verifier_criteria_v6.json),
  [contract v6](../research_rag/evaluation/atomic_verifier_contract_v6.json).
- [Release manifest](atomic-verifier-v6-release.json),
  [Colab payload/release manifest](atomic-verifier-v6-colab-release.json).

Lệnh từ workspace root:

```powershell
$env:TEMP = Join-Path (Get-Location) 'research-runs/v6-test-tmp'
$env:TMP = $env:TEMP
.venv/Scripts/python.exe scripts/freeze_atomic_verifier_v6.py
.venv/Scripts/python.exe scripts/build_atomic_verifier_notebook.py
.venv/Scripts/python.exe scripts/build_colab_atomic_probe.py
.venv/Scripts/python.exe -m unittest discover -s research_rag/tests -v
.venv/Scripts/python.exe -m unittest scripts.test_atomic_notebook scripts.test_colab_atomic_probe -v
.venv/Scripts/python.exe -m research_rag.evaluation.evaluate_atomic_verifier --output-dir research-runs/v6-unused --validate-only
.venv/Scripts/python.exe -m research_rag.evaluation.evaluate_atomic_verifier --output-dir research-runs/v6-unused --decomposition-probe --validate-only
```

## Phần tiếp theo và giới hạn

Người dùng đã chạy notebook Colab v6 và gửi ZIP run `20261015T155608Z-9262cfd5`.
Provenance/replay khớp nhưng 007 hết repair, 008 đổi sang quantity-only metric.
Chưa đủ điều kiện chạy 39 ca; hướng candidate tiếp theo được ghi trong báo cáo
probe ở đầu trang. Không dùng kết quả test backend giả để suy ra model thật đã
repair thành công.

Metric guard là kiểm từ vựng hữu hạn, không thay semantic parser hay review
người. Repair có thể tăng latency hoặc vẫn hết hai attempts. Bộ 18/39 vẫn là
synthetic development đã đọc, không phải held-out độc lập. Không thay serving
hoặc tự động promotion; false support của full verifier vẫn chưa đo.
