# Cellfix13 — member/target semantics và ledger unknown trung thực

Candidate: `atomic-verifier-constrained-v8-cellfix13`.
Criteria SHA256: `fc4d4a8f7baaf88886cbd3047819125752867e7cdb2f2a8fb850f4be293abb4c`.
Notebook: `scripts/colab_atomic_verifier_cellfix13.ipynb`.
Notebook SHA256: `bc09f708b5b66a43a4d1af0c4f48c785e4a2159bc706c6ee2990eb544dbb839e`.
Đã đóng băng 117 input candidate/131 input payload, 7 code cell.
Đây là candidate chờ inference T4 và review mới, chưa phải serving release.

## Mốc giữ nguyên

Cellfix12 run `20261027T092904Z-e02b51ab`: **39/39 nhãn đúng,
false support=0, runtime=0**, nhưng human review Trí Công có **sáu giá trị
explanation_follows_evidence=false**. Giữ nguyên ZIP diagnostic `(6)`,
predictions, source/release và `semantic-review (11).json` trong snapshot.
Manifest bảo toàn: `atomic-verifier-cellfix12-preserved-before-cellfix13.json`.
Không đổi review/gold/predictions cũ thành đạt.

## Thay đổi

Logic mới nằm trong `assessment_members.py`, dùng chung từ
`assessment_focus.py` cho validator và decoder:

1. **Atomic target vắng mặt:** observations=[], coverage rỗng/incomplete,
   scope_match=unknown, missing-information ghi thiếu binding. Workload,
   quantity hoặc câu thiếu báo cáo không được thay thế entity trong claim.
   Điều này xử lý irrelevant và từng part của ba conjunction mà không đoán
   workload là extractor. Gold strict identity hiện hành giữ nguyên, kể cả
   case ID lịch sử chứa support/contradict.
2. **Unknown population member:** phải là noun reference từ source cho
   population/collective scope, hoặc proper name có local metric/status anchor.
   Fragment như `Silver's leak status was not` / `no yield changes were`
   bị loại theo hình thức tham chiếu đối tượng; không dựa riêng vào việc còn
   từ reported/measured trong member hay không. Tên model có chữ số vẫn hợp lệ.
3. **Absence của chính member:** Silver unknown phải cite nguồn nói leak status
   Silver chưa reported; kết quả no-leak của Blue/Green không thay thế absence
   này. Group low-temperature unknown phải giữ quote đúng nhóm. Outcome đã biết,
   polarity ALL/SOME/NONE, numeric ledger và closure giữ các guard cũ.
4. **Admission rõ lỗi hơn:** khi review có criterion false hoặc thiếu notes,
   thông báo nêu case/criterion đang bị chặn. Điều kiện chấp nhận vẫn giữ nguyên;
   review_completed=true không tự trở thành review passed.

Các file runtime thay đổi trong workspace candidate riêng:
`assessment_focus.py`, `atomic_verifier.py`, `atomic_decoding.py`; thêm
`assessment_members.py`. Worker workflow chỉ cải thiện error message.
Không sửa source/release Cellfix12, không rewrite pipeline, không thêm dependency.

Model/revision, NF4/float16/seed42/do_sample=False, 8 calls/case,
2 attempts/stage, 1536 token/call, 180s/case, data/gold và acceptance gate
giữ nguyên. Decomposition prompt không đổi; assessment prompt nói rõ ledger
rỗng khi target vắng mặt và member phải là object reference có căn cứ.

## Regression và kiểm chứng

Regression lấy chín observation lỗi trong sáu case human đã đánh dấu, giữ raw
traces nguyên vẹn làm negative controls. Positive fixtures sửa đúng ledger,
không được dùng để tính model accuracy mới. Thêm câu mới về Willow router,
Detector P4, Onyx/valves, dry-storage/capacity và November trials; có test
fragment prefix khác nhau, model ID chứa số, closed population, scope, absence,
repair/exhaustion và claim hai part trong ngân sách cũ.

Ba file test cũ được cập nhật trong bản copy candidate để kiểm contract mới:
bad member của target vắng mặt phải bị reject; đường hợp lệ là empty unknown
ledger. Các bad fixtures vẫn là negative controls. Không bỏ test hay thay gold;
bản test/source gốc nằm nguyên trong Cellfix12.

Báo cáo của manifest cuối:

- `atomic-verifier-cellfix13-validation.json`: toàn bộ regression và ba
  validate-only của source.
- `atomic-verifier-cellfix13-tokenizer-check.json`: token paths với tokenizer
  Qwen đã pin; không load weights hoặc tạo model predictions.
- `atomic-verifier-cellfix13-packaging-validation.json`: notebook/workflow/
  retry/gate và bốn validate-only từ exact embedded payload.
- `reviews/cellfix13-development/BASELINE_TRACE_REPLAY.json`: replay ledger
  cũ và các output bị guard mới từ chối, không phải accuracy mới.
- `atomic-verifier-cellfix13-validation-overlap.json`: overlap screen của
  development; bộ30 giữ nguyên gold/input/protocol/review/lock, chỉ rebind
  candidate. Không dùng held-out outcomes để tune, không tạo chữ ký human mới.

Kết quả trên manifest cuối: **385/385 regression** (363 kế thừa, 22 method
mới có nhiều subcase); **90/90 đường token filter Qwen**; **35/35 test
notebook/workflow/retry/gate** (15 + 7 + 10 + 3) đạt. Bốn validate-only từ
exact embedded payload đạt, gồm kiểm binding validation30 không inference.
Release catalog và mọi input candidate khớp hash sau đóng băng.

Replay 46 assessment cũ: 36 qua guard, 10 bị từ chối. Chín observation lỗi
trong sáu ca human trượt đều bị chặn; thêm ca May NEI phải cite nguồn trực tiếp
về kết quả May chưa báo cáo. Đường mới này có regression bằng November trial.
Đây không phải điểm accuracy hoặc kết quả inference mới. Overlap screen:
77 file development/3.328 chuỗi, không có cờ theo protocol đã khóa.

## Chạy Colab

1. **Runtime mới, GPU T4.** Upload notebook Cellfix13, chạy **cells1–5**:
   source/binding → environment → regression/validate-only → smoke12 → probe18.
   Giữ ZIP diagnostic cả khi thất bại. Smoke chưa đạt thì dừng trước probe/full39.
2. Probe automated gate đạt: trực tiếp đọc **HUMAN_REVIEW.html của run mới**,
   xác nhận từng tiêu chí trong 18 claim và ghi chú, xuất semantic-review.json.
   Probe đo decomposition; 18/18 không phải label accuracy/false support.
3. Sau review probe đạt, bật `RUN_FULL39=True` ở **cell6**, upload đúng file
   review probe mới. Review Cellfix12 không mở gate của Cellfix13.
4. Full39 automated gate phải đạt **39/39, zero false support, runtime=0** và
   budget/trace đầy đủ. Sau đó review **form full39 mới**, kiểm đủ claim/context,
   từng part/quantity, member, quotes, explanation và missing-information.
   Xuất review mới; chỉ tích khi kết quả thực sự đạt, lưu cả review trượt.
   Có thể đặt tên file xuất là `probe-review-<run>.json` và
   `full39-review-<run>.json` để tránh nhầm hai loại review khi upload.
5. **Giữ RUN_VALIDATION30=False** đến khi automated full39 và human review
   sạch của chính candidate/predictions này cùng đạt. Khi đó mới bật cell7 và
   upload review full39. Review đã hoàn tất nhưng còn false sẽ tiếp tục bị chặn.

Cells6/7 mặc định tắt, review forms không tự tích checkbox. Retry admission
bảo toàn review/status/log cũ, không ghi đè một lần inference đã chạy.

## Giới hạn

Unknown member grammar là finite English nominal/possessive rules, không phải
general NER/coreference. Nó có thể tăng repair/abstention với cách diễn đạt
chưa hỗ trợ. Giữ các witness guards đã biết; không dùng rule lexical để chứng
minh mọi entailment. Kết quả đo trên GPU và review mới mới quyết định acceptance.

Chưa có smoke/probe/full39 inference mới, human review mới hoặc Validation30
Cellfix13 trong lượt sửa local. Không công bố sáu judgments đã thành true hay
validation30 thành công trước khi có kết quả. Chưa promote serving hoặc kiểm
Reader/Summarizer E2E.
