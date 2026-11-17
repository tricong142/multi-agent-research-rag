# Kết quả E2E PDF và demo

Lượt development GPU của candidate `cellfix29-e2e-structured-counts` dùng 9 câu trên ViISA, ViSP và Scaling Up Data-to-Text Generation. File khóa, runtime, payload, PDF, câu hỏi và tham chiếu đều khớp hash. ZIP có đủ 9 ca và cả 9 tiến trình trả mã thoát 0. [File khóa](../artifacts/cellfix29-e2e-cross-paper-v1/development-candidate-lock.json) · [Tham chiếu](../artifacts/cellfix29-e2e-cross-paper-v1/references.json)

ZIP kết quả `cellfix29-e2e-cross-paper-development-v1-yknzxd01.zip`, SHA‑256 `d2f10386a48217cf74fa391d75b352f2122e497715a0c217294b9de82ddc4e9f`.

| Lượt chạy | Điểm | Phạm vi |
| --- | --- | --- |
| QASPER | 3/3 | Smoke E2E trên các ca đã dùng để sửa. |
| Cross-paper v1 trước sửa | 3/9 | Ba paper chưa dùng để sửa tại thời điểm chạy. Ba ca đạt đều thiếu dữ kiện. |
| Cross-paper development v1 sau sửa | 7/9 | Cùng chín câu đã mở để truy lỗi và phát triển. Đạt 4/6 ca có đáp án và 3/3 ca thiếu dữ kiện. |
| Cellfix29 gốc · holdout verifier v6.1 | 12/30 | Gate tự động trượt. Có 2 false support và 1 ca lỗi runtime. Đánh giá này đo Agent 4 riêng. Metrics local: `research-runs/holdout29-v6-1-cache-retry1-f9e804706ed4/evaluation/metrics.json`. |

Tổng thời gian trong metrics của 9 ca development khoảng **21,2 phút**. Bốn báo cáo có đáp án đều mang trạng thái `partial` với cảnh báo `upstream_low_confidence`. Cả bốn trả lời đủ câu hỏi và có trích dẫn đúng, nên đạt theo tiêu chí chấm nội dung. Khoản thời gian trên chỉ gồm tổng các ca trong metrics.

| Ca | Chấm | Đối chiếu |
| --- | --- | --- |
| `viisa-text` | Đạt | 10 vòng gán nhãn, trang PDF 2. |
| `viisa-table` | Đạt | 260 mẫu âm và 42 mẫu dương, đúng hai dòng cột Value, trang PDF 2. |
| `viisa-missing` | Đạt | Báo thiếu nhiệt độ giải mã, không đưa ra giá trị. |
| `visp-text` | Đạt | Hơn 1,2 triệu cặp; đáp án yêu cầu số xấp xỉ và đoạn dẫn trang 1 nêu đúng độ lớn. |
| `visp-table` | Trượt | Generator đã chọn đúng nguồn và tạo đúng 406.308 Train, 380.590 Test. Critic nhầm dòng Sentence Pair với Original và chặn trước Agent 4. |
| `visp-missing` | Đạt | Báo thiếu seed chọn mẫu, không đưa ra giá trị. |
| `triple-sets-text` | Đạt | Đúng 6 LLM được benchmark, trang PDF 1. |
| `triple-sets-table` | Trượt | Hai ô đều vào context nhưng phản hồi hợp lệ chưa ghép đủ nguồn. Ba phản hồi lượt sau lỗi parse JSON và thiếu ô English trong các ID chọn. |
| `triple-sets-missing` | Đạt | Báo thiếu seed chọn mẫu Hum-1.0, không đưa ra giá trị. |

## Hai ca demo từ ZIP GPU

**Trả lời có bằng chứng · `viisa-table`.** Hỏi số mẫu âm và mẫu dương theo Bảng 1. Mở hai câu trong `review.json` cùng `claim_ids`, sau đó chỉ hai ô ở trang PDF 2:

- Claim 1 · “In Table 1, the count for Negative samples in the Value column is 260.”
- Claim 2 · “In Table 1, the count for Positive samples in the Value column is 42.”
- Nguồn · `pdf:57dc3d03781b4f39:p1:b3:c0`. Table trace giữ nhãn dòng, tiêu đề Value và tọa độ mỗi ô. Agent 4 trả `support` với lý do `table_count_matches` cho cả hai cặp đúng.

**Từ chối khi thiếu dữ kiện · `triple-sets-missing`.** Hỏi seed dùng để lấy 21 điểm cho Hum-1.0. Mở đoạn mô tả lấy mẫu ở trang PDF 3, rồi mở hai phản hồi `{"claims":[]}` trong trace. Báo cáo hiển thị thiếu bằng chứng, không có câu nào nêu seed và không có lượt gọi Agent 4. [PDF nguồn](https://aclanthology.org/2025.inlg-main.47.pdf)
