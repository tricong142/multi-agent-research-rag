# Đối chiếu verifier scope_v2 — run 20261012T153832Z

**Thí nghiệm hoàn thành; candidate chưa đạt.** Không tích hợp scope_v2 vào
Fact-checker/Writer. Exit 1 của stage là kết quả gate chất lượng trượt.

## Bằng chứng đã kiểm tra

- ZIP 56.721 bytes, SHA256
  `0f6052667b04213bcc30eb7cdf114815ce3ab4e7413ba988881b3e2dfa3988e5`;
  CRC đạt, 37/37 output files đúng size/hash, không thiếu file trong manifest.
- Trước khi sửa candidate tiếp theo: 45 runtime patch files, 10 verifier patch
  files và 5 provenance sources khớp repo. Criteria, prompt và cả hai input
  datasets khớp bản đóng băng. Metadata pairing với v1 đều true.
- Replay offline khớp 39 predictions từ 41 recorded calls: messages,
  claim/context blinding, output validation, retry và kết quả đều khớp.
  Metrics, 117 comparisons, hai baseline metrics và summary chấm lại khớp.
  Đây là replay từ output đã lưu, không gọi model mới.
- Setup/pip check/preflight đạt. Kaggle ghi nhận **155 tests đạt trong 4,395s**.
  Stage verifier mất 269.871,97 ms, gồm cả nạp model. Tổng elapsed của 39 lượt
  assess là 203.775,107 ms. Cost không được backend báo: `null`, không phải zero.
- 39 review rows vẫn pending; 10 rows được assistant gắn cờ để người đánh giá
  kiểm tiếp. Triage này không phải review độc lập hoặc nghiệm thu bằng người.

[Bản ghi audit](blind-verifier-audit-20261012T153832Z.json),
[bản nháp review 39 ca](blind-verifier-review-draft-20261012T153832Z.jsonl).
Output gốc được lưu nguyên tại `research-runs/kaggle-20261012T153832Z`.

## Kết quả thực đo

| Chỉ số | scope_v2 | Điều kiện đã đóng băng |
| --- | ---: | ---: |
| Đúng nhãn | 33/39 (84,62%) | 39/39 |
| Ca cũ | 11/12 | 12/12 |
| Ca mới | 22/27 | 27/27 |
| Đồng ý một trong hai nhãn sai | 5 | 0 |
| False support | 1 | 0 |
| Verification failure | 1 | 0 |
| Actual model calls | 41 | ≤78, ≤2/case |
| Macro-F1 | 0,85399 | Chỉ số mô tả, không thay gate |

`all_cases_present=true` và attempt budget đạt. Một failure do output quote
validation, không có bằng chứng HTTP/quota/GPU failure trong trace này. Model
trả JSON có nhãn, nhưng quote không nguyên văn; hệ thống từ chối đúng policy.

V1 và v2 cùng đúng 11/12 ca cũ. V2 sửa `contract:scope` từ NEI thành contradict,
nhưng `contract:accuracy_conflict` đổi từ contradict đúng thành NEI sai.
Không có baseline v1 trên 27 ca mới; không suy diễn rằng v2 tăng chất lượng tổng.

## Sáu ca không đạt và nguyên nhân thể hiện trong trace

| Ca | Kết quả v2 | Phân tích |
| --- | --- | --- |
| accuracy_conflict | NEI thay vì contradict | Số đo đối lập đã có, model vẫn yêu cầu thêm accuracy. |
| existential:support | contradict thay vì support | Một witness dương đã đủ cho SOME; model dùng các witness âm khác để bác bỏ. |
| existential:NEI | contradict thay vì NEI | Kết quả chưa được báo cáo bị coi thành bằng chứng phủ định. |
| time:contradict | verification_failed | Cả hai raw labels đúng; model viết lại quote thay vì sao chép substring. |
| direction:contradict | support thay vì contradict | Số sau lớn hơn số trước nhưng explanation gọi là giảm. Đây là false support. |
| conjunction:contradict | NEI thay vì contradict | Một vế đổi theo hướng ngược đã rõ, nhưng model đòi mức thay đổi mà claim không yêu cầu. |

Ba attempts bị quote validator chặn: một ở entity:contradict được repair thành
công, hai ở time:contradict bị chặn hết budget. Không nới exact-substring check.

Các nhận định về suy luận là phân tích của assistant từ claim/context/output.
Chưa có thí nghiệm ablation chứng minh độ dài hay câu nào trong prompt gây lỗi.

## Vấn đề semantic còn có khi nhãn đúng

`contract:cross_sentence` có claim gồm bốn models và hai datasets. Output chỉ
quote/explain bốn models. Label support khớp gold nhưng bằng chứng không phủ
đủ hai factual parts. Existential:contradict cũng có quote/explanation bỏ qua
coverage của toàn population và node thứ ba. Chấm đúng nhãn không thay thế
review độ phủ evidence. Các dòng khác được gắn cờ về thông tin thiếu/phạm vi.

## Đã chuẩn bị bước tiếp theo

- Candidate **logic_v3** có decision procedure riêng: scope → operator của từng
  part → so sánh giá trị → kết hợp parts → trích dẫn nguyên văn. Baseline v1 và
  scope_v2 prompt/criteria vẫn giữ để đối chiếu.
- Quote repair nhận mã lỗi cố định `quote_membership` và hướng dẫn copy text.
  Generic backend exception không đưa nội dung lỗi vào model/log. Model vẫn
  chỉ nhận claim/context, không thấy gold, proposed label hoặc rationale.
- Snapshot scope_v2 gồm đủ 39 predictions, giữ cả failure, SHA artifact/ZIP,
  input hashes và model metadata. Candidate so với v2 trên cùng 39 cases;
  confidence repair lịch sử vẫn chỉ so trên 12 contracts cũ.
- Giữ model revision, generation settings, 384 tokens, ≤2 attempts/case,
  budget ≤78, gate đúng 39/39 và zero false support/failure. Không dùng label
  đúng của evaluator để sửa output, không hard-code claim hoặc câu đã sai.

Candidate thay cả prompt và quote-repair feedback; lượt mới đo policy kết hợp,
không tách hiệu quả từng thay đổi. Chưa có real inference cho logic_v3.

## Thứ tự hoàn thiện

1. Chạy [notebook logic_v3](../scripts/kaggle_blind_verifier_logic_v3.ipynb)
   theo [hướng dẫn](VERIFIER_LOGIC_V3.md), giữ ZIP kể cả gate trượt.
2. Nếu đạt gate, hoàn thiện review nhãn/quote/explanation bằng người và bộ dữ
   liệu đánh giá độc lập trước khi tích hợp. 39 cases này đã được xem để sửa
   prompt; chúng chỉ chứng minh development regression.
3. Nếu trượt, giữ kết quả, không chạy lặp cùng policy hoặc hạ gate. Dùng loại
   lỗi mới để quyết định cần dữ liệu huấn luyện/đánh giá hoặc backend khác;
   chưa có bằng chứng để chọn thay backend hay fine-tune ngay.
4. Sau quality gate: tích hợp quyền đề xuất tìm thêm khi bất đồng/thiếu evidence,
   giữ Writer chỉ dùng claim đã xác minh; hoàn thiện Reader PDF, Summarizer
   heldout_3, tám ca E2E, review trích dẫn và tài liệu bảo vệ.

Toàn hệ chưa đạt gate phát hành. Không chạy lại toàn bộ sáu cell trong bước này.
