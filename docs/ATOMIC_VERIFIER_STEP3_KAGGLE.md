# Bước 3 — chạy riêng atomic verifier v1 trên Kaggle

**Notebook hiện hành là probe v4:** xem
[hướng dẫn mới](DECOMPOSITION_PROBE_V4_KAGGLE.md) và
[notebook 18 claim](../scripts/kaggle_decomposition_probe_v4.ipynb).
V2 trượt 12/18; v3 trượt 13/18. V4 đã đóng băng decoder theo JSON schema,
chưa chạy model thật. 39 ca và tích hợp chờ probe/review đạt.
Trang này giữ lịch sử setup2.

**Kết quả hiện hành:** setup2 đã chạy trên Kaggle. 193 tests/preflight/freeze
check đạt; cả 39 ca trượt decomposition. [Báo cáo run và bước tiếp theo](ATOMIC_VERIFIER_REVIEW_20261013T112627Z-d5bd1415.md).
Lượt tiếp theo cần sửa decomposition và freeze version mới trước inference.
Quy trình dưới đây ghi lại cách chạy notebook setup2 đã dùng, phục vụ đối chiếu.

**Cập nhật sửa cell 2:** dùng bản **setup2**. ZIP `20261013T102527Z-d29489cf`
ghi nhận một test local tìm notebook không có trong workspace Kaggle. Test này
đã chuyển sang bộ test đóng gói local; các test runtime vẫn chạy bằng discover.
Xem [chẩn đoán và bản sửa](ATOMIC_VERIFIER_CELL2_FIX_20261013.md).

## 1. Cấu hình đóng băng trước inference

| Mục | Giá trị |
| --- | --- |
| Criteria version | `atomic-verifier-v1-setup2-20261013` |
| Model | `Qwen/Qwen2.5-3B-Instruct` |
| Revision | `aa8e72537993ba99e69dfaafa59ed015b17504d1` |
| Generation | `do_sample=false`, seed 42, NF4, float16 |
| Dữ liệu | 39 development regressions: 12 contracts + 27 scope cases |
| Attempts mỗi stage | Tối đa 2 |
| Calls mỗi claim | Tối đa 8, gồm decomposition và repair |
| Output token mỗi call | Tối đa 1.536 |
| Deadline mỗi claim | 180 giây; bỏ kết quả muộn và không gọi tiếp |
| Tổng calls | Tối đa 312 |
| Tổng output token theo giới hạn cấu hình | Tối đa 479.232 |
| Hard process timeout | 5.400 giây, gồm tải/load model; có thời gian dọn process sau khi ngắt |

Các giới hạn là trần vận hành, không phải dự báo số calls, chi phí hoặc thời
gian cần dùng. Với N part và không repair cần 1 + N calls. Claim quá nhiều part
hoặc repair có thể hết ngân sách và bị ghi incomplete.

Hash của contract, cả hai prompt, source, dữ liệu và baseline được kiểm trước
model loading. Weights/tokenizer/revision và các thiết lập liên quan phải khớp
baseline đã audit trước generation. Source/criteria đã đóng băng nằm trong
notebook; dùng notebook cũ sẽ không chạy candidate mới.

## 2. Gate và cách diễn giải

Gate tự động giữ **39/39 nhãn đúng**, zero false support, zero final runtime
failure, đủ/correct từng dataset group và nằm trong budget. Thiếu prediction,
incomplete hoặc nhãn sai đều không đạt. Runner báo thêm `gold_support_rejected`
để phát hiện policy từ chối các claim có đủ bằng chứng.

Human gate đã chốt: mọi tiêu chí rubric áp dụng phải đạt cho từng ca trong cả
39 ca; cần reviewer độc lập trước tích hợp. Có thể có quote/missing-information
không áp dụng theo từng nhãn, như quy tắc review bước 1. Chỉ đúng nhãn chưa
đủ để kết luận chất lượng ngữ nghĩa đạt.

Baseline là inference `logic_v3` đã audit: **37/39**, hai false support. Được
chấm lại từ output đã lưu, không inference lại. Candidate có nhiều calls và
output budget khác baseline; đây là so sánh cả policy, không cô lập hiệu quả
của riêng prompt hoặc thuật toán số học.

Bộ 39 ca đã được xem trong phát triển, không phải held-out độc lập. Hai câu
có cách diễn đạt cần làm rõ ở review bước 1 vẫn giữ dữ liệu/nhãn gốc trong
lượt này; khi phân xử cần tạo phiên bản dữ liệu mới, không đổi gold để đạt gate.
Kế hoạch dữ liệu độc lập ở [protocol](VERIFIER_INDEPENDENT_EVALUATION_PROTOCOL.md).

## 3. Quy trình ba code cells đã dùng cho setup2

1. Tạo **notebook Kaggle mới**, import
   [kaggle_atomic_verifier_v1.ipynb](../scripts/kaggle_atomic_verifier_v1.ipynb).
   Bật GPU T4 và Internet. Notebook dùng hai dataset hiện có:
   `trcng23/research-rag-five-agents-workspace` và
   `trcng23/research-rag-runtime-diagnostics`. Cell 1 mount hai dataset.
2. Chạy **cell 1**. Nếu mount lỗi, xử lý quyền truy cập dataset trước cell 2.
3. Chạy **cell 2** một lần. Cell tạo run directory có UUID, môi trường riêng
   bằng `venv --without-pip`, bootstrap pip/wrapt, cài runtime đã dùng ở lượt
   trước, kiểm hash, chạy test/preflight và `atomic-freeze-check`.
   Chỉ coi setup đạt khi xuất hiện:
   `SETUP COMPLETE: atomic-verifier-v1-setup2-20261013; runtime tests, preflight and freeze check passed`.
4. Chạy **cell 3** chỉ sau khi cell 2 hoàn thành thành công. Candidate chạy
   trên base model được pin revision; có thể phải tải weights nếu cache chưa có.
   Notebook này chạy verifier riêng, không cần Gemini Secret.
5. Khi cell 3 kết thúc, giữ toàn bộ output. Lưu **Version WITH Output**, tải ZIP
   ở đường dẫn được in cuối cell rồi dừng GPU. Gửi ZIP để đối chiếu.

Không chạy cell 3 lần thứ hai trong cùng run. Nếu stage đã được ghi hoặc process
bị ngắt, giữ ZIP cũ và tạo run mới cho một lượt mới có lý do. Không tăng retry,
token budget hoặc đổi dữ liệu sau khi xem kết quả dưới cùng version criteria.

## 4. Đọc output

| Artifact trong `atomic-verifier/` | Dùng để kiểm |
| --- | --- |
| `summary.json` | Lượt hoàn thành hay bị ngắt; gate và human review |
| `metrics.json` | Accuracy theo số ca, false support, incomplete, support đúng bị từ chối, budget |
| `predictions.jsonl` | Plan, từng part, tool số học, label, lỗi validation và lý do dừng |
| `calls.jsonl` | Call admission trước backend, kết quả/lỗi, timing và generation tokens nếu backend báo |
| `evidence-review.jsonl` | Phiếu review từng ca, judgments ban đầu pending |
| `comparisons.json` | Gold, baseline và candidate cho từng ca |
| `baseline-metrics.json` | Chấm lại kết quả `logic_v3` đã lưu |
| `criteria.json`, `contract.json`, `provenance.json` | Version, hash, model pairing và giới hạn |

Run root còn có `status.json`, logs setup/test/preflight và
`output-manifest.json`; ZIP chứa hash từng file. `call_started` có thể chưa có
`call_finished` khi process bị ngắt. Call đã admission được tính vào budget;
không diễn giải một call đang treo là generation thành công.

| Exit code / trạng thái | Cần làm |
| --- | --- |
| `0`, `automated_gate_pass=true` | Review đủ bằng chứng/part; human gate vẫn pending |
| `1`, `automated_gates_failed` | Lượt có thể đã chạy đủ nhưng chất lượng trượt; giữ ZIP để phân tích lỗi |
| `2`, `worker_error` | Kiểm source/model/setup và provenance; giữ ZIP/log |
| `124`, `process_timeout` | Đã ngắt worker theo budget; giữ trace đã ghi, không coi incomplete là pass |

`overall_pass=false` và `promoted_to_serving=false` được giữ trong mọi output
của thí nghiệm. Chi phí USD để null khi backend không đo được; không suy ra
chi phí bằng 0. Token counts để null nếu backend không cung cấp đầy đủ.

## 5. Kiểm tra local và file mới

- [Contract manifest](../research_rag/evaluation/atomic_verifier_contract.json).
- [Frozen criteria setup2](../research_rag/evaluation/atomic_verifier_criteria_setup2.json).
- [Runner độc lập](../research_rag/evaluation/evaluate_atomic_verifier.py).
- [Script freeze](../scripts/freeze_atomic_verifier.py).
- [Script đóng gói notebook](../scripts/build_atomic_verifier_notebook.py).
- [Test đóng gói local](../scripts/test_atomic_notebook.py).
- [Kết quả bản sửa](atomic-verifier-cell2-fix-20261013.json).
- [Log kiểm thử bản sửa](atomic-verifier-cell2-fix-tests.log): **65/65 tests đạt**,
  gồm 11 test runtime experiment và ba test đóng gói local. Workspace dựng từ
  payload khám phá đủ 11 test và kiểm frozen source/data khi không có notebook.
  13 source đóng băng và 13 file của baseline v3 khớp hash; 27 file payload của
  candidate khớp byte với repo.
- [Kiểm chứng v1 trước sửa](atomic-verifier-step3-validation.json) là lịch sử;
  source/notebook gốc được giữ trong `research-runs/atomic-verifier-setup-v1-20261013`.

Đã kiểm logic runner bằng backend giả lập, kiểm source/data/schema bị sửa phải
chặn trước inference, replay quyết định, pairing model, ghi call-start, timeout
process thật bằng worker ngủ ngắn, ghi summary an toàn khi bị ngắt và payload
notebook. Các test này không chứng minh chất lượng model thật hay môi trường
Kaggle hiện tại; cell 2 kiểm môi trường đó trước khi chạy model.

SHA256 notebook setup2 bàn giao:
`dae74cb08d6f83ad94d7dec073f7f509b93c58eb58bee975cfc2b4092cff083c`.

**Bước 3 đã có kết quả model thật; quality gate trượt.** Tiếp theo sửa và
thử riêng decomposition theo báo cáo run, rồi mới chạy đủ 39 ca bằng version
mới. Chưa chuyển sang bước 4.
