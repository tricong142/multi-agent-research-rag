# Rà soát ZIP cellfix5 — 18/10/2026 (Asia/Saigon)

Run: `20261017T173345Z-905edcb5`. ZIP: `output-cellfix5-fresh-20261017T173345Z-905edcb5.zip`.

SHA256 ZIP: `e854d7d7276a806941b876ef1a23bc04365677caa2301cda3c9f14356dc4f1bb`.

Kết quả audit/replay đạt. Smoke đúng 12/12; probe hợp lệ về cấu trúc 18/18. AI đã đọc 18 claim/20 part và đánh giá 90/90 tiêu chí đạt. Human review cho run này chưa ký. Không chạy inference full39 trong lượt rà soát này.

## Artifact và kiểm tra tự động

| Kiểm tra | Kết quả |
| --- | --- |
| Output manifest | 62 file khớp size/hash |
| Embedded payload | 84 file đầu vào, 36 source/fixture khớp release |
| Colab regression | 181 test đạt theo log, stage exit 0 |
| Validate-only | probe18, smoke12, verifier39 đều freeze_valid=true; không phải inference39 |
| Model | Qwen/Qwen2.5-3B-Instruct, revision aa8e72537993ba99e69dfaafa59ed015b17504d1; Tesla T4 |
| Smoke12 | 12 đúng; 0 false support; 0 runtime failure; 28 call; 3577 generated tokens |
| Probe18 | 18 hợp lệ; 0 incomplete; 18 call; 972 generated tokens; label_accuracy=null |
| Raw call/trace | 46 lượt gọi đối chiếu raw JSON, prompt, schema, deadline, citation và numeric sources |
| Full39 gate | Chặn unsigned review trước model_loader; không tạo output full39 |

Criteria SHA256: `642d66612c25514e3764840f750a97cc85c93d4a32a3e4f23bcabff6b993e84c`. Payload SHA256: `922bb57ed569982785d026e365c208ef19d4fc5c104e622aa7e9e70395fcb869`.

Hash/provenance xác nhận tính nhất quán với release đã đóng băng; không phải chữ ký xác thực độc lập máy Colab.

## Review 18 claim theo từng tiêu chí

C1: factual predicate đầy đủ. C2: đủ yêu cầu/số liệu/đơn vị/quan hệ. C3: lượng từ/population. C4: chủ thể/metric. C5: scope thời gian/điều kiện. Các dấu đạt dưới đây là nhận xét của AI, không thay chữ ký human.

| Claim | C1 | C2 | C3 | C4 | C5 | Nhận xét đối chiếu output thực tế |
| --- | --- | --- | --- | --- | --- | --- |
| decompose:001 | ✓ | ✓ | ✓ | ✓ | ✓ | Hai predicate uses 25% less memory và retains 94% accuracy được tách đúng; part sau kế thừa Model Juniper. Hai metric memory/accuracy và hai requirement 25%/94% không trộn nhau; quan hệ less/retains vẫn nằm trong quote. |
| decompose:002 | ✓ | ✓ | ✓ | ✓ | ✓ | Một predicate giữ nguyên retains 94% accuracy; entity Model Juniper, metric accuracy, requirement 94%. Không tự thêm population hoặc restriction. |
| decompose:003 | ✓ | ✓ | ✓ | ✓ | ✓ | Một predicate used human labels đầy đủ cả hành động và đối tượng. Metric used human labels hợp lệ vì source không nêu một named measurement riêng. |
| decompose:004 | ✓ | ✓ | ✓ | ✓ | ✓ | Giữ nguyên causal predicate caused the latency improvement trong quote, không biến causation thành correlation. Entity new index và metric latency đúng; assessment vẫn phải kiểm quan hệ caused từ toàn bộ quote. |
| decompose:005 | ✓ | ✓ | ✓ | ✓ | ✓ | All được ánh xạ all trên population tasks; improved là predicate duy nhất source cung cấp, không tự đoán accuracy/latency. after compression giữ đúng thời gian. |
| decompose:006 | ✓ | ✓ | ✓ | ✓ | ✓ | Giữ evaluated four models và condition on two datasets. Numeric requirements gồm 4 models và 2 datasets, mỗi số có object riêng; không chỉ kiểm số 4. |
| decompose:007 | ✓ | ✓ | ✓ | ✓ | ✓ | Metric took 12 seconds giữ quan hệ thời lượng và quantity, không còn took đơn lẻ hoặc 12 seconds thiếu quan hệ. Entity Training, unit seconds đúng. |
| decompose:008 | ✓ | ✓ | ✓ | ✓ | ✓ | Metric contained 240 documents giữ quan hệ chứa và count object, không còn contained đơn lẻ. Requirement 240 documents đầy đủ. |
| decompose:009 | ✓ | ✓ | ✓ | ✓ | ✓ | Entity method, metric recall; On the tested dataset nằm ở condition, time rỗng. Không mở rộng kết luận sang dataset khác. |
| decompose:010 | ✓ | ✓ | ✓ | ✓ | ✓ | Every ánh xạ all trên validation shard; metric hiện là recall, không còn improved recall. after the revision nằm đúng time; hướng improved vẫn giữ nguyên trong quote. |
| decompose:011 | ✓ | ✓ | ✓ | ✓ | ✓ | At least one ánh xạ some; population audited cache node giữ audited. Metric response time giữ cả cụm; after the patch là time của predicate reduced. |
| decompose:012 | ✓ | ✓ | ✓ | ✓ | ✓ | None ánh xạ none trên monitored pumps; metric leaked giữ dạng dương để quantifier none mang phủ định. during the overnight test và modifier monitored được giữ. |
| decompose:013 | ✓ | ✓ | ✓ | ✓ | ✓ | Entity North gateway giữ định danh North; metric error rate không kèm reduced/its. Quan hệ reduced và time after calibration vẫn nguyên trong quote. |
| decompose:014 | ✓ | ✓ | ✓ | ✓ | ✓ | Every ánh xạ all trên weekly trial; metric throughput không còn improved throughput. condition in May lọc các trial conducted in May, không khẳng định việc cải thiện diễn ra trong May. Quote đầy đủ giữ attachment conducted in May; schema scope chưa có trường restriction-owner riêng. |
| decompose:015 | ✓ | ✓ | ✓ | ✓ | ✓ | Metric median request latency giữ cả median và request; không rút còn latency. Entity patch và hướng reduced trong quote đúng. |
| decompose:016 | ✓ | ✓ | ✓ | ✓ | ✓ | Entity configuration change đầy đủ; metric precision không lẫn với change trong subject. Hướng increased giữ trong quote. |
| decompose:017 | ✓ | ✓ | ✓ | ✓ | ✓ | Hai predicate decreased memory use và increased token recall tách đúng; part sau kế thừa extractor. After tuning là prefix chung có dấu phẩy, nên time của cả hai part đúng. Không trộn hai hướng thay đổi hoặc hai metric. |
| decompose:018 | ✓ | ✓ | ✓ | ✓ | ✓ | Every ánh xạ all; entity batch kết hợp condition in the low-temperature group giữ đúng population. Metric yield không còn gained yield; after the update là time, gained giữ nguyên trong quote. |

Không còn lỗi metric kèm change verb ở 010/014/018: lần lượt là `recall`, `throughput`, `yield`. 007 giữ `took 12 seconds`; 008 giữ `contained 240 documents`; 006 có đủ hai quantity requirement.

**Lưu ý 014:** `in May` lọc population trial conducted in May; không suy ra improvement diễn ra trong May. Kết luận C5 đạt khi đọc scope cùng quote đầy đủ. Schema chưa có trường restriction-owner; downstream không được dùng riêng condition để biến thành event time.

## Review nhãn và bằng chứng smoke12

| Ca | Gold | Code | Đối chiếu bằng chứng |
| --- | --- | --- | --- |
| contract:partial_accuracy | not_enough_info | not_enough_info | Memory 25% được chứng minh; accuracy 94% chưa có bằng chứng. |
| contract:partial_memory | not_enough_info | not_enough_info | Accuracy 94% được chứng minh; memory reduction chưa có bằng chứng. |
| contract:both_supported | support | support | Context xác nhận đồng thời memory giảm 25% và accuracy 94%. |
| contract:accuracy_conflict | contradict | contradict | Memory giảm 25% đúng; accuracy 81%, explicitly not 94%. Explanation của model lẫn part; xem lưu ý. |
| contract:irrelevant | not_enough_info | not_enough_info | Không có số accuracy của Model Juniper; mismatched/absent scope không thành support. |
| contract:negation | contradict | contradict | Explicit did not use any human labels phủ định cùng predicate. |
| contract:causality_missing | not_enough_info | not_enough_info | Cùng xuất hiện không chứng minh quan hệ caused; chưa đủ thông tin. |
| contract:scope | contradict | contradict | Một task less accurate là counterexample bác bỏ ALL. |
| contract:cross_sentence | support | support | Hai numeric checks riêng: four models và two datasets, nguồn ở hai câu cùng report. |
| contract:wrong_units | contradict | contradict | 12 hours, not 12 seconds: cùng số nhưng khác unit và có phủ định trực tiếp. |
| contract:atomic_support | support | support | Exactly 240 documents cùng sample. |
| contract:bounded_scope | support | support | Chỉ xác nhận recall trên tested dataset; không mở rộng sang dataset khác. |

## Hạn chế còn thấy

- `accuracy_conflict`: model_truth=false ở memory part và explanation nói về accuracy; code tính true cho memory 25% theo evidence. Aggregate contradict đúng, nhưng lời giải thích model chưa nhất quán. Không dùng prose này như lý do duy nhất cho quyết định; ledger tách rõ model_truth/truth.

- `cross_sentence`: ledger có đủ hai số và citation; observation prose chỉ nhắc four models, model_explanation kết thúc ở `2/`. JSON không bị cắt và gate không hỏng, nhưng chất lượng explanation chưa hoàn chỉnh.

- Smoke/probe là bộ phát triển đã dùng nhiều vòng sửa. Không chứng minh generalization hoặc zero false support trên full39. Số baseline 37/39 nằm trong ZIP là lịch sử, không phải kết quả cellfix5.

- ZIP không kiểm E2E Reader/Summarizer với verifier mới; chưa đủ cơ sở ghi toàn dự án Ready.

## Bước tiếp theo

1. Mở `docs/HUMAN_REVIEW_CELLFIX5_20261017T173345Z-905edcb5.html`, đọc output, đọc/chỉnh sửa ghi chú đề xuất đã điền cho từng ca và xác nhận riêng 90 ô; xuất semantic-review.json nếu mọi tiêu chí thực sự đạt. Tên và ô xác nhận bắt đầu trống; ghi chú có nhãn AI soạn, không kế thừa xác nhận run cũ.

2. Gửi JSON review mới để kiểm đúng predictions/criteria hash. Khi admission hợp lệ mới chuẩn bị chạy full39 trên đúng candidate này. Không cần vá tiếp ba metric 010/014/018 chỉ để chạy lại probe.

3. Full39 phải đo đủ nhãn, false_support=0 và runtime_failed_rows=0. Sau đó còn đánh giá độc lập và tích hợp/E2E theo phạm vi dự án.
