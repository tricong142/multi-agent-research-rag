# Audit admission Full39 — 20261103T070810Z-84730c0f

Nguồn: ZIP người dùng cung cấp và `semantic-review (8).json`. Audit offline, không chạy model, không sửa output/metrics/review gốc.

## Kết luận

Run thực tế là **atomic-verifier-constrained-v8-cellfix15**, không phải Cellfix16. Full39 đạt **39/39 nhãn đúng**, nhưng admission chưa đạt. **Validation30 chưa bắt đầu inference**: ZIP không có thư mục `validation30/`. `validation30-validate-only` kiểm tra cấu hình, không phải chạy 30 ca.

115 output và 140 frozen inputs đã được kiểm tra hash. Payload/criteria trùng release Cellfix15. Không thể xác định chỉ từ ZIP người dùng mở nhầm notebook hay giữ runtime cũ; có thể xác định chắc chắn code thực thi là bản 15.

| Dấu vết | Run nhận được | Cellfix16 cần chạy |
| --- | --- | --- |
| Candidate | atomic-verifier-constrained-v8-cellfix15 | atomic-verifier-constrained-v8-cellfix16 |
| Criteria SHA256 | `95b79b8589980376c9c3ca45780ac3ac1a809bf13c03b84904616ee7da939e69` | `c025247428698d892e549fb12ad22e19561020b034a2a2276c9dfcaf0cbdc966` |
| Payload SHA256 | `48fd28580285e438b488a401c3d28ad53e8841865b5459fbe3e65d025f3b36af` | `1a0f00f7e31d566408d8beac48522c182e600ba704588a0e57b506348e124fd3` |

## Hai tầng chặn đã tái hiện

1. Worker Cellfix15 thêm `usage_complete: true` khi replay, nhưng producer không lưu field này vào `metrics.json`. Hàm `require_full39` so sánh cả dictionary nên báo `Full39 gate failed on replay`. Đây là khác biệt duy nhất giữa metrics replay và metrics gốc; automated gate replay vẫn true.
2. Bản sửa tương thích đã có chỉ chuẩn hóa diagnostic này khi replay xác nhận usage đầy đủ; không sửa metrics lưu. Sau sửa, cùng artifact bị từ chối với `All semantic criteria and notes are required: contract:causality_missing; missing_information_specific`.

Review khớp criteria/predictions của run 15; lỗi không phải nhầm hash của review. Tuy nhiên, `review_completed: true` chỉ nói đã hoàn tất review; không có nghĩa mọi tiêu chí đạt. Có ba ca chứa judgment false:

| Ca / tiêu chí false | Nội dung ghi chú | Record thực tế trong ZIP |
| --- | --- | --- |
| `contract:causality_missing` / `missing_information_specific` | Thiếu mô tả chứng cứ về quan hệ nhân quả | `missing_information` có “Evidence establishing the claimed causal relationship, beyond co-occurrence/correlation”; quote là “The study did not establish a causal relationship.” |
| `scope:metric:not_enough_info` / `quote_relevant` | Chỉ trích recall, bỏ câu precision không được đo | Observation trích đúng “Precision was not measured.” |
| `scope:condition:not_enough_info` / `explanation_follows_evidence` | Observation dùng high-temperature batches | Observation dùng `low-temperature group`, truth unknown và quote nói nhóm này chưa được đo yield changes. |

Những ghi chú này không mô tả đúng record nhận được. Cần người review kiểm tra lại HTML/predictions tương ứng; audit không tự chuyển judgment sang true hoặc tự ký human review. Nếu người review vẫn thấy lỗi, giữ đánh giá false và ghi lý do dựa trên record thực tế.

## Chạy đúng candidate16

1. Import `scripts/kaggle_atomic_verifier_cellfix16.ipynb` trong runtime Kaggle mới. SHA256 notebook: `05aa83b16c4c93b917d61a7c94cc0d242adc5f3e0f28c68f159c3546599be34b`.
2. Chạy cells 1–5; kiểm tra candidate và criteria hash trong provenance. Có thể chạy kiểm tra chỉ đọc sau khi notebook khởi tạo biến:

   ```python
   print('criteria_sha256:', criteria_sha256)
   assert criteria_sha256 == 'c025247428698d892e549fb12ad22e19561020b034a2a2276c9dfcaf0cbdc966', 'Runtime chưa nạp Cellfix16'
   ```

3. Review probe mới, đặt `PROBE_REVIEW_PATH`; chạy Full39 ở cell6 và review output Full39 mới.
4. Đặt `FULL39_REVIEW_PATH` đúng review Full39 mới ở cell7; chỉ bật `RUN_VALIDATION30=True` sau khi automated và human gates cùng đạt. Không dùng review `(8)` của Cellfix15 cho Cellfix16.

Workflow16 đã chứa bản sửa tương thích diagnostic nói trên. Chạy riêng cell7 không thay candidate15 đã nạp thành candidate16. Không cần sửa release16 hoặc đổi metrics để xử lý artifact15 này. Chưa có bằng chứng inference Full39/Validation30 của Cellfix16 trong ZIP được cung cấp.

Nếu chủ đích vẫn là hoàn tất run15, adapter riêng `scripts/kaggle_cellfix15_cell7_replay_compat.py` xử lý lỗi replay nhưng vẫn từ chối review hiện tại. Kết quả đó vẫn thuộc candidate15, không đo các thay đổi của candidate16.

## Tái hiện

Lệnh từ root repo:

```powershell
.venv\Scripts\python.exe -u -m scripts.audit_cellfix15_review_20261103
```

Báo cáo máy đọc: `docs/atomic-verifier-cellfix15-review-audit-20261103T070810Z-84730c0f.json`.

Archive SHA256: `285777195d506c4e20212920d4b3feb8d97cf40dd2dfe80b5c041fd4367c53c3`.
Review SHA256: `cb1f0b16156a61d61c9603c3621b80b91e10e10425836b9ab86b78e65ba27b88`.
Full39 predictions SHA256: `1928a53c907de0e2f0a0f9b335c4336b1f0601439ddf61819d1e19dda7b57120`.
