# Full39 cellfix10 — gate tự động đạt, validation30 chưa được mở

Run: `20261026T102553Z-54409fed`.
ZIP: `output-cellfix10-fresh-20261026T102553Z-54409fed.zip`.
SHA256: `9616c5cfbec7a58b7491a2d985b44c6b1fd8a915a99ba0ac116e884e2975301e`.

**Giữ `RUN_VALIDATION30=False`.** Full39 đã đạt gate tự động nhưng chưa có
human evidence review full39. AI audit còn đánh dấu ba ca về citation, scope
observation hoặc độ cụ thể của thông tin thiếu. Chưa đủ để ký semantic pass.

## Kết quả đã replay

| Hạng mục | Kết quả |
|---|---|
| Provenance | 117 output và 120 input khớp manifest/release/hash |
| Remote regression | 314/314; bốn validate-only đạt |
| Model/config | Đúng Qwen2.5-3B-Instruct revision đã pin, NF4/float16, seed42, budget/gate giữ nguyên |
| Smoke | 12/12 nhãn đúng; false support=0; runtime=0; 28 calls |
| Probe | 18/18 decomposition hợp lệ; 18 calls; human review Trí Công đúng hash |
| Full39 | **39/39 nhãn đúng**, false support=0, runtime=0; **85 calls** |
| Original contracts | 12/12 đúng |
| Scope regression | 27/27 đúng |
| Full39 confusion | Support 12/12; contradict 12/12; NEI 15/15 |
| Full39 token usage | 9.404 generated; 105.796 prompt, trong budget |
| Full39 elapsed | Worker ~754 giây; outer stage ~759 giây |
| Human review full39 | Pending, template chưa ký |
| Validation30 | Chưa chạy; gate replay từ chối do thiếu human review full39 |

Đã replay toàn bộ 69 prediction rows, **131 call triplets** qua raw JSON,
parsed output, normalization/assessment, phần giải thích dựng từ ledger và
aggregate; metrics khớp từng trường. Tất cả call hợp lệ ngay attempt đầu,
không có repair/deadline/runtime failure trong ba stage inference này.
Source quotes và numeric operand grounding cũng được kiểm lại.

Lịch sử retry cell 6 được giữ: `probe-admission` cũ exit1 vì review trước không
khớp. Preflight và `probe-admission-retry-1` exit0, kết quả khớp admission lưu
trong verifier39. Không xóa status thất bại cũ để tạo cảm giác mọi stage đều đạt.
Gate human cho probe mới đã qua; đây khác với gate human full39 đang pending.

Criteria:
`2edd14d0e7fb728b3ba6eb99923ade128573ed2938f55bfeb2d1a0e4a06f8cda`.
Probe predictions:
`2ec8f33a01e4446228e5887fe488df9a515a8adfd7964d9852a19c64ff063681`.
Review probe:
`2f10e631f06b5aa215a0875455181a867639d36a560ed5d2ac595945b6436b37`.

## Các lỗi trước đã có kết quả model mới

- SOME contradict: giữ full roster Birch/Elm/Fir, mọi outcome false cho reduced
  response time, coverage=true nên refute SOME. Quy chiếu complete audited set
  theo xác nhận người dùng được ghi ở population_binding_basis.
- Direction NEI: thiếu before/comparison được biểu đạt đúng, không sinh author
  không có nguồn. Conjunction NEI đã assess đủ hai part và giữ missing identity
  của extractor; không còn repair exhaustion vì nhầm missing của vế khác.
- NONE support: no leaks được ghi positive predicate false trước NONE; closure
  đúng và rendered explanation không còn đảo nghĩa thành có leak.
- North support cite đúng North, precision counterexample dùng đúng pair
  precision; scope May và low-temperature support/contradict giữ đúng population.

Nhãn 39/39 khớp **frozen gold development**. Zero false support là đo được trên
27 ca gold không phải support của bộ này; chưa chứng minh generalization hoặc
zero false support trên validation30. Không đổi gold để đạt 39/39 trong audit.

## Ba ca AI đánh dấu tiêu chí semantic chưa đạt

| Case | Nhãn | Điểm còn thiếu |
|---|---|---|
| `contract:causality_missing` | NEI đúng | Missing chỉ nói evidence cho new index/latency, không nêu thiếu **bằng chứng nhân quả** dù source đã báo index và lower latency cùng deployment. `missing_information_specific` chưa đạt theo AI. |
| `scope:metric:not_enough_info` | NEI đúng | Citation duy nhất là **Recall rose...**, trong khi claim hỏi precision. Cần cite **Precision was not measured** để chứng minh lý do NEI; `quote_relevant` chưa đạt theo AI. |
| `scope:condition:not_enough_info` | NEI đúng | Observation lấy **high-temperature batches** với truth unknown dù nguồn báo nhóm này gained yield. Claim hỏi low-temperature, scope_match lại matched; observation/explanation lệch nhóm. `explanation_follows_evidence` cần xử lý trước khi ký đạt. |

Các warning bổ sung: irrelevant dùng một đoạn văn làm member; ba conjunction
dùng measurement/workload làm member dù extractor chưa bind. Label NEI không
thành false support, nhưng identity/observation chưa tốt. Missing của partial
accuracy/memory nên chỉ rõ requirement 94%/25%, NONE NEI nên gọi rõ Silver.
Các warning này không bị che bởi điểm nhãn.

AI đã đọc đủ 39 claim/context/prediction và ghi nhận xét từng ca trong
`EVIDENCE_REVIEW_39.md` / `AI_EVIDENCE_AUDIT.json`. Review AI không phải human
signature, không tự mở gate validation30.

## Bước tiếp

1. Bảo toàn ZIP, source và predictions **39/39, false support=0** làm mốc
   development đạt về nhãn.
2. Mở `HUMAN_REVIEW_WITH_AI_NOTES.html` của **full39** để review năm tiêu chí
   cho đủ 39 ca, đặc biệt ba ca đánh dấu. Form không tích sẵn và cho lưu cả
   review có tiêu chí trượt. File semantic-review(4) của probe18 không thay
   được review full39.
3. Chưa xác nhận tất cả tiêu chí khi lỗi semantic chưa giải quyết. Nếu reviewer
   xác nhận các lỗi, chuẩn bị candidate mới sửa tổng quát phần observation
   binding/citation và missing causal/quantity, thêm regression từ trace cùng
   câu mới, giữ bộ validation30 độc lập. Phải đánh giá lại candidate mới theo
   workflow; không sửa trực tiếp predictions/source đã đóng băng của cellfix10.
4. Chỉ bật đúng biến **`RUN_VALIDATION30=True`** ở cell 7 khi candidate tương ứng
   có full39 gate đạt **và** review human full39 đúng hash với đủ tiêu chí đạt.
   Sau đó upload review full39 mới; runner kiểm lại admission trước inference.

## Giới hạn

Không gọi model mới trong audit, không chạy validation30, không ký thay human.
Manifest chứng minh tính nhất quán artifact, không xác thực độc lập host Colab.
Chưa có kết quả serving/E2E cho Reader/Summarizer trong lượt này.
