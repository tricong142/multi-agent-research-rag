# Audit và review cellfix8 — 20261020T061934Z-c87bce57

Đây là cellfix8 (xác nhận bằng criteria/payload hash), không phải cellfix7. Đã bảo toàn nguyên ZIP và HTML đính kèm; không sửa predictions/source hoặc chữ ký annotation cũ.

| Kiểm tra | Kết quả |
|---|---|
| Output manifest | 71 file khớp size/hash |
| Frozen inputs | 111 file khớp release cellfix8 |
| Replay | Đủ 12 smoke + 18 probe; 46 call triplets đối chiếu raw/parsed JSON, prompt, schema, deadline và budget |
| Colab checks | 252 regression đạt; cả 4 validate-only đạt |
| Smoke | 12/12 đúng nhãn, false support=0, runtime failure=0; 28 calls |
| Probe | 18/18 hợp lệ, 20 part, 18 calls; label_accuracy=null |
| Review AI | 18/18 claim đạt C1–C5; có ghi chú riêng 90 tiêu chí |
| Human admission | Chưa có xác nhận cho run mới; unsigned và AI review đều bị chặn đúng |
| Full39 / validation30 inference | Chưa chạy |
HTML đính kèm khớp nguyên byte form trong ZIP. Hash/provenance là bằng chứng nhất quán với release, không phải chữ ký độc lập máy Colab.
## Review decomposition
Xem [bảng đủ 18 claim và năm tiêu chí](DECOMPOSITION_REVIEW.md).
014: condition in May giới hạn population trial conducted in May, không suy ra improvement diễn ra trong May. Scope phải đọc cùng quote đầy đủ. 018: entity batch kết hợp condition low-temperature group mới là population; after the update là time.
## Review nhãn/bằng chứng smoke
Đúng nhãn không đồng nghĩa mọi explanation và missing_information đều đúng. Không dùng các kết quả này để gọi hệ thống Ready.
| Ca | Gold / prediction | Nhận xét AI |
|---|---|---|
| contract:partial_accuracy | not_enough_info / not_enough_info | Memory giảm 25% được chứng minh; chưa có accuracy 94%, nên NEI đúng. |
| contract:partial_memory | not_enough_info / not_enough_info | Accuracy 94% đã được chứng minh; phần memory thiếu chứng cứ. NEI đúng, nhưng missing_information của part memory lại nói thiếu retention accuracy: sai đối tượng còn thiếu. |
| contract:both_supported | support / support | Hai requirement 25% memory và 94% accuracy được trích/kiểm riêng, cùng true; support đúng. Diễn giải memory vẫn có câu bị cụt. |
| contract:accuracy_conflict | contradict / contradict | Memory 25% true; accuracy 81% bác 94%, aggregate contradict đúng. Root model_explanation của part memory lại bàn accuracy 81%: diễn giải lạc sang conjunct khác. |
| contract:irrelevant | not_enough_info / not_enough_info | Không có identity/accuracy của Model Juniper nên NEI đúng. Member dạng No model accuracy is reported và missing-information dài, có fragment, không phải trình bày target rõ ràng. |
| contract:negation | contradict / contradict | did not use any human labels là phủ định trực tiếp cùng study/predicate; contradict đúng. |
| contract:causality_missing | not_enough_info / not_enough_info | Đồng xuất hiện không chứng minh quan hệ nhân quả; not establish causal relationship dẫn tới NEI. Cụm denies a causal link trong model_explanation mạnh hơn điều source đã nói. |
| contract:scope | contradict / contradict | Một fourth task became less accurate là counterexample bác ALL; không cần roster đầy đủ để refute. |
| contract:cross_sentence | support / support | q0=4 models và q1=2 datasets kiểm riêng bằng hai câu cùng event. Quote thứ hai được thêm từ source_quote của q1, có ledger rõ. Diễn giải report being evaluated sai cách diễn đạt đối tượng, dù ledger và nhãn đúng. |
| contract:wrong_units | contradict / contradict | Source nói 12 hours, not 12 seconds; numeric record giữ đúng hai unit, không tự đổi đơn vị; contradict đúng. |
| contract:atomic_support | support / support | 240 documents xuất hiện nguyên văn cho sample; numeric value/object khớp, support đúng. |
| contract:bounded_scope | support / support | Chỉ đánh giá tested dataset; evidence trực tiếp xác nhận improved recall, missing_information rỗng. Không đòi dataset khác; support đúng. Model explanation còn kết thúc ở một cụm chưa đầy đủ. |
## Chạy tiếp
1. Mở HUMAN_REVIEW_WITH_AI_NOTES.html, trực tiếp đối chiếu đủ 18 claim/20 part. Các checkbox human đều để trống; notes AI là đề xuất để đọc/chỉnh.
2. Chỉ khi bạn xác nhận đủ 90 tiêu chí, nhập tên và xác nhận đã đọc, xuất semantic-review.json từ form. File semantic-review.json hiện trong thư mục này là bản AI, reviewer_kind=assistant, không được upload để thay chữ ký human.
3. Nếu Colab vẫn còn đúng run này: dán RUN_FULL39_AFTER_HUMAN_REVIEW.py vào một cell. RUN_FULL39 đã đặt True; cell yêu cầu đúng run_id và gọi admission gốc trước model. Upload bản review human mới xuất. Không cần chạy lại cells 1–5.
4. Nếu runtime đã mất: giữ ZIP, cần khôi phục artifact/binding đúng run trước; cell hiện tại chủ động chặn nhầm run. Không Run all notebook mới rồi dùng review cũ cho predictions mới.
5. Sau full39, giữ ZIP cả khi trượt. Zero false support trên full39 của cellfix8 chưa được đo. Nếu gate nhãn đạt, vẫn cần review prediction/evidence39 mới, đặc biệt các lỗi diễn giải/missing đã nêu, trước validation30.
Runner frozen require_probe_review() yêu cầu reviewer_kind=human, review_completed=True, tên reviewer và đủ 90 judgments/notes gắn đúng predictions/criteria hash. Không đổi gate hoặc ký thay để vượt điều kiện này.
Không có inference model mới trong lượt audit. Probe18 là tập development tách mệnh đề; kết quả này không phải đo nhãn/false support trên 18 claim.