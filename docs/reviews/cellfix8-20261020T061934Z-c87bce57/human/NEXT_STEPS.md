# Human admission đạt — chạy full39 cellfix8

File do Trí Công xuất đã được giữ nguyên byte tại `semantic-review.json` trong
thư mục này. Đủ 18 claim/20 part, 90/90 judgments đạt, notes đầy đủ và đúng hash
criteria/predictions. Hàm frozen `require_probe_review()` đã replay và chấp nhận.
Xem `admission.json`; đây là kết quả admission, chưa phải inference full39.

## Nếu phiên Colab của run này còn hoạt động

1. Giữ nguyên notebook/runtime đã chạy smoke và probe. **Không chạy lại cells 1–5.**
2. Mở `RUN_FULL39.py` trong thư mục này, sao chép toàn bộ vào một cell cuối
   notebook rồi chạy. Cell đã đặt RUN_FULL39=True, yêu cầu đúng run_id và kiểm
   validation binding, probe metrics cùng admission gốc.
3. Khi Colab yêu cầu upload, chọn file **semantic-review (1).json** đã gửi hoặc
   bản `human/semantic-review.json` ở đây. Hai bản nguyên byte giống nhau; không
   cần đổi tên. Không chọn bản AI ở thư mục cha.
4. Chờ full39; cell luôn tải ZIP chẩn đoán, kể cả khi gate trượt. Giữ ZIP mới
   và gửi lại để audit/replay. Không sửa flags, hash, nhãn hoặc thresholds.

Cell kiểm đúng SHA256 của human review trước khi tạo reviewed-probe, tránh
chọn nhầm file rồi tạo artifact admission lỗi. Source/prompt/model/revision và
budget của candidate không đổi. Bản unsigned gốc tiếp tục được giữ riêng.

## Nếu runtime đã mất

Nếu gặp assertion run_id không khớp, dùng
[cell khôi phục và chạy full39](RESTORE_AND_RUN_FULL39.py) theo
[hướng dẫn khôi phục](RESTORE_GUIDE.md). Upload ZIP đã audit cùng human review;
cell khôi phục đúng source/artifact/binding, dựng lại môi trường rồi replay
admission trước khi tự chạy full39. Không chạy lại probe hoặc ký lại review18.
Không chạy một probe mới rồi gắn review của predictions cũ vào đó.

## Sau full39

Gate vẫn là 39/39 đúng nhãn, false support=0, runtime failure=0, đủ trace và
đúng budget. Nếu đạt, cell xuất HUMAN_REVIEW.html mới cho 39 prediction/evidence.
Review đủ nhãn, quote/scope, mọi part/quantity, explanation và missing information
trước validation30. Các lỗi giải thích/missing đã thấy trong smoke cần được xem
lại; đúng nhãn không tự chứng minh chất lượng diễn giải.

Full39 và validation30 chưa chạy trong lượt admission local này. Không có
kết luận mới về zero false support trên full39 hoặc hoàn tất E2E.
