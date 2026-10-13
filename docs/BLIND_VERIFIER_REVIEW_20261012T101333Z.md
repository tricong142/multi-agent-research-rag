# Đối chiếu verifier thật — 20261012T101333Z

**Chương trình đã hoàn tất đánh giá; cả hai ứng viên chưa đạt gate chất lượng.**
Base instruct là ứng viên nên ưu tiên cho vòng sửa tiếp theo, chưa đủ điều kiện
đưa vào serving. Không chạy lại notebook cùng cấu hình; không đổi tiêu chí v1
để biến 11/12 thành pass. Không cần sửa môi trường hoặc tăng retry cho lượt này.

## 1. Bằng chứng đã kiểm

ZIP `rag-validation-20261012T101333Z.zip`, 38.292 bytes, SHA256
`4c8e6c8868714f28e78d5372ab5be845497ec5c995bcefb9adf4436c7bcfba6c`.

| Kiểm tra | Kết quả |
| --- | --- |
| ZIP/manifest | CRC đạt; 36/36 file đúng hash/kích thước; không trùng/thừa entry. |
| Runtime/source | 45/45 runtime patch và 5/5 verifier patch khớp repo; 5 source trong provenance khớp. |
| Criteria/data/baseline | Đúng bản đã đóng băng; không đổi sau khi chạy. |
| Kaggle environment | pip check đạt; 145 tests đạt trong 3,041 giây; preflight đạt. |
| Replay offline | 24/24 predictions tái hiện từ 27 response; messages, token budget và attempts khớp. |
| Blinding | User message chỉ có claim/context, kể cả repair; không có gold/proposed label hoặc reasoning Judge. |
| Chấm lại | Metrics, 48 comparisons theo cặp định trước, baseline-metrics và summary đều khớp. |
| Review | 24 rows đúng input/output, vẫn pending; không có human sign-off. |
| Weights/tokenizer | Hash ghi trong provenance khớp lượt confidence trước cho cả hai backend. Audit không tải lại weights. |

Hash xác nhận tính nhất quán của gói nhận được, không phải chứng thực độc lập
từ Kaggle/nhà cung cấp. Replay chỉ dùng response đã lưu, không sinh kết quả mới.
Generation config gốc có do_sample=true nhưng backend gọi generate với
do_sample=False; không suy ra lượt này sampling từ config gốc.

## 2. Kết quả và ý nghĩa exit 1

| Backend | Nhãn đúng /12 | False support /12 | Runtime failure /12 | Calls | Gate |
| --- | ---: | ---: | ---: | ---: | --- |
| Fine-tuned | 10 | 2 | 0 | 15 | Trượt |
| Base instruct | 11 | 0 | 0 | 12 | Trượt |

`experiment_completed=true`, 24 predictions, 27 calls; `automated_gate_pass=false`.
Stage mất 217,90038 giây (~3 phút 38 giây), exit 1 do ứng viên không đạt, không
phải setup crash hoặc lỗi quota Gemini. Không có số liệu USD: cost_usd=null.
Warning HF Hub chưa đăng nhập không ngăn model tải/chạy đủ trong lượt này.

Baseline repair lịch sử nhận 4/12 nhãn đúng và 2/12 nhãn sai ở threshold 0,7.
Blind verifier đo quyết định nhãn rời rạc; baseline đo ngưỡng confidence. Hai số
có thể đối chiếu trên cùng cases nhưng không đồng nhất ý nghĩa xác suất hoặc
chứng minh quan hệ nhân quả. Budget output cũng khác (384 so với 192 tokens).

## 3. Lỗi chính đã xác định

### Fine-tuned: hai false support do chỉ kiểm một phần claim

`partial_accuracy`: claim gồm giảm memory và giữ accuracy; context chỉ cung
cấp memory. Verifier vẫn trả support và missing_information rỗng.

`partial_memory`: context chỉ có accuracy nhưng verifier vẫn support cả claim.
Lần đầu model trả not_enough_info nhưng thiếu field explanation nên bị validator
từ chối; lần repair tạo output đúng schema nhưng đổi nhãn thành support sai.
Điều này chứng minh sửa cấu trúc thành công không đồng nghĩa sửa nội dung đúng.
Không nên giữ nhãn từ output chưa hợp lệ hoặc bỏ validator để làm case đạt.

Ba attempts bị từ chối của fine-tuned (`partial_memory`, `irrelevant`,
`causality_missing`) đều thiếu explanation. Repair giới hạn hai attempts hoạt
động đúng; tất cả cases cuối cùng có cấu trúc hợp lệ. Tăng retry không có căn cứ
giải quyết hai lỗi hiểu claim này.

`cross_sentence` có nhãn đúng nhưng evidence_quotes và explanation chỉ nhắc
bốn models, bỏ phần hai datasets. Cần review độ phủ bằng chứng, không chỉ nhãn.

### Base: nhầm phản ví dụ với thiếu thông tin

Case `scope`:

- Claim: `All tasks improved after compression.`
- Context: `Three tasks improved after compression, but a fourth task became less accurate.`
- Gold: contradict; model: not_enough_info.
- Model yêu cầu thêm hiệu năng của tác vụ thứ tư trước compression. Tuy nhiên,
  context đã nêu hướng thay đổi là kém chính xác hơn, đủ phản bác “tất cả cải thiện”.

Đây là lỗi về phạm vi khẳng định và đối chiếu hướng thay đổi. Lượt này nó dẫn
tới từ chối xác minh một claim sai, chưa dẫn tới false support; vẫn là nhãn sai
và không được tính pass theo tiêu chí 12/12 đã đóng băng.

`causality_missing` có nhãn đúng nhưng wording của explanation và thông tin
thiếu cần review: context đã nói nghiên cứu chưa xác lập quan hệ nhân quả,
model lại hỏi liệu quan hệ đó đã được xác lập chưa. Yêu cầu thêm bằng chứng
nhân quả cụ thể sẽ hữu ích hơn. Đây là nhận xét của trợ lý, chưa phải human review.

## 4. Vì sao wrong_label_agreements=0 vẫn có một nhãn sai?

Phép thử v1 chỉ chọn **một** nhãn sai cho mỗi case. Với gold contradict, nhãn
sai được thử là support. Base trả not_enough_info nên không đồng ý nhãn support
đó, nhưng vẫn khác gold. Gate all_correct_labels_recognized đã bắt lỗi này.

Đã đối chiếu thêm cả hai nhãn sai bằng code **offline trên predictions cũ**:

| Backend | Đồng ý nhãn đúng /12 | Đồng ý nhãn sai /24 alternatives | Support đúng | Support sai |
| --- | ---: | ---: | ---: | ---: |
| Fine-tuned | 10 | 2 | 4 | 2 |
| Base instruct | 11 | 1 | 4 | 0 |

Đây là phân tích bổ sung sau chạy, không thay criteria, summary hoặc gate v1.
36 comparisons/backend vẫn chỉ dựa trên 12 cases, không phải 36 mẫu độc lập.
Không diễn giải 0 false support trên bộ nhỏ này thành bảo đảm an toàn production.

## 5. Hướng làm tiếp theo, theo thứ tự

### Ưu tiên 1: sửa candidate base verifier trong một phiên bản mới

Giữ weights/revision base, validator và budget làm mốc. Chưa promote base vào
serving; không tiếp tục thử fine-tuned như ứng viên verifier mặc định ở vòng kế
tiếp. Không cần retrain hoặc đổi model lớn ngay từ bằng chứng hiện có.

Chuẩn bị prompt v2 nêu quy tắc tổng quát về all/every, some/at least one và
none; phản ví dụ trong đúng phạm vi đủ phủ định mệnh đề toàn thể. Phân biệt
“became worse” (đã có thông tin về hướng thay đổi) với một số đo hiện tại đơn lẻ
(có thể chưa đủ dữ liệu để kết luận cải thiện). Yêu cầu kiểm toàn bộ các vế của
claim và nêu rõ bằng chứng cho từng vế trong explanation.

Không hard-code `scope`, tên model, câu hỏi hoặc gold label vào inference;
không chỉ thêm nguyên mẫu đã sai vào prompt để làm riêng mẫu đó đạt.

### Ưu tiên 2: kiểm lại có kiểm soát sau khi đã sửa

Giữ nguyên 12 contracts v1 làm regression. Thêm các cặp development trước khi
chạy model, có người kiểm nhãn nếu có thể:

- All + một phản ví dụ; all + đầy đủ các trường hợp hỗ trợ.
- Some + một trường hợp hỗ trợ; some + chưa có trường hợp hỗ trợ rõ ràng.
- None + một trường hợp hỗ trợ; none + phủ định rõ cho cả phạm vi.
- Cùng chủ thể/thời điểm so với khác chủ thể/thời điểm.
- Hướng thay đổi rõ so với chỉ có số đo hiện tại.
- Claim nhiều vế: hỗ trợ đủ, hỗ trợ một phần và một vế bị phản bác.

Đóng băng criteria v2, dataset, prompt và nguồn trước inference; giữ kết quả v1
là baseline lịch sử. Chạy candidate base mới riêng; không chạy lại bốn profile
confidence cũ hoặc fine-tuned cùng cấu hình. Gate 12/12 trên contracts cũ phải
giữ; kiểm toàn bộ hai nhãn sai thay vì chỉ một, không false support và review
semantic vẫn bắt buộc. Cases mới do trợ lý tạo là development, không gọi là
held-out độc lập. Không bảo đảm prompt v2 sẽ đạt trước khi đo.

### Ưu tiên 3: nghiệm thu và tích hợp verifier sau khi đủ bằng chứng

Review label, quote, giải thích và thông tin thiếu trên output. Thử bộ độc lập
đã được phân tách/kiểm nhãn để tránh chỉ sửa cho 12 mẫu đã xem. Chỉ tích hợp
khi tiêu chí chất lượng đạt: verifier nhận claim/context trước, rồi code mới
so Judge. Bất đồng, thiếu thông tin hoặc lỗi output giữ claim chưa xác minh;
controller tìm thêm hoặc dừng theo budget; Writer chỉ nhận claim qua gate.
Đo thêm số calls, thời gian, bộ nhớ GPU và hành vi hết budget trong runtime.

### Các việc còn lại của dự án

Reader vẫn chưa đạt full PDF: run Gemini gần nhất có 503 với thông báo nhu cầu
cao. Không suy ra dịch vụ đã phục hồi từ ZIP verifier vì lượt này không gọi
Gemini. Khi quay lại Reader cần kiểm contract thực và quota; nếu phải chia
qua nhiều kỳ quota, cần checkpoint/resume theo trang trước lượt đọc dài.

Sau đó xử lý Summarizer heldout_3 nhầm baseline, chạy regression đủ tám ca E2E,
review câu trả lời/trích dẫn và hoàn thiện đánh giá độc lập/tài liệu bảo vệ.
Không tuyên bố dự án đã nghiệm thu chỉ vì notebook chạy hết hoặc tests code đạt.

## 6. Artifact và phạm vi lượt audit này

- [Audit JSON](blind-verifier-audit-20261012T101333Z.json): hash, replay, confusion và các lỗi thực đo.
- [Đối chiếu cả ba nhãn](blind-verifier-all-labels-20261012T101333Z.json): phân tích offline bổ sung.
- [Review draft 24 rows](blind-verifier-review-draft-20261012T101333Z.jsonl): tám rows được gắn cờ,
  chỉ là assistant triage; human_review vẫn pending. Không có cờ không đồng nghĩa đã đạt human review.
- ZIP gốc được giữ; giải nén tại `research-runs/kaggle-20261012T101333Z`.

Lượt này thực hiện audit, replay và hướng sửa. Không thay prompt/model, không
chạy inference/Gemini mới, không hạ gate và không đổi runtime serving.
