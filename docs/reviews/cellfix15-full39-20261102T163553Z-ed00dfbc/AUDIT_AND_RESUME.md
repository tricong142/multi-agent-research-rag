# Cellfix15 full39 đạt; sửa tương thích replay cho cell7 — 2026-11-03

Run: `20261102T163553Z-ed00dfbc`.
ZIP SHA256: `10c90307e891c845310fbc7083d0646abda9520e14a63a907299913920f7b104`.
Criteria: `95b79b8589980376c9c3ca45780ac3ac1a809bf13c03b84904616ee7da939e69`.

## Kết quả đã kiểm chứng

- 115 output files khớp output manifest; 140 payload inputs khớp release.
- Replay smoke12, probe18, full39 và tái tính metrics khớp các trường đã lưu.
- Full39: **39/39 đúng nhãn**, 0 false support, 0 runtime failures;
  support12/12, contradict12/12, NEI15/15. 85 backend calls,
  9224 generated tokens, 122329 prompt tokens. Mọi automated check đạt.
- `scope:none:not_enough_info` hoàn tất trong 2 calls. Model thực sự ghi
  member Silver, truth unknown, dùng đúng quote về trạng thái chưa báo cáo;
  validator trả NEI. Không sử dụng record sửa tay làm kết quả model.
- Probe review đã admission. JSON full39 review được giữ trong review-attempts,
  bound đúng predictions SHA `59858b700df93bd2a030d2ad07c988018ba00ca0cc528f1cf47084751c275f91`.
  Admission tương thích đọc review này bằng human gate gốc đã đạt.
- Validation30 chưa được gọi trong ZIP này. Audit không gọi model mới.

## Root cause

`evaluate_atomic_verifier.py` ghi metrics full39 không có diagnostic
`usage_complete`. `atomic_workflow_cellfix15.measured_score` tái tính cùng metrics,
nhưng thêm `usage_complete=True`. `require_full39` so sánh hai dictionary bằng
toán tử `!=`, vì vậy từ chối dù toàn bộ giá trị đo và automated checks khớp.

Đây là lỗi tích hợp trong workflow đóng gói; kiểm offline trước đó chưa bao phủ
admission thật với định dạng metrics do runner full39 tạo.

## Phạm vi sửa

Không chỉnh frozen source, payload, criteria, prediction, metrics, gold hay review.
Bản thay cell7 tạo một compatibility worker mới ở thư mục output, ghi hash và
metadata để archive lưu lại. Worker gốc được xác minh SHA trước khi tạo bản mới.

Chỉ khi trace tái tính chứng minh `usage_complete is True` và producer metrics
không có diagnostic này, phép so sánh bỏ diagnostic khỏi bản sao trong bộ nhớ.
Mọi trường còn lại phải bằng nhau và automated gate phải True. Diagnostic False,
metrics khác, provenance khác hoặc human review không đạt vẫn bị chặn.

Original workflow SHA:
`64a838b28d187c795a16edfa525786680539e729e6255f5d45c74546f450f9ee`.
Compatibility worker SHA:
`5b250930ea9ee249ef71c5fae0135628cc664b174244ce88d45ae894bbef4eb8`.
Notebook gốc SHA giữ nguyên:
`2a8ee31ff7fe7558f0ad63caa4a9ba60789d189214fdd438afe75b4a47f1ee6a`.

## Tiếp tục cùng runtime Kaggle

1. Giữ runtime hiện tại và ZIP gốc. Không chạy lại cells1–6.
2. Mở `scripts/kaggle_cellfix15_cell7_replay_compat.py`, copy toàn bộ nội dung
   để thay đúng cell7. Hoặc lấy code cell7 từ notebook
   `scripts/kaggle_atomic_verifier_cellfix15_cell7_fix.ipynb`.
3. Điền lại `FULL39_REVIEW_PATH` bằng đường dẫn JSON full39 review bạn đã dùng
   trong lượt lỗi; giữ nguyên nội dung JSON. Đặt `RUN_VALIDATION30=True` sau
   khi đã review đầy đủ. File cung cấp vẫn mặc định False.
4. Chạy lại chỉ cell7. Preflight sẽ dùng tên retry mới, giữ log lỗi trước.
   Cả preflight và admission phải exit0 trước khi validation30 được gọi.
5. Giữ ZIP mới trong `/kaggle/working`, gồm compatibility worker/metadata và
   mọi kết quả dev30. Nếu có lỗi khác, giữ log và dừng tại gate đó.

Nếu runtime cũ đã mất, không import notebook rồi mong resume được run cũ.
Bản sửa này không khôi phục runtime/weights từ ZIP. Cần workflow restore được
kiểm tra riêng hoặc một lượt mới; không sửa hash/provenance để nhập kết quả cũ.

## Validation

11 regression tests đạt: producer thiếu diagnostic, producer có diagnostic,
incomplete usage, diagnostic False, labels/tokens sai, extra key, gate False,
human rejection, workflow bytes bị thay đổi, notebook chỉ đổi cell7 và
compatibility file idempotent/không ghi đè collision. Có replay/admission thật
trên ZIP nhận được, không chỉ mock unit tests.

Audit JSON: `docs/atomic-verifier-cellfix15-full39-audit-20261102T163553Z-ed00dfbc.json`.
ZIP gốc và output nguyên bản được giữ dưới
`research-runs/audit-cellfix15-full39-20261102T163553Z-ed00dfbc/`.

Chưa có kết quả 30/30. Bộ30-v1 tiếp tục là development, không phải holdout độc lập.
