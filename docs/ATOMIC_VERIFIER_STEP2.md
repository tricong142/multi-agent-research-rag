# Bước 2 — candidate kiểm từng mệnh đề

Ngày: 2026-10-13. Policy: `atomic-verifier-draft-v1`.

**Đã triển khai candidate và kiểm thử logic local bằng backend giả lập.**
Đây là implementation thử nghiệm trước bước đóng băng/chạy model thật.
Chưa có số liệu chất lượng model thật cho candidate này. Kết quả `logic_v3`
đã đo vẫn là 37/39; kết quả review bước 1 vẫn giữ nguyên.

## Luồng thực thi

1. `AtomicVerifier.verify(claim, context)` gọi model để tách claim. Lượt này
   chỉ nhận claim, không nhận context, gold label hoặc kết luận của Judge.
2. Code kiểm từng span `start:end`, quote nguyên văn, thứ tự, độ phủ nội dung,
   quantity/unit, từ nối AND, quantifier và các trường scope bắt buộc. Không
   cho cắt đôi một từ/số hoặc bỏ một vế vào khoảng trống giữa các span.
3. Mỗi part có một lượt model riêng, nhận claim gốc, part và context. Model
   trả bằng chứng, đối tượng quan sát, kết quả predicate, phạm vi quần thể,
   thông tin thiếu và giải thích ngắn. Scope gồm entity, metric, time, condition;
   các giá trị là đoạn có thật trong claim. Ngữ cảnh chung được giữ ở mỗi lượt.
4. Nếu có số liệu cần so sánh, model trích xuất giá trị/đơn vị/quote. Code kiểm
   nguồn và dùng `Decimal` tính quan hệ, thay cho phép tính do model đề xuất.
5. Code tổng hợp từng part theo quantifier và toàn claim theo AND. Trace giữ
   input/output model, lỗi validation, kết quả số học, label từng part, số calls,
   thời gian và lý do dừng.

Đây là các bước trong candidate verifier; chưa nối candidate vào graph phục vụ.

## Quy tắc tổng hợp bằng code

| Loại part | Support | Contradict | NEI |
| --- | --- | --- | --- |
| Atomic | Bằng chứng cùng phạm vi xác nhận, không thiếu dữ liệu | Bằng chứng cùng phạm vi phản bác | Thiếu, sai phạm vi hoặc bằng chứng xung đột |
| All | Có coverage đầy đủ và mọi instance thỏa predicate | Có instance trong phạm vi không thỏa | Chỉ có một phần instance đạt |
| Some | Có instance trong phạm vi thỏa predicate | Coverage đầy đủ, không instance nào thỏa | Một vài instance không đạt chưa đủ để bác bỏ |
| None | Coverage đầy đủ, không instance nào thỏa predicate | Có instance trong phạm vi thỏa | Chưa biết hết quần thể và chưa có positive witness |
| AND giữa các part | Tất cả part support | Ít nhất một part contradict | Không có part contradict nhưng có part NEI |

`truth` ở observation là giá trị của **predicate dương trước quantifier**.
Ví dụ “none leaked”: một thiết bị bị rò rỉ được ghi `truth="true"`, từ đó code
tính `contradict`. Coverage đầy đủ yêu cầu nguồn trích dẫn, tập member không
trùng và observation cho mọi member được khai báo.

Nếu hết budget, quá deadline, backend lỗi, hoặc decomposition chưa giải quyết
được, output là `status="incomplete"`, `assessed_label=null`. Kết quả một phần
không được biến thành xác nhận cả claim. Candidate luôn giữ
`claim_verified=false` và `promoted_to_serving=false` ở giai đoạn thử nghiệm.

## Công cụ số học

`numeric_verifier.check_numeric` hiện hỗ trợ:

- So sánh giá trị chính xác trong claim với giá trị được trích từ context.
- So sánh trước/sau trong một đoạn rõ thứ tự: `from X to Y` hoặc
  `X before ... and Y after ...`; trả increase/decrease/unchanged và delta.
- Số nguyên, số thập phân, số âm, phần trăm và số viết bằng chữ đơn giản đã có
  trong helper của repo. Các giá trị tính toán dùng `Decimal`.
- Kiểm quote chứa đúng số/đơn vị, không lấy `4` từ `94`, bỏ dấu âm hoặc cắt
  phần thập phân. Đơn vị phải khớp; `%` và `percent` là alias được xử lý rõ.
- Kiểm metric của part xuất hiện trong passage số liệu; không dùng phép tăng
  recall để tự xác nhận tăng precision khi metric không khớp.

Ví dụ có trong test: model khai báo predicate giảm là true với **42 ms →
55 ms**. Tool tính `delta=13`, `observed_direction=increase`, predicate giảm
trở thành false; part được tổng hợp là contradict.

Các dạng chưa có quy tắc được giữ unknown: chuyển đơn vị, so sánh ngưỡng/xấp
xỉ, tính lượng thay đổi yêu cầu thêm công thức, thứ tự trước/sau không rõ,
phủ định số học hoặc passage có điều kiện/giả định mà parser chưa hỗ trợ.
Unknown không có nghĩa dữ kiện chắc chắn sai.

## API và ngân sách

Entry point: `04_factchecker.inference.atomic_verifier.AtomicVerifier`.
Backend tiếp tục dùng giao diện `JSONBackend.generate_json` hiện có. Không thêm
dependency và không đổi API của `BlindVerifier`/Judge đang dùng.

Constructor yêu cầu người gọi truyền rõ:

```python
AtomicVerifier(
    backend,
    max_calls=...,
    max_attempts=...,
    max_new_tokens=...,
    timeout_seconds=...,
)
```

Đây là tên tham số API; dấu `...` phải được thay bằng ngân sách hợp lệ ở runner.
Không có ngân sách thí nghiệm mặc định được ngầm coi là đã đóng băng.
Với N part và không repair cần `1 + N` model calls. `max_calls` áp dụng cho
toàn claim, bao gồm decomposition và repair; `max_attempts` áp dụng mỗi stage.
Repair chỉ dành cho JSON/contract lỗi. Backend lỗi dừng ngay, trace chỉ lưu loại
exception để tránh ghi thông tin nhạy cảm trong error message.

**Giới hạn timeout:** candidate kiểm deadline trước/sau mỗi call, bỏ kết quả
trả về muộn và không gọi tiếp. Giao diện JSONBackend hiện là synchronous;
candidate không thể ngắt một call đang bị treo. Khi chạy model thật, runner
phải dùng hard process timeout, có thể tái sử dụng `research_rag.local.run_worker`.
Phần nối runner và chốt budget thí nghiệm thuộc bước 3.

## Kiểm chứng và hồ sơ

Lượt kiểm tra cuối: **51/51 tests đạt**, gồm **21 test candidate mới** và
30 test hồi quy liên quan; không có error/failure. Hash của 13 file trong
manifest verifier `logic_v3` khớp bản đã audit. Trace minh họa dùng stub cho
kết quả `contradict` với delta `13 ms`, được ghi rõ là dữ liệu giả lập.

Lệnh chạy các test liên quan:

```powershell
.\.venv\Scripts\python.exe -m unittest research_rag.tests.test_atomic_verifier research_rag.tests.test_blind_verifier research_rag.tests.test_blind_verifier_logic research_rag.tests.test_blind_verifier_regression research_rag.tests.test_verifier_evidence_screen -v
```

- [Bản ghi kết quả local và hash source](atomic-verifier-step2-validation.json).
- [Log 51 tests](atomic-verifier-step2-tests.log).
- [Trace minh họa với backend giả lập, không phải inference thật](atomic-verifier-step2-example.json).
- [Test candidate](../research_rag/tests/test_atomic_verifier.py).
- [Implementation candidate](../04_factchecker/inference/atomic_verifier.py).
- [Công cụ số học](../04_factchecker/inference/numeric_verifier.py).

Các test kiểm bỏ vế/quantity/scope, quote không có trong nguồn, all/some/none,
coverage thiếu member, phép tính, đơn vị, metric, conflict, blinding, repair,
backend error, call budget và deadline. Backend giả lập cố ý trả một số quyết
định sai để kiểm code phản ứng; test pass không chứng minh model hiểu ngữ nghĩa.

## Giới hạn cần đo ở bước 3

- Decomposition, nhận diện scope, ý nghĩa quote và tính đầy đủ của quần thể
  vẫn có phần do model suy luận. Span đầy đủ và quote nguyên văn không chứng
  minh entailment. Ledger đầy đủ chỉ kiểm cấu trúc theo quần thể model khai báo.
- Parser hiện dành cho cấu trúc tiếng Anh tương đối đơn giản; AND trong tên
  hoặc cấu trúc logic phức tạp có thể bị từ chối. OR/nested quantifiers chưa
  được tổng hợp tự động.
- Bộ lọc số học bảo thủ có thể từ chối bằng chứng đúng nhưng khác cách diễn
  đạt. Cần đo cả false support và số support đúng bị giữ lại.
- Tăng số calls làm tăng latency và token; chưa có cost đo được.

**Bước 2 dừng ở implementation và kiểm thử local.** Bước 3 sẽ chốt schema,
hash prompt/source/data, model revision, budget và criteria; cập nhật runner/
notebook để chạy riêng candidate. Bước 4 tích hợp và E2E chỉ sau quality gate.
