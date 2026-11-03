# Cellfix16 smoke/probe — đã hoàn thành Human Review Probe, sẵn sàng cho Full39

Run: `20261103T091648Z-c8c48869`.
ZIP: `output-cellfix16-kaggle-20261103T091648Z-c8c48869.zip`.
ZIP SHA256: `b8e4585a71a5c6fa95a311ef20555f5cec35cc388a8e8eb0680434be9f4b97b0`.
Criteria SHA256: `c025247428698d892e549fb12ad22e19561020b034a2a2276c9dfcaf0cbdc966`.
Probe predictions SHA256: `4c44ecdb7863ca0cd76be2450233840756872a6205cd5816896d6c1dcdf29dc2`.

## Kết quả đã xác minh

| Hạng mục | Kết quả |
|---|---|
| Provenance | 71 output/144 input khớp hash/manifest và frozen Cellfix16 release |
| Regression Kaggle | 422/422 đạt |
| Validate-only | Đạt cả 4 cấu hình: smoke12/probe18/full39/dev30 |
| Smoke12 | 12/12 nhãn đúng, false support=0, runtime=0, 28 calls |
| Probe18 | 18/18 decomposition hợp lệ, 20 parts, 18 calls, không incomplete |
| Model/config | Qwen2.5-3B-Instruct (NF4, float16, seed 42, do_sample=false) |
| Ngân sách token | Probe generated 994 / prompt 24.026 tokens (nằm sâu trong budget 55.296 tokens) |
| Human probe review | Đã hoàn tất bởi reviewer: Trí Công (`reviewer_kind: human`, 18/18 ca, 90/90 tiêu chí đạt kèm ghi chú riêng) |
| Full39/Validation30 | Chưa inference; sẵn sàng chạy cell 13 trên Kaggle |

## Chi tiết rà soát ngữ nghĩa 18 ca (Probe)

- **001**: Tách đúng hai predicate độc lập `uses 25% less memory` và `retains 94% accuracy`, giữ trọn 25% và 94%, atomic.
- **002**: 1 part `Model Juniper retains 94% accuracy.`, giữ nguyên 94%, atomic.
- **003**: 1 part `The study used human labels.`, giữ hành động used và đối tượng human labels.
- **004**: Giữ nguyên causal predicate `caused the latency improvement`, không suy giảm thành tương quan.
- **005**: Quantifier `all` trên `tasks`, predicate `improved`, time `after compression`.
- **006**: Đầy đủ 2 requirements: `4 models` và `2 datasets`, không gộp/tách sai.
- **007**: Giữ `took 12 seconds` là duration metric, time rỗng đúng chuẩn.
- **008**: Giữ `contained 240 documents` là dung lượng mẫu, time rỗng.
- **009**: Entity `method`, metric `recall`, condition `On the tested dataset`.
- **010**: Quantifier `all` trên `validation shard`, metric `recall`, time `after the revision`.
- **011**: Quantifier `some` cho `At least one`, entity giữ modifier `audited cache node`, metric `response time`, time `after the patch`.
- **012**: Quantifier `none`, entity `monitored pumps`, metric khẳng định `leaked`, time `during the overnight test`.
- **013**: Entity `North gateway`, metric `error rate`, time `after calibration`.
- **014**: Quantifier `all` trên `weekly trial`, condition `in May`, metric `throughput`.
- **015**: Entity `patch`, metric `median request latency` không bị rút gọn.
- **016**: Entity `configuration change`, metric `precision`.
- **017**: Tách đúng 2 predicate `decreased memory use` và `increased token recall`, kế thừa `After tuning` và `extractor`.
- **018**: Quantifier `all` trên `batch`, condition `in the low-temperature group`, time `after the update`, metric `yield`.

## Bước tiếp theo (Chạy Full39 trên Kaggle)

1. Upload `semantic-review.json` lên Kaggle (hoặc ghi thẳng vào runtime).
2. Tại Cell 13 (Cell Full39), cập nhật:
   ```python
   PROBE_REVIEW_PATH = "/kaggle/working/semantic-review.json"  # hoặc đường dẫn file đã upload
   RUN_FULL39 = True
   ```
3. Chạy Cell 13.
4. Tải ZIP kết quả mới có chứa kết quả `verifier39` để đối chiếu và thực hiện human review 39 ca.

