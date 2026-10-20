# Kiểm tra ZIP assessment-smoke cellfix2

**Kết luận: artifact nhất quán và replay được, nhưng candidate chưa đạt smoke.**
Kết quả là **8/12 nhãn đúng**, **0 false support**, **2 ca incomplete** và **2/4 ca gold support bị trả NEI**.
`automated_gate_pass=false`, `overall_pass=false`, `promoted_to_serving=false` là kết luận đúng.
Không chạy tiếp probe18/full39 hoặc đánh dấu Ready từ kết quả này.

ZIP gốc: `C:\Users\dellcuatri142\Downloads\output-cellfix2-20261017T085227Z-e0a1ba82.zip`.
Run ID: `20261017T085227Z-e0a1ba82`.
SHA-256 ZIP: `70ad8c8ba6376b14ac29d3daee53aabc6e76dc7a2fdc7ca631e5f30cf9ea92fe`.
SHA-256 criteria: `a31549bda8776f6a566689c59378e5c47092faf6000d4597ef7ab82fdafa197b`.

**Những phần đã kiểm chứng**

- ZIP có 24 file, không trùng đường dẫn; CRC đạt; toàn bộ 23 file được liệt kê trong output manifest khớp kích thước và hash.
- Tái dựng 75 file đầu vào từ artifact phát hành/cell đã gửi, rồi đối chiếu từng byte với input manifest. Cả 75 file khớp; không chỉ so metadata tự khai báo trong ZIP.
- `load_frozen()` thực sự đạt trên workspace tái dựng: 30 source/fixture file, prompt, contract, corpus, baseline và cấu hình gate khớp hash.
- Criteria cha đúng cellfix1: `11cfd5668bb6b5ee80e3d3e0e5618683f31969be1b21760f776b2cca6d5610d4`.
- Model/revision/data/budget giữ nguyên so với cellfix1. Model được ghi nhận: Qwen/Qwen2.5-3B-Instruct, revision `aa8e72537993ba99e69dfaafa59ed015b17504d1`, Tesla T4, NF4, float16, seed 42, `do_sample=false`.
- Model files, shared tokenizer, repo/revision, dtype, quantization, seed và sampling metadata khớp baseline ở cả tám phép đối chiếu. Đây là kiểm tra metadata/hash đã ghi, không phải một lần tải và hash lại weights trên máy Colab.
- Log Colab ghi nhận **135 test đạt** và validate-only `freeze_valid=true`, 12 case, tối đa 96 call.
- Replay offline đủ 12 kết quả từ output thô, qua chính validator/aggregator của source đã khớp hash. Tái tính toàn bộ metrics được đúng bằng metrics trong ZIP.
- Đối chiếu đủ 30 bộ `call_started` / `generation` / `call_finished`: case ID, call ID, messages, output đã parse và trace khớp nhau. Cả 30 raw output parse JSON thành công.
- Tái tính cả 30 schema hash và kiểm tra decoder/deadline metadata đều đạt. Không có ca hết deadline trong lần chạy này; điều đó không chứng minh mọi tình huống deadline đều an toàn.
- Kiểm tra 27 lần trích dẫn trong observations đều nguyên văn trong context. Cả 18 numeric record đều có nguồn/operand nằm trong văn bản tương ứng. **Có mặt trong nguồn chưa chứng minh gắn đúng entity/metric**; lỗi association vẫn tồn tại như các ca dưới đây.
- Các dòng evidence-review khớp case/prediction; toàn bộ vẫn `pending`, chưa có người ký review. Bản rà soát này là kiểm tra kỹ thuật của trợ lý, không thay chữ ký human review.

Không thay đổi source đang dùng, predictions, gold, budget hoặc ZIP gốc trong quá trình kiểm tra. Các phép thử chẩn đoán dùng bản sao trong bộ nhớ và không được tính lại thành điểm của candidate.

**So sánh đúng phạm vi**

| Chỉ số smoke 12 ca | Cellfix1 | Cellfix2 |
| --- | ---: | ---: |
| Nhãn đúng trên toàn bộ 12 ca | 1 | 8 |
| False support quan sát được | 0 | 0 |
| Incomplete / runtime_failed_rows | 9 | 2 |
| Gold support bị từ chối / 4 | 4 | 2 |
| Backend call | 35 | 30 |
| Generated token | 3.605 | 5.078 |
| Prompt token | 33.135 | 39.090 |
| Automated gate | Trượt | Trượt |

Process assessment-smoke chạy 461.244 ms, khoảng 7 phút 41 giây. Exit code 1 đến từ gate chất lượng chưa đạt; stderr assessment-smoke rỗng. Không có bằng chứng về lỗi CUDA hay thiếu dependency trong lần chạy này.
Hai ca incomplete vẫn phải tính là không đúng; không loại khỏi mẫu để báo 8/10.
Số 37/39 trong `baseline-metrics.json` là kết quả baseline lịch sử, không phải kết quả full39 của cellfix2.

**Review cả 12 ca**

`S` = support; `C` = contradict; `NEI` = not_enough_info; `incomplete` không có nhãn.

| Case | Gold | Candidate | Kết luận và bằng chứng |
| --- | --- | --- | --- |
| partial_accuracy | NEI | NEI | Đúng nhãn: chỉ có bằng chứng giảm 25% memory, không có 94% accuracy. Tuy vậy model explanation nói accuracy bị memory improvement “contradicted”; cách giải thích này sai nghĩa. |
| partial_memory | NEI | incomplete | Trượt: cả hai assessment attempt của part memory lặp cùng member `Model Juniper`, trả đồng thời true/false và ghép 25% memory với 94% accuracy. Validator từ chối `observation_identity_or_truth`. |
| both_supported | S | NEI | Sai nhãn: nguồn xác nhận cả 25% memory và 94% accuracy. Model thêm `baseline: unknown` vào từng atomic part; tập truth có true và unknown nên aggregator trả NEI. Claim không đòi phần trăm riêng của baseline. |
| accuracy_conflict | C | incomplete | Trượt: part accuracy lặp member ở cả hai attempt. Part memory còn bị nhiễm phủ định của vế accuracy; xem chẩn đoán chi tiết bên dưới. |
| irrelevant | NEI | NEI | Đúng nhãn: nguồn không báo accuracy. `scope_match=matched` vẫn quá mạnh khi nguồn không nêu Model Juniper; nhãn NEI không chứng minh scope judgment đã đúng. |
| negation | C | C | Đúng: nguồn phủ định rõ việc dùng human labels, cùng subject study. |
| causality_missing | NEI | NEI | Đúng sau repair: attempt đầu định support từ đồng xuất hiện và bị `causal_relation_not_grounded` chặn; attempt sau trả unknown. Guard có tác dụng trên trace này. |
| scope | C | C | Đúng: `a fourth task became less accurate` là phản ví dụ cho ALL. Không cần biết toàn bộ population để bác bỏ ALL. |
| cross_sentence | S | NEI | Sai nhãn: hai câu cung cấp four models và two datasets. Model gắn yêu cầu two datasets với `Four models` trong câu đầu; validator hạ unknown với `numeric_metric_binding_unresolved`. |
| wrong_units | C | C | Đúng: `12 hours, not 12 seconds` phủ định rõ claimed quantity; numeric checker trả `explicit_quantity_denial`. Không có chuyển đổi đơn vị ngầm. |
| atomic_support | S | S | Đúng: nguồn nêu exactly 240 documents, phép kiểm 240 = 240 hợp lệ. Có hai observation alias `The final sample` và `sample` cho cùng đối tượng; còn dư thừa nhưng không đổi nhãn ca này. |
| bounded_scope | S | S | Đúng: chỉ xác nhận recall trên tested dataset; câu “other datasets are unknown” không phủ định scope được claim giới hạn. |

Tám nhãn cuối đúng không đồng nghĩa mọi explanation, observation hoặc scope decision đều đúng. Đây vẫn là 12 ca synthetic đã được dùng phát triển, không phải tập đánh giá độc lập.

**Nguyên nhân còn lại đã được chứng minh**

1. **Identity của observation chưa được ràng buộc đủ trong decoder/repair.**
   Decoder cho tối đa hai observation cho atomic part; validator chỉ bắt trùng chuỗi member sau generation.
   `assess_part()` trong `04_factchecker/inference/atomic_verifier.py` từ chối member xuất hiện lần hai bằng `observation_identity_or_truth`.
   Có bốn lần từ chối, nằm ở hai attempt của partial_memory và hai attempt part accuracy của accuracy_conflict.
   Không nên bỏ validator này hoặc tự xóa observation trùng: có trace true/false mâu thuẫn nhau.

2. **Observation ngoài subject đang xét làm hỏng quyết định atomic.**
   Trong both_supported, mỗi part đã có observation đúng và numeric check đúng, nhưng có thêm baseline unknown.
   Nhánh atomic chỉ support khi tập truth chính xác là `{true}` và không thiếu thông tin.
   Không được sửa aggregator thành “có một true là support”: như vậy sẽ bỏ qua evidence mâu thuẫn/unknown thực sự trong scope.
   Cần giữ observation đúng target của part và giữ nhiều trích dẫn/numeric requirement bên trong cùng assessment phù hợp.

3. **Binding từng requirement qua nhiều câu vẫn sai.**
   cross_sentence thực sự có đủ hai requirement, nhưng record cho datasets lấy right operand `4 models`.
   Kiểm tra code đã chặn bằng `numeric_metric_binding_unresolved`, nên đây là false negative, chưa phải false support.
   Assessment vẫn được coi hợp lệ về cấu trúc và trả NEI, vì vậy lỗi binding dạng này không tự đi qua repair như lỗi schema.
   Cần feedback/repair có giới hạn cho lỗi binding có thể khôi phục, đồng thời giữ unknown hợp lệ khi thật sự thiếu bằng chứng.

4. **Numeric checker áp từ phủ định của cả source_quote lên một phép kiểm riêng.**
   Trong part memory của accuracy_conflict, record 25% = 25% dùng source_quote toàn câu chứa `not 94%` ở vế accuracy.
   `check_numeric()` trong `numeric_verifier.py` trả `qualified_numeric_evidence` trước phép so sánh, do quét `not` trên toàn proof.
   Phép thử chẩn đoán với cùng operand và cùng claim, chỉ thu hẹp source_quote về đoạn nguyên văn `Model Juniper uses 25% less memory`, trả `exact_value_comparison`.
   Cần localize scope phủ định theo measurement/predicate; không được bỏ toàn bộ negation guard.

5. **Mẫu phủ định quantity chưa bao phủ metric nằm giữa số và “not”.**
   Phép thử chẩn đoán giữ một observation đúng của part accuracy vẫn trả NEI với `qualified_numeric_evidence`.
   Regex phủ định quantity đang nhận dạng dạng `observed_quantity, not claimed_quantity`; ở đây là `81% accuracy, not 94%`, có từ `accuracy` ở giữa.
   Vì vậy sửa duplicate member thôi chưa đủ làm accuracy_conflict đúng.
   Khi mở rộng grammar phải giữ binding đúng metric, chặn modality/approximation và tránh phủ định từ vế khác.

Những phép thử trên không phải prediction mới từ model, không phải một lần chạy smoke khác, và không được dùng để ghi 10/12 hay 12/12.

**Đi tiếp theo thứ tự này**

1. Giữ ZIP, predictions và candidate cellfix2 hiện tại. Không sửa gold hoặc hạ gate.
2. Sửa chung ở identity/target của observation, binding mỗi requirement, scope phủ định và grammar quantity denial. Chưa có patch runtime mới trong lần audit này.
3. Regression cần có trace thật và câu mới về cùng kiểu lỗi, gồm cả evidence mâu thuẫn, thiếu metric, trùng alias, nhiều measurement cùng đơn vị, hai câu bổ sung và vế phủ định không liên quan. Không hard-code ID/câu để đạt smoke.
4. Giữ riêng một bộ ca mới chưa dùng để sửa; chạy sau khi chốt candidate để kiểm tra khả năng tổng quát hóa. Nếu dùng kết quả bộ mới để sửa tiếp, bộ đó trở thành development data và phải thay tập đánh giá độc lập.
5. Chạy regression/validate-only, rồi smoke 12/12 không incomplete và không false support với cùng model/revision/budget. Sau đó probe18 và human review mới gắn đúng candidate; chỉ khi đạt mới chạy full39.
6. Full39 phải báo riêng đúng nhãn, false support, incomplete và supported-claim rejection. Chỉ sau khi gate này đạt mới tiếp tục quyết định tích hợp Reader/Summarizer và đo E2E.

Chi tiết máy đọc được nằm trong `atomic-verifier-cellfix2-smoke-audit-20261017T085227Z-e0a1ba82.json` cùng thư mục.
Không chạy thêm Qwen/GPU trong audit này; chưa có probe18, full39 hoặc Reader/Summarizer E2E cho cellfix2 trong ZIP.
