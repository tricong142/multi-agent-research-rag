# Cellfix8 — sửa hai lỗi smoke cellfix7, giữ gate

Mở [colab_atomic_verifier_cellfix8.ipynb](../scripts/colab_atomic_verifier_cellfix8.ipynb)
trên **Colab, runtime mới, GPU T4**. Không chạy tiếp từ biến của cellfix7.

## Thay đổi

- Parser kiểm ký tự và thay LMFE freetext cache bằng cache lọc theo alphabet/
  whitespace của request, kiểm qua trie tại biên. Cache cũ đã tái hiện cho EOS
  trên JSON chưa hoàn chỉnh. Giữ explanation tối đa 64 ký tự và token/call budget.
- Adapter empty array thực thi maxItems=0, ngăn missing-information xuất hiện
  khi finite witness đủ quyết định part. Không thêm dependency.
- Validator/decoder dùng chung quy tắc hữu hạn cho scoped named property.
  Output đòi dữ liệu ở dataset/thời gian khác đi vào repair; không tự gán nhãn
  support. Genuine missing, sai scope, modality và conflicting reports giữ đường unknown.
- Thêm regression từ trace cellfix7 và câu mới; giữ toàn bộ regression cũ.
- Mốc cellfix7 10/12, false support=0, runtime failure=1 cùng ZIP/source/raw output
  giữ nguyên. Không promote vào serving, không sửa Reader/Summarizer trong lượt này.

Giữ Qwen/Qwen2.5-3B-Instruct revision
`aa8e72537993ba99e69dfaafa59ed015b17504d1`, NF4/float16/seed42, do_sample=False.
Mỗi ca tối đa 8 calls, 2 attempts/stage, 1536 token/call, 180 giây.

Runtime thay đổi chỉ trong candidate
`research-runs/atomic-cellfix8-candidate/workspace/04_factchecker/inference/`:
`decoder_parser.py` (adapter mới), `atomic_decoding.py` (schema/cache),
`assessment_decisions.py` (scoped witness/missing) và `atomic_verifier.py`
(prompt/repair hint/policy). Regression mới ở
`research_rag/tests/test_atomic_assessment_cellfix8.py` trong cùng workspace.
Contract, criteria và manifest mới được đóng băng cùng notebook; serving gốc
không được thay bằng candidate.

## Chạy lần lượt

1. **Cells 1–3:** nạp payload, kiểm hash/binding, dựng GPU, regression, bốn
   validate-only và pinned model cache. Không cần upload lại review30 ở cell 2.
2. **Cell 4 — assessment-smoke:** phải đạt 12/12 nhãn, false support=0,
   runtime failure=0, đủ trace và đúng budget. Luôn tải ZIP kể cả trượt.
3. **Cell 5 — probe18:** chỉ chạy khi smoke đạt. Tải HUMAN_REVIEW.html, review
   đủ 18 ca/90 tiêu chí, ghi notes và xuất semantic-review.json mới.
4. **Cell 6 — full39:** đổi RUN_FULL39=False thành True, upload review probe
   vừa chạy. Runner replay hash/admission trước khi gọi model. Gate vẫn 39/39,
   false support=0, runtime failure=0, đủ trace/budget. Không dùng review cũ.
5. **Review prediction/evidence39:** full39 đạt sẽ xuất form mới; kiểm đủ bằng
   chứng, scope, từng quantity, missing information và nhãn; xuất review mới.
6. **Cell 7 — validation30:** đổi RUN_VALIDATION30=False thành True, upload
   review full39. Admission/replay full39 phải đạt rồi mới gọi validation.

Run all mặc định chỉ đến probe18; cells 6/7 mặc định tắt. Bất kỳ gate nào trượt
thì giữ ZIP và dừng; không sửa passed/hash/gold để chạy tiếp.

## Validation30

Giữ cases, context, gold, protocol, chữ ký annotation và lock cũ nguyên byte;
binding mới tại [atomic-cellfix8-v1](validation/atomic-cellfix8-v1/binding.json).
Đây là rebind candidate theo yêu cầu hiện hành, không phải ký human review mới.
Không dùng outcome của bộ30 để sửa cellfix8. Nếu dùng outcome để tune/chọn
candidate, phải chuyển bộ này sang development và chuẩn bị validation mới.

## Bằng chứng kiểm local và giới hạn

Đã đạt **252/252 regression** (15 test mới), **20/20 test đóng gói/workflow**,
**14/14 đường tokenizer Qwen thật** và replay canonical BPE của prefix lỗi.
Payload 111 file giải nén từ chính notebook qua cả bốn validate-only.

Xem [regression](atomic-verifier-cellfix8-validation.json),
[tokenizer thật](atomic-verifier-cellfix8-tokenizer-check.json),
[đóng gói/workflow](atomic-verifier-cellfix8-packaging-validation.json).

Tests/replay không đo độ chính xác inference mới. Smoke, probe18, full39 và
validation30 của cellfix8 vẫn cần chạy thật trên T4, kèm các review mới.
Parser kiểm chặt có thể tăng CPU latency; deadline/budget không đổi, cần đo từ
ZIP T4. Quy tắc semantic hữu hạn không chứng minh entailment/coreference tổng quát.
Không tuyên bố dự án Ready hoặc zero false support trên full39 khi chưa đo.
