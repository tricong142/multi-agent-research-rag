# Probe v4 — schema-constrained decoding

V3 đạt 13/18 cấu trúc và chưa qua gate. V4 đã chuẩn bị; chưa có model inference.
[Báo cáo ZIP và review 18 ca](DECOMPOSITION_PROBE_REVIEW_20261013T135905Z-ac194776.md).

## Chạy ba cell

Dùng [kaggle_decomposition_probe_v4.ipynb](../scripts/kaggle_decomposition_probe_v4.ipynb).
SHA256:
`8439265ba4f34fd48ea49e251905719aa7fc5e93bd704db43b49f9917d484e1a`.
Phiên bản `atomic-verifier-constrained-v4-20261013`.

1. Tạo notebook Kaggle mới, import file trên; bật GPU T4 và Internet. Hai
   dataset workspace/runtime hiện có được dùng; không cần Gemini Secret.
2. Chạy cell 1 lấy dataset.
3. Chạy cell 2 đến khi hiện:

   ```text
   SETUP COMPLETE: atomic-verifier-constrained-v4-20261013; runtime tests, preflight and freeze check passed
   ```

   Stage `structured-decoder` phải exit 0 trước pip-check/test. Freeze check
   báo `freeze_valid=true`, `cases=18`, `maximum_calls=36`.
4. Chạy cell 3 một lần. Cell chỉ đo decomposition 18 claim, lưu token-constraint
   metadata/schema hash cho từng generation, predictions và phiếu review.
5. Save Version **WITH Output**, tải đúng ZIP in cuối cell, gửi lại để đối chiếu
   và review; dừng GPU. Giữ ZIP gốc.

Notebook đã sửa kiểm hash cho adapter cập nhật; không bỏ assert hoặc pip-check.
Stage lỗi vẫn lưu ZIP. Không chạy lại v3 hoặc lặp stage vào cùng output.

## Điều kiện đi tiếp

```text
decomposition-probe.state=completed
decomposition-probe.exit_code=0
summary.experiment_completed=true
summary.automated_gate_pass=true
metrics.valid_decompositions=18
metrics.incomplete=0
metrics.checks.structured_decoding_trace_complete=true
```

Tiếp đó review đủ 18 claim: predicate thật, đủ yêu cầu, quantifier đúng,
entity/metric đúng, time/condition/population đủ. Đặc biệt giữ modifier như
audited/monitored và property cụ thể; chỉ đúng JSON hoặc đúng source string
chưa đủ. `semantic-review.json` bắt đầu pending. Người review điền tên,
`reviewer_kind=human`, notes riêng và judgments sau khi đọc; giữ nguyên hash
predictions/criteria, review trên bản sao làm việc. Assistant triage không
thay independent human review và không tự điền true.

Gate thất bại thì gửi ZIP để phân tích. Exit 1 là quality gate trượt, 124 là
timeout; không đổi flag hoặc tăng ngân sách mà giữ nguyên tên phiên bản.

## Cấu hình đã đóng băng

Qwen2.5-3B-Instruct revision `aa8e72537993ba99e69dfaafa59ed015b17504d1`, NF4,
float16, seed 42, `do_sample=false`, beam 1, repetition penalty 1.05.
LMFE 0.11.3 + interegular 0.3.3; source enum tối đa 80 từ/claim. Các 18 claim
giữ nguyên bytes; chúng là development đã thấy, không phải held-out độc lập.

Tối đa 2 calls/claim, 2 attempts, 1.536 output tokens/call, 180 giây/claim;
tổng 36 calls và 55.296 generated tokens. Hard timeout 2.400 giây gồm tải/load
model và dựng tokenizer tree; watchdog notebook 2.520 giây. Runtime/cost mới
chưa đo; USD null nếu backend không đo. Token cap vẫn có thể cắt JSON dở dang.

83 runtime tests và 3 packaging tests đã đạt với core cuối/notebook cuối;
[validation](decomposition-v4-validation.json), [log](decomposition-v4-tests.log).
Các test token filter dùng thư viện thật và tokenizer nhỏ, không dùng Qwen weights.

Sau probe và review đạt, runner 39 ca yêu cầu `--probe-dir` đúng phiên bản và
decoder trace. Lượt đó phải đạt 39/39 nhãn, zero false support/failure và review
evidence, explanation, missing information, đầy đủ mọi part/số liệu/qualifier.
Tiếp theo mới tích hợp, hoàn thiện Reader/Summarizer và tám ca E2E.
