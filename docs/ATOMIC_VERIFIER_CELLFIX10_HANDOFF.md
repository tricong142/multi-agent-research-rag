# Cellfix10 — sửa closure, repair và giải thích từ ledger

Candidate được tạo từ cellfix9 full39 run `20261020T110710Z-cf47db2f` đã audit.
Mốc **36/39, false support=0 theo gold, 2 incomplete** và ZIP/source/predictions cũ
được bảo toàn; đây vẫn là kết quả GPU gần nhất, không phải kết quả cellfix10.

## Thay đổi

- Closure: bổ sung nhận diện roster `the complete <selection> set` duy nhất.
  Người dùng đã xác nhận `audited set` trong ca SOME là toàn bộ cache nodes
  được hỏi. Quy ước được lưu trong `atomic_cellfix10_closure_adjudication.json`,
  không đổi claim/context/gold và không có nhánh runtime theo case ID/tên riêng.
  Quy tắc áp dụng cho một số selection modifier hữu hạn; cần đủ kết quả thành
  viên và đúng scope. Tập cạnh tranh, kết quả thiếu, scope khác và thông tin
  đính chính muộn được kiểm trong regression. Đây là quy ước discourse có giới
  hạn, không phải bộ giải coreference tổng quát. Kết quả ghi
  `population_binding_basis` để người review thấy cách binding.
- Sửa số nhiều danh từ kết thúc bằng nguyên âm + y, ví dụ relay/relays. Không bỏ
  qua kết quả thành viên ở câu sau; passage vẫn chịu giới hạn độ dài hiện có.
- Repair: thêm chỉ dẫn giữ roster/coverage khi sửa duplicate; không dùng một
  member=false để refute SOME. Giữ 2 attempt/stage và 8 call/case.
- Decoder dùng một mã missing reason theo part và hai ghi chú cố định, thay
  phần prose tự do từng sinh tác giả không có nguồn hoặc nhầm metric của vế khác.
  Missing reason phân biệt target chưa bind, comparison chưa có, measurement
  chưa báo cáo, population chưa đủ và bằng chứng theo scope còn chưa quyết định.
- `assessment_reporting.py` dựng `explanation` và `missing_information` từ
  ledger đã qua validator. Không sửa truth, label, citation hoặc numeric checks.
  `model_explanation`, `model_missing_information` và trace giữ output gốc.
  Output legacy khi replay vẫn qua các guard cũ trước khi render; không coi
  prose legacy là một output hợp lệ của decoder mới.

Renderer nhất quán với ledger không chứng minh ledger đã hiểu đúng source.
Human review vẫn phải đối chiếu claim, scope, quotes, quantity và closure.

## Kiểm chứng cục bộ

- 314/314 regression: 291 test trước đó và 23 test mới, gồm trace thật cùng câu
  mới. Năm file fixture test cũ đổi chuỗi prose/missing sang contract mới; không
  bỏ test hoặc thay gold của bộ39/validation30.
- 27/27 đường kiểm token filter bằng tokenizer Qwen đã pin; gồm output hợp lệ
  của hai ca repair, reject tác giả bịa và reject duplicate coverage. Đây là
  đường token dựng để thử, không phải 27 prediction do model tạo.
- Ba validate-only của runner đạt. Kiểm notebook sẽ chạy thêm validate-only
  validation30 từ chính payload và kiểm các gate upload/review/hash.
- Model Qwen2.5-3B-Instruct/revision, NF4 float16 seed42, max1536 token/call,
  180 giây/case, decomposition prompt, bộ39 và các gate giữ nguyên.
- Validation30: gold, review, protocol và lock gốc giữ nguyên; chỉ tạo binding
  mới cho candidate. Overlap screen không có cờ. Chưa chạy inference hoặc dùng
  kết quả validation30 để tune.

Xem báo cáo `atomic-verifier-cellfix10-validation.json`,
`atomic-verifier-cellfix10-tokenizer-check.json`, `cellfix10-development/CODE_DIFF.patch`
và `cellfix10-development/PRESERVATION_CHECK.json` trong thư mục reviews.
Kết quả kiểm đóng gói cuối được lưu riêng trong
`atomic-verifier-cellfix10-packaging-validation.json`.

## Chạy trên Colab T4

1. Mở `scripts/colab_atomic_verifier_cellfix10.ipynb`, dùng runtime mới và GPU T4.
   Chạy cells 1–5. Payload tự chứa source đã khóa; không cần vá cell cũ hoặc
   upload review validation30 trong cell 2.
2. Smoke phải đạt trước probe18. Giữ ZIP dù stage đạt hay trượt. Khi probe đạt,
   tải form mới, review từng tiêu chí và xuất semantic-review.json cho chính run
   mới. Review của cellfix9 không mở được gate này.
3. Sau human review probe mới, bật `RUN_FULL39=True` ở cell 6 và upload review
   đó. Full39 cần 39/39 nhãn đúng, false support=0, runtime=0 cùng budget/trace
   đạt. Nếu trượt, giữ ZIP và dừng trước validation30.
4. Nếu full39 đạt, review đủ 39 prediction/evidence/explanation bằng form mới.
   Chỉ sau admission human full39 mới bật `RUN_VALIDATION30=True` ở cell 7.
   Chưa có full39 đạt thì giữ biến này False.

Chưa có CUDA tại máy local. **Chưa đo smoke/probe/full39 GPU cellfix10, chưa có
human review mới, chưa chạy validation30 và chưa promote serving/E2E.** Không
suy từ regression hoặc đường token hợp lệ rằng model sẽ đạt 39/39.
