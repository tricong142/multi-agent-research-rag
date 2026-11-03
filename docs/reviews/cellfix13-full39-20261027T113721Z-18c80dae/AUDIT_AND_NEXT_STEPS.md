# Cellfix13 — audit ZIP sau full39

Run: `20261027T113721Z-18c80dae`. Candidate: `atomic-verifier-constrained-v8-cellfix13`.

**Đủ điều kiện chuyển sang human review full39. Chưa đủ điều kiện chạy Validation30 vì human review full39 chưa được ký cho predictions này.**

## Kết quả đã kiểm

| Hạng mục | Kết quả |
|---|---|
| ZIP và payload | 113 output / 131 input khớp manifest và release; không thiếu/trùng file |
| Regression trong Colab | 385/385 đạt |
| Validate-only | Smoke, probe, full39, validation30 đều hợp lệ; validate-only không phải inference Validation30 |
| Assessment-smoke | 12/12 nhãn đúng; false support=0; runtime_failed_rows=0 |
| Probe | 18/18 decomposition hợp lệ; human review Trí Công đã được gate chấp nhận cho đúng predictions probe |
| Full39 | 39/39 nhãn đúng: support 12, contradict 12, NEI 15 |
| Full39 false support / runtime failures | 0 / 0 |
| Full39 calls / generated / prompt tokens | 85 / 9.138 / 116.698; toàn bộ budget/trace checks đạt |
| Replay local | 131 call triplets của ba stage khớp raw JSON, parsed output, normalized results và metrics; không chạy inference mới |
| Bằng chứng full39 | 34 observation citations nguyên văn; 14 numeric records được replay; một citation bổ sung được trace từ numeric source |
| AI evidence review | Đọc 39 claim/context và 46 assessment; chưa thấy lỗi ở 195 tiêu chí; đây là phán xét AI |
| Human evidence review full39 | Pending; form còn trống 195 tiêu chí và 39 notes |
| Validation30 | Chưa có inference; gate thực tế vẫn chặn review chưa ký hoặc review do assistant |

## Sáu lỗi ngữ nghĩa cũ

- `contract:irrelevant`: không còn clause về việc báo cáo accuracy làm member; atomic target thiếu có ledger rỗng và missing target cụ thể.
- `scope:none:not_enough_info`: member là `Silver`; quote giữ đúng leak status chưa báo cáo, truth unknown.
- Ba `scope:conjunction:*`: cả hai part có empty unknown ledger vì context không bind được `extractor`; không còn quantity/workload/clause thay entity. Gold vẫn NEI theo annotation strict identity đã chốt, bất kể tên ID lịch sử.
- `scope:condition:not_enough_info`: member là `low-temperature group`; quote chỉ absence của low group, không dùng high-temperature để support.

Các control về causal relationship, precision chưa đo, May population, phản ví dụ ALL, closure SOME/NONE và hai quantity độc lập đều đã được đọc lại. Dấu chấm lặp cuối phần causal missing là lỗi trình bày nhỏ; chưa thấy làm sai nghĩa kết luận trong ca này. Một số unknown records không có quote nhưng không được dùng làm true/false evidence.

## Thực hiện tiếp

1. Mở `HUMAN_REVIEW_WITH_AI_NOTES.html` cùng thư mục. Đọc đủ 39 ca, đối chiếu claim/context/parts/ledger/numeric và ghi nhận độc lập năm tiêu chí: nhãn đúng, quote đúng scope, explanation theo evidence, kiểm đủ parts/quantities, missing cụ thể. Nhập notes cho từng ca, tên reviewer và xác nhận hoàn tất; xuất `semantic-review.json`. Các checkbox vẫn trống; ghi chú AI không thay chữ ký human. Nếu có tiêu chí chưa đạt, lưu trung thực false và giữ Validation30 tắt.
2. Khi toàn bộ 195 tiêu chí thực sự đạt và 39 notes có nội dung, giữ nguyên runtime đã chạy full39 này; chỉ bật `RUN_VALIDATION30 = True` ở **cell 7** rồi upload review **full39 mới**, không dùng review probe hay Cellfix12. Cell 7 tự chạy admission preflight trước inference. Không cần chạy lại cells 1–6 hoặc đóng gói notebook mới. Nếu runtime đã mất, cần khôi phục đúng artifact trước; không sửa hash/run_id trong review.
3. Giữ ZIP/predictions hiện tại nguyên vẹn. Sau Validation30, lưu ZIP mới dù đạt hay trượt để audit. Chưa tuyên bố pipeline Ready hoặc chất lượng ngoài bộ39; kết quả Validation30 chưa được đo. Nếu dùng kết quả Validation30 để tune thì phải chuyển bộ này thành development và chuẩn bị holdout khác.

## Binding để đối chiếu

- ZIP SHA256: `2518187dba2f3d9250a87d601d1a408a9cec831502ebfe7478d16294af5491c4`
- Criteria SHA256: `fc4d4a8f7baaf88886cbd3047819125752867e7cdb2f2a8fb850f4be293abb4c`
- Full39 predictions SHA256: `fa533867249df02eea87c6a9e5f48ca0e72111abdb9440b78ba9b3227a67f0f5`
- Payload SHA256: `b935fd2fd8a35e853b9862f5bb9e1f57324638f58eec97b5de93afb12bd4871a`

Bằng chứng máy: `docs/atomic-verifier-cellfix13-full39-audit-20261027T113721Z-18c80dae.json`.
Phán xét và ghi chú AI: `AI_EVIDENCE_AUDIT.json`, `EVIDENCE_REVIEW_39.md`.
Nguồn/notebook/release và predictions gốc không bị chỉnh trong lượt audit này. Kiểm manifest xác nhận tính nhất quán nội bộ artifact, không phải chứng thực máy Colab từ xa.
