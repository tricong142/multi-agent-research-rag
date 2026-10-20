# Cellfix7 — chạy đúng các gate trên Colab T4

Candidate mới sửa assessment từ mốc cellfix6 smoke **7/12, false support=0**.
Mốc cellfix6, ZIP, source, calls và predictions được giữ nguyên. Cellfix7 chưa
có kết quả inference GPU; regression và tokenizer feasibility chỉ là kiểm offline.

## Những gì thay đổi

- Validator và decoder dùng chung quy tắc source có phạm vi hữu hạn để phân
  biệt scope với truth. Khác số liệu/phủ định của cùng chủ thể không được khai
  mismatched để né counterevidence khi nguồn nằm trong grammar được hỗ trợ.
- Một phản ví dụ đúng scope có thể bác ALL. Kết quả khác nhau giữa các member
  không phải mâu thuẫn cho cùng member. Trường hợp thiếu, có modality, có nhiều
  chủ thể/binding chưa rõ hoặc báo cáo trái nhau vẫn giữ đường unknown.
- Với nhiều quantity, model xuất ledger `q0`, `q1`, ... theo thứ tự requirements.
  Mỗi khóa bắt buộc gắn left operand của chính requirement đó. Decoder không
  dùng tuple/uniqueItems vì implementation lm-format-enforcer 0.11.3 được kiểm
  không thực thi ràng buộc đó như yêu cầu. Validator vẫn replay được record/list
  cũ, không sửa raw output hoặc predictions lịch sử.
  Nhánh false phải có ít nhất một record chứng minh sai; không cho ledger toàn null.
- Cặp before/after đối lập và time/condition của chính measurement được kiểm,
  tránh mượn scope từ metric khác. Named-property decomposition giữ nguyên.
- Model/revision, NF4/float16/seed42, 8 call/ca, 2 attempt/stage, 1536 token/call,
  deadline 180s/ca và gate full39 giữ nguyên. Không thêm dependency.

Các quy tắc trên không phải bộ giải NLI/coreference tổng quát. Cấu trúc ngoài
grammar có thể vẫn bị từ chối hoặc được model đánh giá sai; bắt buộc đo smoke,
review prediction và full39/validation thay vì suy ra chất lượng từ unit test.
Việc ép một quyết định theo source chỉ áp dụng cho grammar hữu hạn và chủ thể
đơn hoặc proper name được hỗ trợ. Population có modifier phức tạp vẫn cần model
và review semantic; không suy ra certainty từ substring như certified trong non-certified.

Các file behavior thay đổi nằm trong
`research-runs/atomic-cellfix7-candidate/workspace/04_factchecker/inference/`:
`assessment_decisions.py` (quy tắc chung và ledger), `assessment_rules.py`
(before/after), `atomic_verifier.py` (validator/repair), `atomic_decoding.py`
(schema dùng cùng quy tắc). Serving ở thư mục gốc không được thay bằng candidate.
Regression mới ở `research_rag/tests/test_atomic_assessment_cellfix7.py` trong
cùng workspace, gồm trace thật và câu development mới.

Ba fixture test cũ của candidate được cập nhật có chủ đích: serializer cho wire
ledger mới; context thực sự thiếu dữ liệu cho unknown; test backend luôn NEI
chấp nhận việc bị đưa vào bounded repair. Các test blinding, không false support,
không pass gate và từ chối mọi gold support của backend này vẫn giữ. Không giảm
ngưỡng chấm model để làm test xanh.

## Chạy notebook

Mở [colab_atomic_verifier_cellfix7.ipynb](../scripts/colab_atomic_verifier_cellfix7.ipynb)
trên Colab, chọn **runtime mới, GPU T4**. Chạy cells 1–5:

1. Giải nén source và kiểm manifest; xác nhận binding validation mới.
2. Dựng môi trường cô lập. **Không cần upload lại review30 ở cell 2.** Bản
   review đã được xác nhận cùng lock gốc được nhúng nguyên văn, có hash.
3. Regression, CUDA, validate-only của smoke12/probe18/full39 và validation30;
   tải đúng model revision.
4. Chạy smoke12. Phải đúng 12/12 nhãn, false support=0, runtime failure=0 và
   đủ trace/budget. Nếu trượt: giữ ZIP, dừng; không bỏ gate để chạy tiếp.
5. Chỉ smoke đạt mới chạy probe18. Probe đạt cấu trúc sẽ xuất
   `HUMAN_REVIEW.html` và ZIP. Đọc đủ 18 claim, từng part/scope/quantity, xác nhận
   riêng năm tiêu chí, ghi chú từng ca rồi xuất `semantic-review.json`.

**Run all mặc định dừng ở đây.** Cells 6/7 đều có biến điều khiển mặc định False.
Giữ ZIP tải cuối cùng, kể cả khi trình duyệt thêm hậu tố `(1)` vào tên. Luôn giữ
ZIP chẩn đoán trước khi sửa hoặc chạy lại.

## Full39 sau review probe

Trong cell 6, đổi `RUN_FULL39 = False` thành `RUN_FULL39 = True`, chạy cell và
upload **review của probe cellfix7 vừa chạy**. Không dùng review30 hay review của
candidate cũ. Cell tạo `reviewed-probe` riêng; probe unsigned nguyên gốc được giữ.

Runner kiểm criteria/prediction hashes, đủ 18 ca/90 judgments và notes, replay
probe cùng provenance trước khi gọi model full39. Gate vẫn là đúng 39/39,
false support=0, runtime failure=0, đủ call/token/deadline/structured trace.
Annotation development là `strict-identity-v1`, không thay claim/context.

Full39 trượt thì giữ ZIP và dừng. Full39 đạt sẽ xuất **form review mới cho 39
prediction/evidence**. Kiểm nhãn, evidence/scope, explanation, đủ part/quantity
và missing information. Xuất `semantic-review.json` mới từ form này.

## Validation30 sau full39 và review evidence

Trong cell 7, đổi `RUN_VALIDATION30 = False` thành True, chạy và upload
**review của full39**. Cell giữ bản unsigned, tạo `reviewed-verifier39`, rồi
replay đầy đủ gate full39 và kiểm human review trước validation.

Validation dùng 30 ca / 10 paper đã được review. Model chỉ nhận claim/context;
gold không nằm trong messages. Mỗi ca giữ budget như development; tổng tối đa
240 calls, 368.640 generated tokens. Gate pilot vẫn là đúng 30/30, false support=0,
runtime failure=0, đủ trace/budget và đúng đủ từng paper.

Output có predictions, calls, provenance, metrics, confusion, precision/recall
từng nhãn, kết quả từng paper và latency. Vẫn cần rà evidence của kết quả mới;
automated pass không tự promote vào serving.

Nếu dùng bất kỳ outcome validation nào để chỉnh prompt/code/chọn candidate,
chuyển bộ này thành development và chuẩn bị bộ mới. Không sửa gold hoặc bỏ ca
sau khi xem prediction rồi vẫn báo đây là validation độc lập.

## Binding và bảo toàn

- [Binding hiện hành](validation/atomic-cellfix7-v5/binding.json) dẫn chiếu
  criteria cellfix7 cùng hash của cases, blind inputs, protocol, review và lock
  annotation gốc. Các byte này được giữ nguyên từ cellfix6.
- Căn cứ rebind là yêu cầu trực tiếp của người dùng đổi candidate và lập lock
  mới. `new_human_signature_created=false`: không ký thay người review, không
  đổi tên/ngày/nhãn/notes của review cũ để khớp candidate mới.
- Các binding v1–v4 là bản nháp local đã được thay thế trong quá trình kiểm,
  không có validation inference; notebook phát hành dùng v5.
- Review gold30 không thay review decomposition18 hoặc prediction39 mới.
- [Preservation](atomic-verifier-cellfix6-preserved-before-cellfix7.json) giữ hash
  ZIP/source/predictions và mọi file validation30 cũ. Kết quả cellfix5 21/39 trên
  annotation gốc cùng baseline lịch sử 37/39 giữ nguyên.

## Kiểm đã thực hiện và giới hạn

Xem [regression/validate-only](atomic-verifier-cellfix7-validation.json),
[token filter Qwen thật](atomic-verifier-cellfix7-tokenizer-check.json) và
[kiểm đóng gói/workflow](atomic-verifier-cellfix7-packaging-validation.json).
Backend giả trong test chỉ kiểm orchestration, blinding và gate; không đo
chất lượng model. Reader/Summarizer/E2E thực tế chưa được nghiệm thu qua lượt này.

Nếu Colab hết phiên trước khi review xong, giữ ZIP đã tải. Cần khôi phục đúng
artifact/candidate và kiểm admission trước khi tiếp tục; không lấy lại biến
`passed=True` hoặc sửa hash để vượt gate. Có thể gửi ZIP đó để dựng lượt tiếp
tục từ artifact đã kiểm.
