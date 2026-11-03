# Admission Cellfix12 — human review hoàn tất nhưng chưa đạt

Run Colab: `20261027T092904Z-e02b51ab`.
Đã đọc `semantic-review (11).json` và ZIP diagnostic `(6)` trong Downloads.
File review được bảo toàn nguyên bytes cùng ZIP tại
`research-runs/audit-cellfix12-admission-20261027T092904Z-e02b51ab/`.

## Điều đã chứng minh

- Reviewer **Trí Công**, `reviewer_kind=human`, `review_completed=true`.
- Criteria hash đúng Cellfix12 release; predictions hash
  `42deb4c53f4a5e044ae98f105efb463d95977654fd6ea6ae2bc008f18d87ff3b`
  đúng full39 của run này. Đây không phải review đang bị từ chối vì nhầm hash.
- Đủ 39 case ID, mỗi ca một lần; đủ 195 khóa rubric; mọi ca có notes không rỗng.
- **189 judgments true, 6 false**, đều là `explanation_follows_evidence`.
- 116 file trong ZIP khớp manifest; payload trùng frozen Cellfix12 release.
- Metrics full39: 39/39 nhãn đúng, false support=0, runtime=0, 85 calls.
- `full39-admission-preflight` trượt; chưa có thư mục inference `validation30/`.

`review_completed=true` chỉ ghi nhận người review đã làm xong. Để admission
đạt, cả năm judgments của mỗi ca còn phải `true`. Hàm
`require_human_review()` từ chối tại điều kiện `any(v is not True ...)`.
Sau đó helper `run(required=True)` báo RuntimeError vì worker exit code 1.
Đây là quality gate đang thực thi kết quả review, không cần sửa cell7 để bỏ gate.

## Sáu ca chưa đạt đã được người review ghi nhận

| Case | Vấn đề trong output của run mới |
|---|---|
| `contract:irrelevant` | Member `No model accuracy is reported` là clause, không phải Model Juniper. |
| `scope:none:not_enough_info` | Member `Silver's leak status was not` là fragment, không phải pump Silver. |
| `scope:conjunction:support` | Members `5.4 to 4.6 gigabytes` và `4.6 gigabytes` là quantities, không phải extractor. |
| `scope:conjunction:contradict` | Member là workload clause và memory quantity, chưa bind extractor. |
| `scope:conjunction:not_enough_info` | Workload/memory quantity được gọi là member; quantity memory không phải entity cho token recall. |
| `scope:condition:not_enough_info` | Member `no yield changes were` là fragment, không phải batch/group. |

Các member này đã được đối chiếu với predictions của run mới, không chỉ lấy
ghi chú của run `20261027T025350Z-c67b6d37`. Nhãn NEI đúng nhưng observation
explanation sai loại đối tượng; việc giữ judgment false là trung thực.

## Bước tiếp theo

1. Đặt lại `RUN_VALIDATION30=False`; giữ nguyên ZIP, predictions và human
   review trượt này làm mốc.
2. Candidate tiếp cần sửa chung member/target semantics: không lấy fragment,
   clause hoặc quantity làm entity; có đường unknown không bịa member khi target
   chưa bind. Đồng bộ validator/decoder; không sửa riêng theo sáu case ID.
3. Thêm regression từ traces và câu mới; giữ model/revision/budget/gold/gate.
4. Đóng băng, chạy smoke → probe18 + human review mới → full39 + human review
   mới. Chỉ khi tất cả gate cùng đạt mới mở Validation30 đã khóa.

Lượt này chỉ chẩn đoán và bảo toàn bằng chứng. Không sửa release, source,
predictions hay judgments; chưa triển khai candidate mới hoặc chạy Validation30.
Số liệu chi tiết nằm trong `ADMISSION_DIAGNOSIS.json` cùng thư mục.
