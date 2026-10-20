# Probe v7: 18/18 đạt; human admission hoàn tất, sẵn sàng đánh giá39

Run `20261016T024708Z-a57ee72a` trên Tesla T4. Đã kiểm toàn vẹn ZIP/provenance, replay
18 predictions và review20 parts. **18/18 structural pass, 18 calls, không
repair hoặc lỗi runtime.** Human reviewer **tricong** đã xác nhận cả18 ca đạt
cả năm tiêu chí, đã đọc lưu ý010/014/018; `require_probe_review` chấp nhận.
**Chưa chạy model bộ39; false support chưa đo; chưa kết luận dự án đạt production.**

## Toàn vẹn và số đo

| Mục | Kết quả |
| --- | --- |
| ZIP CRC/output manifest | Đạt,39/39 file và manifest là40 files |
| Input manifest/source |69/69 payload files và26/26 frozen sources khớp |
| Criteria | `3e9a61616903e99f3c767e45c2ba361b44f6ea6c65732598ac3166b6cf23af7f` |
| Model |Qwen/Qwen2.5-3B-Instruct, revision aa8e72537993ba99e69dfaafa59ed015b17504d1 |
| Pairing | Recorded weights/tokenizer hashes, NF4/float16, seed42 và do_sample=false khớp baseline |
| Runtime |Tesla T4; torch2.10.0+cu128, CUDA12.8; Transformers5.16.1, LMFE0.11.3 |
| Colab regression |101/101 đạt; unittest2,393 giây |
| Hai validate-only |Đạt:18/max36 calls và39/max312 calls |
| Replay/trace |18 predictions,18 calls,54 events; raw JSON/parsed output/messages/schema SHA khớp |
| Thành công attempt1 |18/18;0 repair;0 validation failures |
| Tokens |976 generated;22.892 prompt; max117 generated/call, dưới cap1.536 |
| Runner/outer stage |220,913 giây/226,865 giây; trong deadline |
| Original summary |Automated pass; human pending vì file được tạo trước lần review trong chat |
| Admission sau human review |Đạt, reviewer tricong; bản review riêng gắn đúng hashes |

ZIP SHA256: `9501567f9efe425c9d8ed61a416f58a92ccac75bc44afef7c04e71b1eead590f`.
Weights GPU không có trong ZIP: audit so các hash được ghi nhận với frozen
baseline, không hash lại trực tiếp remote weights ở local. Các token count và
thời gian tính từ trace/log; USD chưa đo. Probe không gọi assessment, không có
context/gold labels trong requests; không có accuracy hoặc false-support rate.

## Review đủ18 claim và20 parts

Năm tiêu chí semantic: factual predicate đầy đủ; giữ mọi yêu cầu; đúng lượng từ;
đúng entity/metric binding; đúng time/condition scope. AI review18/18 đạt năm
tiêu chí; human reviewer đã đọc và xác nhận riêng trên form trước admission.

| ID/part | Exact quote | Quantifier | Entity | Metric | Time | Condition | Số liệu |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 001/1 | Model Juniper uses 25% less memory | atomic | Model Juniper | memory | — | — | 25% → 25/% |
| 001/2 | and retains 94% accuracy. | atomic | Model Juniper | accuracy | — | — | 94% → 94/% |
| 002/1 | Model Juniper retains 94% accuracy. | atomic | Model Juniper | accuracy | — | — | 94% → 94/% |
| 003/1 | The study used human labels. | atomic | study | used human labels | — | — | — |
| 004/1 | The new index caused the latency improvement. | atomic | new index | latency | — | — | — |
| 005/1 | All tasks improved after compression. | all | tasks | improved | after compression | — | — |
| 006/1 | The report evaluated four models on two datasets. | atomic | report | evaluated four models | — | on two datasets | four models → 4/models, two datasets → 2/datasets |
| 007/1 | Training took 12 seconds. | atomic | Training | took 12 seconds | — | — | 12 seconds → 12/seconds |
| 008/1 | The sample contained 240 documents. | atomic | sample | contained 240 documents | — | — | 240 documents → 240/documents |
| 009/1 | On the tested dataset, the method improved recall. | atomic | method | recall | — | On the tested dataset | — |
| 010/1 | Every validation shard improved recall after the revision. | all | validation shard | improved recall | after the revision | — | — |
| 011/1 | At least one audited cache node reduced response time after the patch. | some | audited cache node | response time | after the patch | — | — |
| 012/1 | None of the monitored pumps leaked during the overnight test. | none | monitored pumps | leaked | during the overnight test | — | — |
| 013/1 | The North gateway reduced its error rate after calibration. | atomic | North gateway | error rate | after calibration | — | — |
| 014/1 | Every weekly trial conducted in May improved throughput. | all | weekly trial | improved throughput | — | in May | — |
| 015/1 | The patch reduced median request latency. | atomic | patch | median request latency | — | — | — |
| 016/1 | The configuration change increased precision. | atomic | configuration change | precision | — | — | — |
| 017/1 | After tuning, the extractor decreased memory use | atomic | extractor | memory use | After tuning | — | — |
| 017/2 | and increased token recall. | atomic | extractor | token recall | After tuning | — | — |
| 018/1 | Every batch in the low-temperature group gained yield after the update. | all | batch | gained yield | after the update | in the low-temperature group | — |

**001:** Giữ chủ thể Model Juniper, property memory và hướng giảm 25%; numeric requirement 25% còn nguyên. Chưa có evidence để xác nhận baseline hay phép tính phần trăm. Tách riêng retains 94% accuracy; kế thừa đúng Model Juniper trong entity. AND đầu quote là connector được contract cho phép; không ghép accuracy với memory.

**002:** Một factual predicate đầy đủ: Model Juniper giữ accuracy 94%; metric accuracy, quantifier atomic và requirement 94% đúng.

**003:** Quote giữ nguyên quan hệ study used human labels; metric dùng full predicate used human labels, không còn chỉ động từ used. Không thêm phủ định hoặc lượng từ.

**004:** Giữ chủ thể new index, property latency và quan hệ caused trong quote. Decomposition không biến nhân quả thành tương quan; assessment sau này vẫn phải có bằng chứng nhân quả.

**005:** Giữ toàn bộ population tasks, lượng từ all và after compression. Claim không chỉ rõ một property khác ngoài improved; review không tự thêm metric vào claim.

**006:** Giữ một predicate evaluated, entity report, metric evaluated four models và condition on two datasets. Numeric requirements tách đúng 4/models và 2/datasets; không cắt dataset/count thành factual fragment. Chưa kiểm evidence của hai requirement.

**007:** Training là chủ thể; quote giữ toàn bộ Training took 12 seconds. Metric took 12 seconds giữ đủ quan hệ và thời lượng, không còn took hoặc 12 seconds đứng riêng. Requirement 12/seconds đúng; time rỗng vì đây là thời lượng đo, không phải restriction thời điểm.

**008:** Sample là chủ thể; metric contained 240 documents giữ đủ quan hệ chứa, số lượng và đối tượng. Quote đầy đủ; requirement 240/documents đúng; không thêm restriction hoặc tách quantity thành part riêng.

**009:** Entity method và property recall đúng; On the tested dataset giữ nguyên trong quote và condition. Không gán dataset thành thời gian hoặc bỏ tested.

**010:** Giữ validation shard, all, recall và after the revision. Metric improved recall vẫn chỉ đúng property recall nên binding có nghĩa đúng; riêng prompt ưu tiên recall không kèm động từ là điểm chưa đồng nhất về hình thức, không phải mất/sai metric. Metric 'improved recall' vẫn chứa đúng property 'recall' và không làm mất hướng trong quote; binding đúng theo năm rubric semantic. Tuy nhiên base prompt yêu cầu named property không kèm change verb: canonical metric nên là 'recall'. Không tuyên bố prompt-format compliance 100%; human cần đọc lưu ý này.

**011:** At least one chuyển đúng thành some; entity audited cache node giữ audited, metric response time, time after the patch. Không nâng existential thành all hoặc bỏ population modifier.

**012:** None chuyển đúng thành none; entity monitored pumps giữ monitored, metric leaked là positive predicate trước khi áp lượng từ none, time during the overnight test. Không diễn giải unknown/silence thành không rò rỉ.

**013:** Entity North gateway, metric error rate, hướng giảm trong quote và time after calibration đúng. Không đổi North thành một gateway khác.

**014:** Giữ all weekly trial, property throughput và condition in May để chọn tập trial conducted in May. Metric improved throughput vẫn chỉ đúng property, dù prompt ưu tiên throughput không kèm động từ. Không suy ra improvement xảy ra trong May; time rỗng theo schema hiện tại. Metric 'improved throughput' vẫn chứa đúng property 'throughput' và không làm mất hướng trong quote; binding đúng theo năm rubric semantic. Tuy nhiên base prompt yêu cầu named property không kèm change verb: canonical metric nên là 'throughput'. Không tuyên bố prompt-format compliance 100%; human cần đọc lưu ý này.

**015:** Giữ patch, hướng reduced và metric median request latency; không đổi median thành mean hoặc bỏ request. Không thêm thời gian chưa có trong claim.

**016:** Giữ configuration change, property precision và hướng increased trong quote; không nhầm precision với recall.

**017:** Predicate 1 giữ extractor, decreased memory use và time After tuning. Đây là prefix đứng đầu có dấu phẩy nên được dùng chung cho hai part. Predicate 2 giữ increased token recall; kế thừa đúng extractor và After tuning. Hướng tăng recall tách khỏi hướng giảm memory use; leading AND hợp lệ.

**018:** Giữ all batch, condition in the low-temperature group, property yield và time after the update. Population không bị mở rộng sang batch thuộc group khác. Metric 'gained yield' vẫn chứa đúng property 'yield' và không làm mất hướng trong quote; binding đúng theo năm rubric semantic. Tuy nhiên base prompt yêu cầu named property không kèm change verb: canonical metric nên là 'yield'. Không tuyên bố prompt-format compliance 100%; human cần đọc lưu ý này.

010/014/018 giữ đúng property nhưng metric còn kèm động từ. Base prompt ưu tiên
named property không kèm change verb, nên không tuyên bố prompt-format compliance
100%. Đây là lưu ý đã hiển thị và được human chấp nhận theo năm rubric semantic;
không sửa source, predictions hoặc criteria sau run để đổi kết quả.

## Human review và admission

Người dùng đã cung cấp tên `tricong`, rồi xác nhận trực tiếp trong chat:
“Cả 18 ca đạt cả năm tiêu chí; tôi đã đọc các lưu ý”. Ghi chú do AI đề xuất được
người review đọc và xác nhận. Bản JSON human được lưu riêng; ZIP/template gốc
pending giữ nguyên làm lịch sử. Không ký human thay người dùng trước xác nhận.

Predictions SHA256: `55d449e24056ed440ec9e6e660aea164f20a345c045dc70c5411cf2d84b747d4`.
Human review SHA256: `c01870b7f777607508055b0ee12ce44b47141960345ce8ae15babed0d4f9719f`.

[Human review](semantic-review-v7-20261016T024708Z-a57ee72a.json),
[biên bản xác nhận/admission](atomic-verifier-v7-human-admission-20261016T024708Z-a57ee72a.json),
[AI review JSONL](decomposition-semantic-review-20261016T024708Z-a57ee72a.jsonl),
[audit JSON](decomposition-probe-audit-20261016T024708Z-a57ee72a.json).

## Bước tiếp theo đã chuẩn bị

[Notebook39 Colab](../scripts/colab_atomic_verifier39_v7.ipynb) tự chứa payload
v7, ZIP probe gốc và human review đã xác nhận. Chạy bốn code cell trên runtime
T4 mới. Regression/hai validate-only/admission đều phải đạt trước model loading;
không cần chạy lại probe hoặc ký lại human review.

Đã chạy4 packaging tests mới: compile cells và chặn model stage thiếu admission;
kiểm payload/probe/review/release bytes; admission từ exact payload độc lập và
tamper guards; logic form export bằng Node với synthetic data, không tạo chữ ký
thật trong test. [Log](atomic-verifier-v7-full39-packaging-tests.log).
Không render/kiểm giao diện form trong browser; human đã xác nhận trực tiếp trong chat.

[Hướng dẫn39](ATOMIC_VERIFIER_V7_FULL39_RUN_GUIDE.md).
Gửi ZIP39 nguyên trạng để kiểm39/39 labels, zero false support/runtime failures
và review đúng evidence/coverage/numeric binding/missing information từng ca.
Các seen development cases này không chứng minh held-out generalization.
