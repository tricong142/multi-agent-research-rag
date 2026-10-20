# Chạy candidate verifier v8 trên T4

Notebook: [colab_atomic_verifier_v8_smoke_probe.ipynb](../scripts/colab_atomic_verifier_v8_smoke_probe.ipynb).
Đây là candidate cho thí nghiệm độc lập; loader serving vẫn dùng FactChecker cũ.
Kết quả kiểm tra local xem [validation v8](ATOMIC_VERIFIER_V8_VALIDATION.md).

## Chạy năm cell theo thứ tự

Upload notebook lên Colab và chọn T4 trong một session mới. Không tái sử dụng
thư mục output v7. Notebook tự tạo run ID/thư mục/venv/cache riêng dưới `/content`.

1. **Giải nén và kiểm hash.** Payload tự chứa source, dữ liệu, tokenizer và fixture;
   không chứa trọng số model hoặc credentials. Lưu `input-manifest.json`.
2. **Cài môi trường riêng.** Cài dependency đã pin, chạy `pip check` và lưu freeze.
3. **Regression, CUDA và validate-only.** Chạy test từ source trong payload;
   kiểm ba chế độ 18 claim/12 smoke/39 verifier. Tải Qwen ở revision đã đóng băng
   trước khi bắt đầu ngân sách inference. Model/revision, NF4/float16/seed42,
   sampling và ngân sách mỗi case giữ như v7.
4. **Smoke assessment: 12 ca contract dev gốc.** Phải đúng đủ 12 nhãn, không có
   false support/runtime failure và đủ trace decoder/deadline. Mỗi case tối đa
   8 call, 2 attempt/stage, 1.536 token/call, deadline hợp tác 180 giây;
   toàn smoke tối đa 96 call, watchdog process 2.400 giây. Xuất ZIP dù smoke trượt.
5. **Probe 18 claim.** Chỉ chạy khi smoke đạt. Ngân sách probe giữ 2 call/claim,
   tổng 36 call, watchdog process 2.400 giây. Xuất ZIP cuối có cả hai stage.

Nếu cell lỗi hoặc smoke không đạt, giữ ZIP đã xuất; tải lại ZIP sau cùng từ
thư mục run nếu cần. Không chạy lại stage vào cùng output, không sửa metrics,
predictions, review hoặc tăng budget để biến run trượt thành đạt. Nếu session
đứt trước khi tải được artifact, chưa có đủ bằng chứng nghiệm thu run đó.

## Gửi lại artifact và các gate tiếp theo

Gửi **ZIP cuối**, gồm `input-manifest.json`, `output-manifest.json`, `status.json`,
log môi trường, `assessment-smoke/` và `decomposition-probe/`. Mỗi stage phải có
criteria/contract/provenance, calls, predictions, summary và metrics tương ứng.
Khi timeout, giữ nguyên trace dở và summary lỗi; không chỉ gửi metrics.

Từ ZIP, kiểm bytes/hash/model pairing, replay từng kết quả và review bằng chứng.
Nếu probe đạt cấu trúc 18/18, người review phải đọc và xác nhận đủ năm tiêu chí
trên từng claim vào `semantic-review.json` của **chính run v8**. Human review
`tricong` ở v7 được giữ làm lịch sử, không dùng lại làm admission v8.

Sau khi admission v8 đạt mới dựng/chạy notebook full39. Gate dev giữ nguyên:
39/39 nhãn đúng, false support = 0, runtime failure = 0 và không vượt ngân sách.
Smoke dùng dữ liệu dev đã xem; probe chỉ đo tách mệnh đề. Hai kết quả này không
thay phép đo nhãn/false support đủ39, không phải đánh giá khả năng tổng quát hóa.
Bộ validation độc lập với dữ liệu đã dùng để sửa vẫn cần annotation và đánh giá
riêng. Reader/Summarizer/Writer và E2E chỉ được nghiệm thu sau các gate tương ứng.

## Giới hạn cần đọc trước khi chạy

V8 ràng buộc evidence thành đoạn nguyên văn từ context và operand thành các
bộ số/đơn vị/quote lấy từ nguồn. Điều này chặn nhiều output bịa ở mức token,
nhưng không chứng minh model hiểu đúng entity, metric hoặc quan hệ bằng chứng.
Review nội dung vẫn cần thiết.

Context assessment tối đa 600 từ; quote tối đa 384 ký tự; member tối đa 160 ký tự
và decoder chỉ chọn span tới 8 từ; explanation tối đa 128 ký tự. Context vượt
giới hạn dừng rõ trước model. Các ngữ pháp metric/số liệu chỉ hỗ trợ phạm vi
đã ghi trong contract; trường hợp chưa bind được giữ unknown. Đếm nhiều member
hoặc numeric record vẫn có thể vượt ngân sách token.

Deadline được truyền vào Transformers và kiểm tại từng bước decode. Nó có thể
dừng JSON đang sinh và giữ trace, nhưng không ngắt ngay một CUDA kernel/prefill
bị treo; watchdog process vẫn là giới hạn cưỡng bức. Chưa có GPU inference v8
trong lượt chuẩn bị local, nên chưa kết luận giảm timeout hoặc đạt gate39.
