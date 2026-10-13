# Đối chiếu probe v3 — 20261013T135905Z-ac194776

**Gate chưa đạt: 13/18 decomposition hợp lệ, 5 incomplete.**
Lượt model đã thử đủ 18 claim; chưa được chuyển sang 39 ca hoặc tích hợp.

## Bằng chứng và kết quả

ZIP SHA256:
`a92ca909fec97dec644c20268fefc5591995bea2daf647853fff504253530714`.
CRC đạt; 37/37 output files khớp hash/size, đủ mọi file ZIP trừ chính manifest.
45/45 runtime, 28/28 verifier patch và 13 frozen sources khớp repo v3 khi audit,
trước sửa v4. Criteria/contract/data/prompt đúng phiên bản. Recorded model,
revision/tokenizer/settings khớp baseline; không hash lại trực tiếp GPU weights
ở local. Đã replay 18 predictions, đối chiếu 27 calls, tính lại lỗi và token.

| Mục | Kết quả |
|---|---:|
| Test Kaggle | 206/206 đạt |
| Setup/preflight/freeze | Đạt |
| Claim đã thử / hợp lệ / incomplete | 18 / 13 / 5 |
| Calls | 27, dưới cap 36 |
| Đạt attempt 1 / repairs / repairs thành công | 9 / 9 / 4 |
| Generated / prompt tokens | 1.385 / 26.247 |
| Output tokens tối đa một call | 78, dưới cap 1.536 |
| Thời gian stage probe | 165,581 giây, chưa tính setup |
| USD / gate / human review | null / false / pending |

Không có assessment/label trong probe; các số trên không phải accuracy verifier.
V2 đạt 12/18, v3 đạt 13/18 về cấu trúc. Chưa có bằng chứng scope/entailment đủ
để nghiệm thu. Original output lưu nguyên tại
`research-runs/kaggle-20261013T135905Z-ac194776/`.

## Nguyên nhân đã thấy

27 attempts gồm 13 hợp lệ và 14 bị từ chối: **9 invalid JSON, 2 sai quantifier,
3 bỏ sót nội dung**. Các lỗi đầu tiên được ghi có thể che lỗi khác trong cùng draft.

- `001`, `009`, `017`: hai attempts đều sai JSON; draft còn có quantifier sai
  hoặc paraphrase scope. Cú pháp `"unresolved:[]}` vẫn lặp lại dù đã đổi repair.
- `006`: gán `all` cho câu có số đếm four/two, đồng thời bỏ dataset khỏi quote.
  Số đếm không đồng nghĩa lượng từ all.
- `013`: JSON lỗi rồi repair vẫn thiếu thời gian trong quote.
- V3 đã xử lý đúng chữ hoa `Training`, leading AND, metric latency/precision
  tốt hơn ở một số ca. Các cải thiện đó chưa giải quyết hết lỗi.

Model output log chứng minh các lỗi. Chưa có bằng chứng quy lỗi toàn bộ cho NF4,
kích thước model hoặc repetition penalty. Config ghi nhận repetition penalty
1.05; v4 giữ giá trị này và không đổi trọng số để thử chính sách decoding.

## Review đủ 18 ca bằng AI

[Review JSONL](decomposition-semantic-review-20261013T135905Z-ac194776.jsonl)
ghi từng claim, canonical plan và năm judgments. Đây là review AI, không điền
phiếu human thành pass. Kết luận: **9 rõ ràng đạt, 4 cần làm rõ binding/scope,
5 chưa có plan hợp lệ**.

| ID | Review AI | Điểm chính |
|---|---|---|
| 001 | Chưa có plan hợp lệ | JSON; memory usage không nguyên văn; repair đổi quantifier |
| 002 | Đạt | Entity và accuracy 94% |
| 003 | Đạt | Quan hệ dùng human labels |
| 004 | Cần làm rõ | Scope index/improvement quá chung; causal relation vẫn trong quote |
| 005 | Đạt | All tasks, improved, after compression |
| 006 | Chưa có plan hợp lệ | Sai quantifier và thiếu dataset trong quote |
| 007 | Đạt | Training đúng case; đủ 12 seconds; numeric chưa đo |
| 008 | Cần làm rõ | Count 240 documents giữ trong quote; metric contained chung |
| 009 | Chưa có plan hợp lệ | JSON và quantifier; draft dataset đã đúng loại condition |
| 010 | Đạt | All, recall và after revision sau repair |
| 011 | Cần làm rõ | Scope bỏ population modifier audited |
| 012 | Cần làm rõ | Scope bỏ population modifier monitored |
| 013 | Chưa có plan hợp lệ | Thiếu after calibration trong quote |
| 014 | Đạt | All weekly trials, in May, throughput |
| 015 | Đạt | Metric median request latency đúng loại |
| 016 | Đạt | Precision và direction trong quote |
| 017 | Chưa có plan hợp lệ | Leading AND được cho phép; JSON vẫn sai |
| 018 | Đạt | All, low-temperature group và after update |

9/18 ở review AI không thay gate chính thức hoặc chứng minh generalization.
Dataset/reviewer độc lập vẫn cần trước nghiệm thu toàn hệ.

## V4 đã triển khai để thử tiếp

Đổi chính sách sinh output sang schema-constrained decoding; chưa có inference v4.
Thư viện lọc token theo JSON schema thay vì chỉ dựa vào prompt.
[Tài liệu dự án lm-format-enforcer](https://github.com/noamgat/lm-format-enforcer).

- Giữ prompt v3, model/revision/data và budget; thêm decoder 0.11.3 với
  interegular 0.3.3, required keys/types/enums. Không sửa JSON lỗi sau inference
  để giả báo output hợp lệ.
- Quote và scope lấy từ enum trích đoạn nguyên văn theo biên từ của claim.
  Quantifier rõ ràng bị giới hạn theo wording đã dùng trong validator; không dùng gold.
- Schema áp dụng cả decomposition và assessment. Source, coverage, arithmetic,
  scope, semantic review và gate nhãn vẫn chạy sau generation. Truncation vì
  token/time limit vẫn có thể khiến JSON không hoàn tất và phải trượt gate.
- Adapter tiện ích của LMFE 0.11.3 import đường `transformers.tokenization_utils`
  đã mất ở runtime 5.16.1; kiểm tra local thấy ImportError. Code dùng public
  TokenEnforcer core với callback Transformers để tránh đường import đó.
  [API generate của Transformers](https://huggingface.co/docs/transformers/main/en/main_classes/text_generation).
- Shared backend thêm hook trả `{}` mặc định; serving dùng cùng kwargs cũ.
  Candidate loader riêng bật ràng buộc. Notebook cài hai dependency trước test,
  kiểm hash nguồn cũ trước thay hook; không bật decoder cho workflow serving.
- Giới hạn mới: source enum hỗ trợ tối đa 80 từ phân cách bằng whitespace.
  Các scope khác, relation nhân quả, population và mọi số liệu trong part vẫn
  phải review. Schema không chứng minh ngữ nghĩa.

83 runtime tests đã đạt trong suite tổng; một test đóng gói phát hiện thiếu
base hash cho shared adapter. Sau sửa builder, cả 3 test đóng gói đạt trên
notebook cuối. Tổng **86 unique test cases đều đã đạt**, qua hai lượt kiểm tra;
không phải một lượt suite hoàn toàn xanh duy nhất. Test decoder dùng thư viện
thật, tokenizer nhỏ/model giả lập; chưa test Qwen GPU v4.
[Validation](decomposition-v4-validation.json), [log](decomposition-v4-tests.log).

Chạy [notebook v4 ba cell](../scripts/kaggle_decomposition_probe_v4.ipynb) theo
[hướng dẫn](DECOMPOSITION_PROBE_V4_KAGGLE.md). Sau 18/18 và review mệnh đề mới
chạy 39 ca; sau gate verifier mới tích hợp, Reader, Summarizer và tám ca E2E.
Source/notebook/criteria v3 được giữ tại `research-runs/atomic-verifier-v3-source-snapshot/`.
