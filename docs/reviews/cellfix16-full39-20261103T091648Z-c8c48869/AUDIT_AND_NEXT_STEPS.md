# Cellfix16 Full39 — audit run 20261103T091648Z-c8c48869

## Kết quả đã xác minh

ZIP nhận được đúng candidate **atomic-verifier-constrained-v8-cellfix16**. Kiểm
SHA256 của **108 output files và 144 frozen inputs**; replay bằng đúng payload
trong ZIP khớp metrics của cả ba stage. Probe review admission cũng khớp.

| Stage | Kết quả | Gate |
| --- | --- | --- |
| Smoke | 12/12 | Đạt |
| Probe decomposition | 18/18 | Đạt và đã được human admit |
| Full39 | 38/39; 1 incomplete; 0 completed wrong labels; 0 false support | Trượt |

Validation30 chưa bắt đầu: không có thư mục `validation30/` trong ZIP. Giữ
`RUN_VALIDATION30=False` cho run này. Không có cơ sở để mở cell7 bằng sửa metrics,
review hoặc copy một record sửa tay vào predictions.

Archive SHA256: `f66727562119c96e3e871db61652ad8569f8c141ffd24ad80d9ced96b0d0dc00`.
Criteria SHA256: `c025247428698d892e549fb12ad22e19561020b034a2a2276c9dfcaf0cbdc966`.

## Ca lỗi duy nhất

`scope:existential:contradict`

Claim: `At least one audited cache node reduced response time after the patch.`

Context nguyên văn:

> The complete audited set was Birch, Elm and Fir. After the patch, response time increased on Birch and Elm and stayed unchanged on Fir.

Decomposition đúng SOME / audited cache node / response time / after the patch.
Không có node nào có predicate “reduced response time” đúng; roster đầy đủ nên
gold contradict. Hai assessment đều ghi observation member `Birch, Elm and Fir`
với truth false và quote nguồn đầy đủ. Tuy nhiên coverage member lần lượt là:

1. `Audited cache node`
2. `Audited cache node reduced response time after the patch`

Hai chuỗi này không nằm trong context. Validator từ chối đúng
`quote_membership`; hết 2 attempts thì `invalid_output_exhausted`. Ca này dùng
**3 backend calls**, khoảng **34,71 giây**, chưa chạm giới hạn 8 calls/180 giây.
Tăng timeout hoặc số retry không giải quyết nguyên nhân đã chứng minh này.

## Root cause decoder–validator

`cellfix16_rules.coverage_schema` lọc tên coverage bằng regex chỉ cho word/hyphen
và whitespace. Tên collective hợp lệ có dấu phẩy `Birch, Elm and Fir` bị loại.
Schema cuối còn `coverage.members.items.enum = []`, trong khi coverage bị buộc
complete và có một member.

Đã chạy lại parser LMFE trên **hai raw output thật**: parser vẫn cho kết thúc
JSON với enum rỗng này, còn validator từ chối như trên. Đây là mất ràng buộc ở
decoder sau khi lọc tên, không phải thiếu thông tin trong nguồn hoặc lỗi Gemini,
Reader hay Writer. `structured_decoding_trace_complete=true` kiểm metadata trace,
không chứng minh schema không có nhánh enum rỗng bị parser diễn giải rộng hơn.

Audit replay dùng token-list mode không cần optional Torch bitmask do máy local
báo thiếu paging file. Đây cũng là kiểu list mà ConstrainedAtomicBackend đã
chọn; không chạy weights, không sửa scoring hoặc kết quả gốc. Hash I/O dùng
block 64 KiB để giảm peak RAM, cùng SHA256 và cùng bytes nguồn.

## Bản sửa ở candidate kế tiếp

Cellfix17 xây từ frozen Cellfix16, thay bước ràng buộc coverage:

- Dùng exact source spans nằm trong tập member hợp lệ của observations, giữ cả
  dấu phẩy, apostrophe, hyphen và Unicode; không bỏ dấu câu để tạo alias.
- Không còn lựa chọn cho coverage bắt buộc: loại nhánh bất khả thi hoặc báo
  `unrepresentable_coverage_members`, không tạo `enum: []` thành đường free text.
- Với coverage không đầy đủ và không có member hợp lệ, chỉ giữ đường empty
  array / complete false. Giữ đường unknown hợp lệ.
- Validator, prompts, labels, dữ liệu phát triển, model/revision và budgets
  không đổi. Record sửa trong test chỉ chứng minh đường hợp lệ, không thay
  dự đoán Kaggle hoặc chứng minh model sẽ tự sinh đúng.

Không sửa release16 hay mở gate run hiện tại. Sau khi có notebook17 đã kiểm
packaging, dùng runtime mới: smoke → probe mới + human review → Full39 mới +
human review → cell7 development30. Review16 không được tự chuyển sang hash17.

Để promotion vào E2E còn cần independent holdout được human admit, rồi kiểm
Reader → Summarizer → Verifier → Writer. Full39 là bài test riêng của Verifier,
không chứng nhận toàn pipeline. Writer chỉ nhận các claim đã qua kiểm chứng;
Verifier xét claim và source context, không thay OCR của Reader.

Chi tiết máy đọc: `docs/atomic-verifier-cellfix16-full39-audit-20261103T091648Z-c8c48869.json`.
Lệnh tái hiện nhẹ: `python -m scripts.audit_atomic_cellfix16_full39 --no-torch`.
