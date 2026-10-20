# Chạy full39 của cellfix5 sau human review

Human reviewer **Trí Công** đã gửi `semantic-review.json`, đủ 18 ca, 90 tiêu chí
`true` và 18 ghi chú. Runner `require_probe_review()` đã chấp nhận file này cho
probe `20261017T173345Z-905edcb5`. Đây là admission để chạy full39, chưa phải kết
quả của full39.

Notebook: `scripts/colab_atomic_verifier39_cellfix5.ipynb`.
Bản review bảo toàn: `docs/semantic-review-cellfix5-20261017T173345Z-905edcb5-human.json`.
Biên bản admission: `docs/atomic-verifier-cellfix5-human-admission-20261017T173345Z-905edcb5.json`.

## Thao tác trên Colab

1. Upload **colab_atomic_verifier39_cellfix5.ipynb** lên Colab. Chọn runtime
   mới và **GPU T4**. Notebook đã nhúng candidate cellfix5, ZIP probe gốc và
   JSON review đã xác nhận; không cần upload thêm hoặc chạy lại smoke/probe.
2. Chạy lần lượt bốn code cell hoặc Run all:
   - Cell 1 kiểm hash, giải nén source, bảo toàn ZIP probe gốc và tạo
     `reviewed-probe` riêng để nhận human review.
   - Cell 2 cài môi trường cô lập với dependency/CUDA pins của lượt T4 đã chạy.
   - Cell 3 kiểm human admission lại bằng runner, chạy 181 regression, CUDA,
     ba validate-only rồi tải model đúng revision. Admission trượt sẽ dừng
     trước model-cache và inference.
   - Cell 4 chạy 39 ca và tải ZIP kể cả khi lỗi/gate trượt. Watchdog notebook
     là 5520 giây; worker vẫn giữ deadline 5400 giây đã đóng băng.
3. Giữ **ZIP tải cuối cùng**, kể cả trình duyệt thêm `(1)` vào tên. Giữ notebook
   có output nếu có thể. Sau khi tải xong, ngắt runtime GPU.
4. Gửi ZIP mới để audit/replay, đối chiếu nhãn và review bằng chứng từng ca.

Không chạy chồng cell hoặc rerun stage trong cùng run. Nếu lỗi, giữ ZIP/log
trước khi bắt đầu lượt mới; không tự tăng budget hoặc đổi model để bỏ qua gate.

## Điều kiện đạt

Cell kết thúc không tự đồng nghĩa gate đạt. Trong `verifier39/metrics.json`
cần đồng thời:

| Trường | Giá trị yêu cầu |
| --- | --- |
| `n` | 39 |
| `correct_labels` | 39 |
| `false_support` | 0 |
| `runtime_failed_rows` | 0 |
| `automated_gate_pass` | true; mọi check bên trong true |

Sau đó vẫn phải kiểm provenance/replay và từng evidence quote, population,
coverage, numeric binding, scope, missing information. Nhãn đúng không tự
chứng minh mọi lập luận hoặc explanation của model đúng.

## Những gì giữ nguyên

Qwen/Qwen2.5-3B-Instruct revision
`aa8e72537993ba99e69dfaafa59ed015b17504d1`, NF4/float16, seed42;
8 calls/ca, 2 attempts/stage, 1536 tokens/call, deadline 180s/ca;
tổng tối đa 312 calls và 479232 generated tokens. Không đổi source verifier,
prompt, contract, criteria, gold hoặc dataset của cellfix5.

Criteria SHA256:
`642d66612c25514e3764840f750a97cc85c93d4a32a3e4f23bcabff6b993e84c`.
Probe predictions SHA256:
`b555551b7812fd9aa9fcf372715f1551ccd72d1568176de50266c1210c90b014`.
Human review SHA256:
`b1caf56e66a869d7e9c9a3d3b8443449ee3915e1a1a1991304031704364104dc`.

ZIP/predictions/template unsigned gốc được giữ nguyên. Human review chỉ thay
trong bản copy phục vụ admission; các báo cáo AI cũ vẫn là lịch sử trước khi ký.

## Giới hạn kết luận

Full39 cellfix5 chưa chạy tại thời điểm bàn giao notebook. Số 37/39 trong
baseline là kết quả lịch sử. Bộ 18/39 là development data đã được xem nhiều
vòng; kể cả full39 đạt cũng cần đánh giá độc lập để đo generalization.
Reader/Summarizer chưa được ZIP này kiểm E2E với verifier mới; chưa kết luận
toàn dự án Ready. Giữ các lưu ý explanation của `accuracy_conflict` và
`cross_sentence` trong lần review kết quả tiếp theo.
