# Chạy 39 ca với v7 sau khi human review đã đạt

**Cập nhật:** [run20261016T071213Z-7c8c33c6](ATOMIC_VERIFIER_V7_FULL39_REVIEW_20261016T071213Z-7c8c33c6.md)
đã timeout sau5.400 giây;21/22 predictions incomplete, ca completed còn lại
sai nhãn. Không chạy lại nguyên notebook hoặc chỉ tăng timeout; cần sửa
assessment/numeric/deadline trước. Quy trình bên dưới giữ để tái lập lượt v7.

**Probe 18/18 đã đạt, human reviewer tricong đã xác nhận đủ năm tiêu chí của
18 ca và admission local đã đạt.** Dùng đúng notebook mới bên dưới; không cần
chạy lại probe hoặc ký lại review.

[Notebook Colab 39 ca](../scripts/colab_atomic_verifier39_v7.ipynb).
[File human review đã xác nhận](semantic-review-v7-20261016T024708Z-a57ee72a.json).
[Biên bản admission](atomic-verifier-v7-human-admission-20261016T024708Z-a57ee72a.json).

## 1. Thực hiện trên Colab

1. Mở Chrome/Edge, vào Google Colab và chọn **Tệp → Tải notebook lên**.
   Chọn `colab_atomic_verifier39_v7.ipynb`.
2. Chọn runtime mới với **T4 GPU**. Notebook tự chứa source/data/tokenizer v7,
   ZIP probe gốc đã audit và bản human review đúng hash; không cần Drive hoặc
   chép file vào run v7 cũ.
3. Chạy lần lượt **bốn code cell**:
   - Cell 1 kiểm và giải nén payload, giữ ZIP probe gốc và tạo bản copy để review.
   - Cell 2 cài runtime cô lập theo dependency pins đã dùng ở probe.
   - Cell 3 chạy 101 regression, CUDA preflight, cả hai validate-only và kiểm
     human admission bằng chính runner. Chưa tải model ở bước này.
   - Cell 4 chỉ chạy39 sau khi các bước trên đạt; tự tải ZIP kết quả cuối.
4. Lưu ZIP nguyên trạng và notebook có output, rồi gửi ZIP để audit/replay,
   đối chiếu nhãn và review bằng chứng từng ca. Sau khi đã giữ ZIP, dừng GPU.

Giữ nguyên output nếu có lỗi. Không rerun một stage trong cùng run; một lượt
thử khác phải dùng run directory mới. Mỗi run tự có ID riêng.

## 2. Những gì đã hoàn thành

Probe `20261016T024708Z-a57ee72a`: 18/18 cấu trúc hợp lệ, 18 calls, không repair;
39 file output, 69 input files, 26 frozen sources và 54 trace events đều khớp.
101 regression trên Colab cùng hai validate-only đạt. AI đã review 20 parts.

Human reviewer **tricong** đã trả lời trực tiếp trong chat:
“Cả 18 ca đạt cả năm tiêu chí; tôi đã đọc các lưu ý”. Ghi chú từng ca được
đưa vào bản review riêng, gắn prediction/criteria hashes. `require_probe_review`
đã chấp nhận bản này. ZIP và template pending ban đầu giữ nguyên làm lịch sử.

010/014/018 còn metric kèm change verb (`improved recall`, `improved throughput`,
`gained yield`). Binding/property và nội dung predicate được giữ; người review
đã đọc lưu ý này. Đây là deviation của format literal trong prompt, không phải
tuyên bố prompt compliance100%. Không sửa predictions hoặc gate để hợp thức hóa.

## 3. Điều kiện chốt bộ39

Các file kết quả mới ở `output/verifier39/` cần chứng minh:

- Đủ39 ca, đúng39/39 nhãn theo criteria đã đóng băng.
- `false_support=0`, không có runtime failures.
- Số calls, generated tokens và deadline nằm trong budget.
- Provenance/model pairing/source/prompt/criteria khớp; replay khớp từng trace.
- Review từng evidence quote, coverage/population, numeric binding và missing
  information. Nhãn đúng đơn thuần chưa chứng minh sử dụng đúng bằng chứng.

Model/revision, NF4/float16, seed/sampling, dữ liệu và budget không đổi:
tối đa8 calls/ca, hai attempts, 1.536 tokens/call, 180 giây/ca; tối đa312 calls,
479.232 generated tokens, process timeout5.400 giây và watchdog5.520 giây.

**Bộ39 đã chạy một phần và chưa đạt.** False support trong22 rows đã lưu bằng0
nhưng không có nhãn support nào; chưa kết luận cho17 ca còn lại. Probe/human
admission không thay gate full39. Bộ18/39 là development đã đọc, không held-out.
