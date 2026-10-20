# Cellfix9 — chạy candidate mới trên Colab T4

Candidate này sửa assessment; chưa có kết quả inference GPU của cellfix9.
Mốc cellfix8 vẫn là **29/39, false support=0 theo gold, 3 incomplete**, không đạt gate.
ZIP, source và predictions thất bại được giữ nguyên tại
`research-runs/audit-cellfix8-resume-full39-20261020T095348Z-7974a5cc/`.

## Thay đổi

- **Binding:** gắn member và predicate với clause được trích dẫn; không mượn
  predicate từ subject khác. Nhận diện tên ở cả đầu và cuối entity nhiều từ.
  Decoder chọn member/quote theo cùng quy tắc với validator. Numeric ledger vẫn
  cho phép các câu khác nhau chứng minh những quantity khác nhau của cùng event.
- **Polarity:** kiểm kết quả của chính member, giữ truth của positive predicate
  trước ALL/SOME/NONE. Vế một member cải thiện không phủ nhận phản ví dụ của
  member khác. Một danh sách tên không phải bằng chứng về kết quả.
- **Coverage:** chỉ dùng shortcut khi nguồn nêu rõ population đóng và kết quả
  tập thể hoặc đầy đủ kết quả từng tên. Một source span tập thể có thể đại diện
  population khi trích cả khai báo lẫn kết quả, và coverage/observation dùng cùng
  member đó. Validator vẫn chấp nhận ledger từng member hợp lệ. Không ép closure
  cho subset, missing results, sai scope, số lượng không khớp hay báo cáo bị rút lại.
- **Missing-information:** từ chối thiếu sai metric, bỏ qua chứng cứ quyết định
  đã có, hoặc thêm citation tác giả/năm không có trong input. Lỗi đi vào repair
  có giới hạn; không tự sửa predictions hay tự nâng unknown thành support.
- Shortcut collective không dùng `numeric=null` khi claim/evidence cần numeric
  ledger. Các quantity độc lập và arithmetic giữ contract trước.

Source mới nằm trong `research-runs/atomic-cellfix9-candidate/workspace/`.
Năm source/test có sẵn thay đổi: `atomic_verifier.py`, `atomic_decoding.py`,
`assessment_rules.py`, `assessment_decisions.py`, `test_atomic_verifier.py`.
Thêm module `assessment_evidence.py`, fixture trace cellfix8 full39 và 39 test mới.
Diff có tại [CODE_DIFF.patch](reviews/cellfix9-development/CODE_DIFF.patch).

Ba fixture unit-test cũ đã được chỉnh trong bản copy mới: phép toán dùng quote
không có subject, kiểm coverage dùng metric/truth không khớp nguồn, và kiểm
conflict atomic dùng hai subject khác target. Giữ mục đích assertion; thêm test
âm xác nhận citation không bind subject bị từ chối. **Không thay gold, claim,
context hoặc gate của bộ 39 hay validation30.**

## Những gì giữ nguyên

- Qwen/Qwen2.5-3B-Instruct, revision
  `aa8e72537993ba99e69dfaafa59ed015b17504d1`, NF4/float16, seed42, không sampling.
- 8 calls/ca, 2 attempts/stage, 1536 generated tokens/call, deadline 180 giây/ca.
- Full39: 312 calls, 479.232 generated tokens; gate phải đủ 39 ca, 39 nhãn đúng,
  false support=0, runtime failures=0, đủ trace và trong budget.
- Decomposition prompt, dữ liệu development, model files/tokenizer và validation30.
- Validation30 giữ nguyên gold/review/protocol, chỉ có binding mới
  `docs/validation/atomic-cellfix9-v1/`. Không tạo chữ ký human mới cho gold cũ.
- Không promote serving và chưa tích hợp Reader/Summarizer vào verifier này.

## Kiểm local

**291/291 regression** (39 test mới), **21/21 đường token filter Qwen**,
**15 test notebook + 6 test workflow** và cả **bốn validate-only từ payload** đạt.
Payload đóng băng gồm 115 file; criteria SHA-256:
`6abc7038759bd361155c3aa19745c664af67e9f8e3f3fc6e26e1a436d6b6caf8`.
Payload SHA-256:
`73627aa73f466be72a50b2b3f1ff72094db29ff4f1eb9205e0b8bf78358e72ac`.

Xem [regression](atomic-verifier-cellfix9-validation.json),
[tokenizer](atomic-verifier-cellfix9-tokenizer-check.json),
[đóng gói và bốn validate-only](atomic-verifier-cellfix9-packaging-validation.json),
[overlap](atomic-verifier-cellfix9-validation-overlap.json) và
[preservation](reviews/cellfix9-development/PRESERVATION_CHECK.json).
Đây là kiểm code, schema và các đường token được dựng để thử; không phải accuracy
hoặc false support đo từ predictions GPU mới. Workflow test dùng backend giả và
dữ liệu dùng một lần, không chạy model trên validation30 thật.

## Chạy trên Colab

1. Mở `scripts/colab_atomic_verifier_cellfix9.ipynb` trên Colab, chọn T4 và dùng
   runtime mới. Notebook đã chứa payload được khóa; không cần ZIP cellfix8 hoặc
   `RESTORE_AND_RUN_FULL39.py` cũ.
2. Chạy lần lượt cell 1–5 hoặc Run all. Notebook kiểm hash, dựng venv, chạy lại
   regression + bốn validate-only, rồi smoke12. Probe18 chỉ chạy khi smoke đạt.
   ZIP chẩn đoán được tải kể cả khi thất bại. Cell chạy xong không đồng nghĩa gate đạt.
3. Nếu smoke trượt, giữ ZIP và dừng. Không bỏ gate hoặc tăng budget để chạy tiếp.
4. Nếu probe18 đạt, đọc form `HUMAN_REVIEW.html` mới của chính run cellfix9.
   Người review xác nhận từng tiêu chí, ghi notes rồi xuất `semantic-review.json`.
   Review cellfix8 không dùng lại được vì criteria/predictions đã đổi.
5. Đặt `RUN_FULL39 = True` ở cell 6, chạy cell đó và upload đúng review probe
   vừa xuất. Admission phải đạt trước khi worker full39 được gọi. Gửi ZIP kết quả
   mới để audit toàn bộ labels, quotes, numeric ledger, scope và explanations.
6. Chỉ khi full39 qua automated gate và review evidence/explanation đủ 39 ca
   thực sự đạt, mới dùng review full39 cho cell 7. Validation30 mặc định tắt.
   Nếu dùng kết quả validation để chỉnh code, phải chuyển bộ đó thành development
   và chuẩn bị validation khác; không tiếp tục gọi nó là đánh giá độc lập.

## Giới hạn cần giữ khi kết luận

Đây là grammar tiếng Anh hữu hạn, không phải một bộ chứng minh entailment tổng
quát. Modifier không đủ, alias/coreference, collective scope phức tạp và prose
ngoài các mẫu kiểm vẫn cần đánh giá. Ràng buộc structural/source không bảo đảm
model chọn đúng mọi witness hoặc repair thành công trong hai lượt. Chưa được
khẳng định smoke/probe/full39/validation30 của cellfix9 đạt trước khi có run thật.

Human review mới phải do người trực tiếp đọc kết quả thực hiện. AI audit hay
backend giả trong unit-test không thay chữ ký human và không mở gate.
