# Probe Colab v5: cấu trúc đạt, review ngữ nghĩa còn hai ca cần sửa

Đã kiểm ZIP và replay toàn bộ **18 predictions, 18 calls, 20 factual parts**.
Gate tự động đạt. Review AI: **16/18 claim đạt, 2/18 cần sửa metric**; chưa đủ
điều kiện chạy 39 ca. Phiếu human review gốc vẫn pending, không được ký thay.

Run: `20261015T103401Z-723b3e4a`, ngày 2026-10-15. ZIP đầu vào:
`C:/Users/dellcuatri142/Downloads/output.zip`, SHA256
`26c02fffb4cd1c4ae718534a0db1386065241f24a4c7d065055763575d7c9fa7`.
Bản gốc và output giải nén được bảo toàn tại
`research-runs/colab-atomic-v5/20261015T103401Z-723b3e4a/`.

## 1. Provenance và replay

| Kiểm tra | Kết quả |
| --- | --- |
| ZIP CRC và output manifest | Đạt; 39/39 file hash/size, cộng manifest là 40 file |
| Input manifest so với release Colab và bytes local | 67/67 file khớp |
| Frozen source/prompt/contract/data/criteria/baseline | Khớp; 24 frozen source files |
| Criteria SHA256 | `b110c02c404f7b91e52551d90e7605d850b12ac7ebb5a332fd292895ad27fa77` |
| Model/revision, weights hash ghi nhận, shared tokenizer, dtype/NF4/seed/sampling | Khớp baseline đã đóng băng |
| GPU/runtime từ log | Tesla T4; torch 2.10.0+cu128, CUDA 12.8 |
| Runtime đã pin | Transformers 5.16.1, bitsandbytes 0.50.2, LMFE 0.11.3, interegular 0.3.3 |
| Regression trên Colab | 80/80 đạt; unittest ghi 1,600 giây |
| Probe/full verifier validate-only | Đạt; 18 claim/36 calls và 39 ca/312 calls |
| Replay decomposition/normalized offsets/numeric requirements | 18/18 khớp frozen code |
| Đối chiếu trace | 18 call_started + 18 generation + 18 call_finished; raw JSON, parsed output, input và prediction khớp |
| Decoder trace | 18/18 policy/schema SHA khớp schema dựng lại từ input |
| Model quality về evidence/nhãn | Chưa đo; đây chỉ là decomposition probe |

Model là `Qwen/Qwen2.5-3B-Instruct`, revision
`aa8e72537993ba99e69dfaafa59ed015b17504d1`, float16/NF4, seed 42,
`do_sample=False`, 1.536 token/call. Các hash weights trong provenance khớp
baseline; ZIP không chứa GPU weights nên không hash lại trực tiếp weights ở local.
Generation config dùng chung lưu default sampling true, nhưng frozen backend
truyền `do_sample=False` trực tiếp khi gọi generate; không kết luận sampling
đang bật chỉ từ default này.

Không chạy source/script từ ZIP. Replay dùng mã local đã qua `load_frozen()`.
Mỗi call chỉ nhận claim; không có context/gold label lọt vào decomposition.
Không có part assessment hay aggregate label trong 18 kết quả.

## 2. Số đo thực tế

| Mục | Kết quả |
| --- | ---: |
| Claim hợp lệ / incomplete | 18 / 0 |
| Factual parts | 20 |
| Calls / repairs | 18 / 0 |
| Generated / prompt tokens | 967 / 22.892 |
| Generated tokens tối đa mỗi call | 117, dưới cap 1.536 |
| Thời gian runner gồm model loading/download | 315,765 giây |
| Thời gian stage probe có outer worker | 321,562 giây |
| Automated gate | true |
| Human review / overall pass | pending / false |
| Label accuracy / false support / USD | Chưa đo / chưa đo / null |

## 3. Review đủ 18 claim và 20 mệnh đề

[Review JSONL từng part](decomposition-semantic-review-20261015T103401Z-723b3e4a.jsonl)
ghi nguyên plan model, đủ năm judgments và ghi chú riêng cho từng part.
Đây là **review của assistant**, không phải reviewer người hoặc annotation độc lập.

| ID | Review AI | Kiểm tra mệnh đề |
| --- | --- | --- |
| 001 | Đạt, 2 parts | Juniper giảm memory 25%; Juniper giữ accuracy 94%. Subject kế thừa đúng; số, property và hướng thay đổi tách riêng. |
| 002 | Đạt | Juniper, accuracy 94%, quantifier atomic. |
| 003 | Đạt | Study used human labels; full predicate được giữ trong metric. |
| 004 | Đạt | New index, latency; caused vẫn nằm trong quote, chưa biến nhân quả thành tương quan. |
| 005 | Đạt | All tasks và after compression được giữ; không tự thêm property mà claim không nêu. |
| 006 | Đạt | Một predicate evaluated; 4/models và 2/datasets là hai numeric requirements riêng, dataset nằm trong condition. |
| 007 | Cần sửa | Quote và 12/seconds đầy đủ, nhưng metric chỉ là `took`. |
| 008 | Cần sửa | Quote và 240/documents đầy đủ, nhưng metric chỉ là `contained`. |
| 009 | Đạt | Method/recall; On the tested dataset đúng trong condition, còn nguyên tested. |
| 010 | Đạt, có lưu ý | All validation shard; recall và after the revision đúng. Metric `improved recall` còn động từ, khác cách viết ưu tiên `recall`, nhưng property không bị mất hoặc đổi. |
| 011 | Đạt | Some; audited cache node, response time, after the patch. |
| 012 | Đạt | None; monitored pumps, positive predicate leaked, during the overnight test. |
| 013 | Đạt | North gateway, error rate, hướng giảm, after calibration. |
| 014 | Đạt, có lưu ý | All weekly trial; in May giữ điều kiện chọn tập trial được conducted in May. Không suy ra improvement xảy ra trong May. |
| 015 | Đạt | Patch; median request latency và hướng giảm, không đổi median thành mean. |
| 016 | Đạt | Configuration change; precision và hướng tăng, không nhầm recall. |
| 017 | Đạt, 2 parts | Extractor giảm memory use và tăng token recall; cả hai kế thừa đúng prefix After tuning. |
| 018 | Đạt | All batch thuộc low-temperature group, yield, after the update. |

Ở 014, `in May` bổ nghĩa tập trial, nên lưu trong condition vẫn giữ population
restriction. Schema v5 chỉ cho `time=""` ở câu này; code temporal parser chỉ
nhận after/before/during. Không sửa prediction để chuyển field sau inference.
Các cấu trúc lịch phức tạp hơn cần mở rộng grammar và đánh giá riêng; kết quả
này không chứng minh parser hiểu mọi thời gian.

## 4. Hai điểm chặn và nguyên nhân

| ID | Output thật | Yêu cầu chưa đạt | Ví dụ output cần được model sinh lại |
| --- | --- | --- | --- |
| 007 | entity=`Training`, metric=`took` | Metric thiếu object/quantity, trái yêu cầu full actual predicate khi không có named property | `took 12 seconds` |
| 008 | entity=`sample`, metric=`contained` | Metric thiếu object/quantity, trái yêu cầu full actual predicate | `contained 240 documents` |

Các ví dụ sửa ở bảng chỉ minh họa yêu cầu; **không phải output đã chạy lại**.
Số và đơn vị của cả hai ca vẫn còn trong quote và numeric requirements.
Vì vậy đây là lỗi specificity của scope theo prompt, chưa phải bằng chứng model
đã gán sai nhãn hoặc false support. Judgment `entity_metric_binding_correct`
được đánh false cho hai ca này do metric chưa đủ nội dung theo contract prompt.

Nguyên nhân đã kiểm từ source: `decomposition_schema()` cho metric chọn mọi
claim span; `scope_issues()` chỉ buộc entity/metric không rỗng và grounded.
Không có kiểm tra bare generic predicate để gửi `took`/`contained` vào repair.
Do đó các output này qua schema và structural validator, dù trái quy tắc trong
`DECOMPOSE_PROMPT`: không chỉ dùng used/took/contained.

Hướng sửa nhỏ nhất cho candidate tiếp theo: thêm kiểm tra generic predicate
trong shared validation/repair, giữ các named property như accuracy/latency
hợp lệ, thêm regression với claim mới và counterexample. Sau thay đổi behavior,
đóng băng phiên bản mới rồi chạy lại probe. Không sửa file predictions, không
ghi đè v5 criteria/source để làm provenance cũ trông như đạt.

## 5. Quyết định trước 39 ca

Đã gọi đúng `require_probe_review()` với output gốc. Gate từ chối tại:

```text
Completed human review bound to this probe is required
```

Toàn bộ kiểm provenance/replay/decoder trước điểm human admission đã qua.
Đã kiểm cả entry point full39 với model loader được mock: runner bị chặn trước
model loader, không tạo output directory hoặc phát sinh inference.
Phiếu human gốc còn nguyên SHA256
`022e467cfaab6df9b54dc582cc3c0a8fac98a55f34a104c12af11822271f45e0`.
Predictions SHA256:
`883154294887bc51e22fefdf59c6bc931daea4a1f6da3411fcf6e711920187db`.

**Chưa chạy 39 ca**: hai metric cần sửa và chưa có human review hợp lệ.
Sau candidate đạt đủ review 18 claim mới chạy 39 ca rồi kiểm evidence/nhãn
độc lập. Probe không có context để xác nhận evidence hoặc đo zero false support.

Giới hạn phạm vi: đây là 18 claim lấy từ 39 ca synthetic development đã đọc;
chưa là held-out độc lập. Trường hợp hai vế có hai thời gian cục bộ khác nhau
được kiểm bằng regression code, không xuất hiện trong 18 output model này.
Không có promotion sang serving, không có model call mới từ lượt audit.

[Audit máy đọc được](decomposition-probe-audit-20261015T103401Z-723b3e4a.json).
