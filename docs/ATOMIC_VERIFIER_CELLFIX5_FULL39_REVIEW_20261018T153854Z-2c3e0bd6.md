# Audit full39 cellfix5 — 18/10/2026

Run `20261018T153854Z-2c3e0bd6`. ZIP `output-cellfix5-full39-20261018T153854Z-2c3e0bd6.zip`. SHA256 `8425775efc1703b317f2d15d87a54e3fdbf4f0a9ccbe2a0c1490554c61c06e3a`.

**Kết luận: chưa đạt gate verifier, chưa đủ điều kiện tích hợp/nghiệm thu pipeline với candidate này.** Đã đo trên đủ 39 ca: false_support=0, không runtime failure, nhưng chỉ 21/39 nhãn đúng. Human review probe của Trí Công đã được admission; review bằng chứng full39 là bước riêng.

## Artifact và replay

| Kiểm tra | Kết quả |
| --- | --- |
| ZIP/output manifest | 64 file, CRC/size/hash khớp; bản ZIP gốc đã bảo toàn trong research-runs |
| Frozen payload | 84 input files, 36 source/fixture khớp release cellfix5 |
| Source/prompt/contract/criteria/model | Khớp hash/revision, NF4/float16, seed42, budget đã chốt |
| Human admission | Trí Công; review và probe predictions đúng hash; require_probe_review replay đạt |
| Runtime | Tesla T4, torch 2.10.0+cu128; 181 regression, ba validate-only, pip check đạt |
| Full39 replay | 39 predictions, 85 call triplets/raw JSON, 39 stdout records và comparisons chấm lại khớp |
| Decomposition | Cả 39 plan trùng probe đã review; giữ 010/014/018 metric chuẩn |
| Status | verifier39 exit_code=1 do automated_gates_failed; 39 stop_reason=completed |

85 output đều valid theo schema/validator, không repair. Vì vậy đây không phải lỗi JSON bị cắt, thiếu cell, thiếu GPU, hash sai hay timeout. Output hợp lệ về cấu trúc vẫn có thể sai về nghĩa và scope.

## Số đo thực tế

| Metric | Kết quả |
| --- | --- |
| Đủ/completed | 39/39 |
| Đúng nhãn | 21/39 = 53,85% |
| Original contracts | 12/12 |
| Scope regression | 9/27 |
| False support | 0 trên bộ development39 |
| Runtime failed rows | 0 |
| Gold support bị bỏ lỡ | 8/13 |
| Support recall | 5/13 = 38,46% |
| Precision của predictions support | 5/5 đúng; chỉ 5 predictions support, không suy rộng thành bảo đảm production |
| Calls / giới hạn | 85 / 312 |
| Generated / prompt tokens | 9491 / 120976 |
| Thời gian stage / worker | 811,34s / 804,17s; khoảng 13,5 phút |
| Case latency mean / P95 / max | 18.99s / 41.87s / 42.06s |

Zero false support hiện đã được đo trên đủ bộ39 của candidate này. Tuy nhiên nó không thay điều kiện 39/39 nhãn đúng và recall support. Không công nhận đạt bằng cách trả quá nhiều NEI hoặc contradiction.

| Gold \ Prediction | support | contradict | not_enough_info |
| --- | --- | --- | --- |
| support | 5 | 2 | 6 |
| contradict | 0 | 8 | 5 |
| not_enough_info | 0 | 5 | 8 |

Baseline lịch sử trong ZIP là 37/39, false_support=2. So đúng/sai nhãn với baseline: 1 ca cải thiện, 17 ca mất nhãn đúng, 20 ca cùng đúng, 1 ca cùng sai. Đây là so predictions lịch sử, không phải chạy lại baseline hoặc thí nghiệm chỉ thay một yếu tố.

## 18 ca sai chia thành năm nhóm

| Nhóm chính | Số ca | Đã chứng minh từ trace/code |
| --- | --- | --- |
| Quantifier, coverage, positive predicate | 5 | ALL thiếu closure; SOME bỏ positive witness; NONE bị đảo polarity leaked |
| Missing evidence bị coi là false | 5 | Không có results/baseline bị gán false rồi contradict |
| Counterevidence ngoài population | 2 | April refute May; high-temperature refute low-temperature |
| Parser/binding số liệu | 4 | afterward thành unit; exact metric không khớp; nhiều metric làm change passage ambiguous |
| Exact-target schema và annotation | 2 | extractor vắng trong context, schema khóa unknown dù gold giả định matched workload |

### Phân biệt lỗi model và giới hạn code

1. **Coverage không bị decoder cấm.** Schema của universal support cho phép complete=true; model vẫn chọn coverage=false và chỉ Maple. Context đã đóng Cedar/Maple/Pine và xác nhận each improved. Không sửa bằng cách công nhận một positive witness là ALL.

2. **NONE dùng positive predicate trước quantifier.** Silver leaked phải có truth=true cho predicate leaked; model ghi false vì hiểu thành toàn câu NONE. Aggregator đang áp đúng phép lượng từ lên ledger bị gán truth sai. Không đảo logic toán học của NONE để vá một ca.

3. **Exact quote chưa chứng minh entailment.** No calibration results for North bị biến thành phản bác; Some April trials reduced bị dùng refute May; high-temperature lost bị dùng refute low-temperature. Các output vẫn scope_match=matched, nên guard hiện chưa bắt đủ association sai.

4. **Numeric failures có thể tái hiện không cần model.** numeric_requirements nhận 0.86 afterward với unit=afterward; bare operand 0.86 lại bị numeric_unit_required. Pair 42→31 ms có arithmetic decrease đúng nhưng numeric_metric_matches từ chối median latency khi claim là median request latency. Precision 0.81→0.74 bị ambiguous_numeric_passage vì passage chứa cả recall 0.64→0.79. Không bỏ guard hoặc bỏ mọi modifier để tăng điểm; cần bind đúng metric/clause/pair và bảo toàn evidence/chronology.

5. **Conjunction có contract mismatch cần annotation review.** Context nói same extraction workload nhưng không định danh extractor. Gold và annotation_rationale mặc định binding này; source ghi rõ synthetic, not independently adjudicated. Schema exact-target chỉ cho truth=unknown cho cả hai part. Phải chốt alias/coreference với evidence hoặc metadata nguồn hợp lệ trước khi sửa. Claim không tự làm bằng chứng nhận diện; không tự sửa gold để hợp thức hóa code.

## Review đủ 39 ca

S/C/N lần lượt là support/contradict/not_enough_info. Nhận xét dưới đây là review của AI trên fixture đã cung cấp, không phải annotation độc lập hay xác nhận human cho full39. Nhãn đúng vẫn có thể kèm ledger/explanation sai.

| Case | Gold | Code | Khớp nhãn | Nhận xét bằng chứng |
| --- | --- | --- | --- | --- |
| contract:partial_accuracy | N | N | ✓ | Context chỉ có memory giảm 25%; part memory support, accuracy 94% thiếu evidence, nên AND là NEI. |
| contract:partial_memory | N | N | ✓ | Context chỉ có accuracy 94%; part memory thiếu evidence, nên AND là NEI. |
| contract:both_supported | S | S | ✓ | Context xác nhận cả memory giảm 25% so baseline và accuracy 94%; cả hai numeric checks đúng. |
| contract:accuracy_conflict | C | C | ✓ | Memory giảm 25% được chứng minh; accuracy thực tế 81%, not 94%. Nhãn contradict đúng, nhưng model_truth/explanation ở memory part lẫn accuracy; code numeric sửa truth về true. |
| contract:irrelevant | N | N | ✓ | Không có accuracy của Model Juniper; scope mismatched và accuracy không được báo cáo nên NEI, không phải phủ định 94%. |
| contract:negation | C | C | ✓ | did not use any human labels phủ định trực tiếp cùng predicate; contradict đúng. |
| contract:causality_missing | N | N | ✓ | Không thiết lập causal relationship; co-occurrence không chứng minh caused. NEI đúng. |
| contract:scope | C | C | ✓ | Một fourth task less accurate là counterexample đủ bác bỏ All tasks improved. |
| contract:cross_sentence | S | S | ✓ | Bốn models và hai datasets được chứng minh ở hai câu cùng report. Ledger có cả hai check/citation; observation prose chỉ nhắc four models, model_explanation kết thúc ở 2/. |
| contract:wrong_units | C | C | ✓ | 12 hours, not 12 seconds là phản bác trực tiếp; không nhầm cùng số 12 thành cùng duration. |
| contract:atomic_support | S | S | ✓ | Exactly 240 documents cùng sample chứng minh claim. |
| contract:bounded_scope | S | S | ✓ | Cùng tested dataset có recall improved; kết quả ở dataset khác không làm thiếu evidence cho claim đã giới hạn. |
| scope:universal:support | S | N | ✗ | Context đóng population Cedar/Maple/Pine và xác nhận each improved. Model chỉ ghi Maple, coverage.complete=false; code giữ NEI. Thiếu ledger toàn population, không phải thiếu evidence trong context. |
| scope:universal:contradict | C | C | ✓ | Third shard became worse là counterexample đúng scope. Nhãn đúng; member validation set là tập hợp, chưa định danh đúng counterexample theo contract one-record-per-member. |
| scope:universal:not_enough_info | N | C | ✗ | Chỉ biết hai shard improved, các shard còn lại chưa báo cáo. Không có counterexample; model gán false vì chưa đủ coverage nên code trả contradict sai. |
| scope:existential:support | S | N | ✗ | Birch became faster là positive witness đủ cho SOME. Model chọn Elm became slower và bỏ Birch nên trả NEI sai. |
| scope:existential:contradict | C | N | ✗ | Population complete Birch/Elm/Fir, không node nào giảm response time. Model chỉ ghi Fir false, không complete coverage nên NEI sai. |
| scope:existential:not_enough_info | N | N | ✓ | Elm không giảm, các node khác chưa biết; SOME chưa chứng minh hay bác bỏ. Nhãn NEI đúng, nhưng member audited cache nodes là collective và explanation không phân biệt riêng witness đã biết với phần chưa báo cáo. |
| scope:none:support | S | N | ✗ | Population ba pumps đóng, context explicitly no leaks for any. Cần positive predicate leaked=false cho từng member cùng closure. Model ghi Blue unknown, bỏ closure nên NEI sai. |
| scope:none:contradict | C | N | ✗ | Silver leaked là leaked=true trước khi áp NONE, đủ refute NONE. Model lại ghi truth=false, đảo polarity của positive predicate nên NEI sai. |
| scope:none:not_enough_info | N | N | ✓ | Blue/Green không leak, Silver chưa báo cáo; NONE là NEI. Nhãn cuối đúng nhưng observation Silver=false là sai; phải unknown, nên ledger chưa đạt. |
| scope:entity:support | S | S | ✓ | North giảm error rate sau calibration; South tăng không liên quan. Quote chọn đúng North, support đúng. |
| scope:entity:contradict | C | C | ✓ | North tăng error rate sau calibration là counterevidence; không mượn kết quả giảm của South. |
| scope:entity:not_enough_info | N | C | ✗ | North không có calibration results; South giảm không bác bỏ North. Missing evidence bị model biến thành false, dẫn tới contradict sai. |
| scope:time:support | S | C | ✗ | Mọi May trial đều improved; April trial reduced nằm ngoài population. Model dùng April để refute May, scope_match vẫn matched nên false contradiction. |
| scope:time:contradict | C | C | ✓ | Trong bốn May trials, một reduced throughput là counterexample đúng population. Nhãn đúng; ledger dùng member weekly trials chung thay cho member counterexample riêng. |
| scope:time:not_enough_info | N | C | ✗ | Chỉ có April results, May không có throughput results. Đây là NEI, không phải bằng chứng May trial không cải thiện. |
| scope:direction:support | S | N | ✗ | 42 ms before xuống 31 ms after chứng minh decrease. Arithmetic đúng nhưng metric binding đòi nguyên chuỗi median request latency trong proof chỉ ghi median latency, nên code hạ xuống unknown. |
| scope:direction:contradict | C | N | ✗ | 42 ms before lên 55 ms after bác bỏ reduced. Numeric observed_direction=increase, model vẫn nói giảm; code còn hạ về unknown do metric binding nên nhãn NEI sai. |
| scope:direction:not_enough_info | N | C | ✗ | Chỉ có giá trị after-patch 31 ms, không baseline/change. Không thể kết luận giảm hay không giảm; model gán false nên contradict sai. |
| scope:metric:support | S | N | ✗ | Precision 0.81 lên 0.86 đúng claim. Parser/decoder ghi unit afterward cho 0.86 afterward; unit_mismatch_no_conversion làm observation unknown. |
| scope:metric:contradict | C | N | ✗ | Precision 0.81 xuống 0.74, recall tăng là metric khác. Pair precision đúng nhưng change checker nhìn toàn passage bốn số nên ambiguous_numeric_passage, NEI sai. |
| scope:metric:not_enough_info | N | N | ✓ | Chỉ đo recall, precision was not measured, nên NEI đúng. Quote/model prose về recall không phải bằng chứng phủ định precision; explanation denies increase chưa chính xác. |
| scope:conjunction:support | S | N | ✗ | Context nêu memory 5.4 xuống 4.6 GB và recall 0.72 lên 0.81. Gold support giả định cùng extraction workload gắn với extractor trong claim, nhưng không có literal target extractor; decoder khóa cả hai part ở unknown. Cần chốt contract alias/coreference và annotation, không tự xóa entity guard để khớp gold. |
| scope:conjunction:contradict | C | N | ✗ | Context nêu memory giảm, recall 0.72 xuống 0.68; gold contradict dựa trên binding cùng workload với extractor. Literal target extractor vắng, decoder chỉ cho unknown. Đây là xung đột giữa gold có binding ngầm và contract exact target; phải làm rõ annotation/binding trước khi sửa. |
| scope:conjunction:not_enough_info | N | N | ✓ | Recall không được đánh giá nên AND là NEI như gold. Memory part cũng unknown vì exact target extractor vắng dù workload có số giảm. Nhãn cuối đúng không xác nhận binding ngầm của extractor hoặc chất lượng giải thích từng part. |
| scope:condition:support | S | C | ✗ | Mọi low-temperature batch gained; separate high-temperature batch lost nằm ngoài population. Model dùng high-temperature counterexample để refute low-temperature sai scope. |
| scope:condition:contradict | C | C | ✓ | Trong low-temperature group có one lost yield; đủ bác bỏ ALL. Nhãn đúng, member one còn phụ thuộc context group ở câu trước. |
| scope:condition:not_enough_info | N | C | ✗ | Low-temperature chưa đo changes; high-temperature gained không chứng minh hoặc bác bỏ low-temperature. Quote out-of-group và false verdict sai. |

Đặc biệt: scope:none:not_enough_info có label đúng nhưng Silver bị gán false thay vì unknown; conjunction:not_enough_info có aggregate đúng nhưng binding/memory part chưa được giải quyết. accuracy_conflict/cross_sentence còn các lưu ý explanation đã thấy ở smoke. Không suy từ 21 labels đúng thành 21 ledger hoàn toàn sạch.

## Còn thiếu trước khi chuyển sang bước tiếp theo

1. **Ưu tiên hiện tại: candidate assessment mới.** Bảo toàn cellfix5 và ZIP này; sửa quy tắc truth/coverage, phân biệt missing-vs-false, binding population/time/condition, numeric unit/measurement pair và contract exact-target. Chốt annotation/binding của các ca mơ hồ trước; không vá theo ID, không đổi gold/budget/gate để đạt điểm. Thay đổi này chưa được triển khai trong lượt audit.

2. **Regression mới và validation độc lập.** Dùng trace thật làm regression cùng câu mới cho từng nhóm. Đóng băng bộ validation riêng có gold label/evidence/missing-information được người review, kiểm overlap claim/context và không dùng để tune. Cả 18/39 hiện là development đã xem nhiều vòng. 417 QASPER retrieval qrels không thay bộ verifier này.

3. **Nghiệm thu candidate kế tiếp.** Freeze đồng bộ source/prompt/contract/criteria/notebook; regression và validate-only đạt; smoke, probe/new admission theo protocol rồi full39. Cần 39/39 đúng, false_support=0, runtime_failed_rows=0, review bằng chứng đầy đủ và đánh giá riêng. Không cần sửa tiếp metric 010/014/018 chỉ để chạy lại 18 ca hiện đã trùng probe.

4. **Reader local còn một gate riêng.** Code _critique đã có quyết định accept/retry/fallback theo output rỗng, bbox/confidence; chưa thấy local check tỷ lệ ký tự rác hoặc độ lệch dòng trong hàm này. Lệnh tesseract chưa tìm thấy trên PATH trong shell audit; điều đó không chứng minh binary không tồn tại ở đường dẫn khác. Lượt này chưa chạy OCR scan mới. Cần kiểm runtime/binary, OCR scan/layout thật và chất lượng quyết định accept/retry/fallback; Gemini chỉ là tùy chọn.

5. **Tích hợp và E2E vẫn thiếu.** research_rag/local.py còn khởi tạo FactCheckerNode cũ, chưa nạp AtomicVerifier cellfix5. Sau khi verifier đạt gate mới nối Reader → Summarizer → verifier → Writer, log hash verifier thực nạp và chạy model/adapter thật với các nhánh đủ/thiếu evidence, contradiction, scan, timeout/retry. Đánh giá trước/sau integration trên ca đã chốt và bộ độc lập.

Retrieval QASPER đã có audit Dense/BM25 hợp lệ, không fallback, nhưng đó là dev retrieval; không thay gate verifier hoặc E2E. Hiện chưa nên dùng candidate này để nghiệm thu Reader/Summarizer hay ghi toàn dự án Ready.

## Phạm vi audit

Đã bảo toàn ZIP và outputs; không thay prediction, gold, prompt, verifier source, budget hoặc gate. Đã replay và chạy diagnostic schema/numeric bằng source đã đóng băng; không gọi lại Qwen, không chạy model/E2E mới. Hash/provenance chỉ xác nhận nhất quán với release, không phải attestation độc lập máy Colab. Gate thất bại là kết quả cần giữ, không phải lý do ký review để bỏ qua.

Bằng chứng máy đọc: atomic-verifier-cellfix5-full39-audit-20261018T153854Z-2c3e0bd6.json; atomic-verifier-cellfix5-full39-diagnostics-20261018T153854Z-2c3e0bd6.json; atomic-verifier-cellfix5-full39-evidence-review-20261018T153854Z-2c3e0bd6.jsonl.
