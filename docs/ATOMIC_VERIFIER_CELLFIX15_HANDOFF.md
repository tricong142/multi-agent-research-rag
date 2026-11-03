# Cellfix15 — shared member-local absence guard

Candidate: `atomic-verifier-constrained-v8-cellfix15`.
Criteria SHA256: `95b79b8589980376c9c3ca45780ac3ac1a809bf13c03b84904616ee7da939e69`.

**Cập nhật 2026-11-03:** run GPU `20261102T163553Z-ed00dfbc` đã được audit:
full39 đạt 39/39, không false support/runtime failure. Cell7 gặp lỗi so sánh
schema metrics (`usage_complete` chỉ có ở replay). Có
[hướng dẫn thay chỉ cell7 và resume](reviews/cellfix15-full39-20261102T163553Z-ed00dfbc/AUDIT_AND_RESUME.md).
Validation30 chưa chạy; các số offline bên dưới là mốc trước inference.

## Vấn đề và bản sửa

Run Cellfix14 `20261102T120149Z-ca882061` đạt 38/39 nhãn, một incomplete:
`scope:none:not_enough_info`. Model ghi `Silver's leak status → false` từ nguồn
nói trạng thái Silver chưa được báo cáo. Decoder cho phép record này; validator
từ chối với `missing_evidence_is_not_false`. Đây là lỗi assessment, không phải
timeout hoặc lỗi orchestration cell6.

Trong candidate mới, `assessment_focus.observation_focus_issue` gọi
`member_absence_quotes` cho cả nhánh known. Khi member có bằng chứng cục bộ rằng
trạng thái chưa được báo cáo, hàm từ chối cả `true` và `false`. `constrain_focus`
của decoder và `focus_issue` của validator cùng dùng hàm này. Không chép guard
sang hai nơi, không tự đổi output lỗi thành unknown.

`Silver → unknown` vẫn cần bằng chứng absence đúng member và trả NEI.
Blue/Green có kết quả không rò rỉ vẫn đi được nhánh false của predicate `leaked`.
Helper cũ tiếp tục giữ các fact cạnh tranh của chính member để kiểm tra;
không ép unknown toàn bộ population khi chỉ một member thiếu báo cáo.

Nguồn runtime chỉ thêm guard này, policy/decoder metadata và contract mới.
Model/revision, prompt, gold, scoring, budgets và human gates được kế thừa.
Không sửa source/notebook/predictions/review của Cellfix14 và không promote serving.
Giữ `RUN_VALIDATION30=False` cho run Cellfix14 hiện tại.

## Bằng chứng offline

- 413/413 regression tests CPU: 405 kế thừa và 8 test mới.
- 110/110 đường token đạt kỳ vọng với tokenizer Qwen đã pin, không load weights:
  94 kế thừa và 16 mới. Hai record lỗi thực nhận bị chặn; Silver/unknown,
  Blue/false và Green/false được giữ. Có negative controls true/false và
  entities mới với NONE/ALL/SOME.
- Validator trả NEI cho record Silver/unknown sửa tay và các case mới.
- 38/38 kiểm tra notebook/gate đạt; cả bốn chế độ validate-only chạy từ
  payload giải nén thực tế. Colab/Kaggle chứa cùng 140 payload inputs;
  21 file release và 124 source inputs Cellfix14 vẫn đúng hash.
- Các báo cáo `atomic-verifier-cellfix15-{validation,tokenizer-check,
  packaging-validation,kaggle-validation}.json` ghi rõ phạm vi đã kiểm tra.

Các kiểm tra này chỉ đo hợp đồng decoder/validator và đóng gói. Sau đó đã có
run GPU full39 đạt 39/39 như cập nhật đầu trang; vẫn chưa có dev30 đạt 30/30.
Parser absence hiện vẫn theo ngữ pháp hữu hạn của candidate; chưa chứng minh
bao phủ mọi cách diễn đạt ngôn ngữ tự nhiên.

Lượt QA local đầu gặp MemoryError khi tiến trình cha và tiến trình kiểm payload
cùng nạp runtime. Kiểm tra riêng đã đạt; runner mới chạy kiểm payload trước
khi nạp runtime cho các mô phỏng còn lại và toàn bộ 38 kiểm tra đã đạt.
Không giảm hash checks/assertions; log lỗi ban đầu giữ ở
`research-runs/cellfix15-packaging-initial.log`.

## Chạy candidate mới trên Kaggle

1. Import `scripts/kaggle_atomic_verifier_cellfix15.ipynb` vào notebook private
   mới; chọn GPU T4 và bật Internet như release trước. Không thay payload trong
   runtime Cellfix14 cũ. Giữ ZIP của run cũ để đối chiếu.
2. Chạy từng code cell 1–5: source → môi trường → regression/validate-only →
   smoke12 → probe18. Mỗi bước phải đạt trước khi tiếp tục; lưu ZIP khi thất bại.
3. Review nguồn/predictions của probe mới, xuất human JSON thực tế rồi gắn làm
   private Kaggle input. Trong cell6 mới, đặt `PROBE_REVIEW_PATH` thành đường dẫn
   tuyệt đối tới JSON đó, rồi đặt `RUN_FULL39=True`. Review gắn với criteria và
   prediction hashes; không dùng review Cellfix14 để mở gate cho Cellfix15.
4. Chỉ khi full39 mới đạt mọi automated check và được người review đầy đủ:
   gắn JSON review full39 mới, đặt `FULL39_REVIEW_PATH` trong cell7 mới rồi mới
   bật `RUN_VALIDATION30=True`. Trước đó giữ False. Nếu full39 còn lỗi, giữ ZIP,
   không bỏ case hoặc đổi metric để tiếp tục.
5. Tải ZIP trong `/kaggle/working` trước khi dừng runtime. Không chạy lại cell1
   để resume; giữ mọi lần thử, kể cả thất bại.

Cells6/7 của notebook mới mặc định False và giữ gate hiện có.
Bộ30-v1 đã dùng để phát triển nên binding tiếp tục ghi `development`,
`validation_used_for_tuning=true`, `independent_validation_completed=false`.
Ngay cả nếu đạt 30/30, cần holdout mới khác paper để đánh giá độc lập.

## Tái tạo và kiểm tra local

Chỉ tái build trong draft/workspace mới. Builder từ chối ghi đè release đã chốt.
Thứ tự module: `build_atomic_cellfix15_candidate`, `prepare_cellfix15_packaging`,
`check_atomic_cellfix15`, `check_atomic_cellfix15_tokenizer`,
`build_colab_cellfix15`, `build_kaggle_cellfix15`, `check_cellfix15_packaging`,
`check_kaggle_cellfix15`. Chạy với `python -m scripts.<module>` từ repo.
Chỉ dùng `build_colab_cellfix15 --release` sau khi mọi kiểm tra draft đạt.
