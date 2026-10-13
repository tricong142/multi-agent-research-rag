# Probe decomposition v3 — hướng dẫn lịch sử

**Đã chạy v3:** ZIP `20261013T135905Z-ac194776` có 13/18 decomposition hợp lệ,
5 incomplete; gate trượt. [Đối chiếu và review](DECOMPOSITION_PROBE_REVIEW_20261013T135905Z-ac194776.md).
Notebook hiện hành là [v4](../scripts/kaggle_decomposition_probe_v4.ipynb),
theo [hướng dẫn mới](DECOMPOSITION_PROBE_V4_KAGGLE.md). Các nội dung bên dưới
ghi lại cấu hình và quy trình v3 tại thời điểm bàn giao trước inference.

**Lượt v2 vừa gửi đạt 12/18 cấu trúc; gate vẫn trượt.**
Đã audit/review và sửa candidate v3. Model thật v3 chưa chạy.
Xem [báo cáo ZIP](DECOMPOSITION_PROBE_REVIEW_20261013T131400Z-b05a83bd.md).

## 1. Dùng đúng notebook mới

[kaggle_decomposition_probe_v3.ipynb](../scripts/kaggle_decomposition_probe_v3.ipynb)
có **ba code cell**. SHA256:
`05fcd2daa599031a3e9331851ead3d26b7d04a201a1be679650427c0cf5ca928`.
Frozen version `atomic-verifier-quotes-v3-20261013`.

78/78 test local đạt, gồm contract/repair/leading AND/dataset scope, replay,
gate/budget/checkpoint và dựng lại workspace từ payload notebook.
[Validation](decomposition-v3-validation.json), [test log](decomposition-v3-tests.log).
Các test dùng backend giả lập; chất lượng model thật v3 còn chờ probe.

1. Tạo notebook Kaggle mới và import file trên. Bật Internet và GPU T4;
   hai dataset workspace/runtime hiện có tiếp tục được dùng.
2. Chạy cell 1 lấy dataset.
3. Chạy cell 2. Chỉ đi tiếp khi hiện:

   ```text
   SETUP COMPLETE: atomic-verifier-quotes-v3-20261013; runtime tests, preflight and freeze check passed
   ```

   Freeze check phải báo `freeze_valid=true`, `cases=18`, `maximum_calls=36`.
4. Chạy cell 3 **một lần**. Cell chạy riêng decomposition 18 claim và lưu ZIP,
   kể cả khi gate trượt. Không cần Gemini Secret cho probe này.
5. Save Version **WITH Output**, tải ZIP được in cuối cell, gửi lại để đối chiếu
   và review. Dừng GPU sau khi lưu. Giữ ZIP gốc.

Không chạy lại notebook v2 hoặc sửa kết quả cũ. Stage helper giữ bằng chứng và
chặn chạy lại cùng stage vào cùng output; lượt mới cần run ID mới.

## 2. V3 sửa gì

- Leading AND ở đầu một part sau part đầu được chấp nhận; AND giữa hai factual
  predicates trong một part vẫn phải tách. Offset luôn gắn với quote nguyên văn.
- Scope repair có tên trường sai; copy chữ hoa/thường và từ liền nhau chính xác.
- Syntax repair tạo lại JSON từ input, không đưa malformed JSON trở lại dưới
  dạng assistant answer. Đây là thay đổi chính sách cần đo bằng lượt mới.
- Prompt yêu cầu metric nhận diện property có tên, không chỉ generic change
  verb; phân biệt time với dataset/condition; giữ đầy đủ restriction trong quote.
- Guard code cho explicit `on/using/under ... dataset` yêu cầu condition và từ
  chối gắn restriction đó vào time. Các loại scope khác vẫn cần semantic review.

Không đổi model/gold/dữ liệu hoặc nới gate. 18 claim là development đã thấy,
không phải test độc lập. File data giữ tên `decomposition_probe_claims_v2.jsonl`
để dùng đúng cùng bytes; criteria/contract/policy của lượt mới là v3.

## 3. Giới hạn đã chốt

Pinned Qwen2.5-3B-Instruct revision
`aa8e72537993ba99e69dfaafa59ed015b17504d1`, NF4, float16, seed 42,
`do_sample=false`. Tối đa 2 calls/claim, 2 attempts, 1.536 output tokens/call,
180 giây/claim; tổng 36 calls và 55.296 generated tokens. Hard process timeout
2.400 giây gồm tải/load model; watchdog notebook 2.520 giây.
Đây là caps, không phải dự đoán runtime/cost. USD null nếu backend không đo.

Gate tự động cần:

```text
stage decomposition-probe: state=completed, exit_code=0
summary: experiment_completed=true, automated_gate_pass=true
metrics: n=18, valid_decompositions=18, incomplete=0
```

Exit 1 là gate trượt; 124 là timeout. Có ZIP để review trước khi quyết định sửa
hay chạy lại. Không bỏ assert hoặc đổi `automated_gate_pass` bằng tay.

## 4. Review để chuyển sang 39 ca

Đọc `predictions.jsonl`, `evidence-review.jsonl`, `calls.jsonl` và
`semantic-review.json`. Kiểm đủ năm tiêu chí cho từng claim:

1. Part là factual predicate, không phải subject/number/condition fragment.
2. Giữ đủ nội dung, phủ định, số/đơn vị, causal relation và restriction.
3. Giữ đúng all/some/none/atomic, kể cả quantifier dùng chung giữa các vế.
4. Entity và metric đúng với property/predicate của part; exact string chưa đủ
   để chứng minh binding về ngữ nghĩa.
5. Time và condition đúng loại, đầy đủ, được dùng chung đúng phạm vi.

Phiếu human bắt đầu pending, không tự điền true. Người review điền tên,
`reviewer_kind=human`, notes riêng và năm judgments cho đủ 18 ca sau khi đọc.
Giữ nguyên hash liên kết tới predictions/criteria; review trên bản sao làm việc,
ZIP gốc không thay đổi. Assistant review phục vụ triage, không thay người đánh giá.

Sau probe đạt cả hai gate, runner CLI mới cho chạy 39 ca qua `--probe-dir`.
Lượt đó phải đạt 39/39 nhãn, zero false support/failure và review evidence,
explanation, missing information, từng part và numeric tool. Candidate thay đổi
sau probe phải freeze và probe lại. Reader, Summarizer và tám ca E2E theo sau
gate verifier; hiện chưa đủ bằng chứng để nghiệm thu toàn hệ.
