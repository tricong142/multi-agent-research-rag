# Khôi phục run đã review rồi chạy full39

Assertion ở đầu cell cũ chỉ chứng minh globals run_id không khớp. Có thể kernel
đã reset hoặc một cell setup đã tạo run mới; chưa có bằng chứng để kết luận
artifact cũ còn/mất trên máy Colab. Không bỏ assert hoặc tự gán run_id cho
workspace chưa kiểm. Human review cũ vẫn hợp lệ cho đúng predictions đã audit.

## Thao tác

1. Chọn GPU T4 trong Colab.
2. Mở [RESTORE_AND_RUN_FULL39.py](RESTORE_AND_RUN_FULL39.py), sao chép toàn bộ
   nội dung vào một cell mới và chạy. Cell này thay đường chạy của cell cũ
   `RUN_FULL39.py`; không chạy lại cell cũ sau đó.
3. Khi hộp upload mở, chọn **hai file cùng lúc**:
   - `output-cellfix8-fresh-20261020T061934Z-c87bce57 (2).zip`
   - `semantic-review (1).json` human đã được Trí Công xác nhận.
4. Chờ cell kiểm archive, khôi phục source/artifact sang thư mục mới, dựng lại
   đúng dependency/CUDA pins, kiểm GPU, tải đúng model revision, replay smoke
   và human admission, rồi tự chạy full39.
5. Giữ ZIP mới tải xuống, kể cả khi gate trượt, và gửi lại để audit.

Không cần chạy lại các cell sinh smoke/probe18, không cần human review18 mới.
Tên file có hậu tố vẫn được chấp nhận nếu bytes đúng; checksum nội dung quyết
định admission. Nếu upload nhầm file, cell dừng trước khi tạo workspace.

## Điều cell giữ nguyên

Model/revision, source/prompt, contract, criteria, budget, gate và validation30
giữ nguyên. Source được giải nén từ payload đã đóng băng, không dựng candidate
mới. Cell khôi phục run_id từ ZIP đã xác minh, không đổi tên một run khác thành
run đã review. Thư mục recovery dùng ID riêng để không ghi đè kết quả cũ.

Archive/human review, 111 input hashes và probe predictions hash được kiểm
trước khi chạy code restored. Status và output manifest gốc được giữ thành
resume-parent-* trước khi ghi log của lần recovery; resume-provenance.json
ghi rõ nguồn gốc. Bản probe unsigned được giữ riêng với reviewed-probe.

Model chỉ được gọi sau replay smoke12 và require_probe_review() chấp nhận
human review đã gắn đúng hash. Dependency pins được lấy từ chính notebook
cellfix8 đã chạy thành công trước đó, không tự đổi thư viện/model/budget.

## Sau full39

Gate vẫn 39/39 đúng nhãn, false support=0, runtime failure=0 và đủ trace/budget.
Nếu đạt, cell tải form HUMAN_REVIEW.html cho 39 prediction/evidence. Review
đủ bằng chứng/nhãn/explanation/missing information trước validation30.
Cell này không tự chạy validation30 hoặc promote serving.

Đã đạt 7/7 test recovery và replay smoke/human admission thực tế từ bản khôi
phục, không tải weights. Kiểm cả trạng thái globals sai, upload sai, ZIP path,
giữ lịch sử và chặn model khi preflight/admission lỗi. Dependency commands khớp
notebook cũ; verifier release giữ nguyên hash. Xem [báo cáo kiểm](resume-validation.json).

Local chưa thực hiện cài môi trường CUDA/T4 hay inference full39 của lần
recovery; chất lượng full39 vẫn cần đo từ lượt chạy Colab tiếp theo.
