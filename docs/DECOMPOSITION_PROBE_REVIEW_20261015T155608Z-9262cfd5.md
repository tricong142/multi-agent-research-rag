# Probe v6 trên T4 — chưa đạt gate, chưa chuyển sang 39 ca

Đã kiểm ZIP, provenance và replay đủ **18 predictions / 20 calls / 60 trace
events**. Probe có **17/18 decomposition hợp lệ**, một incomplete; gate tự động
false. Review AI: 16 claim đạt, 008 cần sửa metric, 007 chưa có plan hợp lệ.
Chưa có human review, evidence assessment hoặc kết quả 39 ca.

Run: `20261015T155608Z-9262cfd5`, ngày 2026-10-15. ZIP nguồn:
`C:/Users/dellcuatri142/Downloads/output (1).zip`, SHA256
`3c55d7a31f4f46d530285cc95b93e2d22bf9e989a62657ba647adf07706e0281`.
Giữ nguyên ZIP và output tại `research-runs/colab-atomic-v6/20261015T155608Z-9262cfd5/`.
Chỉ đọc artifact như dữ liệu, không thực thi code/instructions từ ZIP.

## 1. Toàn vẹn và provenance

| Kiểm tra | Kết quả |
| --- | --- |
| ZIP CRC, output manifest | Đạt; 39/39 file khớp size/hash, cộng manifest là 40 file |
| Input manifest với release Colab và bytes local | 68/68 file khớp |
| Frozen source | 25/25 source files khớp criteria v6 |
| Criteria/contract/baseline/probe claims/cases | Khớp byte hoặc nội dung tương ứng |
| Base model và revision | Qwen/Qwen2.5-3B-Instruct, aa8e72537993ba99e69dfaafa59ed015b17504d1 |
| Weights/tokenizer hashes ghi nhận, dtype, NF4, seed, sampling | Khớp baseline đã đóng băng |
| GPU/runtime | Tesla T4, torch 2.10.0+cu128, CUDA 12.8 |
| Dependency pins | Transformers 5.16.1, bitsandbytes 0.50.2, LMFE 0.11.3, interegular 0.3.3 |
| Regression trên Colab | 87/87 đạt; log unittest 1,824 giây |
| Probe và verifier validate-only | Đạt; 18/36 calls và 39/312 calls |
| Raw generation → parsed output → prediction trace | Khớp cả 20 calls |
| Decoder policy/schema SHA | Khớp schema tính lại cho cả 20 requests |

Criteria SHA256:
`69b9d45d071d1c4627189f8eeecf3387a3b32b8357b8161ca417f82efc0047ae`.
ZIP không có GPU weights, nên audit xác minh các hash được ghi nhận với frozen
baseline; không hash lại trực tiếp weights từ GPU ở local.

Setup, pip check, CUDA và regression đều exit 0. Riêng probe exit 1 do quality
gate: runner đã đi hết 18 claim (`experiment_completed=true`), nhưng một
decomposition chưa hợp lệ. Không có worker crash hoặc process timeout trong run.

## 2. Số đo tính lại từ trace

| Mục | Kết quả |
| --- | ---: |
| Claim đã thử / hợp lệ / incomplete | 18 / 17 / 1 |
| Calls | 20, dưới cap 36 |
| Đạt ngay attempt 1 | 16 claim |
| Repair attempts / structural repair thành công | 2 / 1 |
| Outputs bị validator từ chối | 3, đều metric_predicate_incomplete |
| Generated / prompt tokens | 1.063 / 25.835 |
| Generated tokens tối đa một call | 117, dưới cap 1.536 |
| Runner gồm model loading/download | 200,958 giây |
| Outer stage probe | 206,880 giây |
| Automated gate / overall pass | false / false |
| Accuracy / false support / USD | Chưa đo / chưa đo / null |

20 call_started, 20 generation và 20 call_finished khớp theo call_id, claim,
messages, raw JSON và parsed output. Replay dùng source local đã qua
`load_frozen()`; kiểm cả chuỗi repair với previous output/error/details.
Mọi request chỉ có claim; không có context/gold label trong probe.

## 3. Review từng claim

[Review JSONL](decomposition-semantic-review-20261015T155608Z-9262cfd5.jsonl)
ghi đủ 18 claim, 19 canonical parts hiện có và hai draft bị từ chối của 007.
Đây là review AI, không phải annotation độc lập hoặc phiếu human admission.
15 canonical plans giống hệt plan v5 đã review; đã so sánh chính xác trước khi
tái sử dụng ghi chú. Ba ca 007/008/014 được review riêng trên output v6.

| ID | Review AI | Kết luận |
| --- | --- | --- |
| 001 | Đạt, 2 parts | Juniper: memory giảm 25%; accuracy giữ 94%. Subject/property/quantity và hướng riêng đúng. |
| 002 | Đạt | Juniper và accuracy 94% đúng. |
| 003 | Đạt | Study used human labels; metric giữ full predicate. |
| 004 | Đạt | New index, latency; caused còn nguyên trong quote. Chưa kiểm bằng chứng nhân quả. |
| 005 | Đạt | All tasks, improved, after compression được giữ. |
| 006 | Đạt | Một predicate evaluated; 4/models và 2/datasets thành hai yêu cầu riêng, giữ dataset condition. |
| 007 | Chưa có plan hợp lệ | Cả hai attempts giữ metric took, validator từ chối, stop invalid_output_exhausted. |
| 008 | Cần sửa | Repair đổi contained thành 240 documents, qua structural check nhưng chưa giữ full predicate trong metric. |
| 009 | Đạt | Method/recall và On the tested dataset đúng. |
| 010 | Đạt, có lưu ý | All validation shard, recall, after revision; metric improved recall vẫn chỉ đúng property dù còn động từ. |
| 011 | Đạt | Some audited cache node, response time, after patch. |
| 012 | Đạt | None monitored pumps; positive predicate leaked và overnight test đúng. |
| 013 | Đạt | North gateway, error rate, hướng giảm, after calibration. |
| 014 | Đạt, có lưu ý | All weekly trial; condition in May chọn tập trial conducted in May. Metric improved throughput giữ đúng property. |
| 015 | Đạt | Patch, median request latency và hướng giảm. |
| 016 | Đạt | Configuration change, precision và hướng tăng. |
| 017 | Đạt, 2 parts | Extractor giảm memory use và tăng token recall; shared prefix After tuning đúng. |
| 018 | Đạt | All batch trong low-temperature group, yield, after update. |

Các lượng từ và scope vẫn cần được xác minh với evidence trong full verifier.
Giữ điều kiện in May cho population ở 014 không tự chứng minh improvement diễn
ra trong May. Những lưu ý này chưa được dùng để đổi nhãn hoặc thêm yêu cầu vào claim.

## 4. Hai điểm chưa đạt và nguyên nhân đã kiểm chứng

| Ca | Attempt 1 | Attempt 2 | Kết quả |
| --- | --- | --- | --- |
| 007 | metric=took | metric=took | Cả hai bị chặn; không có canonical decomposition |
| 008 | metric=contained | metric=240 documents | Attempt 2 được validator chấp nhận; metric vẫn thiếu quan hệ contained |

Ở 007, repair message có đúng error, field `parts[0].scope.metric` và
`required_source=["took 12 seconds"]`. Model vẫn lặp metric cũ; không phải nhánh
repair chưa được gọi. Validation đã dừng an toàn sau hai attempts.

Ở 008, quote vẫn là toàn bộ `The sample contained 240 documents.` và numeric
requirement 240/documents còn nguyên. Vì claim không có named property tường
minh, frozen base prompt yêu cầu full actual predicate; `240 documents` chỉ là
quantity/object fragment, chưa phải `contained 240 documents`. Đây là lỗi
specificity của metric theo prompt, không phải bằng chứng false support: probe
chưa gọi assessment và chưa có nhãn.

Đã dựng lại schema từ chính các claim và kiểm enum:

- 007 cùng cho phép `took`, `12 seconds`, `took 12 seconds`.
- 008 cùng cho phép `contained`, `240 documents`, `contained 240 documents`.

Decoder hiện chỉ ràng metric là source span. Guard v6 từ chối **bare verb có
argument bị bỏ**, nhưng không từ chối **bare quantity/object**. Vì vậy model có
thể lặp output cũ hoặc đổi sang một span khác vẫn thiếu predicate. Unit tests
v6 đã chứng minh backend giả repair được; run này cho thấy model thật chưa đáp
ứng đủ. Không quy lỗi này cho T4, NF4 hoặc model size từ các số đo hiện có.

## 5. Hướng tiếp theo

1. **Bảo toàn v6:** snapshot source/prompt/criteria/contract/notebook và ZIP run
   này trước khi sửa; giữ v5 snapshot và cả hai lượt output làm đối chứng.
2. **Chuẩn bị candidate v7:** với các mẫu đếm/thời lượng thuộc grammar đang hỗ
   trợ, tạo tập metric hợp lệ gắn với từng clause/predicate rồi dùng chung cho
   validator và decoder/schema. Loại cả bare verb lẫn bare quantity/object khi
   contract yêu cầu full predicate. Giữ named properties như accuracy, latency,
   memory hợp lệ. Nếu không biểu diễn rõ được, dừng với lý do cụ thể trước
   generation thay vì tạo schema không thể thỏa mãn.
3. **Regression trước freeze:** bổ sung hai kiểu output thật ở run này, cùng
   claim mới/counterexample. Dùng token filter thật để kiểm full predicate được
   phép, took/contained và quantity-only bị loại cho đúng mẫu hỗ trợ; kiểm repair,
   scope từng vế, lượng từ và nhiều requirement số liệu không bị ảnh hưởng.
4. **Freeze và chạy lại probe 18:** version/decoder policy/contract/criteria và
   notebook mới phải đồng bộ; giữ model/revision, dữ liệu và budget để đánh giá
   thay đổi. Điều kiện vẫn 18/18 structural pass và review ngữ nghĩa đủ từng ca.
5. **Sau probe đạt:** hoàn thành human review đúng hash, rồi mới chạy 39 ca;
   yêu cầu 39/39 nhãn đúng, false support 0, runtime failures 0 và review đúng
   evidence/coverage/numeric binding/missing information từng ca.

Đây là kế hoạch tiếp theo, **chưa triển khai hoặc chạy model v7 trong lượt audit**.
Không cần mua GPU khác từ kết quả run này; chưa có bằng chứng phải đổi hardware.

## Admission và artifact

Đã kiểm entry point full39 với model loader được mock. Runner từ chối trước
khi tải model hoặc tạo output directory:

```text
Probe must finish successfully before semantic admission
```

Human review gốc giữ nguyên SHA256
`ae14b3ab0bd29b9a5713ada76cf104587fc3cea70187662bbcdaedfe6ddd6a44`.
Predictions SHA256:
`fbcc1e35d51cae1b536c25daefb2bd4406a8d864991ab7078f6ce0d06830bf41`.
Không sửa model output, không ký human review thay người dùng, không chạy 39 ca.

[Audit máy đọc được](decomposition-probe-audit-20261015T155608Z-9262cfd5.json).
Bộ 18/39 vẫn là synthetic development đã đọc; kết quả này chưa chứng minh
generalization hoặc cho phép promotion sang serving.
