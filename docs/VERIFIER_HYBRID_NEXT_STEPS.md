# Hướng hoàn thiện verifier sau logic_v3 — 2026-10-13

**Hiện hành:** probe v3 đạt 13/18 cấu trúc, 5 incomplete; chưa qua gate.
Đã audit/review đủ 18 ca: 9 rõ ràng đạt, 4 cần sửa, 5 không review được.
V4 đã đóng băng decoder theo JSON schema/trích đoạn nguồn; giữ model, prompt,
dữ liệu và ngân sách. 83 test runtime và 3 test đóng gói đạt qua hai lượt kiểm
tra local; chưa đo Qwen/CUDA v4.
Chạy [notebook v4](../scripts/kaggle_decomposition_probe_v4.ipynb) theo
[hướng dẫn](DECOMPOSITION_PROBE_V4_KAGGLE.md).
[Báo cáo ZIP v3](DECOMPOSITION_PROBE_REVIEW_20261013T135905Z-ac194776.md).
Chỉ chuyển sang 39 ca sau probe 18/18 và review ngữ nghĩa đạt; tích hợp và toàn
hệ vẫn chờ gate verifier. Ràng buộc JSON không bảo đảm ngữ nghĩa đúng.

**Bàn giao v2 trước inference (lịch sử):** decomposition đã chuyển sang quote + scope object, code tính
offset; có ví dụ JSON và repair cụ thể. Candidate/criteria mới đã đóng băng,
[notebook probe 18 claim](../scripts/kaggle_decomposition_probe_v2.ipynb) sẵn sàng.
Đọc [hướng dẫn hiện hành](DECOMPOSITION_PROBE_V2_KAGGLE.md). Chưa chạy model thật
v2. Probe phải đạt cấu trúc và review mệnh đề trước 39 ca; tích hợp/toàn hệ vẫn chờ.
Các mục bên dưới giữ bối cảnh của những lượt trước.

## Đã làm và chưa làm

Đã audit/replay ZIP 20261012T165922Z, giữ gate trượt 37/39, hoàn tất review AI và
chạy evidence screen offline. Tám tests mới đạt. Không cần Gemini hay GPU cho
những kiểm tra đã làm.

**Cập nhật bước 2:** đã có candidate `AtomicVerifier` và công cụ Decimal,
kiểm thử local bằng backend giả lập. Xem [bàn giao bước 2](ATOMIC_VERIFIER_STEP2.md).
Candidate chưa nối Fact-checker/Writer. Lượt atomic model thật đã chạy nhưng
cả 39 ca trượt decomposition; chưa đo được kiểm từng part/numeric tool.
Xem [đối chiếu và ưu tiên sửa](ATOMIC_VERIFIER_REVIEW_20261013T112627Z-d5bd1415.md).
Không coi screening đã sửa nhãn model hoặc coi 0 false support sau lọc là
chất lượng của model.

## Bước 1 — review bằng chứng và nhãn

**Cập nhật 2026-10-13:** đã review bằng AI đủ 39 ca và điền 195 judgments;
29/39 ca đạt toàn bộ tiêu chí áp dụng theo diễn giải bộ ca hiện tại.
Xem [báo cáo bước 1](STEP1_VERIFIER_SEMANTIC_REVIEW.md). Đánh giá độc lập bằng
người vẫn chờ. Lượt review bước 1 đã dừng đúng phạm vi; sau đó người dùng
yêu cầu triển khai riêng bước 2 và chuẩn bị bước 3, được cập nhật bên dưới.
Inference bước 3 sau đó đã chạy; quality gate trượt và bước 4 còn chờ.

Mở [phiếu đọc 39 ca](VERIFIER_SEMANTIC_REVIEW_20261012T165922Z.md).
Đọc claim/context trước khi kết luận, rồi kiểm output theo năm câu hỏi:

1. Label đúng với context không?
2. Quote thực sự liên quan đến phần cần chứng minh/refute không?
3. Explanation suy ra đúng từ evidence không?
4. Có kiểm đủ từng factual part/quantifier/scope không?
5. Missing information có cụ thể, đúng phần còn thiếu không?

Ghi judgment true/false vào
`docs/blind-verifier-review-draft-20261012T165922Z.jsonl`, tên reviewer, note và
review_status. Không chuyển pending thành pass theo tên file hoặc chỉ số accuracy.
Đặc biệt kiểm hai false supports và các rows assistant gắn cờ; còn lại cũng cần
review. Reviewer tự chịu trách nhiệm đánh giá, assistant triage không thay thế.

## Bước 2 — triển khai candidate kiểm chứng từng phần

**Đã triển khai candidate riêng theo phạm vi dưới đây.** Contract và source
đã đóng băng ở bước 3; đo model thật và review kết quả còn chờ.
Các kiểm tra source/coverage bảo đảm cấu trúc; ngữ nghĩa và scope vẫn cần đo.

1. Thay quyết định whole-claim đơn lẻ bằng output có các factual parts. Mỗi part
   giữ liên kết/span với claim gốc, quantifier/scope, evidence quotes và thông tin
   thiếu. Contract phải phát hiện bỏ sót vế AND, quantity và điều kiện liên quan;
   span coverage đơn thuần không chứng minh decomposition đúng về ngữ nghĩa.
2. Với numerical comparison, model trích xuất values/unit và exact source spans;
   code kiểm nguồn và tính increase/decrease/equality. Không để model tự tính
   hoặc chuyển unit chưa có quy tắc. Scope/association chưa rõ thì unverified.
3. Aggregate theo logic của từng part/quantifier: toàn claim support chỉ khi đủ
   mọi part; explicit conflict trong đúng scope → contradict; gap → NEI.
   Không dùng nhãn gold hoặc hard-code các cases để override verdict.
4. Screen hiện có chỉ là lớp cảnh báo. Không dùng lexical/quantity presence
   thay semantic entailment, không tự mở rộng quote để giả đạt coverage.
5. Trace rõ part được kiểm, numerical tool input/output, evidence, decision và
   validation issues. Giữ blinded input, bounded retry, timeout và ngân sách.
   Tích hợp controller để xử lý yêu cầu bổ sung chỉ sau khi candidate được đo.

Đây là contract mới trong module riêng; test gọi trực tiếp candidate. Khi nối
runner ở bước 3 cần cập nhật caller/criteria/notebook cùng nhau, giữ repair
baseline/serving hiện tại trong khi đo.

## Bước 3 — đóng băng trước lượt model tiếp theo

**Đã chuẩn bị:** frozen contract/criteria/source/data/baseline, runner riêng và
[notebook ba cell](../scripts/kaggle_atomic_verifier_v1.ipynb). Xem
[hướng dẫn](ATOMIC_VERIFIER_STEP3_KAGGLE.md). Bản setup2 sửa test local bị gọi
trong runtime Kaggle; 65/65 tests local đạt, dùng stub. Run `20261013T112627Z-d5bd1415`
đã có inference thật: 39 incomplete do decomposition, gate false. Tiếp theo
sửa interface/schema của decomposition và probe riêng 18 unique claims đã
lưu, rồi chạy lại đủ 39 ca bằng version mới. Bước 4 chưa triển khai.

- Giữ 39 development regressions để tìm regression; chúng đã được inspect nên
  không gọi là held-out độc lập.
- Chốt schema, policy source/prompt/data hashes, model revision và ngân sách
  **trước inference**. Nếu cần thêm model calls, xác định số calls và timeout
  trước khi chạy; không tăng retry đến khi tình cờ đạt.
- Chấm label, false support, failure, coverage/quotes/explanation và missing
  information. Đo cả số support đúng bị từ chối, không tối ưu zero false support
  bằng cách từ chối mọi claim.
- Giữ gate 39/39 đã chốt. Không bỏ ca sai, đổi label hoặc hạ gate sau kết quả.
- Chuẩn bị dữ liệu độc lập do reviewer khác kiểm nhãn/evidence, gồm đủ/thiếu
  evidence, mâu thuẫn, numerical/units, multi-part, scope và causality. Chọn split
  và tiêu chí trước khi dùng kết quả để chọn backend/policy.

Chỉ chạy notebook mới khi bước 2 và frozen criteria/tests hoàn tất. Notebook v3
hiện tại chưa chứa bộ screen mới; chạy lại nó không áp dụng phần sửa offline.

## Bước 4 — hoàn thiện toàn hệ sau quality gate

1. Nối candidate đã được kiểm chứng với Judge/controller; bất đồng/gap giữ
   unverified, controller quyết định tìm tiếp hay dừng theo budget.
2. Giữ Writer dùng claim đã xác minh kèm evidence, không chuyển label agreement
   hay screen_clear thành bằng chứng entailment.
3. Reader toàn PDF: cần endpoint hoạt động và đủ quota; nếu dùng free tier qua
   nhiều kỳ quota thì checkpoint/resume từng trang vẫn phải triển khai/kiểm.
4. Sửa Summarizer heldout_3, chạy tám ca E2E với tiêu chí đóng băng, kiểm sources,
   tool/decision traces, stop reasons, latency/calls và cost nếu backend báo.
5. Review câu trả lời/trích dẫn bằng người, đánh giá độc lập và viết báo cáo bảo vệ
   theo số liệu thực đo. Chỉ ghi hoàn thành khi từng gate có bằng chứng đạt.

## Chạy lại riêng screen offline khi cần tái lập

Trong repo, dùng output-dir mới:

```powershell
.\.venv\Scripts\python.exe -m research_rag.evaluation.screen_blind_verifier --run-dir research-runs/kaggle-20261012T165922Z --output-dir research-runs/evidence-screen-review-new
```

Runner kiểm recorded manifest/metrics, giữ output gốc và từ chối ghi đè output
đã có. Exit 0 của diagnostic chỉ xác nhận chạy script xong; summary luôn giữ
overall_pass=false/promoted_to_serving=false. Kết quả hiện tại đã chạy và lưu,
không cần người dùng chạy lại để hoàn thành phần audit.
