# Cellfix9 full39 — audit và quyết định validation30

**Chưa được chạy validation30.** Gate full39 trượt và chưa có human review full39. Giữ `RUN_VALIDATION30 = False` ở cell 7. Không bỏ assert hoặc đổi summary để vượt gate.

Run `20261020T110710Z-cf47db2f`. ZIP đã kiểm là `output-cellfix9-fresh-20261020T110710Z-cf47db2f (3).zip`; ba bản trước chỉ chứa smoke/probe và trùng hash nhau.
ZIP SHA-256: `27d3e3954c70ce38c6c96bcc87f20bc60b98dcccc5530fbcdf801b979b7d7c58`.

## Provenance và replay

- 105 file output và 115 file input khớp hash. Payload/criteria/source/prompt/contract đúng release cellfix9; model/revision/quantization/seed/budget/gate đúng bản khóa.
- Model provenance ghi Qwen/Qwen2.5-3B-Instruct, revision `aa8e72537993ba99e69dfaafa59ed015b17504d1`, NF4/float16, seed42, do_sample=false; T4.
- Smoke/probe đã chạy trước full39 được giữ nguyên byte. Human probe review của Trí Công có đủ 18 case/90 tiêu chí và notes, gắn đúng criteria/predictions, replay admission đạt. Đây là review decomposition, không phải human review 39 assessment.
- Replay đủ 69 prediction rows và **141 call triplets**: smoke31, probe18, full39 92. Kiểm lại từng validation issue, exact quote, numeric record và metrics; khớp dữ liệu lưu. Cả 141 generation parse JSON hợp lệ.
- Regression Colab **291/291** và bốn validate-only đạt. Validate-only validation30 chỉ kiểm cấu hình, không chạy inference validation30.
- Gọi lại `require_full39()` từ chính frozen workflow bị chặn đúng: `Successful full39 is required before validation30`. ZIP không có inference validation30 hoặc bản reviewed-verifier39.
- Mốc cellfix8 được giữ nguyên. Bộ39/annotation của cellfix9 trùng byte logic với cellfix8 đã audit; không đổi gold trong lượt rà soát này.

## Kết quả đã đo

| Chỉ số | Cellfix9 |
|---|---:|
| Smoke đúng nhãn | 12/12, false support 0, runtime 0 |
| Probe decomposition hợp lệ | 18/18; không đo label accuracy |
| Full39 có output | 39/39 |
| Full39 đúng nhãn | **36/39 (92,31%)** |
| Original contracts | 12/12 |
| Scope regression | 24/27 |
| False support theo frozen gold | **0**, trên 27 gold không-support |
| Gold support được nhận đúng | 12/12 |
| Hoàn tất nhưng sai nhãn | 1 |
| Incomplete vì hết repair | 2 |
| Calls full39 | 92/312 |
| Generated tokens full39 | 11.292/479.232 |
| Prompt tokens full39 | 109.190 |
| Full39 stage time | khoảng 15 phút 41 giây |
| Automated gate / human review full39 | FAIL / chưa hoàn tất |
| Validation30 inference | Chưa chạy |

So với cellfix8 trên cùng 39 ca: nhãn đúng 29 -> 36, incomplete 3 -> 2, false support vẫn 0, gold-support rejected 4 -> 0. Đây là so sánh development, không phải kết quả generalization hoặc bằng chứng quy riêng cải thiện cho một thay đổi.

## Ba ca làm gate thất bại

| Case | Gold -> kết quả | Điều đã thấy trong trace |
|---|---|---|
| `scope:existential:contradict` | contradict -> NEI | Lượt đầu lặp một coverage span 16 lần; repair chỉ giữ Fir=false, coverage=false. Một false witness không refute SOME. Hai node còn lại chưa được đưa vào ledger. |
| `scope:direction:not_enough_info` | NEI -> incomplete | Cả hai lượt thêm Shepherd et al. (2023), không có trong source; guard chặn đúng, repair không bỏ citation bịa. |
| `scope:conjunction:not_enough_info` | NEI -> incomplete | Part memory hai lần liệt kê missing token recall; guard chặn sai metric đúng, repair chưa sửa. Các part chưa được assess xong. |

Hai incomplete là lỗi output/repair theo contract, không phải JSON parse, deadline hay OOM. Không được đổi incomplete thành NEI để ghi 38/39: pipeline chưa trả kết quả hợp lệ cho hai ca đó.

## Chất lượng ngoài điểm nhãn

**`scope:none:support` có label/quotes/ledger đúng nhưng prose ngược nguồn.** Source nói không pump nào leak; observation truth=false trước NONE và aggregate support đúng. Tuy nhiên observation explanation nói có leak ở ít nhất một pump, model_explanation nói claim bị contradicted. Tiêu chí explanation_follows_evidence chưa đạt.

Các ví dụ khác: `contract:irrelevant` gọi thiếu báo cáo là contradiction; `scope:condition:not_enough_info` liệt kê kết quả đã biết của high-temperature như thông tin còn thiếu; hai ca conjunction có label NEI đúng theo strict-identity nhưng giải thích thiếu số liệu vốn đã có. Nhiều câu bị cắt ở giới hạn 64 ký tự hoặc có whitespace rác. Vì vậy zero false support theo gold không đồng nghĩa mọi tiêu chí semantic đạt.

## Nhận xét riêng 39 ca

Đây là **AI audit**, không phải human signature; không tạo semantic-review.json đạt để mở gate. Nhãn đúng và chất lượng lời giải thích được ghi riêng.

| Case | Gold | Prediction | Nhận xét |
|---|---|---|---|
| contract:partial_accuracy | not_enough_info | not_enough_info | Memory 25% có check đúng; thiếu accuracy nên aggregate NEI đúng. Missing accuracy còn dùng từ structural khá chung. |
| contract:partial_memory | not_enough_info | not_enough_info | NEI đúng và missing đã trỏ memory thay vì accuracy. Accuracy 94% có check đúng; model_explanation accuracy kết thúc dở ở ký tự 9. |
| contract:both_supported | support | support | Memory 25% và accuracy 94% có checks riêng, cùng đúng Model Juniper; hai part support, aggregate support đúng. |
| contract:accuracy_conflict | contradict | contradict | Memory 25% đúng, accuracy 81% refute 94% đúng. Explanation memory có cụm but not the exact rồi bị cụt, dù source đã nêu chính xác 25%. |
| contract:irrelevant | not_enough_info | not_enough_info | NEI đúng, nhưng missing_information lại nói absence of reports directly contradicts claim. Thiếu báo cáo không phải phủ định accuracy 94%. |
| contract:negation | contradict | contradict | Source phủ định trực tiếp study dùng human labels; quote, truth=false và contradict đúng. |
| contract:causality_missing | not_enough_info | not_enough_info | NEI đúng vì không establish causal link. Model_explanation dùng denies a causal relationship là mạnh hơn source, và bị cắt kèm ký tự rác. |
| contract:scope | contradict | contradict | Fourth task kém chính xác là counterexample, truth=false và contradict đúng. Prose lại gọi One true witness refutes ALL, sai tên truth theo contract. |
| contract:cross_sentence | support | support | q0=4 models và q1=2 datasets đều có source đúng; thêm citation từ ledger đúng. Explanation có từ datast bị cụt. |
| contract:wrong_units | contradict | contradict | Source 12 hours, not 12 seconds refute đúng; giữ đơn vị, không tự chuyển đổi. Model_explanation dài bị cụt nhưng không đổi kết luận arithmetic. |
| contract:atomic_support | support | support | Sample 240 documents có exact quote/check đúng; model_explanation bị cắt dở dù observation explanation đầy đủ. |
| contract:bounded_scope | support | support | Chỉ support trên tested dataset, không đòi dataset khác; scope và quote đúng. Hai explanation kết thúc dở ở in the. |
| scope:universal:support | support | support | Closed population ba shard có each outcome after revision; collective span three shards với full source hợp lệ. Model_explanation bị cắt dở. |
| scope:universal:contradict | contradict | contradict | the third became worse at recalling relevant records được giữ là false trong đúng population; không mượn polarity của two improved; contradict đúng. |
| scope:universal:not_enough_info | not_enough_info | not_enough_info | NEI đúng vì chưa có complete population. Observation gán unknown cho câu hai shard đã improved và missing All validation shards quá chung; cần phân biệt kết quả đã biết với phần chưa biết. |
| scope:existential:support | support | support | Birch became faster sau patch là true witness cho SOME; không yêu cầu toàn bộ population đều giảm response time. Explanation cuối bị cụt. |
| scope:existential:contradict | contradict | not_enough_info | Gold contradict nhưng prediction NEI: attempt đầu lặp một coverage member 16 lần; repair chỉ giữ Fir=false và coverage=false. Không đủ để refute SOME. Cần adjudicate binding complete audited set với audited cache nodes trước khi mở rộng quy tắc. |
| scope:existential:not_enough_info | not_enough_info | not_enough_info | NEI đúng: Elm không giảm và các node khác chưa báo cáo. Missing lặp lại cả claim thay vì nêu kết quả còn thiếu của các node khác. |
| scope:none:support | support | support | Quote no leaks cho cả ba pump; truth=false trước NONE và aggregate support đúng. Nhưng observation explanation nói có leak ít nhất một pump, model_explanation nói claim bị contradicted: prose ngược source và ledger, không đạt semantic review. |
| scope:none:contradict | contradict | contradict | Silver leaked được truth=true trước NONE, quote gồm population và leak result; aggregate contradict đúng. |
| scope:none:not_enough_info | not_enough_info | not_enough_info | NEI đúng do leak status Silver chưa báo cáo. Missing gọi no leaks và status chưa báo cáo là structural contradiction; đây là khác biệt giữa member đã biết và member chưa biết, không phải contradiction. |
| scope:entity:support | support | support | Đã cite đúng North gateway error rate decreased after calibration, không còn chỉ cite South như cellfix8. Support khớp nguồn. |
| scope:entity:contradict | contradict | contradict | Quote chỉ North error rate increased sau calibration; truth=false và contradict đúng. |
| scope:entity:not_enough_info | not_enough_info | not_enough_info | Không có calibration result của North; không mượn kết quả South. NEI và missing đúng target, observation explanation bị cụt. |
| scope:time:support | support | support | Full quote May closed population và each improved, không gồm phản ví dụ April; support đúng. May giới hạn population trials, không tự gán thời gian improvement. |
| scope:time:contradict | contradict | contradict | one reduced throughput là false witness thuộc bốn trial May, refute ALL đúng; explanation bị cắt dở. |
| scope:time:not_enough_info | not_enough_info | not_enough_info | Không có throughput results May; giữ NEI và missing đúng group, không mượn April. |
| scope:direction:support | support | support | 42 -> 31 ms có numeric change đúng, support đúng. Explanation có newline/tab rác và câu dở, không coi là prose hoàn chỉnh. |
| scope:direction:contradict | contradict | contradict | 42 -> 55 ms được check tăng, refute reduced đúng. Observation/model explanation dở; không có lỗi đảo direction trong ledger. |
| scope:direction:not_enough_info | not_enough_info | incomplete | Hai attempt đều tự thêm Shepherd et al. (2023), không có trong input. Guard unattributed_prose_citation chặn đúng; repair thất bại, không có aggregate label. Gold NEI không cho phép bỏ qua lỗi contract để tính đúng. |
| scope:metric:support | support | support | Precision 0.81 -> 0.86 có check đúng, support đúng; prose bị cụt ở and it. |
| scope:metric:contradict | contradict | contradict | Chọn đúng precision 0.81 -> 0.74, không mượn recall 0.64 -> 0.79; check và contradict đúng. |
| scope:metric:not_enough_info | not_enough_info | not_enough_info | NEI đúng vì precision not measured. Observation chỉ quote câu recall rose; nên cite câu precision chưa được đo để thể hiện lý do thay vì quote metric khác. |
| scope:conjunction:support | not_enough_info | not_enough_info | Gold hiện tại NEI theo strict-identity-v1: context thiếu định danh extractor. Part memory nói đúng thiếu target; part token recall nói không có thông tin dù source có 0.72 -> 0.81. Nhãn đúng nhưng lý do chưa đủ chính xác. |
| scope:conjunction:contradict | not_enough_info | not_enough_info | Gold hiện tại NEI theo strict-identity-v1. Source có memory 5.4 -> 4.6 và recall 0.72 -> 0.68 nhưng không bind extractor. Prose lại nói thiếu số liệu đã có và trộn memory với token recall. |
| scope:conjunction:not_enough_info | not_enough_info | incomplete | Hai attempt của part memory đều nêu missing token recall; guard missing_information_wrong_metric chặn đúng. Chưa assess xong các part, không có aggregate. Missing cần là identity/binding extractor và evidence cho đúng part. |
| scope:condition:support | support | support | Collective three batches có each gained yield after update trong low-temperature group; không mượn high-temperature. Support đúng, model_explanation bị cụt. |
| scope:condition:contradict | contradict | contradict | one lost yield thuộc chính low-temperature population sau update; false witness refute ALL đúng. |
| scope:condition:not_enough_info | not_enough_info | not_enough_info | NEI đúng vì low-temperature chưa đo yield. Missing_information lại lặp một fact đã biết về high-temperature; không phải thông tin thiếu của claim. |

## Hướng tiếp theo

1. Giữ ZIP/source/predictions cellfix9 này làm mốc. Chưa sửa candidate đã phát hành hoặc chạy validation30 trong lượt audit.
2. Trước sửa ca SOME, chốt binding của “complete audited set” có đủ để chỉ đúng “audited cache nodes” không. Frozen gold hiện là contradict; audit ghi đúng kết quả sai theo gold đó, không tự relabel. Nếu annotation cần sửa, dùng fixture/version riêng và giữ score gốc để đối chiếu. Không bỏ modifier hoặc hard-code tên Birch/Elm/Fir để làm xanh một ca.
3. Candidate tiếp theo cần giải quyết closure ledger cho SOME, repair thiếu identity/đúng part, và missing-information bằng cấu trúc/source constraints thay cho regex chặn từng tên tác giả. Cân nhắc dựng explanation từ ledger đã kiểm, giữ nguyên model prose trong trace để audit; không coi model prose chưa kiểm là bằng chứng. Đây là đề xuất, chưa triển khai.
4. Thêm regression từ ba trace thất bại và câu mới, gồm prose ngược truth ở NONE, member có kết quả khác nhau, target absent và thiếu baseline. Kiểm code/decoder có thể biểu diễn kết quả hợp lệ trong budget hiện tại. Giữ model/revision/budget/gate.
5. Đóng băng candidate mới rồi chạy smoke -> probe18 + human review mới -> full39. Chỉ khi **39/39, false support=0, runtime=0, trace/budget đạt**, và review evidence/explanation đủ 39 ca đạt, mới chạy validation30 đã khóa. Không tune trên validation30.

## Giới hạn

Đã kiểm toàn bộ manifest, replay các stage và đọc claim/context/prediction của đủ 39 ca. Không gọi model mới, chưa có human review full39, chưa đo validation30/E2E. Stored provenance chứng minh tính nhất quán artifact, không xác thực độc lập máy Colab.
