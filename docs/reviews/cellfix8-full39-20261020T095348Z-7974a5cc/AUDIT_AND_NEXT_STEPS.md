# Audit cellfix8 resume full39 — 2026-10-20

**Full39 đã chạy đủ nhưng chưa đạt. Dừng trước validation30.** Exit code 1 là gate đánh giá thất bại, không phải lỗi restore/GPU.

- Original run: `20261020T061934Z-c87bce57`; recovery: `20261020T095348Z-7974a5cc`.
- ZIP SHA-256: `07b5fdf87e57e89bf6b19f14c54df29806bb72c08d3210e7a9f9c93fa5d35190`.
- 128 output files và 111 input files khớp manifest/release. 69 file gốc được giữ nguyên; status/manifest gốc được lưu riêng. Bản reviewed-probe chỉ đổi unsigned review thành human JSON thật, các file còn lại trùng byte.
- Human probe review của **Trí Công** đúng hash và được frozen runner admit. Smoke cũ replay lại đạt; không generate lại smoke/probe.
- T4; torch 2.10.0+cu128; Qwen/Qwen2.5-3B-Instruct revision `aa8e72537993ba99e69dfaafa59ed015b17504d1`, NF4/float16, seed42, do_sample=false. Source/prompt/contract/model/budget/gate khớp candidate đóng băng.
- Audit đã replay 39 results và 95 call triplets, kiểm lại từng validation issue, numeric operands và exact source citations; metrics khớp từng trường. Audit không gọi model mới.

| Phép đo | Kết quả |
|---|---:|
| Số ca có output | 39/39 |
| Nhãn đúng, tính cả ca incomplete là chưa đạt | 29/39 (74,36%) |
| Original contracts | 12/12 |
| Scope regression | 17/27 |
| False support theo gold | 0 trên 27 ca gold không-support |
| Gold support được nhận đúng | 8/12 |
| Gold support bị từ chối/chưa hoàn tất | 4/12 |
| Incomplete do hết hai lượt assessment | 3 |
| Hoàn tất nhưng sai nhãn | 7 |
| Backend calls | 95/312 |
| Generated tokens | 11.410/479.232 |
| Prompt tokens | 105.889 |
| Thời gian stage full39 | khoảng 16 phút 48 giây |
| JSON parse hợp lệ trong trace | 95/95 |
| Automated gate | FAIL |
| Human review full39 | Chưa hoàn tất |
| Validation30 inference | Chưa chạy, gate chặn đúng |

`false_support=0` chỉ đếm dự đoán support khi gold khác support. Nó không đo đủ quote relevance hay độ trung thực prose: có ít nhất một support đúng nhãn nhưng sai citation (`scope:entity:support`). Không suy diễn zero false support trên dữ liệu độc lập từ 39 ca development đã dùng để sửa.

## Lỗi cần sửa trong candidate kế tiếp

1. **Binding observation với evidence tại từng clause.** Ca North gateway cite South gateway vẫn được validator nhận. `other_named_target()` hiện hiểu entity nhiều từ theo prefix + tên cuối; với North gateway, head=North/name=gateway nên không bắt South gateway. `evidence_issue()` fallback sang mọi clause khi không tìm được clause của member, làm lọt quote không có target. Cần kiểm cả member thuộc population và predicate thuộc member, không chỉ source span có mặt trong context.
2. **Không mượn polarity từ member khác.** Universal contradiction có hai shard improved và third worse. Guard chọn cả hai clause khi clause của third không chứa đúng chữ metric recall (source dùng recalling), từ đó reject phản ví dụ hợp lệ. Diagnostic trên chính trace đã tái hiện: mixed quote trả observation_polarity_mismatch; riêng clause third không trả lỗi đó. Chưa sửa hoặc thay quote của predictions.
3. **Truth trước ALL/SOME/NONE và coverage closure.** NONE support dùng roster-only quote làm leaked=true; NONE contradiction lại dùng leaked=false cho Silver đã leak. Closure/members/observations không khớp hoặc lặp, repair chuyển sang unknown và mất thông tin có sẵn. Cần regression cho kết quả collective rõ ràng, danh sách population đóng, phản ví dụ trong đúng scope, và kết quả chưa báo cáo.
4. **Unknown/missing và prose phải đúng part.** Precision 0.81 -> 0.74 bị coi thiếu baseline; các ca conjunction sai lý do thiếu; missing ở direction tự tạo Shepherd et al. (2023). Guard/schema hiện chấp nhận chuỗi đúng cấu trúc nhưng không xác minh toàn bộ ý nghĩa. Numeric override đúng không tự sửa prose sai.

Không cần tăng budget, đổi model, bỏ assert, đổi gold để làm gate xanh. 95/95 JSON hợp lệ, không có deadline/OOM trong kết quả này; ưu tiên semantic binding, polarity và coverage thay vì chỉ sửa serialization.

## Rà từng ca

Đây là **AI evidence audit**, không phải chữ ký human và không dùng mở gate. Nhận xét “nhãn đúng” không đồng nghĩa mọi tiêu chí human review đạt. Tên ID conjunction giữ lịch sử; hai gold đầu đã là NEI trong fixture strict-identity-v1 trước run này, audit không sửa annotation.

| Case | Gold | Prediction | Nhận xét |
|---|---|---|---|
| contract:partial_accuracy | not_enough_info | not_enough_info | Memory 25% có numeric check đúng; accuracy không được context xác nhận, aggregate NEI đúng. |
| contract:partial_memory | not_enough_info | not_enough_info | NEI đúng nhưng part memory lại nói thiếu retention accuracy, dù context đã có accuracy 94%. Missing-information sai metric. |
| contract:both_supported | support | support | Hai numeric checks 25% memory và 94% accuracy đúng; câu giải thích accuracy bị cụt, cần review riêng chất lượng prose. |
| contract:accuracy_conflict | contradict | contradict | 25% memory đúng và 81% so với 94% accuracy refute đúng; explanation của part memory lại bàn về accuracy. |
| contract:irrelevant | not_enough_info | not_enough_info | NEI đúng vì không có accuracy Juniper; member không phải target và missing_information bị tách thành chuỗi vụn. |
| contract:negation | contradict | contradict | Context phủ định trực tiếp việc study dùng human labels, contradict đúng. |
| contract:causality_missing | not_enough_info | not_enough_info | Không thiết lập quan hệ nhân quả; unknown/NEI đúng, không biến correlation thành causation. |
| contract:scope | contradict | contradict | Fourth task became less accurate là phản ví dụ trong population; ALL bị refute đúng. |
| contract:cross_sentence | support | support | q0=4 models và q1=2 datasets có source riêng đúng; citation thứ hai được thêm từ ledger. Explanation nói evaluation done on report, lệch vai trò report/models. |
| contract:wrong_units | contradict | contradict | 12 hours, not 12 seconds là phủ định rõ, numeric check giữ đơn vị và contradict đúng. |
| contract:atomic_support | support | support | Sample 240 documents được exact quote và numeric check xác nhận. |
| contract:bounded_scope | support | support | Support chỉ trên tested dataset đúng; explanation bị cắt dở, không đủ để coi mọi tiêu chí semantic đạt. |
| scope:universal:support | support | not_enough_info | Gold support: toàn bộ 3 shards đều improved. Lượt đầu coverage/member không trùng observation; repair nói thiếu dữ liệu vốn đã có, trả NEI. |
| scope:universal:contradict | contradict | incomplete | Third became worse at recalling relevant records là phản ví dụ. Guard polarity lấy cả vế two improved recall và reject cả hai lượt; không có aggregate. |
| scope:universal:not_enough_info | not_enough_info | not_enough_info | NEI đúng vì population chưa đầy đủ; missing All validation shards quá chung, explanation thêm only two were tested trong khi source chỉ nói hai shard improved. |
| scope:existential:support | support | support | Birch became faster sau patch là witness true cho SOME; các node khác không cần cùng cải thiện. |
| scope:existential:contradict | contradict | not_enough_info | Population Birch/Elm/Fir đóng; cả ba không giảm response time. Lượt đầu lặp coverage member 16 lần; repair chỉ giữ Fir và coverage=false, mất chứng cứ refute SOME. |
| scope:existential:not_enough_info | not_enough_info | not_enough_info | NEI đúng do các node khác chưa báo cáo; member và missing chưa chỉ rõ kết quả response time của các node còn lại. |
| scope:none:support | support | contradict | No leaks for any pump phải support NONE. Model gán leaked=true từ câu roster không có leak result, coverage=false; guard vẫn chấp nhận và aggregate contradict. |
| scope:none:contradict | contradict | incomplete | Silver leaked phải là truth=true trước NONE, từ đó contradict. Model hai lần dùng false; guard positive_predicate_before_quantifier chặn đúng nhưng repair thất bại. |
| scope:none:not_enough_info | not_enough_info | not_enough_info | NEI đúng vì leak status Silver chưa báo cáo. Missing cần hỏi trạng thái leak của Silver, không mặc định Silver không leak. |
| scope:entity:support | support | support | Nhãn support khớp gold nhưng quote chỉ nói South tăng error rate. Observation North không được quote chứng minh; không đạt quote_relevant dù toàn context có câu đúng về North. |
| scope:entity:contradict | contradict | contradict | Quote nói North error rate increased sau calibration, trực tiếp refute reduced. |
| scope:entity:not_enough_info | not_enough_info | not_enough_info | Kết quả North chưa ghi nhận; South không thay thế North. NEI đúng. |
| scope:time:support | support | incomplete | May trials đều improved; April giảm nằm ngoài population. Model chọn April làm counterexample; cả hai lượt bị polarity/scope guard chặn. |
| scope:time:contradict | contradict | not_enough_info | Bốn trial May: ba tăng, một giảm. Model coi mixed outcomes giữa các member là unknown, bỏ phản ví dụ, trả NEI. |
| scope:time:not_enough_info | not_enough_info | not_enough_info | NEI đúng vì không có kết quả May. Missing lại yêu cầu một May trial không tăng; nên hỏi kết quả May còn thiếu, không định trước chiều kết quả. |
| scope:direction:support | support | support | 42 -> 31 ms kiểm change đúng, support đúng. Explanation bị cụt và có newline/tab rác. |
| scope:direction:contradict | contradict | contradict | 42 -> 55 ms refute reduced đúng nhờ numeric override. Model_truth=true và prose nói confirms claim vẫn lệch với kết luận numeric false. |
| scope:direction:not_enough_info | not_enough_info | not_enough_info | NEI đúng vì thiếu before-patch baseline. Missing_information tự thêm Shepherd et al. (2023), không xuất hiện trong context; đây là chi tiết bịa dù nhãn đúng. |
| scope:metric:support | support | support | Precision 0.81 -> 0.86 đúng cùng metric và numeric support; prose bị cụt. |
| scope:metric:contradict | contradict | not_enough_info | Precision 0.81 -> 0.74 là giảm và refute increased. Model nói thiếu original precision dù source có 0.81, trả NEI. |
| scope:metric:not_enough_info | not_enough_info | not_enough_info | Precision không được đo; recall tăng không chứng minh precision tăng. NEI đúng. |
| scope:conjunction:support | not_enough_info | not_enough_info | Gold hiện tại NEI theo strict-identity-v1, không còn support: context chưa định danh extractor. Model đúng nhãn nhưng nói thiếu số liệu vốn có và member là số liệu, sai lý do. |
| scope:conjunction:contradict | not_enough_info | not_enough_info | Gold hiện tại NEI theo strict-identity-v1, không còn contradict: context chưa định danh extractor. Prose của token recall bàn memory; không được coi bằng chứng hoàn chỉnh. |
| scope:conjunction:not_enough_info | not_enough_info | not_enough_info | NEI đúng: extractor chưa được bind, token recall chưa đánh giá. Member là quantity; part memory lại giải thích token recall. |
| scope:condition:support | support | not_enough_info | Mọi batch low-temperature đều gained yield; high-temperature ngoài scope. Repair có true nhưng member=the update, coverage=false nên NEI. |
| scope:condition:contradict | contradict | not_enough_info | Một batch trong đúng low-temperature group lost yield. Model dùng the update làm member, nói thiếu third batch dù source có kết quả, trả NEI. |
| scope:condition:not_enough_info | not_enough_info | not_enough_info | Aggregate NEI đúng do scope unknown; observation lại false cho the update với câu nói no yield changes measured. Prose mượn high-temperature, không phải bằng chứng refute low-temperature. |

## Bước tiếp theo

1. Giữ ZIP/source/predictions và audit này làm mốc thất bại của cellfix8. Không sửa predictions, không chạy validation30 hoặc tích hợp serving/Reader/Summarizer ở gate này.
2. Làm candidate kế tiếp, đề xuất cellfix9: sửa quy tắc chung cho binding/evidence/polarity/closure; thêm regression từ trace thật và câu mới (tên chủ thể ở đầu/cuối, câu roster không có predicate, nhiều member có kết quả trái chiều, NONE có leak/no leak/unknown, các tháng/nhóm ngoài scope, metric cùng context). Tránh vá theo case ID hay chỉ câu của full39. Kiểm validator và decoder dùng cùng quy tắc; giữ model/revision/budget/gate.
3. Chạy regression/validate-only, đóng băng đồng bộ source/prompt/contract/criteria/notebook và binding mới. Chạy smoke -> probe18 + human review cho candidate mới -> full39. Gate vẫn là 39/39, FS0, runtime0, đủ trace và trong budget; sau đó review evidence/explanation full39, rồi mới validation30.
4. Giữ nguyên validation30 đã khóa, không dùng kết quả hoặc gold để tune. Chỉ cập nhật binding cho candidate mới theo workflow; nếu có kết quả sau này thì báo riêng khỏi development full39.

## Giới hạn

Đã kiểm hash/replay và đọc claim/context/prediction của đủ 39 ca. Chưa chạy model mới tại máy local, chưa có human review full39, chưa đo validation30 hay E2E. Manifest chứng minh tính nhất quán artifact, không phải chữ ký xác thực host Colab.
