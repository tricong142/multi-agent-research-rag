# Cellfix14 — candidate cho deadline/trace, quantity và binding

Candidate: `atomic-verifier-constrained-v8-cellfix14`.
Đây là candidate kiểm offline và chuẩn bị inference, chưa phải serving release.
Không có bằng chứng 30/30 bằng model thật cho phiên bản này.

## Thay đổi và giới hạn

- Decoder và validator dùng chung quy tắc lượng từ theo từng mệnh đề. AND nối
  danh từ/mục đích không bắt buộc tách thành fragment. Kiểm subject/comparator
  và population của lượng từ; không biến comparator thành subject.
- Quantity giữ offset/quote gốc, loại model/section IDs, giữ danh từ ghép;
  count và duration được kiểm riêng. `half-hour` là 0.5 hour có nguồn nguyên văn;
  không bổ sung chuyển đổi đơn vị tùy ý. Ngữ pháp vẫn hữu hạn, không phải parser
  tổng quát cho mọi đơn vị, số viết bằng chữ hoặc cấu trúc tiếng Anh. Explicit
  partitive như `800 events, 230 of which...` giữ object từ antecedent ngay
  trước trong cùng câu; không suy ngược qua câu khác. Count object trong nguồn
  có thể có thêm modifier nhưng không được thay `video clips` bằng `audio clips`.
- Binding nhận shared-head list, apposition/acronym và tác giả `our model`
  khi có nguồn rõ ràng. Không fuzzy-match mọi tên; không đọc gold/case ID để
  quyết định nhãn. Known member cũng không được là clause fragment. Không có
  assertion về ngôn ngữ không được coi là bằng chứng phủ định ngôn ngữ đó.
- Cache phân tích chỉ sống trong một request. Kiểm deadline trong token filter;
  POSIX signal ngắt Python schema/filter work. Tiến trình cha giám sát deadline
  của case và dừng đúng worker đã tạo nếu native call không trả về. Trường hợp
  watchdog phải dừng worker sẽ kết thúc stage có lỗi, không tự gán nhãn cho case
  hoặc giả vờ đã hoàn thành 30 ca.
- Mỗi attempted generation có diagnostic event kể cả khi tokenize/schema/
  generation lỗi; ghi thời gian từng phase. Usage chưa đo được giữ null và
  `usage_complete=false`, chỉ ghi token lower bound khi thực sự quan sát được.
  Nếu worker bị kill thì trace có thể thiếu event cuối: gate phải fail, không
  điền token 0 hoặc gọi đây là trace đầy đủ.

Model/revision, budgets call/token/time, gold và gate full39 giữ nguyên.
Prompt/contract/source/decoder có version/hash mới. Serving loader không đổi.
Cellfix13 và predictions/review cũ được giữ nguyên; builder kiểm hash parent.

## Bộ30 hiện là development

Cellfix13 đã có kết quả 10/30, 4 runtime failures. Lượt sửa này dùng các dạng lỗi
đã công bố, vì vậy validation30-v1 chuyển thành development regression.
Gold, input, annotation review và lock gốc giữ nguyên bytes; binding mới ghi
`validation_used_for_tuning=true`, `evaluation_role=development` và
`independent_validation_completed=false`. Không tạo chữ ký human mới.

Ngay cả khi lần inference tới đạt 30/30, đó vẫn chỉ là kết quả trên bộ development
đã xem. Cần holdout mới disjoint theo paper, được người review và khóa trước
inference để đánh giá generalization. Không đổi tên bộ30 cũ thành holdout mới.

## Chạy trên Kaggle

1. Import `scripts/kaggle_atomic_verifier_cellfix14.ipynb` vào notebook private;
   chọn GPU T4 và bật Internet cho dependency/model revision đã pin.
2. Chạy từng code cell 1–5: nạp payload → môi trường → regression/validate-only
   → smoke12 → probe18 nếu smoke đạt. Giữ ZIP cả khi một stage thất bại.
3. Probe đạt: tải form mới, trực tiếp đối chiếu nguồn và điền review. Đưa JSON
   review lên Kaggle, đặt `PROBE_REVIEW_PATH` trong cell6; chỉ khi review thực sự
   đạt mới bật `RUN_FULL39=True`. Review của run cũ không mở gate mới.
4. Full39 đạt: review toàn bộ predictions/evidence của run mới, xuất JSON và đặt
   `FULL39_REVIEW_PATH` trong cell7. Chỉ khi cả automatic/human gate đạt mới bật
   `RUN_VALIDATION30=True` để chạy **dev30-v1**.
5. Tải ZIP output trong `/kaggle/working` trước khi dừng session. Không chạy lại
   cell1 để tiếp tục run cũ. Giữ run lỗi; không chọn một lượt thuận lợi rồi bỏ
   các lượt thất bại. Không sửa gold, bỏ case, tăng budget hoặc tự tích review
   để làm acceptance đạt.

Cells6/7 mặc định tắt. Không chạy builder/checker Python trên Kaggle thay cho
notebook; payload tự chứa source cần thiết, không cần upload toàn bộ repository.

## Bằng chứng kiểm offline

- `atomic-verifier-cellfix14-validation.json`: regression và validate-only.
- `atomic-verifier-cellfix14-tokenizer-check.json`: đường token hợp lệ/không
  hợp lệ với tokenizer Qwen đã pin; không load weights hoặc tạo predictions.
- `atomic-verifier-cellfix14-packaging-validation.json`: test notebook, gates,
  review retries, development binding và exact embedded payload.
- `atomic-verifier-cellfix14-release.json`: hash source/notebook Colab/payload.
- `atomic-verifier-cellfix14-kaggle-validation.json`: notebook Kaggle và hash
  payload; chưa chứng minh inference/download hoạt động trên Kaggle.

Các file trên không được diễn giải thành model accuracy. Chỉ có ZIP inference
mới, classification/trace được kiểm lại và review thật mới xác nhận điểm dev30.
