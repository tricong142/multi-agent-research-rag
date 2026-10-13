# Protocol đánh giá độc lập verifier — chuẩn bị trước lượt inference

Bộ 39 ca hiện tại là development regression đã được xem. Protocol này hướng
dẫn chuẩn bị bộ độc lập cho quyết định tích hợp; **chưa có bộ độc lập đã gán
nhãn hoặc kết quả đo độc lập** trong repository từ công việc bước 3.

## Chuẩn bị dữ liệu

Một reviewer khác người viết prompt/chẩn đoán lỗi chọn nguồn và tạo bộ ca
mới trước khi xem output model. Dùng tài liệu chưa xuất hiện trong development
suite; không chỉ đổi tên hoặc số của 39 ca đã có.

Thiết kế khởi đầu: ít nhất 27 ca, gồm ba nhãn support/contradict/NEI trên chín
nhóm: all, some, none, entity, time, direction, metric, conjunction, condition.
Đây là yêu cầu coverage của thí nghiệm, không đại diện thống kê cho toàn bộ
nhiệm vụ nghiên cứu trong production. Với số học, thêm độ đa dạng đơn vị và
cách trình bày; giữ các dạng parser chưa hỗ trợ để đo abstention rõ ràng.

Mỗi record cần có `example_id`, `claim`, `context`, `label`, `source_id`, vị
trí nguồn, `evidence_quotes`, `missing_information` và annotation rationale.
Phân biệt absence of evidence với evidence of absence. Làm rõ metric, phạm
vi, thời điểm và điều kiện; tránh hai cách hiểu như các ca đã ghi ở bước 1.

Reviewer thứ hai kiểm nhãn/evidence; bất đồng được phân xử trước đóng băng.
Lưu tên vai trò reviewer, ngày, phương pháp chọn nguồn và quyết định phân xử.
Những trường annotation/gold không được chuyển qua ranh giới input model.

## Đóng băng và chạy

1. Chốt toàn bộ records và hash dữ liệu; lưu riêng split development/independent.
2. Chốt criteria/version/source/prompt/model revision, ngân sách và rubric
   trước inference độc lập. Gate development 39/39 hiện tại vẫn giữ riêng.
3. Gate độc lập phải đo cả nhãn, false support, coverage/quote/explanation,
   thông tin thiếu, support đúng bị từ chối, failure, calls và latency. Chốt
   ngưỡng cụ thể theo phạm vi dữ liệu trước khi chạy; chưa dùng số liệu bộ mới
   để chọn ngưỡng hoặc sửa prompt.
4. Chạy policy đã chọn một lần, giữ output đầy đủ và review ngữ nghĩa bằng
   người. Nếu dùng lỗi của bộ độc lập để chỉnh policy, bộ đó trở thành dữ liệu
   phát triển; đánh giá cuối cần một bộ chưa bị xem tiếp theo.

Hồ sơ cần bàn giao gồm dataset/criteria hashes, model/source provenance,
predictions/traces, metrics, judgments và các hạn chế. Không ghi “đánh giá
độc lập đạt” khi mới có protocol hoặc annotation do AI tạo.
