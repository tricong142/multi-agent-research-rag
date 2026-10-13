# Đối chiếu atomic verifier setup2 — 20261013T112627Z-d5bd1415

## 1. Kết luận

**Lượt thí nghiệm đã chạy hết 39 ca; gate chất lượng trượt.** Bản sửa cell 2
đã được kiểm chứng trên Kaggle: 193/193 tests đạt, preflight và freeze check
exit 0. Candidate model thật không hoàn tất được decomposition cho ca nào.
Chưa có bằng chứng về chất lượng kiểm từng mệnh đề hoặc công cụ số học.

| Mục | Kết quả đối chiếu |
| --- | --- |
| CRC / output manifest | CRC đạt; 38/38 file đúng size/hash, không có file ngoài manifest |
| Source runtime / candidate patch | 45/45 runtime và 27/27 verifier patch khớp repo |
| Criteria | `atomic-verifier-v1-setup2-20261013`, source/prompt/data/contract/baseline khớp |
| Model pairing | Weights/tokenizer/revision/dtype/NF4/seed/do_sample ghi trong provenance khớp baseline |
| Replay | 39 predictions, 78 calls, metrics, comparisons và 39 review rows khớp |
| Hoàn tất kiểm chứng claim | **0/39**, cả 39 incomplete, assessed_label=null |
| Nhãn đúng theo gate toàn pipeline | **0/39**, baseline logic_v3 đã lưu là 37/39 |
| False support | 0; không có nhãn được phát ra, chưa chứng minh precision |
| Gold support chưa có verdict | 13/13 (`gold_support_rejected` trong scorer) |
| Stop reason | 39 × `invalid_output_exhausted`, mỗi ca đúng 2 attempts decomposition |
| Tool/part assessment | 0 calls; chưa thực thi |
| Chi phí | USD null, backend không đo chi phí |

`experiment_completed=true` nghĩa là vòng đánh giá đã thử đủ các ca.
`atomic-verifier.exit_code=1` là chất lượng trượt theo gate, không phải setup
chưa xong. Các kết quả incomplete không được đổi thành nhãn NEI.
Accuracy trên các prediction hợp lệ và support precision đều chưa tính được
vì không có prediction hợp lệ. So sánh này chưa đo hiệu quả của thuật toán
per-part; pipeline đang dừng trước thuật toán đó.

## 2. Lỗi cụ thể và nguyên nhân đã có bằng chứng

78 calls đều chỉ ở stage `decompose`:

| Lỗi đầu tiên validator ghi nhận | Attempt 1 | Attempt 2 | Tổng calls |
| --- | ---: | ---: | ---: |
| `part_span_membership` | 27 | 0 | 27 |
| `part_count` | 9 | 0 | 9 |
| `invalid_json` | 3 | 39 | 42 |

Ví dụ ca `contract:partial_accuracy`: model trả quote `Model Juniper`,
start=0, end=7; quote có 13 ký tự và không bằng claim[0:7]. Scope lại là
chuỗi `entity`, trong khi contract yêu cầu object có bốn trường entity,
metric, time, condition. Đây là nhiều lỗi trong cùng output; bảng trên chỉ
đếm lỗi đầu tiên validator gặp. Cả 27 output parsed có parts đều chứa scope
không đúng kiểu object.

Ở repair có các key không được đặt trong dấu nháy, ví dụ `forget: 18`.
Parser hiện có đã hỗ trợ JSON được bọc trong markdown hoặc có đoạn mở đầu;
replay xác nhận cả 42 raw output lỗi vẫn không parse được bằng parser này.
Đầu ra còn chia danh từ/từ riêng thành parts và dùng quantifier không đúng
với claim. Sửa vị trí ký tự riêng lẻ chưa đủ để tạo decomposition hợp lệ.

Prompt đang yêu cầu model đồng thời tách mệnh đề, tính offset ký tự, giữ
quantifier, tạo scope lồng nhau và trả JSON. Repair chỉ nhận mã lỗi; nó không
nhận output cũ cùng chỉ dẫn cụ thể về trường sai. **Đã chứng minh đầu ra
không tuân thủ contract.** Chưa đủ bằng chứng để kết luận do kích thước model,
quantization hay cần fine-tune; thay prompt/interface là ứng viên cần đo.

## 3. Ngân sách và trace

- 78 call-start + 78 generation + 78 call-finished; không có call treo.
- Model inputs decomposition chỉ chứa claim; không có context, gold label,
  reasoning của Judge hoặc case ID trong input model.
- 78/312 calls; 9.764 generated tokens, 23.245 prompt tokens được backend báo.
- Call dài nhất theo output tokens là 232/1.536; không call nào chạm token cap.
- Mỗi ca dùng 2/8 calls, elapsed 6,812–22,640 giây, dưới deadline 180 giây.
- Stage model mất 670,291 giây, khoảng 11 phút 10 giây, dưới hard timeout 5.400 giây.
- `overall_pass=false`, human review pending, serving/promotion giữ false.

Những kiểm tra này chứng minh giới hạn và cơ chế chặn output lỗi hoạt động
trong lượt đã quan sát. Chưa cần tăng token/retry/deadline theo bằng chứng này.

## 4. Việc đã lưu để làm tiếp

- [Audit có cấu trúc](atomic-verifier-audit-20261013T112627Z-d5bd1415.json).
- [39 ca triage lỗi](../research-runs/atomic-verifier-diagnostic-20261013T112627Z-d5bd1415/failure-triage.jsonl).
- [18 claim duy nhất cho probe decomposition](../research-runs/atomic-verifier-diagnostic-20261013T112627Z-d5bd1415/decomposition-probe-claims.jsonl).
- [Output gốc](../research-runs/kaggle-20261013T112627Z-d5bd1415/atomic-verifier/summary.json).

18 claim được lấy từ 39 ca đã inspect; đây là dữ liệu diagnostic development,
không phải held-out độc lập. File probe chỉ có ID trung tính và claim; ID cũng
không cần truyền vào model. Chưa chạy probe hoặc sửa policy runtime trong lượt
đối chiếu này. Output, gold và frozen criteria của run gốc giữ nguyên.

## 5. Thứ tự tiếp theo

1. **Sửa decomposition trong candidate riêng.** Model đề xuất exact quotes,
   quantifier và scope object; code xác định start/end từ quote. Quote không
   thuộc claim hoặc vị trí không xác định chắc chắn vẫn bị chặn. Giữ kiểm tra
   thứ tự, coverage, AND, quantity và shared scope. Dùng ví dụ JSON đầy đủ,
   tổng quát, khác dữ liệu đánh giá; repair nêu trường sai và schema cần sửa.
   Không dùng gold để sửa output hoặc biến mọi lỗi thành NEI.
2. **Freeze và chạy decomposition probe trước.** Tiêu chí đề xuất: 18/18 claim
   có decomposition hợp lệ, đầy đủ coverage; review atomicity/quantifier/scope
   cho cả 18. Chốt version, hashes và ngân sách trước inference. Giữ tối đa
   2 attempts và 1.536 output tokens/call cho lần thử đầu; 18 claim tối đa 36
   calls. Thời gian dừng toàn process cũng phải chốt trước lượt mới.
3. **Sau probe đạt, chạy lại đủ 39 ca bằng version mới**, giữ gate 39/39,
   zero false support/failure. Review từng part, quotes, explanation, missing
   information; kiểm numeric tool thực sự được gọi và có input/output đúng.
   Candidate có cải thiện hay không chỉ được kết luận sau kết quả này.
4. **Sau gate verifier và review độc lập**, thực hiện bước 4: tích hợp với
   Judge/controller, hoàn thiện Reader PDF và Summarizer heldout_3, rồi đo đủ
   tám ca E2E và review câu trả lời/trích dẫn. Chuẩn bị dữ liệu độc lập theo
   [protocol](VERIFIER_INDEPENDENT_EVALUATION_PROTOCOL.md); chưa có bộ dữ liệu
   độc lập hoặc human adjudication mới trong lượt này.

Bước 3 đã có kết quả model thật; nghiệm thu chất lượng bước 3 còn chưa đạt.
Bước 4 chưa bắt đầu. Lượt tiếp theo cần candidate decomposition mới, không
lặp lại toàn verifier với policy setup2 hiện tại.
