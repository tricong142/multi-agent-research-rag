# Cellfix6: annotation validation và notebook smoke/probe

Trạng thái ngày 2026-10-19: đã chuẩn bị bộ validation và notebook có gate;
annotation còn chờ người review. Chưa có inference mới, kết quả full39 của
cellfix6, kết quả validation hoặc nghiệm thu pipeline.

Mốc cellfix5 vẫn là **21/39 đúng nhãn, false support=0 trên annotation gốc**.
ZIP, source và predictions gốc được giữ nguyên. Thay đổi nhãn strict-identity-v1
ở candidate mới không sửa kết quả lịch sử này.

## Những gì đã được chuẩn bị

- Source cellfix6 giữ nguyên 89 file đã kiểm, criteria SHA-256
  `b9d77823b5c8d6d2a56d4053667b8b53f6e059a1f5edb9e7e3a7578a50f34071`.
- [Validation v1](validation/atomic-cellfix6-v1/manifest.json): 30 ca / 10 paper,
  10 nhãn support, 10 contradict, 10 NEI **đề xuất**. Claim mới do AI soạn trên
  các đoạn QASPER nguyên văn; đây không phải nhãn entailment chính thức của QASPER.
- Tách paper khỏi QASPER dev, paper trong dữ liệu Writer đã kiểm, và toàn bộ
  paper từng được trả về trong trace BM25/Dense dev đã lưu. Kiểm lexical với
  fixtures/tests/evaluation của candidate, SciFact train/dev, dữ liệu Writer và
  Summarizer được liệt kê trong [overlap report](validation/atomic-cellfix6-v1/overlap-report.json).
  Không có flag theo chuẩn hóa exact, token-set Jaccard >= 0,8 hoặc cụm 8 token.
- Đã ghi tiêu chí trước inference trong [criteria.json](validation/atomic-cellfix6-v1/criteria.json):
  đủ 30 ca, đúng 30/30, false support=0, runtime failure=0, đúng budget và đủ trace.
  Báo cả confusion, support recall, precision/recall từng nhãn và từng paper.
  Đây là gate của pilot mới; không thay gate full39 hoặc tự suy ra READY.

Giới hạn: mỗi paper có ba ca liên quan, không phải 30 quan sát độc lập. Đây là
mẫu chọn để bao phủ lỗi, không phải mẫu ngẫu nhiên đại diện. Corpus QASPER đã
được lập chỉ mục; paper được chọn không xuất hiện trong top-k dev đã lưu.
Paper ID của dữ liệu Summarizer chưa hoàn toàn đáng tin; kiểm text không chứng
minh không trùng ngữ nghĩa. Không biết mức tiếp xúc dữ liệu của pretraining.
Chỉ có thể gọi đây là pilot tách khỏi dữ liệu sửa verifier trong phạm vi đã kiểm.

## Anh cần làm tiếp

1. Mở [REVIEW.html](validation/atomic-cellfix6-v1/REVIEW.html) bằng Chrome/Edge.
   Điền tên/ngày review; đọc toàn bộ context của mỗi ca. Xác nhận riêng năm tiêu
   chí, chọn nhãn kết luận và ghi chú của anh. Với NEI, trích dẫn chỉ là phần
   liên quan; phải đọc hết context để kiểm đúng thông tin còn thiếu.
2. Đọc giới hạn provenance và protocol, rồi xuất
   `annotation-review-cellfix6-v1.json`. Có thể xuất bản dở để giữ nội dung,
   nhưng bản dở không được admission. Nếu không đồng ý nhãn hoặc một tiêu chí,
   ghi rõ lý do và gửi lại; cần phiên bản dữ liệu mới trước inference.
   Không tích đạt chỉ để notebook chạy.
3. Gửi file review để kiểm/khóa tại repo, hoặc upload đúng file đó ở cell 2 của
   [notebook cellfix6](../scripts/colab_atomic_verifier_cellfix6_fresh.ipynb).
   Notebook kiểm toàn bộ hash, đủ 30 quyết định và candidate rồi mới tạo
   `validation-lock.json`; chưa đạt thì chặn trước dựng GPU/tải model/inference.
   File này là tự xác nhận của người review, không phải chữ ký số xác thực danh tính.
4. Sau admission, chạy notebook từ runtime Colab mới, GPU T4, lần lượt năm cell.
   Notebook dựng môi trường pin sẵn, chạy regression và ba validate-only, rồi
   smoke12. Chỉ smoke đạt mới chạy probe18. Giữ ZIP cuối cùng kể cả khi thất bại.
5. Gửi ZIP mới để audit provenance/replay và review decomposition mới. Chỉ khi
   probe18 và review mới đạt mới chạy full39 dưới annotation strict-identity-v1.
   **Notebook này không chạy full39 hoặc validation30.** Sau gate full39 mới
   chuẩn bị lượt đo validation trên đúng candidate, giữ nguyên bộ đã khóa.

Nếu upload nhầm file, giữ ZIP chẩn đoán rồi chạy lại từ cell 1 trong runtime mới
với file review đúng. Không sửa hash hoặc bỏ assertion/gate để đi tiếp.

Có thể kiểm và khóa offline bằng lệnh sau từ thư mục repo (thay đường dẫn review
bằng file anh thực sự xuất; không dùng template làm bản xác nhận):

```powershell
.venv/Scripts/python.exe -m scripts.atomic_validation_review --packet docs/validation/atomic-cellfix6-v1 --review "C:/duong-dan/annotation-review-cellfix6-v1.json" --lock docs/validation/atomic-cellfix6-v1/validation-lock.json
```

Nếu dùng bất kỳ kết quả validation nào để chỉnh code/prompt/chọn candidate,
chuyển bộ này thành development và tạo một bộ mới. Giữ mọi kết quả thất bại;
không bỏ ca khó hoặc đổi gold sau khi đã xem prediction rồi vẫn báo độc lập.

## File phục vụ kiểm và tái lập

- [Manifest notebook bản chờ review](atomic-verifier-cellfix6-notebook-draft.json)
  chứa 99 file payload: 89 đầu vào candidate và 10 file validation/review.
- [Builder dữ liệu](../scripts/prepare_atomic_validation_v1.py),
  [gate review](../scripts/atomic_validation_review.py),
  [builder notebook](../scripts/build_colab_cellfix6_fresh.py).
- [Test packet](../scripts/test_atomic_validation_packet.py) và
  [test notebook](../scripts/test_colab_cellfix6_fresh.py) kiểm hash, evidence
  nguyên văn, review thiếu/sai, dữ liệu đổi sau khóa, payload và gate smoke/probe.
  Các chữ ký mô phỏng chỉ tồn tại trong thư mục test tạm, không dùng để mở gate thật.
- Kết quả local ở [báo cáo kiểm gói](atomic-verifier-cellfix6-packet-validation.json).
  Test offline và validate-only không phải số đo chất lượng model.
