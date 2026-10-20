# Full39 v7 — không đạt; timeout và assessment chưa hoạt động đúng

Run `20261016T071213Z-7c8c33c6`, ngày2026-10-16. **Không hoàn tất bộ39:** process dừng
ở5.400 giây, mới lưu22 predictions;21 incomplete, một completed nhưng sai nhãn.
Không có `metrics.json` cuối. Probe18/18 và human admission vẫn hợp lệ; chúng
không chứng minh bước assessment sử dụng đúng evidence.

**Không chạy lại nguyên notebook hoặc chỉ tăng timeout lúc này.** Trước lượt
GPU tiếp theo cần sửa generation/grounding/numeric/deadline của assessment,
thêm regression từ run thật và một assessment smoke probe ngắn. Bản v7 cùng ZIP
được giữ nguyên; chưa sửa source/prompt/criteria/notebook đã đóng băng trong audit.

## 1. Kết quả đã xác minh

| Mục | Kết quả |
| --- | --- |
| ZIP CRC/output manifest |Đạt:54/54 file +manifest,55 files tổng |
| Input/frozen source |69/69 input files và26/26 source khớp |
| Human admission |Đạt, reviewer tricong; đúng probe/review hashes |
| Model/runtime |Qwen2.5-3B-Instruct pinned revision/NF4/float16/seed42; Tesla T4, torch2.10.0+cu128, CUDA12.8 |
| Regression/hai validate-only |101/101 đạt; probe18/max36calls và verifier39/max312calls đạt |
| Full stage |exit124, `process_timeout`,5.400,867 giây |
| Saved predictions |22/39; replay22/22 khớp source frozen |
| Decisions hoàn tất |1; goldsupport nhưng candidateNEI ở contract:cross_sentence |
| Incomplete saved rows |21; không tính là nhãn NEI đúng |
| Nhãn đúng trong22 rows |0; chưa phải accuracy của đủ39 |
| False support phần đã lưu |0, nhưng số quyết định support cũng bằng0 |
| False support toàn39 |Chưa kết luận:17 ca không có prediction |
| Trace |68started/67generation/67finished; call68 chưa hoàn tất |
| Known tokens của67 calls hoàn tất |50.237 generated/65.850 prompt; token tổng còn thiếu call68 |
| Token cap |27/67 generations chạm1.536tokens, cả27 JSON chưa đóng |
| Deadline theo ca |17/22 rows mất hơn180 giây; deadline hiện là cooperative |
| Gate |false; chưa human evidence review39, chưa step2 hoặc production pass |

`runtime_failed_rows=21` trong partial score nghĩa là không có aggregate label,
không có nghĩa21 lần process crash. Hai stop reasons của21 rows này là7
`deadline_exceeded` và14 `invalid_output_exhausted`. Tất cả22 decompositions
giống chính xác các plan probe đã được human review; lỗi xuất hiện ở assessment.

ZIP nguồn SHA256:
`8507b6d8efba875882a5fe07a5f7a5dc1cf9fac7df7f5bcda6274e3774f9333a`.
Criteria SHA256:
`3e9a61616903e99f3c767e45c2ba361b44f6ea6c65732598ac3166b6cf23af7f`.
Predictions SHA256:
`167a7bf18a1142eb8b01b1d1eac9b9e4f5c9e84376962f0b9902982d2c6aabbd`.

Recorded weight/tokenizer hashes và runtime pairing khớp baseline. ZIP không có
weight bytes, nên không hash lại GPU weights trực tiếp tại local. CostUSD chưa đo.

## 2. Vì sao68 calls nhưng22 predictions chỉ có65 calls

65 calls thuộc22 rows đã flush. Case23 `scope:entity:contradict` có call66
decomposition hợp lệ và call67 assessment JSON chưa đóng. Call68 là repair đang
chạy khi worker bị kill; case23 chưa kịp ghi prediction. Còn16 ca chưa bắt đầu.
Không suy diễn label hoặc tokens của call68. `trace_truncated_tail=false` chỉ
nghĩa JSONL không có dòng bị cắt, không có nghĩa mọi started call đã kết thúc.

## 3. Nguyên nhân có bằng chứng

### 3.1 Chuỗi assessment không có giới hạn và output bị cắt giữa JSON

[atomic_decoding.py](../04_factchecker/inference/atomic_decoding.py) dùng TEXT
không maxLength cho explanation/member/quotes/operand.value. Schema assessment
không nhận context để giới hạn các field evidence theo source. Một prefix JSON
vẫn có thể hợp schema trong khi model tiếp tục lặp trong string đến hết token cap.

27 generations đều dừng ở1.536 tokens và báo unterminated string;21 trong27
xác định được string đang mở là explanation. Ví dụ call2 lặp lời giải thích
memory, call5 lặp lại instruction numeric. Đây không phải JSON sai schema root
như bug6 cũ, mà JSON chưa sinh xong. Guard không cho output này thành nhãn.

### 3.2 Model chép claim hoặc annotation thành evidence

Call14 (`contract:irrelevant`) đưa `Model Juniper retains 94% accuracy` vào
evidence dù context chỉ nói benchmark ngàyTuesday và không báo accuracy.
Call46/47 thêm claim và ký tự1 vào quote; call58/59 thêm scope annotation vào
member/quote; call64/65 đổi `the North...` thành `The North...` không có nguyên
chuỗi trong context. `quote_membership` chặn đúng cả7 outputs được validate.
Không nới membership hoặc tự sửa quote sau generation để làm chúng pass.

Operand.value còn cho phép arbitrary string: các draft dùng `faster/slower`,
`two/one` hoặc lời văn nhân quả thay decimal string. Cần ràng schema/repair phù
hợp với executable numeric contract; cấu trúc JSON đơn thuần chưa đủ.

### 3.3 Thiếu numeric không được repair, còn mô hình nhầm semantics

`contract:cross_sentence`: context nêu four models và two datasets, model khai
truth=true nhưng numeric=null. Code hạ truth xuống unknown với
`numeric_tool_required`, trả NEI và coi assessment hợp lệ; không yêu cầu repair.
Goldsupport nên đây là ca completed sai. Numeric requirements đã được code tạo
đủ; model chưa cung cấp hai proof records như contract yêu cầu.

`contract:both_supported` hai lần `numeric_evidence_not_cited`: source_quote
dài hơn observation.quotes. Ngoài ra dùng kindchange với hai operand cùng25%
không biểu diễn đúng reported reduction. Draft `none:support` còn gán
truth=true cho positive predicate leaked khi context nói no leaks; draft negation
đánh sai scope_match. Các draft này chưa thành quyết định hợp lệ. Cần kiểm bằng
model thật trên một smoke set assessment có support/contradict/NEI và all/some/none.

### 3.4 Một regression giữa full-predicate metric và numeric binding

Đã dựng **hai fixture offline riêng**, không sửa model output hoặc chấm chúng
như predictions mới. [Chi tiết fixture](atomic-verifier-v7-assessment-witnesses-20261016T071213Z-7c8c33c6.json).

- Với atomic_support, proof đúng là `The final sample contained exactly 240 documents.`.
  Numeric checker trả true/exact_value_comparison cho240/documents. Nhưng
  assess_part đòi nguyên metric `contained 240 documents` xuất hiện trong proof;
  từ exactly chen giữa làm nó đổi true thành unknown/numeric_metric_binding_unresolved
  và trả NEI. Sửa metric đầy đủ ở v7 làm lộ chỗ binding vẫn coi metric như tên
  property phải hiện nguyên chuỗi.
- Với wrong_units, proof nói `Training took 12 hours, not 12 seconds.` và
  model-truth fixture=false. Numeric checker trả unknown/qualified_numeric_evidence
  vì not; lớp binding lại thiếu nguyên `took 12 seconds`. Kết quả NEI dù frozen
  case yêu cầu contradict từ phủ định tường minh. Cần xử lý explicit denial riêng,
  không suy ra contradiction chỉ vì hai unit khác nhau và không bỏ guard chống
  ghép đại lượng/chủ thể sai.

Hai ca GPU thực tế đều dừng sớm vì JSON/deadline; fixture minh chứng thêm lỗi
code/contract sẽ còn tồn tại ngay cả khi sửa riêng generation. Chưa khẳng định
mọi output khác đều không thể pass.

### 3.5 Deadline chưa hủy generation đang chạy

[Hàm invoke bên trong AtomicVerifier.verify](../04_factchecker/inference/atomic_verifier.py) kiểm
clock trước call và sau khi generate_json trả thành công. Nó không hủy call
blocking; nhánh ModelOutputError còn continue mà không kiểm deadline ngay sau
lỗi cuối. Vì vậy có ca mất khoảng330 giây dù cấu hình180, và một số ca quá hạn
vẫn ghi stop invalid_output_exhausted. Hard worker5400 giây đã dừng run đúng.
Cần truyền remaining deadline vào cơ chế dừng generation thực sự và giữ đúng
stop reason/logging ở cả nhánh thành công/lỗi; tăng process timeout không giải
quyết được các output đang sai này.

## 4. Trạng thái đủ39 ca

| ID | Gold frozen | Nhãn candidate | Trạng thái | Calls đã bắt đầu | Giây/ca đã lưu |
| --- | --- | --- | --- | ---: | ---: |
| contract:partial_accuracy | not_enough_info | — | deadline_exceeded | 3 | 191.307 |
| contract:partial_memory | not_enough_info | — | invalid_output_exhausted | 3 | 316.122 |
| contract:both_supported | support | — | invalid_output_exhausted | 3 | 105.522 |
| contract:accuracy_conflict | contradict | — | invalid_output_exhausted | 3 | 329.166 |
| contract:irrelevant | not_enough_info | — | invalid_output_exhausted | 3 | 191.487 |
| contract:negation | contradict | — | deadline_exceeded | 3 | 189.528 |
| contract:causality_missing | not_enough_info | — | deadline_exceeded | 3 | 233.119 |
| contract:scope | contradict | — | invalid_output_exhausted | 3 | 329.531 |
| contract:cross_sentence | support | not_enough_info | completed | 2 | 22.033 |
| contract:wrong_units | contradict | — | invalid_output_exhausted | 3 | 326.518 |
| contract:atomic_support | support | — | deadline_exceeded | 3 | 217.601 |
| contract:bounded_scope | support | — | invalid_output_exhausted | 3 | 330.328 |
| scope:universal:support | support | — | invalid_output_exhausted | 3 | 330.946 |
| scope:universal:contradict | contradict | — | deadline_exceeded | 3 | 189.406 |
| scope:universal:not_enough_info | not_enough_info | — | invalid_output_exhausted | 3 | 330.815 |
| scope:existential:support | support | — | invalid_output_exhausted | 3 | 140.645 |
| scope:existential:contradict | contradict | — | invalid_output_exhausted | 3 | 317.092 |
| scope:existential:not_enough_info | not_enough_info | — | deadline_exceeded | 3 | 187.521 |
| scope:none:support | support | — | deadline_exceeded | 3 | 226.227 |
| scope:none:contradict | contradict | — | invalid_output_exhausted | 3 | 112.420 |
| scope:none:not_enough_info | not_enough_info | — | invalid_output_exhausted | 3 | 334.216 |
| scope:entity:support | support | — | invalid_output_exhausted | 3 | 54.077 |
| scope:entity:contradict | contradict | — | inflight_no_prediction | 3 | — |
| scope:entity:not_enough_info | not_enough_info | — | not_started_no_output | 0 | — |
| scope:time:support | support | — | not_started_no_output | 0 | — |
| scope:time:contradict | contradict | — | not_started_no_output | 0 | — |
| scope:time:not_enough_info | not_enough_info | — | not_started_no_output | 0 | — |
| scope:direction:support | support | — | not_started_no_output | 0 | — |
| scope:direction:contradict | contradict | — | not_started_no_output | 0 | — |
| scope:direction:not_enough_info | not_enough_info | — | not_started_no_output | 0 | — |
| scope:metric:support | support | — | not_started_no_output | 0 | — |
| scope:metric:contradict | contradict | — | not_started_no_output | 0 | — |
| scope:metric:not_enough_info | not_enough_info | — | not_started_no_output | 0 | — |
| scope:conjunction:support | support | — | not_started_no_output | 0 | — |
| scope:conjunction:contradict | contradict | — | not_started_no_output | 0 | — |
| scope:conjunction:not_enough_info | not_enough_info | — | not_started_no_output | 0 | — |
| scope:condition:support | support | — | not_started_no_output | 0 | — |
| scope:condition:contradict | contradict | — | not_started_no_output | 0 | — |
| scope:condition:not_enough_info | not_enough_info | — | not_started_no_output | 0 | — |

Gold là nhãn development đã đóng băng, không được đưa vào model requests.
Dấu— là chưa có aggregate label, không phải NEI.16 ca not_started không có
evidence output; không được đánh dấu review/pass hoặc tự bổ sung nhãn.

## 5. Review phần evidence hiện có

**contract:partial_accuracy:** Context chỉ hỗ trợ memory, thiếu accuracy94%; nhãn đúng của cả claim là NEI. Pipeline dừng ở assessment memory nên không có quyết định hợp lệ, không được tính incomplete là NEI đúng.

**contract:partial_memory:** Context chỉ có accuracy94%, không có memory25%. Draft dùng câu memory từ claim làm evidence rồi lặp explanation; JSON không đóng. Chưa đánh giá được part accuracy.

**contract:both_supported:** Context hỗ trợ cả memory25% và accuracy94%. Cả hai assessment memory bị numeric_evidence_not_cited: source_quote có Compared with the baseline nhưng quotes ngắn hơn. kind=change với hai operand cùng25% cũng chưa biểu diễn đúng reported reduction. Không có nhãn cuối.

**contract:accuracy_conflict:** Context ghi memory giảm25% và accuracy81%, not94%; đủ phản bác claimAND. Pipeline mắc JSON ở part memory nên chưa tới part accuracy và không đưa ra contradict.

**contract:irrelevant:** Context không nêu Juniper/accuracy. Call14 tự chép Model Juniper retains94% từ claim vào evidence; quote_membership chặn đúng. Repair sau đó hết tokens.

**contract:negation:** Context phủ định rõ used human labels. Repair JSON call18 đặt scope_match=mismatched dù đúng chủ thể và predicate, còn bị loại vì quá deadline. Cần phân biệt phủ định với sai scope.

**contract:causality_missing:** Context chỉ nói đồng thời index và latency, chủ động nói chưa xác lập nhân quả; goldNEI. Draft call21 gán numeric cho causal relationship, operand là chuỗi chữ, còn dùng member không có trong context. Output quá deadline nên không được chấp nhận.

**contract:scope:** Một task giảm accuracy là phản ví dụ cho all tasks improved. Hai assessment không đóng JSON; chưa có quyết định contradict.

**contract:cross_sentence:** Context có four models và two datasets ở hai câu. Model khai truth=true nhưng numeric=null. Code hạ xuống unknown/numeric_tool_required và trả NEI; đây là ca duy nhất completed và sai goldsupport. Thiếu numeric không đi vào repair vì assessment vẫn được coi hợp lệ.

**contract:wrong_units:** Context nói12hours, not12seconds, goldcontradict. Run thực dừng vì JSON. Fixture offline riêng còn cho thấy numeric checker dè dặt với not và lớp binding tìm nguyên took12seconds không có trong proof; chưa được dùng fixture như model output.

**contract:atomic_support:** Context đúng là The final sample contained exactly240 documents. Repair call32 bịa member/quote thiếu final/exactly, còn quá deadline. Fixture offline dùng proof/operand đúng vẫn bị numeric_metric_binding_unresolved: full predicate contained240documents không xuất hiện nguyên chuỗi vì có exactly.

**contract:bounded_scope:** Context hỗ trợ method cải thiện recall trên đúng tested dataset; không cần kết quả dataset khác. Hai assessment hết tokens trong JSON; chưa có support.

**scope:universal:support:** Context liệt kê đầy đủ3shards và nói mỗi shard cải thiện recall sau revision, goldsupport. Hai assessment không đóng JSON; chưa có ledger hợp lệ.

**scope:universal:contradict:** Hai shard cải thiện, shard thứ3xấu đi là phản ví dụ all. Draft repair chọn truth=false nhưng numeric.value là two/one dạng chữ và quotes rỗng; quá deadline. Cần truth predicate và numeric schema nhất quán.

**scope:universal:not_enough_info:** Chỉ biết hai shards cải thiện và không có toàn bộ population; goldNEI. Hai assessment không đóng JSON; không có decision hợp lệ.

**scope:existential:support:** Birch nhanh hơn sau patch là witness cho some; Elm/Fir chậm không bác some. Hai draft thêm claim và ký tự1 vào evidence quote, operand numeric lại là faster/slower; quote_membership từ chối đúng.

**scope:existential:contradict:** Tập audited đầy đủBirch/Elm/Fir, không node nào giảm response time; goldcontradict. Hai assessment không đóng JSON.

**scope:existential:not_enough_info:** Elm tăng response time, các node khác chưa báo cáo nên chưa đủ bác hoặc chứng minh some; goldNEI. Repair call53 chép chính claim làm quote và gán truth=true, nhưng kết quả quá deadline nên không có quyết định.

**scope:none:support:** Context báo rõ không pump nào leak trong toàn bộ3pumps; goldsupport cho none. Draft call56 dùng truth=true cho positive leaked, còn chèn claim vào member/quotes và tạo numeric change không liên quan. Quá deadline; không phải evidence hợp lệ.

**scope:none:contradict:** Silver leaked là witness phản bác none; goldcontradict. Draft truth=true có thể phù hợp positive leaked, nhưng member/quotes chèn scope annotation ngoài context. Cả hai bị quote_membership.

**scope:none:not_enough_info:** Blue/Green không leak nhưng Silver chưa biết; goldNEI. Hai assessment không đóng JSON; chưa có ledger hợp lệ.

**scope:entity:support:** Context North giảm error rate sau calibration, South tăng; goldsupport cho North. Hai draft copy The North... trong khi source là the North... sau comma, sai capitalization exact-span; quote_membership chặn đúng.

**scope:entity:contradict:** Case23 chưa có prediction: decomposition call66 hợp lệ, assessment call67 không đóngJSON và repair call68 đang chạy khi process bị kill. Context North tăng còn South giảm, nên cần đánh giá đúng chủ thể trước contradict; chưa có kết quả để review.

[Review JSONL đủ39 trạng thái](atomic-verifier-v7-evidence-review-20261016T071213Z-7c8c33c6.jsonl)
ghi context, raw observation truths, numeric presence và các span không có trong
context cho mọi assessment JSON đã đóng. Đây là AI review, không human sign39.
[Audit máy đọc được](atomic-verifier-v7-full39-audit-20261016T071213Z-7c8c33c6.json).

## 6. Hướng sửa tiếp theo

1. Snapshot v7 source/prompt/contract/criteria/notebooks, probe/human review và
   cả run39 này trước khi thay đổi. Giữ v5/v6 snapshots.
2. Candidate v8: giới hạn text trong assessment; ràng source spans và decimal
   operands; prompt có ví dụ ngắn cho đúng numeric, missing evidence và positive
   predicate của none. Giữ các guard source membership và đủ mọi requirement.
3. Sửa quantity/entity/metric binding cho full predicate và evidence có từ chen
   giữa/paraphrase được hỗ trợ; xử lý explicit numeric denial theo contract mới.
   Regression phải chứng minh không tạo false support từ số của đối tượng khác.
4. Cho lỗi thiếu numeric bắt buộc hoặc quote/citation sai đi vào repair hữu hạn
   với lỗi cụ thể; unknown có lý do thiếu evidence vẫn được phép. Bổ sung hủy
   generation theo thời gian còn lại và test nhánh ModelOutputError quá hạn.
5. Regression từ raw trace thật và câu mới đạt rồi mới freeze đồng bộ. Chạy
   decomposition probe theo frozen protocol và một assessment smoke probe nhỏ
   trước full39; giữ model/revision/data/budgets để đánh giá đúng thay đổi.

Chưa triển khai v8 trong lượt kiểm ZIP này. Không có lệnh resume trong CLI v7;
dòng stderr gợi ý resume là thông báo chung, không phải tính năng đã có của
runner này. Chạy tiếp17 ca cũng không khắc phục21 rows đang incomplete.
**Bước2 chưa hoàn tất, candidate v7 chưa đạt gate full39, chưa promotion serving.**
