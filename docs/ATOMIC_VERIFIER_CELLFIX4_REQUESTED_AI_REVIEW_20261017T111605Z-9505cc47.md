# Review theo yêu cầu người dùng — 18 claim cellfix4

**Kết luận: 15/18 đạt đầy đủ yêu cầu biểu diễn; 010/014/018 cần sửa metric.**
Cả 18 giữ nội dung semantic theo review AI; không dùng con số đó để tuyên bố tuân thủ prompt 100%.

Reviewer: Codex, reviewer_kind=assistant. Đây là review AI của output Qwen cố định; không phải chữ ký human. Tôi không sinh lại decomposition để thay output đang được chấm. Ghi chú AI cũ không phải chuẩn chấm.

Tệp người dùng gửi khớp chính xác 18 claim/20 parts của probe. Quote, offset và numeric span đều đã kiểm; không bỏ nội dung nguồn.

Chuẩn chấm là claim gốc, năm rubric semantic và prompt đã đóng băng. Semantic binding đúng và metric-format compliance là hai kết quả riêng; không đánh đồng lỗi format với sai property hoặc sai nhãn.

Tôi đính chính cách gọi trước đây: prompt không chỉ “ưu tiên” named property. Nó yêu cầu: **When a property is named, copy that property without its change verb**. Vì vậy ba metric còn change verb chưa được tôi chấp nhận là đạt đầy đủ contract.

| Claim | Predicate | Coverage | Quantifier/population | Entity/property binding | Time/condition | Metric format | Kết luận |
|---|---|---|---|---|---|---|---|
| 001 | Đạt | Đạt | Đạt | Đạt nghĩa | Đạt | Đạt | Đạt |
| 002 | Đạt | Đạt | Đạt | Đạt nghĩa | Đạt | Đạt | Đạt |
| 003 | Đạt | Đạt | Đạt | Đạt nghĩa | Đạt | Đạt | Đạt |
| 004 | Đạt | Đạt | Đạt | Đạt nghĩa | Đạt | Đạt | Đạt |
| 005 | Đạt | Đạt | Đạt | Đạt nghĩa | Đạt | Đạt | Đạt |
| 006 | Đạt | Đạt | Đạt | Đạt nghĩa | Đạt | Đạt | Đạt |
| 007 | Đạt | Đạt | Đạt | Đạt nghĩa | Đạt | Đạt | Đạt |
| 008 | Đạt | Đạt | Đạt | Đạt nghĩa | Đạt | Đạt | Đạt |
| 009 | Đạt | Đạt | Đạt | Đạt nghĩa | Đạt | Đạt | Đạt |
| 010 | Đạt | Đạt | Đạt | Đạt nghĩa | Đạt | Chưa đạt | Cần sửa |
| 011 | Đạt | Đạt | Đạt | Đạt nghĩa | Đạt | Đạt | Đạt |
| 012 | Đạt | Đạt | Đạt | Đạt nghĩa | Đạt | Đạt | Đạt |
| 013 | Đạt | Đạt | Đạt | Đạt nghĩa | Đạt | Đạt | Đạt |
| 014 | Đạt | Đạt | Đạt | Đạt nghĩa | Đạt, đọc cùng quote | Chưa đạt | Cần sửa |
| 015 | Đạt | Đạt | Đạt | Đạt nghĩa | Đạt | Đạt | Đạt |
| 016 | Đạt | Đạt | Đạt | Đạt nghĩa | Đạt | Đạt | Đạt |
| 017 | Đạt | Đạt | Đạt | Đạt nghĩa | Đạt | Đạt | Đạt |
| 018 | Đạt | Đạt | Đạt | Đạt nghĩa | Đạt | Chưa đạt | Cần sửa |

## Nhận xét từng claim

**decompose:001 — Đạt**

Model Juniper uses 25% less memory and retains 94% accuracy.

Part 1: Part 1 giữ đúng Model Juniper, memory, mức giảm 25%. Không tự thêm baseline không có trong claim; baseline thuộc phần xác minh bằng chứng sau đó.

Part 2: Part 2 giữ retains 94% accuracy; entity kế thừa Model Juniper đúng. AND là connector hợp lệ. Hai property độc lập được tách, không trộn hai số.

**decompose:002 — Đạt**

Model Juniper retains 94% accuracy.

Part 1: Một sự việc giữ accuracy 94%; entity Model Juniper, property accuracy và numeric requirement 94% đúng. Không có restriction bị thêm hoặc mất.

**decompose:003 — Đạt**

The study used human labels.

Part 1: Động từ used cùng đối tượng human labels được giữ đầy đủ trong metric; không đặt metric chỉ là used. Không có named measurement property để phải tự thêm.

**decompose:004 — Đạt**

The new index caused the latency improvement.

Part 1: Quan hệ caused được giữ trong quote. Entity new index và property latency đúng. Việc giữ nguyên cấu trúc nhân quả không chứng minh đã có bằng chứng nhân quả.

**decompose:005 — Đạt**

All tasks improved after compression.

Part 1: All và population tasks giữ nguyên; after compression là restriction đúng. Claim chỉ nói improved, chưa nêu đại lượng cụ thể; decomposition trung thành không được tự đoán accuracy/latency. Đây là giới hạn của claim gốc.

**decompose:006 — Đạt**

The report evaluated four models on two datasets.

Part 1: Một event evaluated với hai đối số số liệu: four models và two datasets. Cả hai requirement có đúng value/unit/span. Không ép tách hai đối số thành hai factual fragments; condition giữ on two datasets.

**decompose:007 — Đạt**

Training took 12 seconds.

Part 1: Training là entity; metric took 12 seconds giữ quan hệ và measurement. 12 seconds là thời lượng được đo, không phải restriction thời điểm, nên time rỗng hợp lý.

**decompose:008 — Đạt**

The sample contained 240 documents.

Part 1: Sample là entity; contained 240 documents giữ quan hệ chứa và đúng đối tượng được đếm. Numeric requirement 240/documents đúng, không tách count thành part rời.

**decompose:009 — Đạt**

On the tested dataset, the method improved recall.

Part 1: Chỉ method trên tested dataset; property recall đúng và hướng improved giữ trong quote. Dataset condition không bị biến thành time hoặc bỏ tested.

**decompose:010 — Cần sửa**

Every validation shard improved recall after the revision.

Part 1: Every được giữ bằng all; validation shard, after the revision và quan hệ cải thiện recall không mất. Entity/property binding đúng nghĩa, nhưng metric improved recall vi phạm yêu cầu copy property không kèm change verb. Metric đúng format phải là recall.

**decompose:011 — Đạt**

At least one audited cache node reduced response time after the patch.

Part 1: At least one chuyển đúng thành some; audited là population modifier phải được giữ và đã có trong audited cache node. Response time và after the patch đúng. Không biến existential thành all.

**decompose:012 — Đạt**

None of the monitored pumps leaked during the overnight test.

Part 1: None chuyển đúng thành none; monitored pumps giữ population. Leaked là predicate dương trước khi áp none, tránh phủ định hai lần. During the overnight test được giữ nguyên.

**decompose:013 — Đạt**

The North gateway reduced its error rate after calibration.

Part 1: North gateway giữ định danh North; its error rate thuộc đúng gateway. Hướng reduced giữ trong quote; after calibration không bị bỏ hoặc chuyển sang đối tượng khác.

**decompose:014 — Cần sửa**

Every weekly trial conducted in May improved throughput.

Part 1: Every weekly trial conducted in May là tập được lượng từ all áp dụng. Quote đầy đủ giữ conducted in May; condition in May chỉ được diễn giải như bộ lọc population, không suy ra improvement xảy ra trong May. Đánh giá scope là đạt khi đọc cùng part.quote, như assessment prompt quy định; scope JSON riêng không nêu rõ owner của restriction. Metric improved throughput vi phạm named-property format, cần throughput.

**decompose:015 — Đạt**

The patch reduced median request latency.

Part 1: Metric median request latency giữ cả median và request, không đổi sang mean hoặc latency chung. Entity patch và hướng reduced đúng; không tự thêm thời gian.

**decompose:016 — Đạt**

The configuration change increased precision.

Part 1: Configuration change là entity, precision là property; increased vẫn nằm trong quote. Không đổi precision thành recall và không tách change khỏi entity.

**decompose:017 — Đạt**

After tuning, the extractor decreased memory use and increased token recall.

Part 1: Part 1 giữ extractor, giảm memory use và After tuning. Prefix đầu câu có dấu phẩy thực sự dùng chung cho hai predicate.

Part 2: Part 2 giữ tăng token recall; kế thừa extractor và After tuning đúng. Không làm mất token hoặc trộn hướng tăng recall với giảm memory use.

**decompose:018 — Cần sửa**

Every batch in the low-temperature group gained yield after the update.

Part 1: All chỉ áp dụng batch trong low-temperature group; condition giữ nguyên giới hạn population. After the update và quan hệ gained yield giữ trong quote. Metric gained yield đúng property nhưng sai yêu cầu named-property format; cần yield.

## Kết luận xử lý

Chưa chấp nhận kết luận “18/18 đạt đầy đủ”. Ba thay đổi đề nghị, chưa áp dụng vào predictions: 010 metric=recall; 014 metric=throughput; 018 metric=yield. Không tự chuyển in May thành thời điểm improvement.

Nếu sửa implementation, dùng một quy tắc chung cho named properties trong validator và decoder, kèm regression bằng câu mới và các negative cases; không hard-code mã claim. Đóng băng candidate mới và chạy lại smoke/probe, thay vì sửa predictions sau run.

Review decomposition không xác nhận 18 phát biểu đúng với bài báo. Không có ngữ cảnh/bằng chứng tương ứng trong file này để suy ra support/contradict hoặc false support. Không có lần chạy full39 mới.

Bản JSON đi kèm ghi reviewer_kind=assistant, human_review_completed=false. Không sửa gate hoặc tạo semantic-review.json mang danh human.
