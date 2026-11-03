# Cellfix13 smoke/probe — đủ điều kiện chuyển sang human review probe

Run: `20261027T113721Z-18c80dae`.
ZIP: `output-cellfix13-fresh-20261027T113721Z-18c80dae (2).zip`.
ZIP SHA256: `badf556e5137b1c47a780a05cfae03b81ff4115d4c62a287230c17c0a47040fd`.
Criteria SHA256: `fc4d4a8f7baaf88886cbd3047819125752867e7cdb2f2a8fb850f4be293abb4c`.
Probe predictions SHA256: `572b3307c1310d6af4ace391837e3624f94044a8d8094ffd3c403640a43d40ec`.

## Kết quả đã xác minh

| Hạng mục | Kết quả |
|---|---|
| Provenance | 71 output/131 input khớp hash/manifest và frozen Cellfix13 release |
| Regression Colab | 385/385 đạt |
| Validate-only | Cả bốn chế độ đạt cấu hình; validation30 chưa inference |
| Smoke12 | 12/12 nhãn đúng, false support=0, runtime=0, 28 calls |
| Probe18 | 18/18 decomposition hợp lệ, 20 parts, 18 calls, không incomplete |
| Model/config | Đúng revision/quantization/seed/prompt/source; budget/gate không đổi |
| Replay | 30 prediction rows/46 call triplets được đối chiếu, metrics tính lại khớp |
| Human probe review | Chưa có: reviewer trống, review_completed=false |
| Full39/Validation30 | Chưa inference cho run/candidate này |

Smoke generated 3.548/prompt 38.817 tokens; probe generated 972/prompt 22.892,
đều trong ngân sách. Mọi stage trong status.json completed/exit0.
Các quote, numeric operands/checks, normalization và aggregate labels được replay
bằng đúng source đã phát hành; audit không chạy model mới hoặc sửa outputs.

## Rà soát nội dung

- Đọc lại đủ 18 claim/20 part và năm tiêu chí decomposition. AI đánh giá
  90/90 đạt; đây là **review AI, không phải chữ ký human**.
- 006 giữ cả 4 models và 2 datasets với requirement riêng. 007/008 giữ metric
  đầy đủ `took 12 seconds`/`contained 240 documents`; các named properties
  recall, throughput, yield không bị thêm động từ không cần thiết.
- 014: in May lọc population weekly trials conducted in May; không suy ra
  improvement diễn ra trong May. 018: low-temperature là population condition,
  after the update là time. 017 giữ extractor và After tuning cho cả hai part.
- Smoke `contract:irrelevant` đã đúng dạng mới: observations=[], scope unknown,
  missing target=Model Juniper; không còn lấy câu absence làm member.
- Smoke còn giữ đúng causal_relationship, counterexample ALL, hai quantity
  ở hai câu, denial/units và bounded dataset scope.

18/18 ở probe đo decomposition, **không đo label accuracy hay false support
của 18 claim**. Smoke chỉ kiểm 12 ca gốc; chưa đủ để kết luận cả sáu lỗi semantic
của full39 Cellfix12 đã hết. Những ca NONE/conjunction/condition cần output
full39 Cellfix13 và review mới.

## Bước tiếp theo

1. Mở `HUMAN_REVIEW_WITH_AI_NOTES.html` đúng run này (hoặc form gốc từ ZIP).
   Đọc đủ 18 claim/20 part, xác nhận từng tiêu chí và ghi chú; tên reviewer
   và checkbox không được điền sẵn. Xuất semantic-review.json, kể cả review
   có ca trượt để lưu bằng chứng. Review AI không mở gate full39.
2. **Chỉ khi human probe review đủ 90 tiêu chí thật sự đạt**, bật
   RUN_FULL39=True tại cell6, upload review probe của run này. Giữ runtime
   hiện tại; chạy lại cell1 sẽ tạo run mới và cần review khớp predictions mới.
3. Giữ RUN_VALIDATION30=False. Full39 phải đạt automated gate và human review
   39 ca bằng form mới trước khi chạy cell7. Không dùng review Cellfix12 hoặc
   review probe18 thay cho review full39.

Chi tiết nhận xét từng claim nằm trong `DECOMPOSITION_REVIEW.md` và
`AI_REVIEW.json`. Báo cáo machine-readable:
`docs/atomic-verifier-cellfix13-smoke-probe-audit-20261027T113721Z-18c80dae.json`.

Hash/provenance xác nhận tính nhất quán artifacts, không phải remote-host
attestation. Chưa đo generalization/Validation30, chưa promote serving hoặc
kiểm Reader/Summarizer E2E trong lượt này.
