# Đối chiếu logic_v3 — kiểm tra ngày 2026-10-13

**Thí nghiệm hoàn thành, chưa đạt gate chất lượng.** Run 20261012T165922Z có
37/39 nhãn đúng nhưng hai false support. Không tích hợp candidate vào serving,
không đổi gate 39/39 hoặc coi exit 1 là setup bị hỏng.

## Bằng chứng đã kiểm

- ZIP 61.011 bytes, SHA256
  `878bad4550f0364224325e5bdfec48a914a00e66e2f1c7a3725863dc7bca37ff`.
  CRC đạt, 37/37 output files khớp size/hash, không thiếu file trong manifest.
- 45 runtime patch files, 13 verifier patch files và 5 provenance sources khớp
  repo. Prompt/profile, criteria, input datasets và historical model pairing
  đều khớp bản đóng băng.
- Replay offline khớp 39 predictions từ 40 calls đã lưu, gồm một ModelOutputError
  được repair thành công. Messages chỉ chứa claim/context; gold/rationale và
  proposed label không đưa vào verifier. Metrics, 117 comparisons, hai baseline
  metrics, summary và 39 pending review rows chấm lại khớp.
- Kaggle setup/pip check/preflight đạt; **161 tests đạt trong 3,157s**.
  Stage verifier 311.526,76 ms, gồm nạp model; tổng elapsed assess 242.799,176 ms.
  Cost backend không báo (`null`), không suy diễn thành zero.
- Không gọi model mới khi audit. Output gốc giữ tại
  `research-runs/kaggle-20261012T165922Z`.

[Audit JSON](blind-verifier-audit-20261012T165922Z.json),
[bản nháp review](blind-verifier-review-draft-20261012T165922Z.jsonl).
Review của assistant không thay review bằng người/annotation độc lập.

## So với scope_v2 trên cùng 39 ca

| Chỉ số | scope_v2 | logic_v3 |
| --- | ---: | ---: |
| Đúng nhãn | 33/39 (84,62%) | 37/39 (94,87%) |
| Ca cũ | 11/12 | 11/12 |
| Ca mới | 22/27 | 26/27 |
| Nhãn sai | 5 | 2 |
| False support | 1 | **2** |
| Support precision theo nhãn gold | 12/13 (92,31%) | **13/15 (86,67%)** |
| Verification failures | 1 | 0 |
| Calls | 41 | 40 |
| Macro-F1 | 0,85399 | 0,94952 |
| Automated gate | false | false |

V3 sửa năm ca không đạt ở v2 (accuracy_conflict, hai ca existential, time,
conjunction) nhưng partial_accuracy chuyển từ NEI đúng thành support sai.
Direction:contradict vẫn sai. Accuracy tăng đồng thời false support tăng;
chưa đủ bằng chứng an toàn để Writer dùng các claim được candidate xác nhận.
Prompt và repair policy thay cùng lúc; đây không phải ablation riêng từng phần.

## Hai lỗi nhãn còn lại

1. **partial_accuracy**: claim gồm giảm memory và giữ accuracy. Context chỉ có
   memory. Model xác nhận support, quote/explanation chỉ kiểm memory và bỏ
   accuracy. Đây là lỗi độ phủ các mệnh đề, không phải thiếu context truyền vào.
2. **direction:contradict**: quote chứa before=42 ms, after=55 ms. Model vẫn gọi
   là giảm. Phép so sánh số học cho thấy after > before. Lỗi này xuất hiện cả
   v2/v3, dù v3 prompt đã có quy tắc số học; tăng hướng dẫn chưa giải quyết được.

Không có HTTP/quota/GPU failure trong trace này. Một raw response universal:support
có JSON sai cú pháp; repair lần hai thành công và vẫn trong budget. Không thấy
quote validation failure cuối cùng. Điều đó chỉ chứng minh trên lượt này,
không chứng minh lỗi quota Reader đã được giải quyết.

## Nhãn đúng nhưng semantic/evidence vẫn cần sửa

- **both_supported**: quote đủ hai vế, nhưng explanation nói accuracy không cần
  kiểm vì claim chỉ nói memory. Explanation đọc sai phạm vi claim.
- **cross_sentence**: quote thiếu câu hai datasets, explanation không chứng minh
  vế đó. Label support đúng chưa đủ để nghiệm thu.
- **existential:contradict**: quote/explanation chỉ nêu Birch/Elm tăng latency;
  bỏ qua population đầy đủ và Fir không đổi. Một vài witness âm không refute SOME.
- **conjunction:support**: chỉ quote/explain giảm memory, bỏ token recall.
- **conjunction:contradict**: explanation nhắc recall giảm, nhưng quote chỉ chứa
  memory giảm, không quote bằng chứng phản bác.
- **metric:NEI**: label đúng nhưng explanation gán số đo recall sang precision.
- Các ca irrelevant/condition:NEI còn được gắn cờ về yêu cầu ngoài claim hoặc
  quote khác scope. Người đánh giá cần chấm rubric trên cả 39 ca.

Các nhận xét trên là triage của assistant, chưa được người đánh giá độc lập xác nhận.

## Phần đã thực hiện sau audit

Thêm **evidence-screen-v1**, runner offline và tám tests không gọi model:

- kiểm quantity trong claim có xuất hiện trong quote;
- gắn cờ vế AND không có content-word overlap với quote;
- tính hướng before/after bằng Decimal trong dạng câu được hỗ trợ, cùng unit,
  một atomic direction và một phép so sánh; scope/unit chưa rõ thì yêu cầu review;
- giữ nguyên nhãn model, không đổi gold, không tự đánh dấu claim đã xác minh.

Kết quả trên output đã lưu:

| Chỉ số bộ lọc | Kết quả |
| --- | ---: |
| Candidate support | 15 |
| False support gắn cờ | 2/2 |
| Gold-support gắn cờ | 2/13 |
| Support không bị screen gắn cờ | 11 |
| False support còn trong 11 ca đó theo gold | 0 |
| Model calls mới | 0 |
| Đúng nhãn model gốc | **37/39, không đổi** |

Hai gold-support bị gắn cờ là cross_sentence và conjunction:support: context
đủ hỗ trợ claim nhưng output quote thiếu một vế. Đây là phân biệt giữa claim
đúng theo dataset và chất lượng bằng chứng của output, không tự coi gold sai.

Các rule được viết sau khi xem run này. Đây là **post-hoc diagnostic trên dữ liệu
development**, không phải kết quả prospective hoặc bằng chứng generalization.
Presence/overlap không chứng minh entailment; synonyms, numeric formats, unit
conversion, negation/quantifiers và grammar ngoài phạm vi còn cần review.
Ví dụ một số đo xuất hiện trong câu phủ định vẫn có thể vượt presence check.
`screen_clear` không có nghĩa verified; mọi result giữ `claim_verified=false`.
Screen chưa được nối vào serving hoặc notebook GPU.

[Kết quả screen](../research-runs/evidence-screen-20261012T165922Z-v1/summary.json),
[review 39 rows](../research-runs/evidence-screen-20261012T165922Z-v1/screen-review.jsonl).

## Hướng đi tiếp theo

Không chạy lại notebook v3 hoặc toàn hệ với policy không đổi.
Ưu tiên **structured checks cho từng factual part và numerical tool**, kiểm
annotation/semantic bằng người, đóng băng lượt mới rồi mới chạy GPU.
[Checklist và kế hoạch implementation](VERIFIER_HYBRID_NEXT_STEPS.md).

Reader PDF, Summarizer heldout_3, tám ca E2E và đánh giá độc lập toàn hệ vẫn
chưa hoàn thành. Dự án chưa đạt nghiệm thu.
