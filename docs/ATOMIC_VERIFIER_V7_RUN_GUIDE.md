# Chạy probe v7 và hoàn thành review trước 39 ca

Candidate: `atomic-verifier-constrained-v7-20261016`.
Notebook: [colab_decomposition_probe_v7.ipynb](../scripts/colab_decomposition_probe_v7.ipynb).
Probe này đã được người dùng chạy: [run20261016T024708Z-a57ee72a](DECOMPOSITION_PROBE_REVIEW_20261016T024708Z-a57ee72a.md)
đạt18/18 và human admission hoàn tất. **Không cần chạy lại probe**; chuyển sang
[hướng dẫn39](ATOMIC_VERIFIER_V7_FULL39_RUN_GUIDE.md). Quy trình probe tổng quát
bên dưới giữ để tái lập. Mỗi output mới vẫn cần review/hash riêng.

## 1. Chạy notebook trên T4

1. Mở Google Colab bằng Chrome/Edge, chọn **Tệp → Tải notebook lên** và chọn
   đúng file `colab_decomposition_probe_v7.ipynb` ở liên kết trên.
2. Chọn **Thời gian chạy → Thay đổi loại thời gian chạy → T4 GPU**.
   Dùng một runtime mới; không chép source v7 vào thư mục run v6.
3. Chạy lần lượt bốn code cell. Cell 1 giải nén và kiểm hash; cell 2 cài runtime
   cô lập; cell 3 chạy regression, CUDA preflight và cả hai validate-only;
   cell 4 chạy probe 18 claim và tải `output.zip`.
4. Giữ ZIP nguyên trạng và gửi ZIP đó để kiểm provenance, replay và review.
   Lưu lại notebook có output. Sau khi đã giữ ZIP, có thể dừng GPU.

Nếu stage lỗi, giữ nguyên ZIP/log lỗi. Không chạy lại cell cuối trong cùng run;
một lượt thử khác phải có run directory mới. Notebook tự tạo ID riêng cho run.

## 2. Đọc kết quả tự động

Trong `output/decomposition-probe/`:

| File/trường | Điều kiện cần |
| --- | --- |
| `metrics.json`: `n` | 18 |
| `metrics.json`: `valid_decompositions` | 18 |
| `metrics.json`: `incomplete` | 0 |
| `metrics.json`: `automated_gate_pass` | true |
| `summary.json`: `experiment_completed` | true |
| `summary.json`: `automated_gate_pass` | true |
| `semantic-review.json` | Ban đầu vẫn pending, chưa có người ký |

Ngân sách giữ nguyên: 2 attempts/claim, tối đa 36 calls, 1.536 generated
tokens/call, 180 giây/claim, 2.400 giây cho process probe; watchdog ngoài 2.520
giây. Không tăng ngân sách để vượt gate. Probe không gọi evidence assessment,
nên không có accuracy hay false-support rate của verifier ở bước này.

007 cần metric đầy đủ `took 12 seconds`; 008 cần `contained 240 documents`.
Đây chỉ là hai lỗi đã biết. Vẫn phải đọc output thực tế của cả 18 claim.

## 3. Human review trên đúng predictions mới

Sau khi ZIP mới được kiểm toàn vẹn và replay, tôi sẽ đưa bảng đầy đủ claim,
từng part, quantifier, entity, metric, time, condition và numeric requirements
để bạn review. Review AI là tài liệu hỗ trợ, không thay thế người review.

Bạn kiểm cả năm tiêu chí ở **mỗi claim**:

1. `factual_predicates_not_fragments`: mỗi part là factual predicate đầy đủ;
   không tách chủ thể, số liệu hoặc điều kiện thành một fact riêng.
2. `all_requirements_preserved`: không mất yêu cầu, quan hệ, số, đơn vị hay
   đối tượng; nhiều đại lượng độc lập phải còn đủ.
3. `quantifier_preserved`: `all/some/none/atomic` đúng, population modifiers
   còn nguyên và chủ thể dùng chung được kế thừa đúng.
4. `entity_metric_binding_correct`: đúng chủ thể và thuộc tính; nếu không có
   named property thì metric giữ đủ predicate cùng object/quantity.
5. `time_condition_scope_correct`: restriction thuộc đúng vế; chỉ kế thừa
   prefix thực sự dùng chung; dataset nằm trong condition.

Trong `semantic-review.json`, giữ nguyên `predictions_sha256`,
`criteria_sha256` và 18 `example_id`. Mỗi ca cần năm judgment thực tế và một
ghi chú riêng giải thích điều đã kiểm. Điền đúng tên người đã đọc, đặt
`reviewer_kind="human"` và chỉ đặt `review_completed=true` sau khi người đó
hoàn tất cả 18 ca. Giữ bản template gốc trong ZIP; lưu bản đã review riêng.
Nếu có bất kỳ ca chưa đạt, giữ trạng thái đó và sửa candidate trước khi chạy39.

## 4. Kiểm admission rồi mới chạy 39 ca

Lệnh sau chạy trong workspace v7 bằng Python có các dependency hiện có;
không tải model và sẽ báo lỗi nếu review/predictions/provenance chưa đạt:

```python
from pathlib import Path
from research_rag.evaluation.evaluate_atomic_verifier import require_probe_review
print(require_probe_review(Path("<thu-muc-probe-da-review>")))
```

Chỉ khi lệnh admission đạt, dùng Python của venv trong notebook v7 để chạy:

```text
<venv>/bin/python -m research_rag.evaluation.evaluate_atomic_verifier --output-dir <thu-muc-output-moi> --probe-dir <thu-muc-probe-da-review> --online-model-downloads
```

Nếu Colab đã mất runtime, khôi phục đúng payload v7 và thư mục probe đã review
trước. Không dùng predictions v5/v6 hoặc đổi hash để ghép với criteria v7.
Runner tự kiểm admission trước khi model loader chạy; không có cờ bỏ qua.

Bộ39 cần 39/39 nhãn đúng, false support 0, runtime failures 0 và review bằng
chứng từng ca. Bộ18/39 là dữ liệu development đã đọc, không chứng minh
generalization và chưa cho phép promotion sang serving.
