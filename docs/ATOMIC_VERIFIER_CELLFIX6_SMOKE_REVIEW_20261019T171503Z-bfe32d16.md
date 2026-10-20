# Cellfix6: audit smoke — 20261019T171503Z-bfe32d16

Audit ngày 2026-10-20. **Chưa đạt smoke; chưa được chạy probe18/full39/validation30.**
Lượt này đã qua admission ở cell 2 và dựng được môi trường T4. Worker smoke
hoàn tất 12 ca, nhưng trả exit 1 vì trượt gate chất lượng.

## Provenance và replay

- ZIP SHA-256: `d28195992d0d2bd20d6dbbc3b6d7553ab3dd5c0aaf9677dd6504b5057c4518e7`.
- Kiểm đủ **50 file output** theo output manifest và CRC ZIP; **99 file input**
  khớp payload notebook đã đóng gói. Source/prompt/contract/criteria/tokenizer
  khớp freeze; không phát hiện bản vá ngoài manifest.
- Criteria SHA-256: `b9d77823b5c8d6d2a56d4053667b8b53f6e059a1f5edb9e7e3a7578a50f34071`.
- Payload SHA-256: `3d9d570f6bc7468f176c19952bbafe6212b609adf672fd3285a79f875ef9582a`.
- Replay đủ **12 predictions, 29 bộ call-start/generation/call-finish**,
  12 decomposition và 17 assessment attempts. Kiểm lại aggregate và metrics
  khớp hoàn toàn artifact. Có 16 part cuối; một assessment phải repair.
- Kiểm 15 trích dẫn raw và 7 numeric records nguyên văn, gồm record trong
  attempt bị từ chối. Đúng chuỗi nguồn không tự chứng minh đúng ngữ nghĩa.
- Model/revision, weights/tokenizer hashes, NF4/float16/seed42/do_sample=false
  khớp provenance và lịch sử được freeze. Không tải trọng số/chạy model khi audit.
- Bản ZIP nguyên gốc, output và workspace được giữ tại
  `research-runs/audit-cellfix6-fresh-20261019T171503Z-bfe32d16/`.

Đây là kiểm tính nhất quán artifact và replay, không phải chữ ký xác thực máy
Colab. [Machine audit](atomic-verifier-cellfix6-smoke-audit-20261019T171503Z-bfe32d16.json),
[trace các ca sai](atomic-verifier-cellfix6-smoke-diagnostics-20261019T171503Z-bfe32d16.json),
[script tái lập](../scripts/audit_atomic_cellfix6_smoke.py).

## Admission và môi trường

- File review thực tế trong ZIP đủ 30 ca, replay admission thành công;
  `validation-lock.json` khớp chính file đã upload.
- Review SHA-256 trong run:
  `8ff233fff0c01eb7bbbbb14746a82a7295b2ad294dc9c1eba55cd52303cd946a`.
  So với review đã lưu ở repo, nhãn và năm checks giống nhau; khác ghi chú ở
  004/008/010/025. Giữ riêng hai bản, không ghi đè file review/lock tại repo.
- Lỗi thiếu accepted_label ở 018/025 của ZIP `a124d5b5` trước đó không còn trong
  ZIP này. Không cần hạ gate hoặc tự điền nhãn để vượt cell 2.
- CUDA preflight: Tesla T4, torch 2.10.0+cu128, CUDA 12.8. `pip check` đạt.
  Regression trên Colab **211/211 đạt**; ba validate-only đạt smoke12/probe18/full39.
- Các phiên bản trọng yếu khi so với môi trường cellfix5 full39 đã lưu giống
  nhau: torch 2.10.0+cu128, transformers 5.16.1, bitsandbytes 0.50.2,
  tokenizers 0.23.3, lm-format-enforcer 0.11.3, accelerate 1.14.0 và
  huggingface_hub 1.33.0. Điều này không tách riêng ảnh hưởng của prompt và code.

## Kết quả mới thực sự đã đo

| Chỉ số | Kết quả smoke cellfix6 |
|---|---:|
| Ca hoàn tất | 12/12 |
| Nhãn đúng | **7/12 (58,33%)** |
| False support | **0** |
| Runtime failure | 0 |
| Support đúng | 3/4 gold support |
| Precision của nhãn support | 3/3 |
| Contradict đúng | **0/4** |
| NEI đúng | 4/4 |
| Backend calls | 29 |
| Generated / prompt tokens | 3.708 / 32.956 |
| Thời gian worker báo cáo | 349,96 giây |
| Automated gate | **Không đạt** |

Model dự đoán support 3 ca, NEI 9 ca, không có prediction contradict.
Zero false support trên smoke này đi cùng việc bỏ sót toàn bộ counterevidence
cần nhãn contradict; không đủ để nghiệm thu verifier.

Cùng 12 claim/context/gold này trong full39 cellfix5 đã lưu đạt 12/12; cellfix6
đạt 7/12. Đây là suy giảm quan sát được trên bộ development. Chỉ có một run
mỗi candidate; code và prompt cùng đổi, chưa đủ để quy nguyên nhân cho riêng
prompt hoặc khẳng định suy giảm trên phân phối chung.

`baseline-metrics.json` có 37/39, false support=2 thuộc baseline lịch sử,
không phải lượt full39 cellfix6. Bản rescore baseline theo annotation hiện hành
cũng là chấm lại predictions cũ. Không có artifact probe18/full39/validation30
trong ZIP mới. `probe-validate-only` chỉ kiểm cấu hình, không chạy 18 claim.

## Rà từng ca

S = support; C = contradict; N = not_enough_info. Đây là rà soát bởi AI,
không ghi thay chữ ký human review của prediction.

| Ca contract | Gold → prediction | Nhận xét |
|---|---|---|
| partial_accuracy | N → N | Tách memory/accuracy đúng; memory có bằng chứng, accuracy thiếu. |
| partial_memory | N → N | Nhãn đúng; câu missing nói cả memory và accuracy thiếu dù accuracy đã có. Chất lượng explanation chưa đạt. |
| both_supported | S → S | Hai numeric checks riêng đúng 25% và 94%. Explanation có chuỗi `94%+1` không có trong nguồn; nhãn đúng không bảo đảm explanation đúng. |
| accuracy_conflict | **C → N** | Model gán cả memory và accuracy `scope=mismatched`, truth unknown, dù cùng Model Juniper; accuracy 81%, not 94% là counterevidence. |
| irrelevant | N → N | Đúng khi không có accuracy; missing cuối được code bổ sung. Không được hiểu là model tự giải thích đầy đủ. |
| negation | **C → N** | `did not use any human labels` bị trả mismatched/unknown thay vì counterevidence cùng study. |
| causality_missing | N → N | Nhãn đúng do chưa chứng minh nhân quả; model gán mismatched cho quan hệ chưa được chứng minh. Cần phân biệt scope và evidence sufficiency. |
| scope | **C → N** | “Three tasks improved, but a fourth ... less accurate” bị hiểu thành conflicting results cho một member. Một phản ví dụ đúng scope đủ bác ALL. |
| cross_sentence | **S → N** | Attempt 1 kiểm `four models` hai lần; không kiểm `two datasets`. Validator từ chối đúng; repair bỏ cả hai checks và khai thiếu dữ liệu dù nguồn có đủ. |
| wrong_units | **C → N** | “12 hours, not 12 seconds” bị trả mismatched/unknown. Khác giá trị/đơn vị của cùng phép đo không tự tạo khác scope. |
| atomic_support | S → S | Check 240 documents đúng; explanation dở câu nhưng không ảnh hưởng phép kiểm số. |
| bounded_scope | S → S | Bằng chứng qualitative đúng trong tested dataset. Explanation “lacks quantitative details” không phải thiếu sót cần có của claim này. |

## Nguyên nhân có bằng chứng và phần còn phải kiểm

1. **Lẫn scope với truth đã được chứng minh từ output.** Sáu part cuối mang
   `scope=mismatched`; bốn ca sai liên quan lựa chọn này. Hàm `assess_part`
   chỉ tạo support/contradict khi scope matched, nên trả NEI theo đúng dữ liệu
   model đã khai. Cần sửa cách khai báo/kiểm scope, không đổi aggregate để
   mặc nhiên bỏ qua mismatch.
2. **Unknown hợp lệ che lỗi đọc bằng chứng.** Validator kiểm cấu trúc,
   trích dẫn và số học; các guard cellfix6 bỏ qua nhiều kiểm khi truth unknown.
   Schema cũng giữ unknown/null. Điều này cần cho thiếu bằng chứng thật,
   nhưng cho phép chấp nhận các output sai ở trên mà không vào repair.
   Không được xóa unknown toàn cục hoặc đổi NEI thành nhãn quyết định.
3. **Numeric array chưa ràng mỗi slot với một requirement khác nhau.** Decoder
   đặt min/maxItems nhưng các item dùng chung tập lựa chọn record. Vì vậy hai
   record cho số 4 vẫn sinh được. `assess_part` phát hiện
   `duplicate_numeric_requirement` đúng; đây là validation issue duy nhất trong
   29 lượt gọi. Repair tiếp theo hợp schema nhưng sai nội dung.
4. **Xung đột trong một member khác với kết quả khác nhau giữa các member.**
   Model dùng unknown cho phản ví dụ thứ tư, làm mất quy tắc bác lượng từ ALL.
5. **Explanation cần đánh giá riêng.** Giới hạn 64 ký tự vẫn cho chuỗi dở câu
   hoặc thêm chi tiết không có nguồn. Dù nhãn đúng, không tự công nhận các
   tiêu chí explanation/missing_information đã đạt.

Chưa chạy ablation/model mới để xác định sửa prompt riêng có đủ hay không.
211 regression chủ yếu kiểm bằng output dựng sẵn và trace development; chúng
không chứng minh model sẽ tự sinh output đúng dưới prompt mới.

## Hướng tiếp theo

1. Giữ run thất bại này, source, review, calls và predictions nguyên vẹn. Chưa
   chạy lại cùng notebook với kỳ vọng gate tự đổi, chưa chạy probe/full39.
2. Làm candidate tiếp theo, đề xuất **cellfix7**, tập trung vào assessment:
   phân biệt identity/metric/time/condition với agreement; yêu cầu bằng chứng
   thực sự cho mismatch/unknown khi cấu trúc nguồn có thể kiểm được. Bảo toàn
   NEI thật và trường hợp binding chưa rõ, không tự nâng nhãn theo heuristic rộng.
3. Tách và kiểm ledger cho từng requirement, tránh sinh hai bản ghi cùng số rồi
   repair sang unknown. Kiểm khả năng hỗ trợ của decoder hiện dùng trước khi
   chọn cách biểu diễn; không mặc định một tính năng JSON Schema là khả dụng.
4. Thêm regression từ đúng output sai trong ZIP và câu development mới cho:
   negation cùng chủ thể, mismatch thật về chủ thể/time/condition, một phản ví dụ
   bác ALL, bằng chứng thiếu thật, hai số độc lập ở hai câu và sai đơn vị rõ ràng.
   Kiểm cả validator, repair và token filter thật; không chỉ đưa JSON gold vào test.
5. Đóng băng candidate mới, giữ model/revision/budget/gate; chạy smoke12 lại.
   Smoke đạt mới probe18 và review mới; tiếp đó full39, rồi mới validation30.
   Mục tiêu full39 vẫn phải đo đúng nhãn và false support, không thay bằng
   structural pass hoặc tỷ lệ abstain cao.
6. Giữ 30 ca validation và gold đã review. Chưa có kết quả model của bộ này và
   không dùng chúng để sửa cellfix7. Nếu candidate đổi, lập bản binding/lock
   mới trước inference, giữ nguyên chữ ký và lock lịch sử; không sửa JSON review
   cũ cho khớp hash mới. Nếu kết quả validation được dùng tune thì chuyển bộ
   thành development và chuẩn bị bộ khác.

Lượt audit này chỉ tạo snapshot, script, báo cáo và cập nhật trạng thái. Chưa
thay source/prompt/criteria của verifier và chưa khẳng định candidate kế tiếp
sẽ đạt gate. Reader/Summarizer/E2E vẫn chờ các gate verifier thực tế.
