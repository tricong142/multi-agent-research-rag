# Cellfix11 smoke/probe audit — đủ điều kiện review probe mới trước full39

Run: `20261026T125935Z-2cff8d38`.
ZIP: `output-cellfix11-fresh-20261026T125935Z-2cff8d38.zip`.
SHA256: `88b618f5d7e501f7532159ff2cfb0e3c8ebecc7338f228b6a940057dd14e140a`.

**Có thể chuyển sang human review probe Cellfix11, rồi chạy cell6/full39 sau
khi review đúng candidate/predictions được admission. Chưa chạy cell7.**

## Kết quả kiểm tra

- 71 output và 124 input khớp manifest/hash, đúng release Cellfix11. Payload,
  source, prompt, contract, criteria và validation binding đều replay đạt.
- Đúng model/revision, NF4/float16/seed42, budget/gate đã khóa. Log preflight ghi
  Tesla T4, torch 2.10.0+cu128, CUDA runtime 12.8. Không thay serving.
- Regression Colab **342/342**, pip-check và **bốn validate-only** đạt. Validation30
  validate-only chỉ kiểm cấu hình/lock, không phải inference held-out đã chạy.
- Replay đủ 30 prediction rows và **46 call triplets**: raw JSON, parsed output,
  normalization/assessment, stored parts/explanations và aggregate khớp hoàn toàn.
  Tất cả call valid ngay attempt đầu; không có repair/deadline/runtime failure.
- Kiểm lại 14 citation entries và 10 numeric records. Cả q0=4 models và
  q1=2 datasets có source_quote/requirement/check riêng ở ca cross_sentence.

| Stage | Kết quả | Calls / generated tokens / prompt tokens |
|---|---|---|
| Assessment smoke | **12/12 nhãn đúng; false support=0; runtime=0** | 28 / 3.577 / 36.561 |
| Probe18 | **18/18 decomposition hợp lệ**, 20 part; label_accuracy=null | 18 / 972 / 22.892 |
| AI review decomposition | 18/18 claim, 90/90 tiêu chí đạt theo AI | Không gọi model mới |
| Human review probe trong ZIP | Chưa ký: reviewer trống, review_completed=false | Frozen admission chặn đúng |
| Full39 Cellfix11 | Chưa chạy | Chưa đo nhãn/false support đầy đủ |
| Validation30 | Chưa chạy | Giữ RUN_VALIDATION30=False |

## Rà soát nội dung

Đã đọc đủ 18 claim/20 part và đối chiếu riêng năm tiêu chí. Normalized plans giữ
đúng entity, metric, quantifier, numeric requirements và scope. Dữ liệu/plan giống
probe Cellfix10 đã review, nhưng candidate/hash/run mới nên cần human review mới.
Không chuyển chữ ký human từ candidate cũ.

- 001/017: vế sau kế thừa subject; 017 giữ `After tuning` cho cả hai part.
- 006: một event chứa hai quantity độc lập: 4 models và 2 datasets.
- 007/008: metric đầy đủ `took 12 seconds`, `contained 240 documents`.
- 010/014/018: metric `recall` / `throughput` / `yield`, giữ đúng population.
- 014: May lọc trial được tiến hành trong May, không khẳng định improvement xảy
  ra trong May. 018: low-temperature group giới hạn population, after update là time.

**Ca causality trong smoke đã cải thiện đúng trên output model mới:**
`contract:causality_missing` vẫn NEI, quote nguyên văn
`The study did not establish a causal relationship.`; missing reason là
`causal_relationship`, nêu thiếu bằng chứng quan hệ nhân quả và giữ causal predicate.
Không nhầm co-occurrence thành cause hoặc thiếu metric latency.

Hai lỗi còn lại ở scope39 — quote precision chưa đo và member low/high-temperature
— **chưa được kiểm bằng inference full39 trong ZIP này**. Probe chỉ kiểm decomposition,
không chứng minh assessment của hai ca đó đã đúng.

Warning giữ trung thực: ca irrelevant trong smoke vẫn dùng `No model accuracy is
reported` làm member thay vì một entity. Label NEI và missing target đúng, không
tạo false support, nhưng chất lượng identity/observation chưa sạch. Các missing
partial numeric còn generic theo metric; phần causal có dấu chấm cuối lặp, chỉ
là formatting. Không suy smoke gate đạt thành mọi tiêu chí evidence/prose đã đạt.

## Anh làm tiếp

1. Mở **`HUMAN_REVIEW_WITH_AI_NOTES.html` trong thư mục review Cellfix11 này**,
   đọc từng claim/part/ghi chú, xác nhận năm tiêu chí, điền tên và xuất
   `semantic-review.json`. Form Cellfix10 đang mở ở browser thuộc candidate/run
   cũ, không dùng để mở gate Cellfix11.
2. Giữ **cùng runtime tạo run `20261026T125935Z-2cff8d38`**. Ở cell6 notebook
   Cellfix11, đổi `RUN_FULL39=True`, chạy và upload review vừa xuất. Cell6 đã giữ
   cơ chế preflight và tên stage retry riêng; không cần thay bằng cell6 Cellfix10.
   Không chạy lại cells 1–5 để tạo run mới rồi dùng review này.
3. Giữ ZIP sau full39 dù đạt hay trượt và gửi để audit. Review đủ 39 prediction,
   citation, scope, quantity, explanation và missing-information trước khi ký human.
4. **Giữ `RUN_VALIDATION30=False`** cho đến khi full39 và human evidence review
   của đúng Cellfix11 đều đạt. Nếu Colab đã reset/mất run, cần restore đúng ZIP
   và binding trước; không sửa run_id/hash trong review cũ.

Binding dùng để đối chiếu:

- Criteria: `e0d6bb116d32f4485e678e635c8e911577148212875c9c24f782b2ed2ad84789`.
- Probe predictions: `1bacfda578c745805be53b3b759f00e5737602f7a8386249a3201b847ed20ae6`.

## Giới hạn

Audit không gọi model mới, không ký thay human. Hash/provenance chứng minh tính
nhất quán artifact, không xác thực độc lập host Colab. Zero false support ở smoke
12 ca chưa chứng minh full39 hoặc validation30; 39/39 trước đó thuộc Cellfix10.
