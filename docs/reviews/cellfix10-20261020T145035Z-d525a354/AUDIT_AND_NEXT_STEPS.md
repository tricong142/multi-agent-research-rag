# Audit ZIP smoke/probe cellfix10

Run: `20261020T145035Z-d525a354`.
ZIP: `output-cellfix10-fresh-20261020T145035Z-d525a354 (2).zip`.
SHA256: `04ff97595018bc643f5f1101ba23abf396df1bf2dde33b771597ad93091d8e36`.

**Đủ điều kiện kỹ thuật để hoàn tất human review probe, rồi chạy full39 để đánh
giá. Chưa bật full39 ngay bằng review hiện có trong ZIP: review đó chưa ký.**
Không cần sửa hoặc đóng băng candidate mới chỉ để chạy bước đánh giá này.

## Kiểm provenance và replay

- Bảo toàn bản ZIP nhận được; 71 output và 120 input đều khớp manifest/hash,
  đúng payload release cellfix10. Không sửa predictions/source/criteria.
- Criteria `2edd14d0e7fb728b3ba6eb99923ade128573ed2938f55bfeb2d1a0e4a06f8cda`;
  payload `9b842274db1927db85e07f6ba128f7c6f0359a0b8820c76cb27af61180f37e9c`.
- Model/revision, NF4/float16/seed42, prompt/source/contract và budget/gate đúng
  release. Log preflight ghi Tesla T4, torch 2.10.0+cu128, CUDA runtime 12.8.
- Regression Colab 314/314, pip-check và bốn validate-only đều đạt. Validate-only
  validation30 không phải đã chạy inference validation30.
- Replay đủ 30 prediction rows và 46 call triplets; raw JSON, parsed output,
  normalization/assessment, parts lưu, numeric checks và aggregate khớp. Tất cả
  46 call hợp lệ ngay attempt đầu, không có repair/deadline failure trong run này.
- Replay 13 citation entries, 10 numeric records; một source_quote của ledger
  q1 được thêm vào citation theo contract, vẫn nguyên văn trong context.
- Binding validation30 và review/lock gốc khớp. Không có full39/validation30
  inference trong ZIP. Baseline/comparisons đi kèm là lịch sử.

| Phép đo | Kết quả | Ý nghĩa |
|---|---|---|
| Assessment-smoke | 12/12 nhãn đúng; false support=0; runtime=0 | Đạt gate tự động của 12 ca development |
| Smoke calls/tokens | 28 calls; 3.568 generated; 35.025 prompt | Trong budget; không có attempt sửa |
| Probe18 | 18/18 decomposition hợp lệ; 20 part; 18 calls | Đạt cấu trúc/contract, không đo độ đúng nhãn |
| Probe tokens | 972 generated; 22.892 prompt | Trong budget và trace đủ |
| AI review probe | 18/18 claim, 90/90 tiêu chí đạt theo AI | Đề xuất review, không thay human admission |
| Human review probe trong ZIP | reviewer trống; review_completed=false | Chưa mở gate full39 |
| Full39 candidate/run này | Chưa chạy | Chưa đo zero false support trên full39 cellfix10 |

## Rà soát ngữ nghĩa

Đã đối chiếu đủ 18 claim/20 part theo năm tiêu chí; nhận xét riêng từng tiêu chí
trong `DECOMPOSITION_REVIEW.md` và `AI_REVIEW.json`.

- 007/008 giữ metric đầy đủ `took 12 seconds` / `contained 240 documents`.
- 010/014/018 giữ metric `recall` / `throughput` / `yield`, không còn động từ
  thay cho property. Lượng từ, subject và restriction được giữ.
- 001/017: vế sau kế thừa entity; 017 kế thừa time chung `After tuning`.
  Predicate cần đọc cùng scope kế thừa, không chỉ riêng quote bắt đầu bằng and.
- 006 có hai requirement độc lập: 4 models và 2 datasets. Smoke cross_sentence
  thực sự có q0/q1, source_quote và arithmetic check riêng cho cả hai.
- 014: `in May` lọc trial được tiến hành trong May; không khẳng định thời điểm
  improvement. 018: condition giới hạn population low-temperature group.
- 011 mới chỉ chứng minh decomposition giữ đúng quantifier some và population.
  Run này chưa chạy lại assessment SOME/closure ở scope39; không coi lỗi đó đã
  được model giải quyết chỉ dựa vào smoke/probe.

Các nhãn smoke khớp gold; citation/numeric của bốn gold support đã đối chiếu.
Tuy nhiên còn hai hạn chế output cần theo dõi khi review full39:

1. `contract:irrelevant`: observation member là
   `The benchmark was conducted on a Tuesday. No`, một đoạn source thay vì entity.
   Truth vẫn unknown, label NEI và missing target đúng; không tạo false support,
   nhưng đây là chất lượng identity/ledger chưa tốt. Không gọi observation này
   là binding đã đúng. Scope_match=matched cũng chưa phản ánh target vắng mặt.
2. `contract:causality_missing`: label NEI đúng vì nguồn không thiết lập causal
   relationship. Missing renderer chỉ nói thiếu evidence cho new index/latency,
   chưa nêu rõ thiếu chứng cứ nhân quả; đánh giá AI cho
   missing_information_specific là chưa đạt ở ca này. Hai ca partial numeric
   cũng mới nêu metric, chưa chỉ rõ requirement 94%/25% trong phần missing.

Những điểm này không thay đổi kết quả gate tự động hiện tại hoặc rubric
decomposition, nên có thể tiếp tục full39 như phép đánh giá candidate. Chúng
ngăn việc coi mọi prose/evidence đã đạt semantic review. Khi review full39,
phải đánh riêng tiêu chí explanation/missing; không tích đạt chỉ vì nhãn đúng.
Chưa có human evidence review full39 và chưa được promote serving/E2E.

## Anh làm tiếp

1. Mở `HUMAN_REVIEW_WITH_AI_NOTES.html`, đọc 18 claim/20 part, kiểm đủ năm tiêu
   chí từng ca, điền tên/ghi chú và xuất **semantic-review.json** human. Form
   không tích sẵn. `AI_REVIEW.json` không phải file để upload mở gate.
2. Trong **cùng runtime tạo run này**, cell **6 — Sau human review probe: full39**,
   đổi `RUN_FULL39 = True`, chạy và upload semantic-review.json vừa xuất.
   Admission kiểm đúng criteria và predictions hash trước khi gọi model.
   Không chạy lại cells 1–5 để tạo run mới rồi dùng review run này.
3. Giữ ZIP sau full39 dù đạt hay trượt và gửi để audit. Giữ
   `RUN_VALIDATION30 = False` cho tới khi full39 39/39, false support=0,
   runtime=0, trace/budget đạt và review evidence đủ 39 ca hoàn tất.
4. Nếu Colab đã reset/mất thư mục run, cần restore đúng ZIP + review của run này
   trước full39; không đổi run_id thủ công hoặc bỏ kiểm hash.

## Giới hạn audit

Audit kiểm tính nhất quán artifact và replay, không xác thực độc lập host Colab.
Không gọi model mới. AI review không phải human signature. Smoke/probe development
không chứng minh generalization hoặc zero false support trên full39/validation30.
