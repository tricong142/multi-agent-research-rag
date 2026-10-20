# Trạng thái hoàn thiện Research RAG — 2026-10-20

**Chưa đạt gate phát hành.** Đã có workflow LangGraph và các lượt inference
thật; diagnostic còn trượt confidence/Reader PDF và atomic verifier. Đây là
trang trạng thái hiện hành; các run log khác giữ lịch sử và bằng chứng chi tiết.

## Hiện tại — cellfix10 T4 smoke/probe đạt; chờ human probe trước full39 — 2026-10-20

- Audit run `20261020T145035Z-d525a354`: **71 output/120 input khớp release**,
  replay 30 predictions/46 call triplets; metrics và derived parts khớp source.
  Colab regression 314/314 và bốn validate-only đạt; model/revision/budget giữ nguyên.
- Smoke **12/12 nhãn đúng, false support=0, runtime=0**, 28 calls. Probe **18/18
  decomposition hợp lệ**, 20 part, 18 calls; không phải phép đo label accuracy.
- AI review đủ 90 tiêu chí decomposition: 18/18 claim đạt theo AI, notes riêng.
  Review human trong ZIP trống; admission chặn đúng. Full39 cellfix10 chưa chạy,
  chưa đo lỗi scope/SOME mới trên model, validation30 vẫn chưa chạy.
- Chất lượng smoke còn điểm cần theo dõi: member ở irrelevant là một đoạn văn,
  missing causality chưa nêu rõ chứng cứ nhân quả, partial numeric chưa chỉ rõ
  quantity trong prose missing. Nhãn đúng không đồng nghĩa mọi evidence/prose đạt.
- Có thể chạy full39 để đánh giá **sau human review probe đúng run/hash**.
  Chưa có human evidence review full39 hoặc serving/E2E pass.
- [Audit và bước tiếp](reviews/cellfix10-20261020T145035Z-d525a354/AUDIT_AND_NEXT_STEPS.md),
  [form có ghi chú AI](reviews/cellfix10-20261020T145035Z-d525a354/HUMAN_REVIEW_WITH_AI_NOTES.html),
  [hash/replay](atomic-verifier-cellfix10-smoke-probe-audit-20261020T145035Z-d525a354.json).

## Mốc đóng băng — cellfix10 kiểm local trước T4 — 2026-10-20

- Đã bảo toàn cellfix9 ZIP/source/predictions **36/39, false support=0, 2 incomplete**.
  Đây vẫn là mốc GPU gần nhất. Chưa có kết quả model mới của cellfix10.
- Người dùng xác nhận audited set là toàn bộ cache nodes trong ca SOME. Candidate
  mới lưu adjudication và bổ sung quy ước unique complete selection-set; không
  đổi claim/context/gold, không có nhánh runtime theo ID hoặc tên của ca test.
  Closure vẫn cần toàn bộ kết quả và đúng scope; hiển thị binding basis để review.
- Sửa repair coverage và dùng missing reason code theo part. Decoder phát ghi chú
  cố định; explanation/missing cho người dùng được dựng từ ledger đã kiểm.
  Raw model prose giữ trong trace/model_explanation, không coi là evidence.
- **314/314 regression** (23 test mới), **27/27 đường token filter Qwen**,
  **15 test notebook + 6 test workflow**, **bốn validate-only từ payload** đạt.
  Replay 39 output legacy từ chối ba ca lỗi; không tạo prediction/model score mới.
- Criteria `2edd14d0e7fb728b3ba6eb99923ade128573ed2938f55bfeb2d1a0e4a06f8cda`;
  **106 file candidate, 120 file payload**. Model/revision/budget/gate và
  decomposition prompt giữ nguyên. Validation30 giữ nguyên gold/review/protocol,
  binding mới cellfix10-v1, overlap screen 0 cờ và chưa dùng để tune.
- Notebook mặc định chỉ chạy smoke -> probe18. Cần human review cho probe mới
  trước full39 và human evidence review full39 đạt trước validation30. **Chưa có
  inference GPU cellfix10, chưa có human review mới và chưa promote serving/E2E.**
- [Notebook](../scripts/colab_atomic_verifier_cellfix10.ipynb),
  [hướng dẫn và giới hạn](ATOMIC_VERIFIER_CELLFIX10_HANDOFF.md),
  [release](atomic-verifier-cellfix10-release.json),
  [kiểm đóng gói](atomic-verifier-cellfix10-packaging-validation.json).

## Mốc GPU gần nhất — cellfix9 full39 đạt 36/39, validation30 bị chặn — 2026-10-20

- Đã audit ZIP `output-cellfix9-fresh-20261020T110710Z-cf47db2f (3).zip`:
  **105 output/115 input khớp hash**, đúng release. Replay đủ 69 prediction rows
  và **141 call triplets** (smoke31, probe18, full39 92); metrics khớp từng trường.
  Colab regression 291/291 và cả bốn validate-only đạt.
- Smoke **12/12 nhãn đúng, false support=0, runtime=0**; probe **18/18 decomposition
  hợp lệ**, không phải phép đo accuracy. Human probe review Trí Công đủ 90 tiêu chí
  và notes, đúng hash, admission replay đạt.
- Full39 **36/39 đúng, false support=0 theo gold, 2 incomplete**, một ca hoàn tất
  sai nhãn. Original contracts 12/12; scope regression 24/27; gold support 12/12.
  Gate giữ nguyên 39/39 và runtime=0 nên **chưa đạt**, exit code 1 là gate failure.
- `scope:existential:contradict`: sửa coverage lỗi lặp thành chỉ Fir=false,
  coverage=false, nên NEI thay vì frozen gold contradict. Hai incomplete do
  hai lượt đều bịa author/year ở direction:NEI hoặc missing sai metric ở
  conjunction:NEI. Guard chặn output sai đúng, nhưng repair chưa thành công.
- Ngoài điểm nhãn: `scope:none:support` có quote/ledger/label đúng nhưng prose
  nói có leak và claim bị contradicted; một số missing/prose vẫn sai hoặc bị cụt.
  Không suy zero false support theo gold thành đạt semantic review toàn bộ.
- **Validation30 chưa chạy, chưa có human review full39, admission chặn đúng.**
  Giữ `RUN_VALIDATION30=False`, bảo toàn ZIP/predictions/source. Audit này không
  sửa candidate/gold, không tạo human signature và không promote serving/E2E.
- [Audit, đủ 39 notes và hướng tiếp](reviews/cellfix9-full39-20261020T110710Z-cf47db2f/AUDIT_AND_NEXT_STEPS.md),
  [hash và replay](atomic-verifier-cellfix9-full39-audit-20261020T110710Z-cf47db2f.json).

## Mốc đóng băng — cellfix9 kiểm local trước T4 — 2026-10-20

- Mốc thất bại cellfix8 giữ nguyên ZIP/source/predictions và kết quả 29/39,
  false support=0 theo gold, 3 incomplete. Snapshot và hash có trong
  `atomic-verifier-cellfix8-preserved-before-cellfix9.json`.
- Cellfix9 sửa binding member/predicate/citation dùng chung validator/decoder,
  polarity theo từng member, coverage tập thể đóng rõ trong nguồn và
  missing-information sai metric/citation không có nguồn. Có regression từ trace
  cellfix8 và câu mới; không dùng case ID trong quy tắc runtime.
- **291/291 regression** (39 test mới), **21/21 đường token filter Qwen**,
  **15 test notebook + 6 test workflow**, cả **bốn validate-only từ payload** đạt.
  Đây là kiểm code/đường token dựng để thử và backend giả, chưa đo chất lượng model.
- Criteria `6abc7038759bd361155c3aa19745c664af67e9f8e3f3fc6e26e1a436d6b6caf8`;
  101 file candidate, 115 file payload. Model/revision, decomposition prompt,
  dữ liệu, budget/gate giữ nguyên. Validation30 gold/review/protocol giữ nguyên;
  binding mới cellfix9-v1, overlap screen không báo cờ, chưa dùng để tune.
- Notebook mới mặc định chạy smoke -> probe18; full39/validation30 tắt. Cần human
  review probe cho chính predictions mới trước full39. **Chưa có smoke/probe/full39
  inference GPU cellfix9, chưa có human review mới, chưa promote serving/E2E.**
- [Notebook](../scripts/colab_atomic_verifier_cellfix9.ipynb),
  [hướng dẫn và giới hạn](ATOMIC_VERIFIER_CELLFIX9_HANDOFF.md),
  [release](atomic-verifier-cellfix9-release.json),
  [kiểm đóng gói](atomic-verifier-cellfix9-packaging-validation.json).

## Mốc bảo toàn — cellfix8 full39 chạy đủ, 29/39, chưa đạt — 2026-10-20

- Recovery `20261020T095348Z-7974a5cc` từ run probe
  `20261020T061934Z-c87bce57`: **128 output/111 input khớp hash**; lineage,
  human admission Trí Công và smoke replay đạt. Model/revision, source/prompt,
  contract, budget và gate không đổi. Môi trường Colab T4 dựng thành công.
- Replay đủ **39 predictions/95 call triplets**, metrics khớp: **29/39 đúng,
  false support=0 theo gold, 3 incomplete do invalid_output_exhausted**.
  Original contracts 12/12; scope regression 17/27. Bảy ca hoàn tất sai nhãn;
  bốn trong 12 gold support chưa được nhận đúng. Exit code 1 do gate thất bại.
- Cả 95 generation đều parse JSON được, không có deadline/OOM trong kết quả.
  Ba incomplete: universal:contradict, none:contradict, time:support.
- **Có support đúng nhãn nhưng sai citation**: scope:entity:support nói North
  gateway nhưng chỉ cite South gateway. Guard polarity còn reject nhầm phản ví dụ
  third shard vì mượn vế improved của shard khác. NONE/coverage còn sai; prose
  nêu thiếu sai metric và tự thêm Shepherd et al. (2023) không có trong context.
  Zero false support theo gold không chứng minh evidence đã đúng toàn bộ.
- Đã bảo toàn ZIP/source/predictions và AI audit từng ca; không ký human full39,
  không thay annotation/predictions, **validation30 chưa chạy và bị chặn đúng**.
  Chưa promote serving/E2E. Candidate tiếp cần sửa binding, polarity, closure,
  missing-information qua regression trace thật + câu mới; giữ validation30 độc lập.
- [Audit, 39 nhận xét và hướng tiếp](reviews/cellfix8-full39-20261020T095348Z-7974a5cc/AUDIT_AND_NEXT_STEPS.md),
  [replay và hash](atomic-verifier-cellfix8-full39-audit-20261020T095348Z-7974a5cc.json),
  [diagnostic guard](atomic-verifier-cellfix8-full39-audit-20261020T095348Z-7974a5cc-guard-diagnostics.json).

## Lịch sử trước recovery — cellfix8 smoke12 và human probe18 đạt — 2026-10-20

- Run `20261020T061934Z-c87bce57`: 71 output/111 input khớp hash; replay đủ
  smoke12/probe18 và 46 call triplets, metrics khớp. Colab regression 252 đạt,
  cả bốn validate-only đạt. HTML đính kèm trùng nguyên byte form trong ZIP.
- **Smoke đúng 12/12, false support=0, runtime failure=0**, 28 calls. Probe
  **18/18 cấu trúc hợp lệ**, 20 part, 18 calls; chưa đo label accuracy trên probe.
- AI đã đánh giá riêng 90 tiêu chí decomposition, 18 claim đạt. 014: in May lọc
  population trial conducted in May, không gán May làm thời điểm improvement.
  018: entity batch + low-temperature group giới hạn population đúng.
- Trí Công đã gửi human review của run mới, đủ 90 judgments và notes; hash
  khớp criteria/predictions. **require_probe_review admission/replay đạt**.
  Giữ file human nguyên byte, AI review/unsigned gốc giữ riêng, không ký thay.
- Smoke còn vấn đề chất lượng explanation/missing-information: partial_memory
  nêu thiếu sai metric; accuracy_conflict diễn giải memory sang accuracy;
  một số câu giải thích bị cụt. Không suy từ đúng nhãn thành đạt review evidence.
- Chưa có full39 hoặc validation30 của cellfix8. Đã chuẩn bị cell RUN_FULL39=True
  với run_id/admission gốc và kiểm đúng hash human upload trước khi copy;
  chưa execute model. Chưa promote serving/E2E.
- [Human admission và bước full39](reviews/cellfix8-20261020T061934Z-c87bce57/human/NEXT_STEPS.md),
  [machine admission](reviews/cellfix8-20261020T061934Z-c87bce57/human/admission.json).
- Handoff gặp globals run_id không khớp; chưa có bằng chứng artifact cũ còn/mất
  trong Colab. Đã chuẩn bị [đường khôi phục từ ZIP + human review](reviews/cellfix8-20261020T061934Z-c87bce57/human/RESTORE_GUIDE.md),
  workspace riêng, pins cũ, replay/admission trước model; không sửa assert để
  gán nhầm source và không tạo candidate mới. **7/7 test recovery đạt**, replay
  smoke/human admission thực tế từ bản khôi phục đạt, pins/release giữ nguyên.
  Full39 recovery chưa chạy trên T4.
- [Audit và bước tiếp](reviews/cellfix8-20261020T061934Z-c87bce57/AUDIT_AND_NEXT_STEPS.md),
  [review đủ 18 claim](reviews/cellfix8-20261020T061934Z-c87bce57/DECOMPOSITION_REVIEW.md),
  [form human có notes AI](reviews/cellfix8-20261020T061934Z-c87bce57/HUMAN_REVIEW_WITH_AI_NOTES.html).

## Lịch sử — cellfix7 trượt smoke 10/12; cellfix8 kiểm local trước T4 — 2026-10-20

- ZIP run `20261020T033551Z-c7337790` khớp 53 output/107 input; replay đủ
  12 predictions/29 calls và metrics. **10/12 đúng, false support=0, runtime=1**.
  Chưa có probe18/full39/validation30 của cellfix7; baseline 37/39 là lịch sử.
- Hai lỗi: JSON còn mở sau 111 token ở both_supported; bounded_scope khai thiếu
  dữ liệu dataset ngoài claim dù observation true/matched. Đã bảo toàn ZIP,
  source/predictions và validation30 gốc.
- Cellfix8 sửa freetext parser/cache theo alphabet và biên ký tự, empty array
  maxItems=0, cùng scoped missing-information qua bounded repair. Model/revision,
  budget/gate, decomposition prompt và gold validation giữ nguyên.
- **252/252 regression**, **20/20 test đóng gói/workflow**, **14/14 đường tokenizer
  Qwen thật** đạt; đã tái hiện EOS sớm ở parser cũ và chặn prefix lỗi ở parser mới.
  Payload 111 file qua cả bốn validate-only. Binding validation mới là cellfix8-v1;
  source/predictions cellfix7 và review/lock/gold validation30 giữ nguyên hash.
- Chưa có inference GPU cellfix8. Kiểm local không xác nhận smoke12/full39 đạt.
- [Audit cellfix7](ATOMIC_VERIFIER_CELLFIX7_SMOKE_REVIEW_20261020T033551Z-c7337790.md),
  [hướng dẫn cellfix8](ATOMIC_VERIFIER_CELLFIX8_RUN_GUIDE.md),
  [kiểm đóng gói cuối](atomic-verifier-cellfix8-packaging-validation.json).

## Lịch sử — cellfix7 đã kiểm local trước inference — 2026-10-20

- Cellfix7 là candidate riêng từ source cellfix6 đã audit; ZIP/source/predictions
  thất bại 7/12, false support=0 và toàn bộ validation30 cũ giữ nguyên hash.
- Sửa quy tắc chung scope/truth, witness bác ALL và ledger q0/q1 cho từng quantity;
  nhánh false cần một record thực sự sai. Model/revision, budget/gate và prompt
  decomposition giữ nguyên; không promote vào serving.
- **237/237 regression đạt**, gồm 26 test mới từ trace/câu development mới;
  **20/20 test đóng gói/workflow đạt**. Payload giải nén từ notebook qua cả bốn
  validate-only smoke12/probe18/full39/validation30. Token filter Qwen thật đạt
  10/10 đường thử, không tải weights/generate predictions.
- Validation30 dùng gold/review cũ nguyên byte, binding mới
  [v5](validation/atomic-cellfix7-v5/binding.json) theo yêu cầu đổi candidate;
  không ký human review mới. Kiểm thêm 53 file development, không thấy overlap
  lexical theo các quy tắc đã công bố; chưa dùng outcomes validation để tune.
- Notebook 7 cell chạy smoke → probe18 + review → full39 + review → validation30.
  Hai chặng cuối mặc định tắt, kiểm admission/replay trước khi gọi model.
  Chưa có inference cellfix7, số đo full39/validation30 hoặc E2E thực tế.
- [Notebook và hướng dẫn](ATOMIC_VERIFIER_CELLFIX7_RUN_GUIDE.md),
  [kết quả regression](atomic-verifier-cellfix7-validation.json),
  [kiểm đóng gói cuối](atomic-verifier-cellfix7-packaging-validation.json).

## Lịch sử — cellfix6 trượt smoke 7/12; probe/full39 bị chặn — 2026-10-20

- Run `20261019T171503Z-bfe32d16` đã qua cell 2, review admission và T4 preflight.
  211 regression và ba validate-only đạt; 12 ca smoke hoàn tất, **7/12 đúng nhãn,
  false support=0, runtime failure=0**. Contradict recall 0/4; support recall 3/4.
- Audit đủ 50 output/99 input; replay 12 predictions và 29 call triplets khớp
  metrics. Năm ca sai liên quan scope-vs-truth, phản ví dụ ALL và numeric ledger.
  Một attempt bị từ chối đúng vì duplicate_numeric_requirement; repair trả NEI sai.
- Cùng 12 claim/context/gold trong cellfix5 đã lưu đạt 12/12. Đây là suy giảm
  trên development, chưa có ablation xác định ảnh hưởng riêng code/prompt.
- Notebook chặn probe18; chưa có full39/validation30 inference của cellfix6.
  Số 37/39 trong baseline-metrics là lịch sử, không phải kết quả candidate này.
- [Audit và hướng tiếp theo](ATOMIC_VERIFIER_CELLFIX6_SMOKE_REVIEW_20261019T171503Z-bfe32d16.md),
  [machine audit](atomic-verifier-cellfix6-smoke-audit-20261019T171503Z-bfe32d16.json).

## Annotation validation cellfix6 đã khóa — 2026-10-20

- File review của Trí Công, ngày 2026-10-19, đạt admission đủ 30 ca / 10 paper.
  Đã tạo [validation-lock.json](validation/atomic-cellfix6-v1/validation-lock.json)
  khớp manifest và criteria cellfix6. Notebook vẫn khớp hash đã đóng gói.
- Có thể chạy notebook Colab T4 từ đầu và upload đúng file review ở cell 2.
  Chưa có inference mới, kết quả full39 hoặc validation30 của cellfix6.

## Chuẩn bị packet validation — 2026-10-19

- Chuẩn bị 30 ca từ 10 paper QASPER, claim mới và gold đề xuất kèm evidence
  nguyên văn/thông tin thiếu. Tách khỏi paper dev và paper từng trả về trong
  retrieval dev đã lưu; không thấy overlap lexical theo các kiểm đã công bố.
  Nhãn chưa được người review xác nhận; chưa gọi là final test độc lập.
- Protocol/hash đã được ghi trước inference. Notebook smoke/probe chứa đúng
  89 đầu vào candidate cộng 10 file packet; chặn GPU khi review chưa hợp lệ,
  tạo lock khi đủ xác nhận. Chưa chạy full39 hoặc validation30 của cellfix6.
- Kiểm bản đóng gói đạt 23/23 test admission/lifecycle; payload giải nén từ
  notebook đạt lại 211/211 regression và cả ba CLI validate-only.
  [Báo cáo kiểm gói](atomic-verifier-cellfix6-packet-validation.json).
- [Form review 30 ca](validation/atomic-cellfix6-v1/REVIEW.html),
  [hướng dẫn bước tiếp theo](ATOMIC_VERIFIER_CELLFIX6_VALIDATION_RUN_GUIDE.md).

## Cellfix6 sửa assessment, local đạt; chờ inference — 2026-10-18

- Người dùng chọn giữ context và đánh nhãn theo evidence nghiêm ngặt.
  Bản annotation `strict-identity-v1` chuyển hai ca conjunction S/C thành NEI
  vì thiếu identity extractor; ca NEI giữ nhãn, sửa rationale. Giữ nguyên bộ39
  gốc, ZIP/predictions cellfix5 và báo cáo lịch sử 21/39.
- Candidate riêng sửa absence-vs-false, scope của witness, positive predicate
  trước lượng từ, temporal adverb bị hiểu là unit và binding cặp số theo metric.
  Prompt assessment đổi; decomposition, model/revision, budget/gate giữ nguyên.
- **211/211 regression đạt**, gồm 30 test mới từ trace/câu development mới;
  ba CLI validate-only smoke12/probe18/full39 đạt. Token filter thật với tokenizer
  Qwen đạt 7/7 đường thử (4 hợp lệ, 3 bị chặn đúng). Kiểm này không nạp trọng số.
- Chưa có inference T4/smoke/probe/full39 mới, review candidate mới, validation
  độc lập hoặc tích hợp/E2E. Candidate chưa được promote vào serving.
- [Quyết định và phạm vi cellfix6](ATOMIC_VERIFIER_CELLFIX6_ASSESSMENT_DECISIONS.md),
  [kết quả local](atomic-verifier-cellfix6-validation.json).

## Lịch sử — full39 cellfix5 đã chạy, gate chưa đạt — 2026-10-18

- Run `20261018T153854Z-2c3e0bd6`: đủ 39 completed, **21/39 đúng nhãn**,
  **false_support=0**, runtime_failed_rows=0. Original contracts 12/12;
  scope regression 9/27. Đây là số đo của candidate cellfix5, không phải baseline.
- Support recall **5/13 (38,46%)**; chỉ có 5 predictions support. Zero false
  support không thay gate đúng 39/39. `automated_gate_pass=false`, exit 1 là
  trượt chất lượng, không phải crash/timeout. Human admission probe của Trí Công đạt.
- Đã kiểm hash/provenance, replay 39 predictions/85 calls và rà 46 part.
  181 regression và ba validate-only đạt trên T4; cả 39 decomposition trùng
  probe đã review. Lỗi còn ở truth/coverage, missing-vs-false, population,
  numeric binding/unit parser và exact-target schema. Hai ca conjunction cần
  làm rõ binding ngầm trong annotation trước khi thay guard.
- [Audit full39 và việc cần làm](ATOMIC_VERIFIER_CELLFIX5_FULL39_REVIEW_20261018T153854Z-2c3e0bd6.md).
  Chưa đủ điều kiện tích hợp/nghiệm thu verifier. Validation độc lập và E2E
  Reader/Summarizer/Writer với atomic verifier mới vẫn thiếu.

Các mục ngày 17/10 bên dưới giữ lịch sử trước lượt full39 cellfix5.

## Candidate verifier v8 — chuẩn bị local, chưa inference T4 — 2026-10-17

- Đã kiểm lại snapshot v7 211 file và ZIP/hash; giữ nguyên prediction/review cũ.
- V8 giới hạn explanation/quote, decoder chọn evidence nguyên văn và operand
  từ nguồn; thiếu numeric bắt buộc đi vào repair có giới hạn. Sửa binding
  predicate có `exactly`, explicit quantity denial và hint repair riêng assessment.
  Các quan hệ chưa hỗ trợ hoặc giả định vẫn unknown.
- Deadline tuyệt đối đi qua RecordingBackend vào Transformers stopping criteria;
  JSON dở được giữ trong trace và kết quả đến muộn bị loại. Đây là ngắt hợp tác
  khi decode; watchdog process vẫn cần để xử lý CUDA/prefill treo.
- Model/revision/data/budget và prompt decomposition giữ như v7. Chưa có kết quả
  GPU, human review v8, full39 hoặc validation độc lập; chưa kết luận zero false
  support. Agent3/Agent5 và toàn dự án vẫn chưa Ready với verifier mới.
- Regression local đạt332/332; payload độc lập đạt123 frozen tests, validate-only
  probe18/smoke12/verifier39 đạt. Những kiểm tra này không nạp trọng số model v8.
- [Validation local](ATOMIC_VERIFIER_V8_VALIDATION.md) và [hướng dẫn T4](ATOMIC_VERIFIER_V8_RUN_GUIDE.md):
  smoke12 contract dev trước probe18; chỉ admission người mới của đúng v8 mới
  được chạy full39. Không vá riêng claim007 hoặc dùng lại chữ ký v7.

## Hiện tại — QASPER Dense đã chạy hợp lệ; verifier/E2E còn chờ — 2026-10-17

- Run `20261017T053445Z-0d2b6961`: đã kiểm ZIP/CRC,34 output files,13 input
  files khớp release.12 stage và4 Colab regression đạt. FAISS mới18.587 vector,
  1.024 chiều, IndexFlatIP; tất cả vector hữu hạn/normalized, mapping khớp corpus.
- Đã chấm lại393 BM25 +393 Dense traces; **fallback/error=0**. Dense Hit@5
  **40,97%**, paragraph Recall@5 **27,07%**, MRR@5 **0,23087**; BM25 lần lượt
  **27,99%**, **15,97%**, **0,15895**. Top-5 và scores BM25393 câu khớp lượt local.
- Dense còn232/393 câu không lấy được đoạn gold trong top-5. Đây là retrieval dev
  theo đoạn văn, không phải official QASPER answer score, nhãn verifier hoặc E2E.
  417 test-candidate qrels chưa được chấm trong lượt này; adaptive/hybrid chưa đo.
- Bước tiếp theo: chạy candidate verifier v8 theo smoke12/probe18 + human review
  mới rồi đủ39 ca; tách bộ validation có annotation riêng, sau đó Reader OCR
  và tích hợp model E2E.
  Claim007 đã qua probe v7; không vá theo ID để tăng điểm. Full39 v7 vẫn không đạt.
- **Agent3, Agent5 và toàn dự án chưa Ready với verifier mới.** Xem
  [audit và các bước nghiệm thu](QASPER_BM25_DENSE_REVIEW_20261017.md).

## Lịch sử — gate nghiệm thu và QASPER — 2026-10-16

**Agent 3 và Agent 5 chưa Ready với atomic verifier mới, chưa có E2E đạt.**
Loader vẫn nạp FactChecker cũ. Probe18 chỉ đo cấu trúc tách mệnh đề; không thay
accuracy nhãn hoặc false support39. V7 hiện đạt18/18 probe/human review nhưng
full39 timeout, chưa hoàn tất phép đo. Không tiếp tục vá riêng007.

BM25 mới chạy393/393 dev QASPER: Hit@5=0,2798982188, paragraph
Recall@5=0,1596641625, fallback/error=0. QASPER chưa có FAISS: Dense metrics=null,
so sánh hai phương pháp chưa hợp lệ. Notebook GPU đã đóng gói riêng dev/corpus,
giữ417 test candidate riêng, kiểm backend từng query và từ chối điểm Dense khi
fallback. Reader mặc định local PyMuPDF → Tesseract; binary OCR trên host còn thiếu.
Xem [protocol, bằng chứng và thứ tự chạy](PRODUCTION_GATES_20261016.md).

## Lịch sử — full39 v7 timeout, assessment không đạt — 2026-10-16

- Run `20261016T071213Z-7c8c33c6`:54/54 output files,69 input files,26 frozen
  sources, model pairing và human admission đều khớp;101 Colab regression và
  hai validate-only đạt. Hard timeout5.400 giây dừng run, chưa có metrics.json cuối.
-22 predictions đã lưu replay khớp:21 incomplete, một completed nhưng sai
  gold ở contract:cross_sentence;0 nhãn đúng và0 support ở phần này.17 ca chưa
  có prediction, gồm một đang chạy và16 chưa bắt đầu; chưa kết luận false support39.
-68 started/67 finished calls;27 generations chạm1.536 tokens và JSON chưa
  đóng. Quotes bịa/paraphrase bị guard chặn; numeric bắt buộc bị bỏ. Fixture
  offline còn tái hiện full-predicate metric không bind được proof có exactly,
  cùng mismatch explicit denial/numeric policy.17 rows vượt soft deadline180 giây.
- Giữ nguyên v7/output; chưa triển khai v8 hoặc chạy inference mới trong audit.
  Cần sửa assessment generation/grounding/numeric/deadline và smoke probe ngắn
  trước full39 mới. [Audit và hướng sửa](ATOMIC_VERIFIER_V7_FULL39_REVIEW_20261016T071213Z-7c8c33c6.md).
- **Bước2 và gate toàn dự án chưa hoàn tất; chưa promotion serving.**

## Lịch sử — probe v7 đạt; human admission hoàn tất — 2026-10-16

- Run `20261016T024708Z-a57ee72a`: provenance/CRC/39 output files/69 input files/
  26 frozen sources và replay18 predictions/18 calls/54 events khớp.
  **18/18 structural pass, không repair**; Colab101 tests và hai validate-only đạt.
- AI đã review20 parts. Human reviewer **tricong** cung cấp tên và xác nhận rõ
  cả18 ca đạt cả năm tiêu chí, đã đọc lưu ý named-metric010/014/018. Human JSON
  được lưu riêng và `require_probe_review` đã chấp nhận; original ZIP/template
  pending giữ nguyên làm lịch sử. [Audit/review](DECOMPOSITION_PROBE_REVIEW_20261016T024708Z-a57ee72a.md).
- Đã dựng notebook39 tự chứa đúng source/data, probe gốc và human review đã
  xác nhận;4 packaging/admission tests mới đạt. Người dùng chạy bốn cell trên
  T4 mới; không cần chạy lại probe. [Hướng dẫn39](ATOMIC_VERIFIER_V7_FULL39_RUN_GUIDE.md).
- **Chưa có kết quả39 hoặc số đo false support; bước2 và gate toàn dự án chưa hoàn tất.**

## Lịch sử — candidate v7 đóng băng offline — 2026-10-16

- Đã bảo toàn v6 bằng snapshot/ZIP 140 file có hash; replay đủ 18 predictions
  bằng source v6 độc lập. Giữ nguyên ZIP, predictions và human review gốc.
- V7 dùng chung source-derived metric requirement theo từng vế cho validator
  và decoder policy v4; chặn bare verb và quantity/object fragment trong mẫu
  đếm/thời lượng được hỗ trợ. Model/revision, base prompts, dữ liệu và budget giữ nguyên.
- **299/299 regression và 7/7 kiểm thử đóng gói đạt**. Payload Colab độc lập
  chạy đủ 101 frozen tests và hai validate-only; source/contract/criteria/notebook
  mới đồng bộ hash. Đây là kết quả chuẩn bị trước khi inference; probe/human
  admission mới được ghi ở mục hiện tại phía trên.
- Chỉ sau18/18 output thực tế đạt cùng human review đúng hash mới admission39.
  [Notebook và hướng dẫn](ATOMIC_VERIFIER_V7_RUN_GUIDE.md),
  [validation và giới hạn](ATOMIC_VERIFIER_V7_VALIDATION.md).

## Lịch sử — probe v6 đã chạy T4, gate chưa đạt — 2026-10-15

- Run `20261015T155608Z-9262cfd5`: CRC/39 output files, 68 input manifest files,
  25 frozen sources, model pairing và replay 18 predictions/20 calls khớp.
  Colab 87 tests và hai validate-only đạt. Probe **17/18 hợp lệ, 1 incomplete**.
- 007 giữ metric `took` ở cả hai attempts; 008 repair sang `240 documents`, còn
  thiếu full predicate theo prompt. Review AI: 16 claim đạt, 1 cần sửa, 1 chưa
  có valid plan. **Chưa admission 39 ca, chưa human review, false support chưa đo.**
  [Báo cáo và bước tiếp theo](DECOMPOSITION_PROBE_REVIEW_20261015T155608Z-9262cfd5.md).

## Lịch sử chuẩn bị — candidate v6 đóng băng offline — 2026-10-15

- Đã bảo toàn v5: snapshot/ZIP 127 file có hash; replay đủ 18 predictions bằng
  source v5 trong snapshot. Giữ nguyên ZIP và human review gốc.
- V6 thêm `metric_predicate_incomplete` vào validator/repair hữu hạn. Bảy
  regression mới, 87 test verifier/summarizer và 7 test packaging đạt; cả hai
  validate-only đạt. Decoder, model, base prompts, dữ liệu và ngân sách không đổi.
- Đã dựng notebook Colab/Kaggle v6, freeze 25 source files. Ở thời điểm đóng gói
  chưa có inference; run model sau đó được ghi ở mục hiện tại phía trên.
- Lượt cuối: **285/285 test `research_rag/tests` và 7/7 test đóng gói đạt**.
  Đã sao lưu và dựng lại notebook resume cùng các notebook phụ thuộc để đồng
  bộ Summarizer/Judge source cũ; không đổi assertions hoặc quality gate.
  [Chi tiết validation và artifact](ATOMIC_VERIFIER_V6_VALIDATION.md).

## Lịch sử — probe Colab v5 đã audit — 2026-10-15

- Đã nhận và audit ZIP Colab run `20261015T103401Z-723b3e4a`: CRC, 39 output
  files, 67 input manifest files và 24 frozen sources khớp; replay 18 predictions/
  18 calls khớp. Tesla T4, 80 regression tests và hai validate-only đạt.
  Probe **18/18 cấu trúc, 18 calls, không repair**. Review AI đủ 20 parts:
  **16/18 claim đạt, 007/008 cần sửa metric `took`/`contained` quá chung**.
  Human review còn pending; chưa chạy 39 ca, chưa đo false support.
  [Báo cáo review](DECOMPOSITION_PROBE_REVIEW_20261015T103401Z-723b3e4a.md).

- Chuyển môi trường theo yêu cầu: dựng notebook Colab 4 cell, 67 file payload;
  80 regression tests từ payload độc lập và hai `validate-only` đạt (2 test
  packaging Colab đạt). Trình duyệt agent lỗi tải Monaco; người dùng chạy bằng
  Chrome/Edge và gửi ZIP probe đã kiểm ở mục trên.
  [Notebook Colab](../scripts/colab_decomposition_probe_v5.ipynb),
  [trạng thái bước 2](ATOMIC_VERIFIER_V5_STEP2_20261015.md).

- Bước chạy model đã thử trên Kaggle: phát hiện và sửa hash nền thiếu trong
  payload `test_summary_trace.py`; 3 test packaging đạt, draft tải ngược khớp
  đủ ba code cell. Lượt chạy từ draft đã xác minh bị chặn trước model loading
  bởi `Firebase: Error (auth/internal-error)`; Refresh vẫn lỗi. Lượt Kaggle không
  có inference; kết quả Colab sau đó ghi ở mục trên. Chưa đo false support.
  [Báo cáo thực thi](ATOMIC_VERIFIER_V5_STEP2_20261015.md).

- Đã sửa bug 6/8/9/10: schema Generator/Critic và retry hữu hạn; scope theo từng
  vế AND; danh sách yêu cầu số liệu và bằng chứng riêng; criteria/notebook v5 đồng bộ hash.
- 83 test regression/experiment/đóng gói và 55 test autonomy/E2E/graph/integration đạt.
  `validate-only` cho 39 ca và probe 18 ca đều đạt. Notebook được kiểm payload,
  compile ba cell và freeze check trong runtime giải nén tạm.
- Đã chạy Qwen/CUDA v5 decomposition; review ngữ nghĩa bằng người và full 39 ca
  vẫn chờ. Quality gate toàn hệ chưa đạt.
  Xem [chi tiết, artifact và lệnh kiểm tra](ATOMIC_VERIFIER_V5_VALIDATION.md).

## Hiện tại — local demo đã chạy; quality gate toàn hệ còn chờ — 2026-10-14

- Đã chạy runner local riêng cho năm agent: 94 test logic được chọn đạt; bốn test
  runner/report đạt. BM25 chạy trên corpus thật, Hit@5 = 7/10; công cụ Reader
  PyMuPDF khớp 7/7 span ở hai PDF text, toàn bộ ba PDF = 7/9; Writer baseline
  không dùng LLM đạt schema 100% nhưng warning 100%.
- Summarizer/Fact-checker chấm lại predictions lưu trong repo, chưa inference
  mới trên local: verbatim span 86,67% trên 18 ca; accuracy 79,91%, macro-F1
  0,78308 trên 468 ca. Đây là dữ liệu development, không thay đánh giá độc lập.
- Host chỉ có CPU, 7,69 GiB RAM tổng; Summarizer/Writer thiếu base weights trong
  cache. Reader chưa có Tesseract/Gemini key trong môi trường. Chưa xác nhận chạy
  đủ năm checkpoint trên laptop. [Hướng dẫn demo và nguồn số đo](LOCAL_AGENT_DEMO.md).
- ZIP probe v4 `20261013T152836Z-a86e9199` đã chạy model: 214 test Kaggle đạt,
  16/18 decomposition hợp lệ, 2 incomplete, 23 calls; gate vẫn false. Bản sửa v5
  đã đóng băng offline ngày 2026-10-15, chưa chạy model. Local demo không thay gate verifier.

## Lịch sử — probe v3 trượt; chuẩn bị v4 trước inference — 2026-10-13

- ZIP `20261013T135905Z-ac194776` đạt CRC; 37/37 output files, 45/45 runtime,
  28/28 patch và frozen source/prompt/data/model pairing khớp. Replay 18
  predictions và 27 calls khớp; Kaggle 206 tests đạt. Probe có 13/18 decomposition
  hợp lệ, 5 incomplete; `automated_gate_pass=false`.
- Review AI đủ 18 ca: 9 rõ ràng đạt, 4 cần sửa scope/metric/population và 5
  không có plan hợp lệ. Đây chưa phải review độc lập bằng người. Kết quả này
  chưa đo độ chính xác nhãn của verifier.
- V4 thêm decoder giới hạn token theo JSON schema và trích đoạn claim; các
  kiểm tra offset/coverage/quantifier/scope vẫn chạy sau generation. Giữ nguyên
  model/revision, dữ liệu, prompt, tiêu chí nhãn và ngân sách của v3. Thêm hook
  trên backend dùng chung; đường serving mặc định không bật decoder này.
- Đóng băng `atomic-verifier-constrained-v4-20261013`, 16 source files. **83 test
  runtime và 3 test đóng gói đạt qua hai lượt kiểm tra**; kiểm bằng parser thật
  và model giả lập, chưa chạy Qwen/CUDA v4. Xem [validation](decomposition-v4-validation.json)
  và [test log](decomposition-v4-tests.log).
- [Đối chiếu ZIP và review 18 ca](DECOMPOSITION_PROBE_REVIEW_20261013T135905Z-ac194776.md),
  [notebook v4 ba cell](../scripts/kaggle_decomposition_probe_v4.ipynb),
  [hướng dẫn chạy](DECOMPOSITION_PROBE_V4_KAGGLE.md).
- **Chưa có inference v4.** Chạy probe v4, kiểm 18/18 cấu trúc và review ngữ
  nghĩa trước 39 ca. Tích hợp, Reader, Summarizer và tám ca E2E vẫn chờ gate
  verifier. JSON schema không chứng minh tách đúng mệnh đề; v4 giới hạn claim
  80 từ. ZIP/source/criteria/notebook v3 gốc được bảo tồn.

## Lịch sử — probe v2 trượt; chuẩn bị v3 — 2026-10-13

- ZIP `20261013T131400Z-b05a83bd` khớp CRC, 37/37 output files, 45/45 runtime,
  28/28 patch và source/prompt/data/model pairing của v2. Replay 18 predictions
  và 29 calls đạt; Kaggle 203 tests đạt. Probe 12/18 valid, 6 incomplete; gate false.
- Review AI 18 ca: 9 rõ ràng đạt, 2 cần làm rõ metric, 1 sai loại dataset/time,
  6 không có plan hợp lệ. Human review vẫn pending; 39 ca và tích hợp chưa được gate cho đi tiếp.
- V3 sửa leading AND connector bị từ chối quá chặt; scope repair chỉ rõ trường
  sai; syntax repair tạo lại thay vì echo malformed JSON. Prompt phân biệt named
  property/time/condition/fragment; guard hẹp cho explicit dataset restriction.
- Đóng băng `atomic-verifier-quotes-v3-20261013`; cùng model/revision/dữ liệu,
  2 calls/claim, 36 calls tổng, 1.536 output tokens/call, hard timeout 2.400 giây.
  **78/78 test local đạt**, gồm runtime/replay/budget/checkpoint/packaging; dùng stub.
- [Đối chiếu ZIP và review](DECOMPOSITION_PROBE_REVIEW_20261013T131400Z-b05a83bd.md),
  [notebook v3 ba cell](../scripts/kaggle_decomposition_probe_v3.ipynb),
  [hướng dẫn](DECOMPOSITION_PROBE_V3_KAGGLE.md),
  [validation](decomposition-v3-validation.json).
- **Chưa có inference v3.** Việc tiếp theo là probe v3 và review đúng mệnh đề,
  sau đó 39 ca; Reader, Summarizer và tám ca E2E vẫn theo sau gate verifier.
  Original output/criteria/notebook v2 giữ nguyên; source v2 lưu tại
  `research-runs/atomic-verifier-v2-source-snapshot/`.

## Lịch sử — decomposition v2 đã sửa, chuẩn bị probe — 2026-10-13

- Model trả quote/quantifier/scope object; code tính offset từ trích đoạn duy nhất
  và kiểm coverage/order/quantifier/scope. Prompt có ví dụ JSON tổng quát;
  repair nhận output trước và phản hồi cụ thể theo mã lỗi.
- Đóng băng `atomic-verifier-quotes-v2-20261013`: cùng model/revision và gate
  39 ca. Probe riêng 18 unique development claims, tối đa 36 calls/55.296 output
  tokens, hard timeout 2.400 giây. Không truyền context/gold vào decomposition.
- CLI 39 ca yêu cầu probe hoàn tất, đúng model/provenance/freeze, replay 18/18
  và review năm tiêu chí ngữ nghĩa cho từng claim, gắn với hash predictions.
- [Notebook probe ba cell](../scripts/kaggle_decomposition_probe_v2.ipynb),
  [hướng dẫn chạy/review](DECOMPOSITION_PROBE_V2_KAGGLE.md).
  **Chưa chạy model thật v2; chưa có kết quả 18/18 hoặc gate verifier đạt.**
  Tích hợp, Reader, Summarizer và tám ca E2E chờ gate verifier theo thứ tự yêu cầu.
- Candidate và runner thí nghiệm được sửa; serving/baseline repair và ZIP cũ giữ
  nguyên. Bản source setup2 trước sửa lưu tại
  `research-runs/atomic-verifier-setup2-source-snapshot/` để tái hiện lịch sử.
- Bản cuối đạt **75/75 test local**, gồm regression decomposition, chốt review,
  replay, budget, checkpoint và đóng gói. Backend giả lập; xem
  [bản ghi kiểm tra](decomposition-v2-validation.json).

## Lượt trước — model thật đã chạy, decomposition trượt — 20261013T112627Z-d5bd1415

- CRC đạt; 38/38 output files, 45/45 runtime và 27/27 patch khớp hash.
  Replay khớp 39 predictions/78 calls, blinding, metrics/comparisons/review rows.
- Kaggle 193/193 tests đạt; preflight/freeze check đạt. Lỗi đóng gói cell 2 đã
  được kiểm chứng sửa thành công trên host thật.
- Cả 39 ca incomplete tại decomposition, không phát ra label hay gọi part/tool
  số học. 42 invalid JSON, 27 span mismatch, 9 empty parts trên 78 calls;
  cả 39 repairs sai JSON. False support=0 với zero predictions không chứng
  minh chất lượng verifier. Gate vẫn false, human review pending.
- 78 calls, 9.764 generated tokens, 23.245 prompt tokens; stage mất 670,291 giây,
  dưới giới hạn. Không chạm token cap/deadline; USD null. Baseline v3 giữ 37/39.
- [Báo cáo và thứ tự sửa](ATOMIC_VERIFIER_REVIEW_20261013T112627Z-d5bd1415.md),
  [audit](atomic-verifier-audit-20261013T112627Z-d5bd1415.json). Đã lưu triage 39
  ca và 18 unique claims cho diagnostic. Tiếp theo sửa/freeze decomposition
  candidate rồi probe riêng trước lượt 39 ca mới. Chưa đổi policy/serving.
- Phần chạy thí nghiệm bước 3 đã thực hiện; quality acceptance chưa đạt, bước 4
  chưa bắt đầu. Human review/dataset độc lập vẫn còn chờ.

## Chuẩn bị bước 3 và sửa cell 2 — 2026-10-13 (lịch sử)

- Đã chốt contract/prompt/source/data/model/budget cho candidate riêng trên 39
  development regressions. Gate giữ 39/39, zero false support/failure; baseline
  logic_v3 37/39 được lấy từ output đã audit, không inference lại.
- Runner ghi call-start trước backend, replay quyết định, kiểm model pairing,
  deadline và hard worker timeout. Báo support đúng bị từ chối; human review
  pending và không tự promote.
- ZIP `20261013T102527Z-d29489cf`: setup cài runtime đạt, 194 tests chạy với một
  FileNotFoundError ở test đóng gói notebook; chưa đến inference. Đã chuyển
  test đóng gói sang local và tạo notebook setup2; model/prompt/data/budget giữ
  nguyên, criteria v1 gốc được bảo tồn.
- 65/65 tests local của bản sửa đạt; hash source/dữ liệu/notebook đã đối chiếu.
  Backend giả lập dùng để kiểm logic, chưa đo chất lượng model thật.
- [Hướng dẫn ba cell](ATOMIC_VERIFIER_STEP3_KAGGLE.md),
  [notebook mới](../scripts/kaggle_atomic_verifier_v1.ipynb),
  [kiểm chứng bản sửa](atomic-verifier-cell2-fix-20261013.json),
  [chẩn đoán cell 2](ATOMIC_VERIFIER_CELL2_FIX_20261013.md).
- Khi bàn giao setup2 chưa có inference atomic. Lượt model thật sau đó được
  đối chiếu ở mục phía trên. [Protocol độc lập](VERIFIER_INDEPENDENT_EVALUATION_PROTOCOL.md)
  đã chuẩn bị, dataset/reviewer độc lập vẫn còn chờ.

## Bước 2 — candidate kiểm từng mệnh đề đã triển khai — 2026-10-13

- Thêm `AtomicVerifier`: decomposition có span, kiểm từng part, evidence/coverage
  theo scope và tổng hợp AND/all/some/none bằng code. Số liệu được trích có
  nguồn, kiểm đơn vị và tính bằng Decimal. Có trace, repair/call budget/deadline.
- [Bàn giao implementation và giới hạn](ATOMIC_VERIFIER_STEP2.md),
  [kiểm chứng local](atomic-verifier-step2-validation.json). 51/51 tests đạt,
  gồm 21 test mới; 13 file v3 khớp manifest cũ. Kiểm thử dùng backend giả lập;
  chất lượng model thật của candidate chưa được đo.
- Candidate riêng, chưa tích hợp serving. `logic_v3` vẫn 37/39; gate chất
  lượng chưa đạt. Phần chuẩn bị bước 3 đã hoàn tất theo yêu cầu tiếp theo;
  inference riêng và review còn chờ. Bước 4 (tích hợp/toàn hệ) chưa bắt đầu.

## Bước 1 — đã review bằng AI đủ 39 ca — 2026-10-13

- Đã đọc claim/context/output và ghi đủ 195 judgments: đúng nhãn 37/39,
  đạt toàn bộ tiêu chí áp dụng 29/39, 10 output cần sửa (hai sai nhãn, tám
  đúng nhãn nhưng còn lỗi ngữ nghĩa). Hai câu dữ liệu có cách diễn đạt cần
  làm rõ; số liệu giữ theo diễn giải bộ ca hiện tại.
- Reviewer là Codex (AI). Đánh giá độc lập bằng người vẫn pending. Đây là
  bộ development đã được xem, không phải held-out độc lập.
- [Báo cáo bước 1](STEP1_VERIFIER_SEMANTIC_REVIEW.md),
  [phiếu đã điền đủ 39 ca](VERIFIER_SEMANTIC_REVIEW_20261012T165922Z.md),
  [tổng hợp có cấu trúc](blind-verifier-semantic-review-20261012T165922Z.json).
- Giữ nguyên output/gold/criteria và runtime; không inference mới. Gate
  verifier vẫn trượt. Trong lượt review bước 1 chưa triển khai atomic verifier;
  implementation bước 2 và chuẩn bị bước 3 sau đó được cập nhật phía trên.

## Logic_v3 đã chạy: 37/39, hai false support — 20261012T165922Z (lịch sử)

- CRC/hash đạt: 37 output files, 45 runtime và 13 verifier patch files khớp.
  Replay khớp 39 predictions/40 calls, blinding, frozen criteria/data/prompt,
  metrics/comparisons/baselines và 39 pending review rows. Kaggle 161 tests đạt.
- Đúng 37/39; ca cũ 11/12, mới 26/27; không còn final verification failure.
  Hai false support: partial_accuracy và direction:contradict. Support precision
  theo gold giảm từ 92,31% ở v2 còn 86,67%; gate 39/39 vẫn trượt.
- Quote/explanation còn thiếu factual parts ở một số ca nhãn đúng. Chưa tích hợp
  candidate hoặc coi label accuracy là semantic quality pass.
- Đã thêm evidence-screen-v1 và runner offline: tám tests mới đạt; trên output
  đã lưu gắn cờ hai false supports và hai gold-support có quote thiếu một vế.
  Không gọi model mới; nhãn gốc 37/39 không đổi. Đây là post-hoc diagnostic,
  screen_clear không có nghĩa verified; serving chưa đổi.
- [Báo cáo ZIP](BLIND_VERIFIER_REVIEW_20261012T165922Z.md),
  [audit](blind-verifier-audit-20261012T165922Z.json),
  [kết quả screen](../research-runs/evidence-screen-20261012T165922Z-v1/summary.json),
  [hướng đi tiếp theo](VERIFIER_HYBRID_NEXT_STEPS.md).
- Tiếp theo: human semantic review và candidate kiểm chứng từng factual part,
  numerical tool, freeze/evaluate riêng rồi mới tích hợp. Atomic verifier chưa
  triển khai. Reader PDF, Summarizer heldout_3, tám ca E2E và đánh giá độc lập
  toàn hệ vẫn pending. Không chạy lại v3/toàn hệ với policy không đổi.

## Scope_v2 đã chạy: 33/39, candidate logic_v3 sẵn sàng — 20261012T153832Z (lịch sử)

- ZIP CRC/hash đạt, 37 output files khớp; trước sửa candidate mới có 45 runtime
  và 10 verifier patch files khớp repo. Replay khớp 39 predictions/41 calls,
  criteria/inputs/prompt, metrics/comparisons và 39 pending review rows.
- Kaggle 155 tests đạt, setup/preflight đạt. Candidate trượt: đúng 33/39,
  ca cũ 11/12, mới 22/27; năm nhãn sai, một false support, một quote validation
  failure. Gate không thay đổi; serving chưa tích hợp.
- Lỗi phạm vi cũ sửa được nhưng accuracy_conflict lùi từ đúng về sai. Các lỗi
  mới ở existential, direction, conjunction và quote không nguyên văn.
  Cross_sentence còn thiếu quote/explanation cho vế hai datasets dù nhãn đúng.
- Đã chuẩn bị logic_v3: operator-aware decision procedure, numeric comparisons,
  quote-specific repair feedback; snapshot v2 đủ 39 ca giữ cả failure. Cùng
  model revision/generation budget, cùng dữ liệu/gate; human review pending.
- 26 focused tests local đạt với model giả lập; prompt v1/v2 và criteria v2
  giữ nguyên, baseline v2 chấm lại khớp metrics đã nhận.
- [Báo cáo ZIP](BLIND_VERIFIER_REVIEW_20261012T153832Z.md),
  [audit](blind-verifier-audit-20261012T153832Z.json),
  [notebook mới](../scripts/kaggle_blind_verifier_logic_v3.ipynb),
  [hướng dẫn ba cell](VERIFIER_LOGIC_V3.md).
- Logic_v3 chưa có inference thật. Tiếp theo: chạy candidate riêng, review bằng
  người/dữ liệu độc lập rồi mới quyết định tích hợp. Reader toàn PDF, Summarizer
  heldout_3 và tám ca E2E vẫn chưa hoàn thành; chưa đạt gate phát hành.

## Bước 2: regression mở rộng sẵn sàng chạy — 2026-10-12 (lịch sử)

- Scope_v2 được đóng gói với 39 cases (12 cũ + 27 synthetic mới), chín nhóm
  contrast và 13 cases/nhãn. Model chỉ nhận claim/context. Nhãn mới là
  assistant-authored, independent annotation/semantic review còn pending.
- Chỉ chạy base verifier, tối đa 78 calls. Hash prompt/data/baseline kiểm trước
  inference; chấm cả ba labels và từng dataset/family. Gate giữ đủ đúng 12/12
  ca cũ và 27/27 ca mới, zero false support/failure; không promote tự động.
- Snapshot base v1 đã audit được chấm offline trên 12 ca cũ (11/12); kiểm pairing
  weights/tokenizer/revision/generation trước calls mới. Confidence repair cũ
  vẫn là mốc riêng, không chạy lại model để tạo baseline.
- 19 focused tests local đạt với model giả lập; chưa có kết quả scope_v2 thật.
  [Notebook ba cell](../scripts/kaggle_blind_verifier_scope_regression.ipynb),
  [hướng dẫn chạy/đọc kết quả](VERIFIER_SCOPE_REGRESSION.md),
  [bản ghi validation](blind-verifier-scope-regression-local-validation.json).
- Bước cần người dùng thực hiện: chạy notebook regression mới trên Kaggle GPU,
  lưu Output/ZIP để đối chiếu. Review độc lập, tích hợp verifier, Reader toàn PDF,
  Summarizer heldout_3 và tám ca E2E vẫn chưa hoàn thành; chưa đạt gate phát hành.

## Bước 1: prompt candidate base scope_v2 đã triển khai — 2026-10-12

- Thêm quy tắc all/some/none, phản ví dụ trong đúng phạm vi, hướng thay đổi rõ
  so với số đo hiện tại đơn lẻ, và độ phủ mọi vế của claim. Không nhúng cases
  hoặc gold label. Profile được giữ trên first/repair call; blinding vẫn có.
- Candidate criteria mới chọn base_instruct/scope_v2, giữ weights revision,
  token/retry budget, 12 contracts cũ và gate 12/12. Provenance lưu profile thực
  dùng. Baseline prompt và criteria v1 khớp artifact đã audit; serving chưa tích hợp.
- Có [notebook candidate riêng](../scripts/kaggle_blind_verifier_scope_v2.ipynb),
  [mô tả và danh sách file](VERIFIER_SCOPE_V2.md). 11 focused tests local đạt
  với model giả lập; [bản ghi](blind-verifier-scope-v2-local-validation.json).
- Chưa có inference mới chứng minh sửa được nhãn sai. Bước 2 mở rộng regression,
  semantic/human review và đánh giá độc lập vẫn pending. Kết quả v1 dưới đây
  giữ nguyên; không chuyển 11/12 thành pass hoặc promote candidate.

## Verifier thật đã chạy: base 11/12, chưa đạt — 20261012T101333Z

- ZIP CRC đạt; 36/36 output files đúng hash, 45/45 runtime patch và 5/5 verifier
  patch khớp repo. Kaggle pip check/preflight đạt, 145 tests đạt trong 3,041 giây.
- Replay local khớp 24 predictions từ 27 calls; messages/blinding, criteria,
  metrics/comparisons/summary và 24 review rows đều khớp. Human review pending.
- Fine-tuned đúng 10/12, hai false support trên claim chỉ được hỗ trợ một phần;
  15 calls, ba repair vì thiếu explanation. Base đúng 11/12, zero false support,
  12 calls; case scope trả NEI thay vì contradict trước phản ví dụ rõ.
- Stage hoàn thành thí nghiệm nhưng exit 1 do gate chất lượng trượt. Giữ gate
  12/12; chưa ứng viên nào được promote. Không cần chạy lại notebook cùng cấu hình.
- Phân tích offline cả hai nhãn sai cho thấy base có một wrong-label agreement;
  chỉ số zero trong v1 chỉ áp dụng cho một nhãn sai định trước, không phải zero
  classification errors. Summary/gate v1 được giữ nguyên.
- Ưu tiên tiếp theo: base verifier candidate v2 về phạm vi all/some/none và
  hướng thay đổi; mở rộng regression và freeze trước inference, review bằng
  người và dữ liệu độc lập trước khi tích hợp. V2 chưa được sửa/chạy trong lượt audit.
- [Báo cáo và thứ tự hoàn thiện](BLIND_VERIFIER_REVIEW_20261012T101333Z.md),
  [audit](blind-verifier-audit-20261012T101333Z.json),
  [review draft](blind-verifier-review-draft-20261012T101333Z.jsonl).
- Reader full PDF/quota và resume nếu cần, Summarizer heldout_3, regression tám
  ca E2E và nghiệm thu bằng người/độc lập vẫn còn. Chưa đạt gate phát hành.

## Endpoint đã đối chiếu; chuyển sang ứng viên verifier — 2026-10-12

- ZIP `reader-endpoint-20261012T094200Z-8bf24d19` CRC đạt, 23/23 output files
  và 5/5 code files đúng hash. Router SDK/REST 503, critique SDK contract đạt,
  critique REST 503. Provider trả thông báo model đang có nhu cầu cao. Không
  có 403/429; chưa đủ căn cứ đổi REST hoặc kết luận Reader đạt.
- Stage failed/exit 1; hai backend contract false, Reader quality chưa được đo.
  ZIP vẫn có warning thiếu wrapt, chưa có artifact cell repair wrapt. Bản notebook
  CPU đã sửa vẫn dành cho các run sau; giữ nguyên bằng chứng run hiện tại.
- [Báo cáo đối chiếu](READER_ENDPOINT_REVIEW_20261012T094200Z.md),
  [audit JSON](reader-endpoint-audit-20261012T094200Z.json).
- Đã triển khai ứng viên verifier chỉ nhận claim/context, kiểm output/quote
  trước khi so Judge; mới chạy riêng trong diagnostic, chưa tích hợp serving.
  Có tiêu chí đóng băng, snapshot repair lịch sử, trace từng call, review rows
  và [notebook GPU ba cell](../scripts/kaggle_blind_verifier.ipynb).
- 11 tests local đạt với model giả lập; chưa đo chất lượng verifier thật.
  [Hướng dẫn bước B](BLIND_VERIFIER_VALIDATION.md). Bước chạy tiếp theo là
  verifier riêng, không chạy lại confidence cùng cấu hình hoặc Reader liên tục.
- Reader full PDF/quota, checkpoint resume theo trang nếu cần, verifier được đo
  và tích hợp, lỗi Summarizer heldout_3, tám ca E2E và human/independent review
  vẫn chưa hoàn thành. Chưa được tuyên bố hệ thống đã nghiệm thu.

## Setup CPU mới: SETUP_OK kèm cảnh báo thiếu wrapt — 2026-10-12

- Output người dùng gửi từ run `reader-endpoint-20261012T094200Z-8bf24d19`
  đã tới `SETUP_OK`, còn hai cảnh báo sitecustomize thiếu module wrapt.
  Chưa có kết quả Gemini trong lượt này.
- Notebook CPU đã thêm `wrapt==2.1.2` như runner chính, kiểm import/version
  và chặn SETUP_OK khi smoke process exit 0 nhưng stderr báo lỗi sitecustomize.
- Có [cell sửa cho phiên hiện tại](../scripts/kaggle_reader_wrapt_fix.cell.py)
  để cài wrapt vào venv sau cell 1, giữ setup gốc, log/freeze/ZIP và chặn cell 2
  khi repair thất bại. Chỉ tiếp tục cell 2 sau `ENV_OK`; chưa chạy repair trên
  Kaggle hoặc gọi Gemini thật. [Hướng dẫn](READER_ENDPOINT_COMPARISON.md).
- 4 focused tests local đạt: setup/fallback pip, repair wrapt, venv thật không
  có pip (offline) và notebook/source/setup/rerun guards. Regression bao gồm
  exit code 0 kèm lỗi sitecustomize, giữ log và chặn probe sau repair failed.
- File cập nhật: builder và notebook endpoint, `test_validation_notebook.py`,
  hướng dẫn endpoint và trang trạng thái; thêm `kaggle_reader_wrapt_fix.cell.py`.

## Setup notebook CPU: đã sửa đường gọi ensurepip — 2026-10-12

- Người dùng gửi lỗi cell 1 run `reader-endpoint-20261012T092028Z-7ff9eaac`:
  Python 3.13 tạo venv rồi ensurepip exit 1, trước khi gọi Gemini. Chưa có
  stderr để xác định nguyên nhân nội bộ ensurepip.
- Notebook CPU đã sinh lại: tạo venv `--without-pip`, dùng pip hiện có hỗ trợ
  `--python` cài SDK vào môi trường riêng; kiểm import/version trước Secret.
  Ghi stage/state/error_type/exit_code khi setup lỗi và vẫn lưu ZIP.
- 3 focused tests local đạt, gồm một integration offline tạo venv thật không
  có pip và quản lý bằng pip bên ngoài. Notebook/source và gate setup/rerun
  đã kiểm. Local là Windows/Python 3.10; chưa chạy Kaggle Python 3.13 hoặc
  cài SDK qua mạng trong lượt kiểm tra này. Lỗi Gemini 503 vẫn chưa giải quyết.
- [Notebook đã sửa](../scripts/kaggle_reader_endpoint_comparison.ipynb),
  [hướng dẫn chạy](READER_ENDPOINT_COMPARISON.md). Giữ ZIP setup lỗi cũ;
  chạy cell 1 của bản sửa trong run mới, cell 2 chỉ sau `SETUP_OK`.

## Chặn hiện tại: router 503 trong cả probe và retry — 20261012T082718Z

- ZIP mới CRC hợp lệ, 44/44 file đúng hash/kích thước; runtime khớp 45/45.
  Hai replay offline local khớp Kaggle. Kaggle ghi nhận 139 tests đạt.
- Availability JSON nhỏ đạt 200. Router trang index 3 trả 503/UNAVAILABLE
  cả ba attempts trong probe và cả ba attempts trong manual retry; chưa có
  tool/extraction/critique. Hai stages failed/exit 1/gate false.
- Pacing khoảng 61 giây và giới hạn attempts hoạt động đúng. Chưa có căn cứ
  sửa timeout, tăng retry, bỏ gate hoặc tự đổi model/backend.
- Đã bổ sung [notebook CPU hai cell kiểm yêu cầu thật](../scripts/kaggle_reader_endpoint_comparison.ipynb),
  đối chiếu payload từng vai trò qua SDK/REST, giữ lỗi đã lọc và token usage;
  tối đa bốn request, không retry, dừng sớm với lỗi client/quota.
- 6 tests local đạt (API giả lập); notebook/source hash và setup/rerun guards
  đã kiểm. Chưa chạy live API/Kaggle mới; chưa khắc phục được 503 phía dịch vụ.
- [Hướng dẫn chạy](READER_ENDPOINT_COMPARISON.md) và
  [báo cáo, giới hạn, danh sách file](READER_REVIEW_20261012T082718Z.md).
- Reader full PDF, verifier confidence, Summarizer và full E2E/human review
  vẫn chưa đạt đủ gate nghiệm thu.

## Lịch sử: Reader trang thử dừng sau ba lỗi critique 503 — 20261012T041305Z

- Đã nhận và audit ZIP: CRC hợp lệ, 32/32 file đúng hash/kích thước, runtime
  khớp 45/45 file. Replay offline local khớp chính xác bản Kaggle.
- Theo status/summary trong run `rag-validation-20261012T041305Z`,
  `reader-failed-page` failed/exit 1, thời gian process 186,403.6 ms;
  `automated_gate_pass=false`. Cell 4 chặn đúng trước khi đọc toàn PDF.
- Hai logical calls, bốn transport attempts: một success, hai retry,
  một exhausted; HTTP counts gồm ba 503 và một `not_available`.
  Code Reader hiện ghi http_status=null trên response thành công vì SDK không
  cung cấp mã HTTP thành công; `not_available` ở đây không phải một lỗi thứ tư.
- Policy hiện tại tối đa ba attempts mỗi logical call (một lần đầu + hai retry),
  khớp việc kết thúc exhausted; đây không phải bằng chứng timeout process.
  Tổng thời gian chờ 157,028.245 ms, transport 17,117.872 ms;
  `within_attempt_and_deadline_policy=true`.
- Trace xác nhận router thành công, chọn LayoutLMv3; critique trên trang index 3
  trả `503 UNAVAILABLE` ba lần, kết thúc exhausted sau 162.054 giây.
  `ReaderBatchError` là lỗi tổng hợp khi trang không hoàn tất. Chưa rõ nguyên
  nhân nội bộ phía dịch vụ; không phải bằng chứng timeout process.
  0 PDF được chấm thành công; điểm overall=0 bao gồm thất bại vận hành, chưa
  dùng để kết luận chất lượng trích xuất của model.
- Lượt mới không ghi nhận 403/429, có một response thành công. Chưa có bằng
  chứng về cách xử lý hạn chế project trước đó hoặc quyền/quota ở các lượt sau.
- Availability trong ZIP lúc 04:12:49 UTC đạt metadata/generation 200 và JSON
  hợp lệ. Không xác nhận quyền truy cập hoặc quota của các lượt tương lai.
- Đã tạo [hai cell retry có kiểm soát](READER_RETRY_503.md) để dùng trong phiên
  Kaggle hiện có: thử lại riêng trang 4 ở stage mới, giữ nguyên stage lỗi cũ.
  Cell full PDF kiểm trạng thái và quality gate của stage retry nếu đã chạy;
  vẫn chặn khi retry failed/running/interrupted. Chỉ một manual retry stage.
- 5 test methods local đạt; Reader/API trong test giả lập. Chưa chạy API/GPU
  mới. Nếu mất phiên thì chạy notebook Reader chính trong run mới.
- [Báo cáo và danh sách thay đổi](READER_REVIEW_20261012T041305Z.md).

## Lịch sử: Google từ chối quyền truy cập project — 2026-10-12

- JSON người dùng gửi lúc `2026-10-12T04:01:19.635884+00:00` đã giữ được lời
  giải thích: `Your project has been denied access. Please contact support.`
  Metadata HTTP 200/model khớp; generation HTTP 403 `PERMISSION_DENIED`.
  Model được kiểm tra: `gemini-3.6-flash`; endpoint_available=false.
- Đã xác định phạm vi từ chối là quyền truy cập project theo thông báo Google.
  Chưa biết nguyên nhân Google từ chối (và có liên quan đến tài khoản hay không).
  Log này không chứng minh sai key, hết quota, vi phạm chính sách hoặc cần nâng tier.
- Tiếp theo: chọn đúng project gắn với key, kiểm tra cảnh báo trên
  [AI Studio Projects](https://aistudio.google.com/projects) và
  [Billing](https://aistudio.google.com/billing); làm theo hướng dẫn xử lý/review
  nếu có. Nếu chưa rõ, dùng
  [hướng dẫn hỗ trợ Cloud Billing](https://docs.cloud.google.com/support/docs/get-billing-support)
  theo [phản hồi cho đúng lỗi này trên diễn đàn Google](https://discuss.ai.google.dev/t/persistent-error-gemini-api-keys-from-google-ai-studio-returns-403-error-and-instruct-to-contact-support-which-it-does-not-let-me-do/170486/4).
  Không kết luận nguyên nhân billing chỉ từ việc được chuyển đến kênh hỗ trợ đó.
- Giữ JSON `gemini-availability-c9ea614dbd4744089992cdad2d4564e9.json` trên Kaggle.
  Chờ xử lý quyền rồi chạy lại diagnostic một lần. Chỉ tiếp tục Reader khi probe
  đạt; quota cho toàn PDF vẫn phải được xác nhận riêng.
- Lượt này chỉ cập nhật tài liệu từ log người dùng; không sửa runtime, không gọi
  Gemini, không gửi yêu cầu hỗ trợ hoặc thay đổi tài khoản Google.

## Lịch sử chẩn đoán: Gemini generation bị 403 — 2026-10-12

- Theo JSON người dùng gửi lúc `2026-10-12T03:36:33Z` và `03:50:32Z`, Secret đã đọc được,
  metadata HTTP 200/model khớp, nhưng generation HTTP 403 `PERMISSION_DENIED`.
  `error_reasons=[]` chỉ cho biết không có reason thuộc allowlist được ghi nhận.
  Chưa đủ chi tiết để xác định key bị chặn, restriction hay quyền project.
- Probe trước đó bỏ `error.message`, làm mất lời giải thích khi ErrorInfo vắng mặt.
  Đã bổ sung `error_message_redacted`: che key đang dùng (cả URL-encoded), các
  dạng credential phổ biến, URL, email, resource project/account, số dài và IP;
  lọc trước khi giới hạn độ dài. Không lưu raw body/ErrorInfo metadata.
  Đây là lọc theo mẫu; người dùng vẫn cần kiểm tra phần văn bản trước khi chia sẻ.
- Có [notebook chẩn đoán một cell](../scripts/kaggle_gemini_access_check.ipynb):
  dùng cùng probe với Reader, không GPU/setup/dataset, không retry; giữ JSON lỗi
  và hiện `PROBE_FAILED`. Reader chính vẫn dừng nếu probe không đạt.
- 7 focused tests đạt, có regression metadata 200 → generation 403 không có ErrorInfo,
  kiểm tra che thông tin, lưu JSON khi thất bại và gate Reader;
  API trong tests là giả lập. Notebook local đã tạo lại. Chưa sửa quyền trên
  tài khoản Google/Kaggle và chưa có kết quả live chứng minh 403 được giải quyết.
- File thay đổi: `scripts/kaggle_gemini_probe.py`, `scripts/build_component_notebooks.py`,
  `scripts/kaggle_reader_diagnostics.ipynb`, `research_rag/tests/test_validation_notebook.py`,
  trang trạng thái này; thêm `scripts/kaggle_gemini_access_check.ipynb`.
  Notebook confidence được sinh lại có SHA256 không đổi.

## Reader full PDF gần nhất: probe đạt, full PDF bị quota ngày — 20261012T024449Z

- Đúng hash 44/44 file; runtime khớp 45/45. Kaggle đạt 139 tests. Hai replay
  tính lại local khớp chính xác bản Kaggle.
- Trang thử index 3 đạt 3/3 spans, 128 blocks; ba lần 503 phục hồi qua retry.
- Full PDF failed/exit 1/gate false ngay router trang index 0, không có blocks.
  HTTP 429 chỉ rõ `GenerateRequestsPerDayPerProjectPerModel-FreeTier`, limit
  20/ngày; retry delay 75,907 giây vượt call budget 240 giây nên dừng đúng policy.
- **Bước A chưa đạt nghiệm thu.** Xử lý quota trước khi chạy lại; đường chạy
  thuận lợi của notebook cần khoảng 20 lần sinh, chưa có dự phòng retry.
- Có thể triển khai/thử nghiệm verifier bước B song song; giữ baseline repair.
  Human review, Summarizer và full E2E vẫn chưa hoàn tất.
- [Báo cáo, nguyên nhân và thứ tự tiếp theo](READER_REVIEW_20261012T024449Z.md).

## Lịch sử: Reader sẵn sàng chạy mới — 2026-10-11

- Notebook Reader vẫn bốn cell, thêm kiểm tra Gemini ở cell 1 trước setup;
  lưu JSON đã lọc kể cả khi lỗi và đưa bằng chứng vào ZIP khi chạy Reader.
- Cell 4 yêu cầu đủ `completed`, exit code `0` và `automated_gate_pass=true`.
  10/10 notebook tests đạt; API trong tests được giả lập.
- Đã mở tab Kaggle trong Codex; thao tác điều khiển bị timeout. Chưa import
  bản notebook mới lên Kaggle, chưa chạy API/Reader mới, chưa xác nhận endpoint
  của tài khoản đã hoạt động trở lại. Lượt Reader gần nhất vẫn gặp 503.
- [Bản notebook và hướng dẫn tiếp tục](READER_RESUME_20261011.md).
  Confidence, Summarizer và full E2E vẫn còn công việc; chưa đạt nghiệm thu.

## Confidence backend đã chạy thật — 20261010T101538Z

- ZIP mới đúng hash **35/35 file**, runtime **45/45 file khớp repo**; Kaggle
  đạt 139 tests. Replay offline 96 predictions từ 99 response khớp; metrics
  và summary tính lại đúng. Đây là diagnostic confidence, chưa phải full E2E.
- **0/4 profile đạt.** Fine-tuned repair nhận 4/12 nhãn đúng, 2/12 nhãn sai;
  fine-tuned explanation nhận 11/12 đúng, 10/12 sai, một runtime failure.
  Base repair nhận 2/12 đúng, 1/12 sai; base explanation nhận 12/12 đúng nhưng
  9/12 sai. Giữ baseline `repair`; chưa profile nào đủ điều kiện promote.
- Có score 0.95 đi kèm explanation thừa nhận nhãn đề xuất sai. Score đúng/sai
  trùng nhau nên chỉ đổi threshold không đạt đủ tiêu chí. 96 review rows pending.
- Tiếp theo: chạy Reader bốn cell riêng; phát triển/thử nghiệm verifier nhãn
  có evidence trước khi thay phục vụ; sau đó xử lý Summarizer và full E2E.

Chi tiết, bằng chứng lỗi và kế hoạch:
[CONFIDENCE_BACKENDS_REVIEW_20261010T101538Z.md](CONFIDENCE_BACKENDS_REVIEW_20261010T101538Z.md).
Bằng chứng tính lại: [confidence-backend-audit-20261010T101538Z.json](confidence-backend-audit-20261010T101538Z.json).

## Lịch sử: đã chuẩn bị diagnostic thành phần — 2026-10-10

- Reader đã thêm metadata quota có lọc, xuất blocks theo trang/exact chunks và
  replay offline kiểm hash rồi tính lại metric/gate. PDF lỗi vẫn là lỗi.
- Confidence đã có ma trận hai backend × hai prompt × 24 lượt; tiêu chí lưu
  trước inference, không tự đổi prompt/backend phục vụ. Giữ `repair`.
- Notebook chạy thủ công mới: `kaggle_confidence_backends.ipynb` **3 code cell**,
  `kaggle_reader_diagnostics.ipynb` **4 code cell**. Reader thử đúng trang 4 từng
  lỗi trước, chỉ đọc toàn PDF khi probe đạt. Chưa cần chạy lại sáu cell cũ.
- **147/147 test local đạt** (20,650 giây unittest), dùng model/API giả lập;
  chưa có kết quả GPU/API mới cho những thay đổi này. Dự án vẫn chưa đạt gate.

Hướng dẫn chi tiết và điều kiện đọc kết quả:
[COMPONENT_DIAGNOSTICS_20261010.md](COMPONENT_DIAGNOSTICS_20261010.md).
Bằng chứng code/test: [component-diagnostics-validation-20261010.json](component-diagnostics-validation-20261010.json).

## Lịch sử: đối chiếu model/API thật 20261010T025939Z — Reader gần nhất

- ZIP mới đúng hash **63/63 file**, runtime **42/42 file khớp repo**. Kaggle
  đạt 130 contract tests. Đủ 142 predictions và 312 backend calls confidence.
- Candidate `explanation_repair` đạt 9 gate cũ trên 47 ca nhưng trượt controlled
  labels: tin 10/12 nhãn sai, nhận 11/12 nhãn đúng, 1/24 runtime failure.
  Giữ `repair`, không promote. 71 explanation rows vẫn human review pending.
- Reader trang từng lỗi và smoke đạt automated gate. Có **4 lần 503 phục hồi
  thành công** sau retry trên hai stage smoke/PDF thật.
- Reader PDF thật dừng tại `page_no=3` vì critique trả **429 cả 3 attempts**.
  Chưa đủ dữ liệu để xác định quota nào bị chạm. Chưa đọc đủ 12 trang; không
  diễn giải score toàn PDF bằng 0 thành OCR sai 100%.
- Cần kiểm quota và chạy diagnostic thành phần mới ở mục phía trên, review
  nội dung, rồi sửa Summarizer và chạy đủ 8 ca E2E. Lượt này chưa phải E2E
  toàn hệ và chưa có human sign-off.

Chi tiết và thứ tự tiếp theo:
[COMPLETION_REVIEW_20261010T025939Z.md](COMPLETION_REVIEW_20261010T025939Z.md).
Bằng chứng: [completion-audit-20261010T025939Z.json](completion-audit-20261010T025939Z.json).

## Lịch sử: chuẩn bị explanation và Reader reliability — 2026-10-10

- **Giữ `repair` làm mặc định**, nguyên Judge/confidence prompt đã được audit,
  ngưỡng 0.7 và tối đa 3 attempts/stage. Không promote `label_confidence_repair`.
- Đã thêm ứng viên explanation chỉ trong diagnostic, tiêu chí v2 được lưu
  trước inference, 24 ca kiểm nhãn đề xuất đúng/sai và 71 dòng review trống.
  Chưa có kết quả model thật cho ứng viên này; không tự đóng human review.
- Đã sửa Reader để pacing áp dụng cho mỗi lần gửi API, chỉ một tầng retry,
  tối đa 3 lần gửi/call, budget gồm chờ/backoff và log từng attempt. Chưa xác
  nhận hết 503 trên dịch vụ thật; lỗi 503 kéo dài vẫn phải dừng có bằng chứng.
- Notebook mới **`scripts/kaggle_completion_validation.ipynb` có 6 code cell**:
  mount → setup/test → confidence explanation → trang PDF từng lỗi → Reader
  smoke → PDF thật. Payload 42 file được kiểm hash. Đây là diagnostic thành
  phần; chưa thay thế bộ E2E 8 ca.
- Kiểm tra local: **137/137 test đạt, 27.011 giây** trong lượt chạy lại ngoài
  sandbox đã được phê duyệt. Lượt sandbox đầu có lỗi quyền đổi tên ZIP tạm;
  không sửa code để bỏ qua kiểm tra đó. Model/API đều giả lập trong test.
- Chưa sửa lỗi Summarizer ở `heldout_3`, chưa chạy E2E đầy đủ với runtime mới,
  chưa có calibration/final test độc lập. **Dự án chưa đạt gate phát hành.**

Thứ tự chạy, điều kiện đạt và danh sách file:
[COMPLETION_VALIDATION_20261010.md](COMPLETION_VALIDATION_20261010.md).
Hash artifact và bằng chứng test local:
[completion-validation-20261010.json](completion-validation-20261010.json).

Các mục bên dưới là lịch sử tại ngày được ghi, không mô tả trạng thái runtime mới.

## Bước 1 confidence — bản sửa sau rà soát 2026-10-09

Đã thêm feedback lỗi/output vào retry có giới hạn, validation score/reasoning
đúng kiểu và diagnostic so ba profile giữ Judge/threshold cố định. Có notebook
riêng `scripts/kaggle_confidence_validation.ipynb` để người dùng chạy thủ công.
**Đã nhận model diagnostic 20261009T120708Z:** repair đạt 9/9 automated checks,
runtime failure 7/47 → 0/47; 7 output lỗi được sửa ở attempt thứ hai. Đã xác
minh 44/44 file và tính lại đúng metric/gate từ predictions/calls. Chưa đóng
nghiệm thu đầy đủ vì human review chưa xác nhận và còn explanation sai ý nghĩa
(wrong_units). Prompt thử nghiệm cho 1.0 cả 47 dòng, gồm 12 nhãn dev sai; chưa
được promote. Reader/Summarizer chưa sửa ở lượt này. Xem
[đối chiếu diagnostic](CONFIDENCE_STEP1_REVIEW_20261009T120708Z.md).
Kiểm tra local: **118/118 test đạt, 15,519 giây**, gồm contract/regression và
kiểm payload notebook. Lượt sandbox đầu lỗi rename ZIP tạm; lượt chạy lại ngoài
sandbox đạt. Không dùng kết quả test giả lập này thay cho inference thật.
Chi tiết, file thay đổi và hướng dẫn: [CONFIDENCE_STEP1_20261009.md](CONFIDENCE_STEP1_20261009.md).

## E2E lượt hai — 2026-10-09

ZIP mới đúng hash 80/80 file và chạy đúng runtime ngày 07/10; tiêu chí/câu hỏi
không đổi. **3/8 gate tự động đạt**, gồm missing/conflict/budget; overall_pass=false.
Missing nay trả lời 42 đúng nguồn. Conflict chặn claim phản bác nhưng vẫn có
confidence_failed. Reader lỗi HTTP 503 tại critique trang 0. Confidence có 15
output JSON hợp lệ với reasoning rỗng (5 review × 3 attempts), đã tái hiện lỗi
validator offline. heldout_3 nhầm baseline và bị verbatim gate chặn.

99 contract tests trên Kaggle đạt; re-score offline tái tạo đúng cả tám case và
summary. Lượt rà soát ZIP ban đầu chưa sửa runtime; bản sửa confidence sau đó
được ghi riêng ở mục bước 1 phía trên.
Kế hoạch chi tiết theo thứ tự và điều kiện nghiệm thu:
[E2E_COMPARISON_20261009.md](E2E_COMPARISON_20261009.md).

## Lịch sử: E2E model thật đã nhận — rà soát 2026-10-07

Đã xác minh ZIP lượt Kaggle 2026-10-02: 80/80 file trong manifest đúng hash,
hai Tesla T4, suite thực thi đủ tám kịch bản. **Kết quả gốc 2/8 gate tự động đạt**,
nhưng ca `missing` báo hoàn thành với câu chỉ dẫn phụ lục, chưa trả lời cỡ mẫu.
`overall_pass=false`; chưa đạt nghiệm thu. Ba policy retrieval hòa trên ba câu
paper-scoped, chưa chứng minh lợi thế adaptive hoặc tổng quát hóa.

Đã sửa contract câu trả lời/hoàn thành, audit nguồn mâu thuẫn, dùng được nguồn
full chunk hỗ trợ, giữ context evidence và bổ sung diagnostics Reader/confidence.
Đã tạo notebook mới cho **regression rerun** thủ công; chưa chạy model thật cho
bản sửa 2026-10-07. Các lỗi Reader và confidence chưa đủ log để kết luận root cause.

Báo cáo, từng file đã sửa và các bước tiếp theo:
[E2E_AUDIT_20261007.md](E2E_AUDIT_20261007.md).

Các số liệu kiểm tra bên dưới thuộc lịch sử của từng bản, không thay cho lượt rerun mới.

Kiểm tra local hiện hành 2026-10-07: **104/104 test research_rag đạt**, 44,523 giây,
gồm 11 regression mới và kiểm payload notebook. Backend giả/API mock; chưa phải
kết quả model thật của bản sửa. Chi tiết: `e2e-audit-20261007.json`.

## Điều phối tự chủ — 2026-09-30

Đã triển khai controller theo luật, contract quyết định/kết quả agent, vòng điều
phối theo bằng chứng, đọc PDF theo câu hỏi, yêu cầu thêm context, giới hạn bước/
thời gian/call/chi phí dự trù, SQLite checkpoint và timeout tiến trình CLI.
Chi tiết và lệnh chạy: [AUTONOMOUS_RESEARCH.md](AUTONOMOUS_RESEARCH.md).

Kiểm tra local hiện tại: **91/91 test research_rag đạt** (2026-10-01, 33,404 giây).
**65/65 test Writer đạt** trong lượt kiểm tra trước. Có kiểm tra
SQLite đóng/mở lại và resume, timeout tiến trình, yêu cầu thêm context, giữ nguồn
mâu thuẫn và báo cáo một phần. Backend điều phối trong test là giả lập.
Đã thêm kế hoạch có nhiệm vụ con, RetrievalAgent với policy BM25/dense, năm node riêng,
trace quan sát/quyết định/kết quả và bộ E2E có tiêu chí chốt trước inference.
Notebook riêng: `scripts/kaggle_autonomy_validation.ipynb`; nguồn/tiêu chí không chứa secret.
Notebook đã nén payload, khôi phục và đối chiếu đúng hash mã nguồn/bộ đánh giá.
Ca PDF có deadline 900 giây để đủ thời gian gọi Reader API; các ca khác vẫn 300 giây.
Chi tiết lần tiếp tục và cách chạy: [AUTONOMY_VALIDATION_20261001.md](AUTONOMY_VALIDATION_20261001.md).

Ở snapshot 2026-10-01, preflight local không có CUDA và thiếu base weights Qwen
7B/1.5B. Lượt E2E người dùng chạy 2026-10-02 đã được rà soát ngày 2026-10-07 ở
phần trên; bản sửa sau rà soát vẫn chưa được chạy lại bằng model thật.

## Lịch sử rà soát — 2026-09-27

1. **Giữ nguồn qua retry:** `seen_chunks` tích lũy và loại trùng các chunk đã
   truy xuất. Fact-Checker kiểm cả nguồn cũ và mới, nên đổi lượt retrieval không
   làm mất nguồn phản bác. Summarizer vẫn nhận context có giới hạn của lượt hiện
   tại. Quá budget kiểm chứng thì từ chối xác minh, không bỏ bớt nguồn để pass.
2. **Evidence đầy đủ:** mọi span Summarizer trả về phải khớp nguồn, với quy tắc
   khoảng trắng/ligature hiện có. Một span đúng không che được một span bịa.
3. **Contract Fact-Checker:** nhãn lạ, thiếu status/score, `None`, bool, chuỗi,
   NaN/Infinity hoặc score ngoài [0,1] được coi là lỗi kiểm chứng. Graph chặn
   claim và giữ tên loại lỗi, không làm rơi exception ra khỏi workflow.
4. **Scorer:** calibration từ chối nhãn không hợp lệ và prediction runtime lỗi;
   báo thêm reliability bins, accuracy/confidence theo nhãn dự đoán và precision
   của support tại ngưỡng cho trước. Reader báo thêm tỷ lệ span được đánh giá và
   `overall_exact_span_rate`, tính cả PDF lỗi vào mẫu số. Điểm conditional cũ
   vẫn giữ để so sánh, được mô tả rõ.
5. **Encoder:** preflight, dựng index và truy vấn cùng dùng BGE revision
   `d4aa6901d3a41ba39fb536a557fa166f842b0e09`, đã đối chiếu metadata công khai.
   Download theo SHA không tự tạo cache ref `main`; loader offline cần dùng
   đúng SHA. Chưa có dense benchmark mới từ thay đổi này.
6. **Notebook phục hồi:** `scripts/kaggle_resume_validation.ipynb` chứa bản vá
   10 file code/test, kiểm before/after hash trên workspace đã overlay dataset
   diagnostics v2. Có test contract trước inference; timeout, status/log và ZIP
   kết quả cho từng stage. ZIP đã được phê duyệt/upload trước đây không thay đổi.
   Generator được lưu tại `scripts/build_validation_notebook.py`; entry point
   cũ trong `kaggle_transfer/` chuyển tiếp sang script này.

Regression được kiểm trước/sau sửa bằng backend giả. Lượt cuối ngày 2026-09-27: **62 test đạt,
0 lỗi, 0 test bỏ qua**. Kết quả suite mới nhất ở
`runtime-hardening-tests-20260927.json`. Hai test notebook kiểm cú pháp/payload,
tiến trình thành công/thất bại và hash ZIP; không nạp model hoặc gọi API.
Nhánh kill process group khi timeout trên Linux chưa được kiểm trên Windows.

### File code và test đã thay đổi

- Runtime: `research_rag/graph.py`, `state.py`, `retrieval.py`, `indexing.py`,
  `preflight.py`, `evaluate.py`, `evaluation/reader_smoke.py`.
- Regression: `research_rag/tests/test_graph_safety.py`,
  `test_evaluation_contracts.py`, `test_indexing.py`, `test_validation_notebook.py`.
- Phục hồi: `scripts/build_validation_notebook.py`,
  `scripts/kaggle_resume_validation.ipynb` và entry point tương thích
  `kaggle_transfer/build_resume_notebook.py`.
- Báo cáo mới: `docs/factchecker-dev30-confidence-audit-20260927.json` và
  `docs/runtime-hardening-tests-20260927.json`. Các README liên quan trỏ về
  trang trạng thái này; kế hoạch cũ được đánh dấu là snapshot lịch sử.

## Đánh giá lại prediction đã lưu, không inference mới

`factchecker-dev30-confidence-audit-20260927.json` giữ hash prediction GPU ngày
2026-09-26 và kết quả chấm lại:

- ECE: **0,402**; Brier: **0,400087**.
- Ngưỡng 0,7 nhận **5/30** dòng là support: precision quan sát 5/5, coverage
  **16,7%**. Mẫu quá nhỏ và đã dùng cho development; không chứng minh precision
  tổng quát, không phủ nhận false support của ca DistilBERT đã biết.
- 18 prediction `not_enough_info` có mean confidence 0 nhưng accuracy 0,5;
  confidence hiện không thể coi là xác suất đúng đã calibration.

Không promote profile `coverage`, không đổi ngưỡng, không fit trên dev30.

## Kế hoạch validation thành phần — snapshot 2026-09-27

Thứ tự hiện hành sau E2E nằm trong `E2E_AUDIT_20261007.md`: chạy regression bản
sửa trước; các đánh giá thành phần bên dưới vẫn là công việc bổ sung chưa đủ bằng chứng hoàn tất.

| Bước | Thực hiện | Bằng chứng cần thu |
|---|---|---|
| 1 | Import notebook phục hồi mới vào notebook Kaggle Private; attach workspace + diagnostics v2. Kiểm Output/Draft cũ trước khi chạy lại. | Hash patch, `pip check`, contract tests, preflight thành công. |
| 2 | Chạy cell Fact-Checker: baseline/coverage trên cùng 30 dev + 12 synthetic, giữ cả lỗi. | 84 prediction, false support từng ca, metrics/latency/VRAM; review trước khi chọn profile. |
| 3 | Chạy Reader smoke rồi PDF thật 12 trang với Secret hiện có; không nhập key vào code. | Không lỗi API, đủ dòng sau overflow; span đúng trang, coverage toàn manifest. Thêm scan thực tế và nhãn đã được người rà. |
| 4 | Dựng BGE index QASPER và so BM25/dense/policy trên cùng 393 dev. | Corpus/index/qrels hashes, recall@k, latency, `dense_fallback_queries == 0`. 417 test candidate vẫn chưa chấm. |
| 5 | Hoàn tất provenance, annotation review, calibration/final split theo claim/paper. | Tách dữ liệu chọn prompt/ngưỡng khỏi final test; chưa có split đủ bằng chứng độc lập toàn pipeline. |
| 6 | Dùng corpus đã có căn cứ license; chạy đủ ca lỗi/mâu thuẫn bằng model thật. | QASPER có license nguồn công bố và attribution; corpus arXiv cũ vẫn chưa xác minh. Kiểm abstention, nhiều claim, nguồn đối lập qua retry, OCR/API lỗi, citation, RAM/VRAM, latency và token/cost nếu backend cung cấp. |
| 7 | Sau khi các gate đạt, triển khai API và checkpoint bền vững. | Auth, input validation, timeout, giới hạn tài nguyên và lưu/xóa dữ liệu phù hợp. |

Notebook phục hồi thực hiện setup và bước 2–4; nó **không tự hoàn thành** annotation,
calibration/final test, toàn bộ adverse E2E hoặc serving. Lưu Quick Save **kèm
Output** sau từng stage và xác nhận phiên bản thành công; sau đó Stop session.

Ở lượt ngày 2026-09-27, công cụ browser timeout ngay khi mở notebook; chưa khởi động
GPU/API hoặc upload notebook mới. Lần dừng GPU gần nhất có bằng chứng:
`VALIDATION_RUN_20260927.md`, **0 Active Events / Cancelled**. Không suy ra một
lượt model thành công từ test local hoặc từ trạng thái khởi chạy tiến trình.

## Lệnh kiểm tra local

```powershell
$env:OMP_NUM_THREADS='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
.venv\Scripts\python.exe -m unittest discover -s research_rag/tests -q
.venv\Scripts\python.exe scripts/build_validation_notebook.py
.venv\Scripts\python.exe -m unittest research_rag.tests.test_validation_notebook -q
```

Generator cần hai ZIP đã có trong `kaggle_transfer/` để kiểm đúng base hashes.
Không đưa thư mục đó, checkpoint hoặc credential vào Git để tái tạo notebook.

Tài liệu API được đối chiếu: [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api).
Revision encoder: [BGE model metadata](https://huggingface.co/api/models/BAAI/bge-large-en-v1.5).
