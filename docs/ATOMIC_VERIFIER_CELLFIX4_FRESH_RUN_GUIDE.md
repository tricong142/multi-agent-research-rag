# Cellfix4: audit ZIP và chạy lại từ runtime mới

ZIP đầu vào: `output-cellfix3-fresh-20261017T101839Z-a9590fe1.zip`.
SHA256: `37fa91b236c15078ebaf2fb571a3fdf91dd76f96ad88dae6ee1fd6adf759eec2`.

Audit xác nhận 47 file đầu ra, 78 file đầu vào và 32 file source/fixture khớp
release cellfix3. Toàn bộ 12 kết quả replay được; 29 lượt gọi khớp raw JSON,
prompt, schema hash và provenance. Model/revision khớp baseline đã chốt.
Đây là kiểm tính nhất quán artifact, không phải chữ ký xác thực máy Colab.

Kết quả thực tế của ZIP: **11/12 đúng nhãn, 0 false support, 1 incomplete**.
153 regression và ba validate-only đã qua trên Colab. Đây là smoke development;
chưa có probe18 hoặc full39 của candidate này. Số 37/39 thuộc baseline lịch sử.

## Lỗi và thay đổi

`contract:cross_sentence` lần đầu chỉ kiểm số models nên bị
`numeric_requirement_missing`. Repair trả đủ hai check, mỗi check có
`source_quote` đúng nguyên văn, nhưng `observations[].quotes` chỉ lặp câu đầu.
Validator cellfix3 từ chối `numeric_evidence_not_cited`; gate dừng đúng thiết kế.

Cellfix4 xác định `numeric.source_quote` cũng là citation tường minh do model
trả về. Code kiểm source và toán hạng trước rồi hợp nhất citation đó vào bản sao
ledger `quotes`. `citation_additions` ghi rõ phần được thêm; raw output không bị
sửa nên có thể replay. Đây là **thay đổi contract serialization có chủ đích**:
thiếu bản sao citation không còn tự làm output hỏng. Không tạo quantity/check,
không thêm bằng chứng từ corpus, không suy ra quan hệ còn thiếu.

Validator giữ kiểm tra mỗi quantity, duplicate, binding, toán học, phủ định,
scope, giới hạn quote và ngân sách repair. Thêm guard bảo thủ cho citation của
another/other/different/second/third target; ca negative “second report” vẫn bị
chặn kể cả khi trích dẫn đầy đủ. Guard hữu hạn này không giải quyết toàn bộ
coreference, quan hệ giữa câu hoặc semantic entailment.

Original v8, cellfix3, ZIP và predictions được giữ nguyên. Candidate mới ở
`scripts/colab_atomic_verifier_cellfix4_fresh.ipynb`; source chạy độc lập trong
payload, không thay source đang serving. Source, prompt, contract, criteria,
regression và fixture của candidate được đóng băng cùng nhau.

## Cách chạy

1. Upload `colab_atomic_verifier_cellfix4_fresh.ipynb` vào Colab; dùng runtime mới
   và chọn GPU T4. Không chạy chồng các cell vá của notebook cũ.
2. Chạy lần lượt năm code cell hoặc Run all. Ba cell đầu kiểm hash, dựng môi
   trường, chạy regression/validate-only, xác nhận CUDA và tải model đúng revision.
3. Cell 4 chạy smoke12, tải ZIP kể cả khi trượt. Chỉ kết luận đạt khi metrics có
   `automated_gate_pass: true`, đúng 12/12, false_support=0, runtime_failed_rows=0.
4. Cell 5 tự bỏ qua khi smoke trượt. Nếu smoke đạt, cell này chạy probe18 và tải
   ZIP cập nhật. Giữ ZIP tải **sau cùng**, kể cả trình duyệt đổi tên thêm `(1)`.
5. Gửi ZIP mới để audit và review 18 claim. Chỉ sau probe đạt và human review mới
   đúng candidate mới chạy full39. Notebook không tự chạy full39/serving.

Giữ nguyên Qwen/Qwen2.5-3B-Instruct revision
`aa8e72537993ba99e69dfaafa59ed015b17504d1`, NF4/float16/seed42; mỗi ca 8 call,
2 attempt/stage, 1536 token/call, deadline 180 giây. Không đổi gold hoặc gate.

Kết quả validation local nằm trong `atomic-verifier-cellfix4-validation.json`.
Regression/replay không thay thế lần chạy model T4 mới. Chưa thể khẳng định
smoke mới đạt 12/12, probe đạt 18/18 hoặc zero false support trên full39.
