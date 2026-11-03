# Full39 Cellfix11 — chưa được chạy validation30

Run: `20261026T150123Z-615bf4eb`.
ZIP: `output-cellfix11-fresh-20261026T150123Z-615bf4eb (3).zip`.
SHA256: `5dadfe8e17b86b3172c88aed423c953b0ccd79a7a003bd0b6528709ab7ad6076`.

**Giữ `RUN_VALIDATION30=False`.** Full39 chạy đủ và không crash, nhưng chỉ
**36/39 nhãn đúng**, chưa đạt gate 39/39. Human review không thay thế gate này.

## Kết quả đã xác minh

| Phép kiểm | Kết quả |
|---|---|
| Output/input hash | **109 output / 124 input** khớp release và manifest |
| Same-run lineage | ZIP smoke/probe `(2)` được giữ nguyên bytes, trừ root status/manifest cập nhật |
| Model/source/config | Đúng Cellfix11 release, pinned revision/quantization/seed/budget/gate |
| Regression Colab | **342/342**, bốn validate-only đạt |
| Smoke | 12/12 nhãn đúng, false support=0, runtime=0 |
| Probe | 18/18 decomposition hợp lệ; human review Trí Công đúng hash, admission đạt |
| Full39 | **36/39 đúng; false support=0; runtime=0** |
| Dataset groups | original_contracts 12/12; scope_regression 24/27 |
| Gold support | 11/12 được nhận đúng; 1 bị trả NEI |
| Full39 calls/tokens | 85 calls; 9.440 generated; 110.212 prompt, trong budget |
| Stop reasons | 39 completed; không repair exhaustion, deadline hoặc runtime failure |
| Overall | automated_gate_pass=false; human_review=pending; overall_pass=false |
| Validation30 | Chưa chạy; admission replay từ chối vì full39 chưa đạt |

Replay đủ 69 prediction rows và **131 call triplets** của smoke/probe/full39:
raw JSON, parsed output, source/prompt/schema trace, normalization/assessment,
stored parts/explanations, numeric records và aggregate. Metrics tính lại khớp.
Tất cả call inference valid ngay attempt đầu; cả ba nhãn sai không bị validator
đưa vào repair. Exit code 1 của verifier39 là **quality gate failure**, không
phải lỗi Colab/CUDA hay JSON parse.

Validation binding và annotation review/lock gốc đúng hash. Bộ39 khớp đúng
Cellfix10 baseline, không có relabel hoặc thay context. Source/predictions trong
ZIP được giữ nguyên; audit không chạy model mới hoặc thay serving.

## Ba ca sai và cơ chế từ trace/code

### 1. `scope:entity:support`: support -> NEI

Claim nói **North gateway reduced error rate after calibration**. Source có
North decreased và South increased. Observation member=North, truth=unknown,
nhưng quote duy nhất là **South gateway's error rate increased**.

Validator vẫn chấp nhận. `member_scope_issue()` không tìm thấy member trong
quote rồi dùng `cited or source`, quay về clause North ở toàn context. Kiểm
time/condition không phát hiện citation thuộc subject khác. Các guard entity
trước đó cũng lỏng với truth=unknown.

### 2. `scope:entity:contradict`: contradict -> NEI

Source có **North error rate increased**, trực tiếp refute claim reduced, nhưng
model trả unknown và quotes=[]. `decision_evidence()` không yêu cầu decisive
witness cho trường hợp này: guard nhiều từ vốn bảo vệ qualified population
cũng loại atomic entity `North gateway` trước khi xét fact.

Điều này giải thích vì sao unknown không bị repair dù evidence của North đã có.
Đây là lỗ hổng quyết định/binding; không cần đổi gold hay đòi thêm dữ liệu.

### 3. `scope:condition:not_enough_info`: NEI -> contradict

Source nói **low-temperature chưa được đo yield changes**; high-temperature
được báo gained yield. Model đã bỏ member high-temperature, nhưng chọn toàn
clause `no yield changes were measured for that group` làm **member=false**,
quote câu low-temperature, rồi refute ALL.

Absence không phải false outcome. Helper mới nhận diện được direct absence này
nhưng áp quote rule cho **unknown**; nhánh **false** vẫn qua. `_MISSING` cũ không
bắt cấu trúc `no ... changes were measured`, nên `evidence_issue()` không chặn.
Scope đúng nhóm mới chỉ giải quyết một phần; truth của absence vẫn sai.

`GUARD_DIAGNOSTICS.json` tái hiện cả ba output sai được **validator và LMFE
character-token fixture** chấp nhận. Đây là kiểm code bằng dữ liệu lưu, không
phải Qwen inference mới. Không đổi bad trace thành prediction đúng để tính điểm.

## Những phần đã cải thiện và giới hạn còn lại

- `contract:causality_missing`: NEI, cite câu không thiết lập causal relationship,
  missing `causal_relationship` đúng.
- `scope:metric:not_enough_info`: cite **Precision was not measured.**, không
  còn dùng Recall rose... làm bằng chứng thiếu precision.
- SOME closed roster, NONE polarity/coverage, May population, precision numeric
  pair, direction arithmetic và low-temperature support/contradict vẫn khớp gold.
- Các cảnh báo identity còn: irrelevant dùng câu absence làm member, conjunction
  dùng measurement/workload làm member khi extractor vắng mặt. Nhãn NEI đúng
  không biến những observation này thành identity tốt.

Đã đọc đủ 39 claim/context/prediction; nhận xét từng ca trong
`EVIDENCE_REVIEW_39.md` và `AI_EVIDENCE_AUDIT.json`. Không tạo human signature.

Zero false support hiện chỉ có nghĩa không có predicted support trên 27 gold
non-support của bộ development này. Nó không loại bỏ false contradiction, bỏ
sót support hoặc chứng minh khả năng khái quát trên validation30.

## Bước tiếp trước validation30

1. Giữ baseline Cellfix10 **39/39 nhãn nhưng còn lỗi semantic** và run Cellfix11
   **36/39, false support=0, runtime=0** làm hai mốc riêng.
2. Candidate tiếp cần sửa chung: quote/member binding cho unknown; phân biệt
   atomic named target với qualified population trong decisive-witness guard;
   absence semantics áp dụng trước truth ở mọi branch, không cho clause thiếu
   measurement làm member=false. Dùng chung quy tắc ở validator/decoder.
3. Thêm regression từ ba trace này cùng tên entity, metric, nhóm và cấu trúc
   absence mới. Giữ model/revision/budget/gate; không tune trên validation30.
4. Đóng băng rồi chạy smoke -> probe18 + human review mới -> full39. Chỉ khi
   full39 39/39, false support=0, runtime=0, trace/budget đạt và human evidence
   review sạch của đúng candidate/predictions thì mới chạy cell7.

Đây là hướng sửa tiếp, **chưa triển khai candidate mới trong lượt audit này**.
Không bật cell7 hoặc đổi file review/metrics thành đạt để vượt gate.

## Giới hạn audit

Hash/provenance kiểm tính nhất quán artifact, không chứng thực độc lập host.
Chưa chạy validation30, chưa có human review full39 đạt, chưa promote serving
hoặc kiểm Reader/Summarizer E2E trong lượt này.
