# Audit cellfix7 — 20261020T033551Z-c7337790

ZIP hợp lệ và khớp candidate đã phát hành. Smoke trượt **10/12**, false support=0,
runtime failure=1, 29 backend calls. Không có probe18, full39 hoặc inference
validation30 trong ZIP. `baseline-metrics.json` chứa kết quả lịch sử, không phải
kết quả full39 của cellfix7.

## Kiểm toàn bộ artifact

- ZIP SHA256: `1846677f19204d47e9dae6691c83005e8411d13bb2fd4ee1a06f5c3776ce962f`.
- Đủ 53 file kể cả output-manifest; tất cả size/hash khớp. 107 đầu vào trong
  frozen-inputs.zip khớp payload đã phát hành, gồm source/prompt/contract và binding.
- Replay 12 predictions, đối chiếu đủ 29 call triplets và tính lại metrics khớp.
- Regression trên Colab đạt 237 test; cả bốn validate-only đạt; các bước dựng
  môi trường/model cache đạt. Assessment-smoke hoàn tất đánh giá nhưng exit 1
  vì gate chất lượng trượt, không phải lỗi cài CUDA.
- Model/revision/NF4/float16/seed/budget giữ nguyên. Review và lock annotation30
  được replay; không có review mới của predictions probe/full39.

## Hai ca chưa đạt

| Ca | Gold | Kết quả | Chẩn đoán |
|---|---|---|---|
| contract:both_supported | support | incomplete | Part memory sinh JSON còn mở trong explanation; cả hai attempts lặp cùng prefix, mỗi lần 111 token; invalid_output_exhausted. |
| contract:bounded_scope | support | NEI | Observation true, matched, trích đúng dataset; nhưng missing_information đòi “structural information about other datasets”, làm aggregate hạ thành NEI. |

Hai ca support còn lại đúng; cả bốn contradict và bốn NEI đúng. Support recall
2/4; không nên chỉ nhìn false support=0 rồi cho full39 chạy tiếp.

## Nguyên nhân và sửa chung

LMFE 0.11.3 có đường `json_freetext` cache không tôn trọng alphabet của parser.
Với prefix nhận được, callback cũ vẫn nhận token `内存`, sau đó cho EOS khi JSON
chưa đóng. Đã tái hiện bằng tokenizer pinned và kiểm nhỏ với token ngoài alphabet.
ZIP không lưu nguyên token IDs hoặc finish reason; phép replay tokenizer sử dụng
canonical BPE của text đã lưu, không khẳng định đây là tokenization gốc từng bước.
Đây không phải bằng chứng thiếu ngân sách 1536 token.

Candidate cellfix8 bọc parser để kiểm ký tự và thay freetext cache bằng cache
đã lọc theo alphabet/whitespace của request; kiểm qua trie tại biên chuỗi.
Giữ length/schema/field-order hiện có. Đồng thời xử lý lỗi LMFE đẩy item đầu vào array
maxItems=0 bằng parser literal `[]`; validator vẫn kiểm lại dữ liệu.

Với missing information: dùng quy tắc hữu hạn chung cho root subject + đúng verb
+ named property và restriction trong chính clause. Khi witness đủ quyết định
part thì missing_information ngoài part bị từ chối, đưa vào bounded repair;
decoder chặn nhánh đó. Không xóa missing rồi tự promote kết quả. Scope khác,
modality, causal/qualified statement, dữ liệu thật sự thiếu và báo cáo đối lập
vẫn cần model/unknown; không mở rộng thành bộ suy luận ngôn ngữ tổng quát.

## Mốc và bước tiếp

ZIP, predictions/source cellfix7 được lưu nguyên byte trong
`research-runs/audit-cellfix7-fresh-20261020T033551Z-c7337790/`. Candidate mới ở
workspace riêng, không thay serving và không sửa prediction lịch sử.

Đọc [hướng dẫn cellfix8](ATOMIC_VERIFIER_CELLFIX8_RUN_GUIDE.md). Vẫn chạy smoke
→ probe18 + review mới → full39 + review evidence → validation30. Giữ nguyên
model/budget/gate. Chưa thể kết luận cellfix8 đạt smoke hay zero false support
trên full39 trước khi có inference T4 mới.

[Machine audit](atomic-verifier-cellfix7-smoke-audit-20261020T033551Z-c7337790.json),
[trace hai ca lỗi](atomic-verifier-cellfix7-smoke-diagnostics-20261020T033551Z-c7337790.json).
