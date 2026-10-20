# Candidate atomic verifier v8 — kiểm tra local 2026-10-17

**Đã sửa candidate và dựng notebook; chưa có inference v8 trên T4.**
Không suy ra accuracy nhãn, zero false support39, human approval hoặc trạng thái
Ready từ các regression dưới đây. Serving/Reader/Summarizer/Writer chưa được
đổi sang atomic v8 trong lượt này.

## Vấn đề và thay đổi

| Lỗi đã thấy ở v7 | Thay đổi v8 | Phạm vi bằng chứng local |
| --- | --- | --- |
| Assessment dài tới 1.536 token và JSON bị cắt | Giới hạn prose/quote/array; decoder chọn quote và operand từ nguồn; repair JSON dùng đúng field assessment | LMFE token filter thật với fixture; JSON assessment dở được lưu và repair trong ngân sách. Chưa đo tỷ lệ JSON hoàn chỉnh bằng model v8 |
| Quote bịa hoặc paraphrase | Enum đoạn nguyên văn trong context, member là span nguồn; validator vẫn kiểm membership/citation | Dùng nguyên generation lỗi v7 call14 và câu mới; bằng chứng bịa bị chặn |
| Khẳng định true nhưng bỏ numeric checks, hoặc bỏ một trong nhiều đại lượng | `numeric_tool_required`/`numeric_requirement_missing` vào repair có giới hạn; hết attempt trả incomplete/null | Trace thật call26 và câu mới seven models/three datasets; kiểm đủ hai yêu cầu mới support. Một yêu cầu đã chứng minh false có thể refute mệnh đề hội |
| Full predicate không bind proof có `exactly`; explicit denial khác đơn vị bị xử lý như thiếu thông tin | Binding hữu hạn cùng họ động từ take/contain/use/evaluate + quantity; so số bằng Decimal; nhận mẫu observed X, not claimed Y rõ ràng | Câu mới về shipment/rehearsal; predicate khác, unit mismatch ngầm, threshold, phủ định/giả định giữ unknown; không tự quy đổi đơn vị |
| Deadline chỉ kiểm sau generation; invalid JSON cuối attempt bỏ qua deadline | Deadline monotonic tuyệt đối qua RecordingBackend tới Transformers stopping criteria; kiểm cả preparation và parse error | StoppingCriteriaList thật trên CPU và adapter thật với model giả lập dừng giữa JSON; partial output/trace được giữ |

`DECOMPOSE_PROMPT`, model/revision, dữ liệu và ngân sách giữ như v7. Không thêm
nhánh theo claim ID007 hoặc sửa prediction để đạt điểm. Sửa thêm hint JSON ở
assessment để không yêu cầu `unresolved` của stage decomposition.

## File chính

- `04_factchecker/inference/atomic_verifier.py`: validation, bounded repair,
  preflight context, binding và truyền deadline.
- `04_factchecker/inference/atomic_decoding.py`: schema evidence/member/operand
  theo nguồn, giới hạn output và stopping criterion.
- `04_factchecker/inference/numeric_verifier.py`: binding identity của từng
  yêu cầu và explicit quantity denial có guard cho ngữ cảnh giả định.
- `research_rag/evaluation/evaluate_atomic_verifier.py`: criteria v8 mặc định,
  smoke12, trace admission và replay nghiêm ngặt; full39 vẫn yêu cầu review mới.
- `research_rag/tests/test_atomic_assessment_v8.py` và fixture
  `fixtures/atomic_v8_v7_assessments.json`: 22 test mới từ trace thật/câu mới.
  Các test cũ thiếu numeric được đổi từ kỳ vọng valid NEI sang yêu cầu repair.
- Contract/criteria v8, freezer/builder v8 và notebook T4 được tạo riêng.
  Packaging test v7 đối chiếu snapshot v7 khi workspace đang phát triển v8.

## Kết quả local

- **332/332** test trong `research_rag/tests` đạt. Log:
  `research-runs/atomic-v8-all-regression.log`.
- Payload notebook giải nén vào thư mục tạm độc lập: **123/123 frozen tests**
  đạt, gồm test mới và fixture trace. Model weights không được nạp.
- Validate-only từ payload đạt cả ba chế độ: probe18/36 call,
  smoke12/96 call, full39/312 call. Không tạo prediction hoặc thư mục output.
- Kiểm compile cell, ZIP/CRC/manifest, bytes nguồn, prerequisite gate, từ chối
  review v7 và guard metadata release đã được thêm vào packaging test v8.
- 11 kiểm tra packaging/admission lịch sử v7 đạt từ snapshot. Log lượt gộp
  `research-runs/atomic-v8-packaging.log` có thêm 4 kiểm tra draft v8 cũ;
  kết quả payload v8 cuối nằm riêng trong `atomic-v8-final-packaging.log`.

Hash/count và log của artifact chốt được ghi trong
[atomic-verifier-v8-validation.json](atomic-verifier-v8-validation.json).
Tokenizer Qwen thật đã cho phép cùng fixture hai yêu cầu số liệu đi qua filter
bằng đường226 token gồm EOS; quote bịa, số không grounded và explanation quá dài
bị chặn. [Báo cáo tokenizer](atomic-verifier-v8-tokenizer-check.json) ghi rõ
đây là fixture feasibility, không phải prediction của model v8. Lượt cuối chỉ
kiểm assessment; không tính lượt re-encode decomposition bị dừng trước đó thành
probe v8 hoặc human review.

Lưu ý phép kiểm ban đầu dùng duy nhất canonical BPE và trượt ở token gộp `.",`
trong free text. Đã kiểm lại bằng cách tách token bị chặn thành các token ký tự
của cùng chuỗi; tất cả token thay thế và EOS đều được callback thật chấp nhận.
Đây là sửa giả định của công cụ QA, không nới schema/validator hoặc thay decoder.
Hai log thất bại đầu được giữ trong `atomic-v8-tokenizer.log` và
`atomic-v8-tokenizer-diagnosis.log`; log đạt là `atomic-v8-tokenizer-final.log`.

## Bảo toàn và đóng băng

Đã kiểm lại 211 file trong snapshot v7 và ZIP/hash đã lưu trong
`atomic-verifier-v7-preserved-before-next-candidate.json`. Giữ nguyên notebook,
criteria, contract, ZIP, prediction và human review v7. Các test release cũ
đọc snapshot thay vì so với source candidate mới.

V8 đóng băng 28 file source/fixture cùng prompt, contract, criteria và manifest
payload 71 file. Các file đã phát hành được khóa bằng hash; freezer/builder
từ chối ghi phiên bản khác lên release v8. Muốn thay behavior sau release cần
candidate mới. Báo cáo freeze/release không ký human review thay người dùng.

## Giới hạn và bước còn thiếu

Deadline mới ngắt hợp tác ở từng bước decode; không ngắt ngay CUDA kernel hoặc
prefill bị treo. Watchdog process vẫn cần. Output nhiều member/numeric record
vẫn có thể vượt 1.536 token; giới hạn độ dài chưa chứng minh hết truncation
trên model thật.

Assessment context tối đa 600 từ; quote 384 ký tự, member 160 ký tự/decoder span
tới 8 từ, explanation 128 ký tự, missing information tối đa 4 item ×160 ký tự.
Input vượt giới hạn context dừng rõ trước model; không âm thầm cắt context.
Enum nguyên văn chặn quote bịa nhưng không chứng minh đúng quan hệ entity/metric
hoặc entailment. Arithmetic không tự nâng observation unknown thành support.

Các fixture mới, smoke12 và bộ39 đều là dữ liệu development đã xem. Chưa có bộ
validation độc lập được nghiệm thu trong lượt này. Không dùng các test đó để
tuyên bố khả năng tổng quát hóa hoặc zero false support ngoài phạm vi đã đo.

Tiếp theo chạy [notebook năm cell trên T4](ATOMIC_VERIFIER_V8_RUN_GUIDE.md), gửi
ZIP để kiểm provenance/replay/evidence. Chỉ khi smoke đạt và probe18 cùng review
người mới của v8 đạt mới chạy đủ39. Sau gate39 còn validation độc lập và tích hợp
Reader/Summarizer/Writer, E2E; dự án hiện chưa Ready.
