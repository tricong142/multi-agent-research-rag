# Bước B — chạy ứng viên verifier riêng trên Kaggle

Mục tiêu: kiểm tra model tự phân loại claim/context và chỉ ra bằng chứng trước
khi thấy nhãn Judge. Đây là thử nghiệm development, chưa tích hợp vào runtime.
Giữ cấu hình serving `repair` hiện hành. Không cần chạy lại confidence cũ.

## Cách chạy

1. Lưu Output/ZIP của notebook endpoint hiện tại. Tạo notebook Kaggle mới,
   Private; import `scripts/kaggle_blind_verifier.ipynb`.
2. Bật GPU T4 (T4 x2 cũng dùng được, chỉ nạp một model tại một thời điểm) và
   Internet. Dùng hai dataset hiện có của tài khoản: Research RAG Five Agents
   Workspace và Research RAG Runtime Diagnostics **v2**. Cell 1 mount qua
   kagglehub; cell 2 xác thực đúng manifest v2. Không cần bật Secret Gemini.
3. Chạy **cell 1** để mount dataset.
4. Chạy **cell 2** để tạo workspace mới, áp source patch có hash, cài runtime,
   chạy tests và preflight. Chờ `SETUP COMPLETE`; nếu lỗi, giữ ZIP setup và dừng.
   Runner dùng `venv --without-pip`, cài wrapt như runner GPU đã chạy trước đây.
5. Chạy **cell 3 một lần**. Nó chạy module `compare_blind_verifier`, hiển thị
   summary, metrics và baseline-metrics, rồi đóng ZIP.
6. Save Version **with Output**, tải ZIP `rag-validation-…zip` ở cuối cell 3
   và gửi lại để đối chiếu. Dừng GPU session sau khi đã lưu.

Không copy cell này vào notebook CPU endpoint: hai notebook có runtime khác
nhau. Không chạy lại cùng stage hoặc sửa tiêu chí sau khi đã thấy kết quả.
Notebook đã đóng gói source mới nên không cần upload lại dataset/repo.

## Phép thử đã đóng băng trước inference

- Hai backend: checkpoint fine-tuned hiện có và Qwen2.5-3B-Instruct ở revision
  `aa8e72537993ba99e69dfaafa59ed015b17504d1`. Base weights có thể tải khoảng
  6,2 GB nếu chưa có cache; tái sử dụng loader của phép thử confidence trước.
- 12 claim/context đã xem trước đây, một prediction cho mỗi case/backend:
  tổng 24 predictions, tối đa hai attempts cho lỗi output mỗi case, tối đa
  48 calls. Lỗi backend không được retry như lỗi JSON. Budget 384 output tokens.
- Mỗi request chỉ chứa claim/context. Gold label, proposed label và explanation
  Judge không đi vào model, kể cả repair. Sau inference, code mới so với hai
  nhãn được kiểm soát (đúng/sai) để chấm khả năng phát hiện bất đồng.
- Baseline là 24 kết quả `finetuned__repair` từ run `20261010T101538Z`, có hash
  nguồn và hash snapshot. Mốc đã đo: nhận 4/12 nhãn đúng và 2/12 nhãn sai ở
  threshold 0,7. Không phát sinh lượt model mới để tạo lại baseline.
- Mỗi backend đạt gate tự động khi: đủ 12 case duy nhất, nhận đúng 12/12 nhãn,
  không đồng ý nhãn sai trong các cặp đã định, không false support, không runtime
  failure và attempts nằm trong budget. Có ít nhất một backend đạt thì summary
  automated_gate_pass=true; **overall_pass vẫn false vì chờ người review**.

Output của verifier gồm `assessed_label`, `evidence_quotes`, `missing_information`,
`explanation`. Code kiểm kiểu, enum, trường bắt buộc, trích dẫn nguyên văn trong
context và sự nhất quán tối thiểu giữa nhãn/thông tin thiếu. Quote đúng vị trí
chưa chứng minh suy luận đúng; người review phải kiểm nội dung.

`claim_verified` trong phép so chỉ true khi hai nhãn cùng support, có quote hợp
lệ và không thiếu thông tin. Hai nhãn cùng not_enough_info vẫn là needs_context.
Đây là quyết định mô phỏng trong diagnostic; controller/Writer chưa sử dụng nó.

## Đọc output và quyết định

| Kết quả | Bước tiếp theo |
| --- | --- |
| experiment_completed=true, automated_gate_pass=false | Chương trình đã chấm xong nhưng ứng viên chưa đạt. Giữ trace và phân loại lỗi; chưa đổi serving. Exit 1 là chủ ý. |
| automated_gate_pass=true | Review `evidence-review.jsonl` theo rubric; kiểm đầy đủ quote, suy luận, phạm vi và thông tin thiếu. Chưa tự động nghiệm thu. |
| summary thiếu hoặc experiment chưa hoàn tất | Kiểm status/stderr; không coi dữ liệu một phần là pass. |

Sau review đạt, cần thử trên dữ liệu độc lập và regression trước khi tích hợp.
Khi tích hợp, bất đồng/thiếu bằng chứng phải quay về controller để tìm thêm hoặc
dừng theo ngân sách; Writer tiếp tục chỉ nhận claim đã qua gate xác minh.

## Giới hạn và kiểm tra local

12 case là synthetic development đã được xem. 24 phép đối chiếu/backend là
hai nhãn dùng chung một prediction, không phải 24 mẫu độc lập. Verifier không
thấy nhãn Judge nhưng có thể sai giống Judge; đồng thuận không phải xác suất
đúng đã được hiệu chỉnh. Budget 384 tokens khác 192 của baseline, nên không
diễn giải chênh lệch tốc độ/chi phí như một so sánh nhân quả có kiểm soát.

11 tests local đạt: sáu verifier/experiment tests, bốn tests của loader/harness
confidence dùng lại và một test notebook/source/setup. Models trong tests giả
lập; chưa chạy notebook mới hoặc verifier với weights thật trên Kaggle.

## File mới/thay đổi

- `04_factchecker/inference/verifier.py`: ứng viên blind verifier và validator.
- `research_rag/evaluation/compare_blind_verifier.py`: trace, chấm, review rows.
- `research_rag/evaluation/blind_verifier_criteria.json`: tiêu chí trước chạy.
- `research_rag/evaluation/blind_verifier_repair_baseline.json`: snapshot lịch sử.
- `research_rag/tests/test_blind_verifier.py`: regression về evidence/blinding/gate.
- `research_rag/tests/test_validation_notebook.py`: thêm kiểm tra notebook mới.
- `scripts/build_blind_verifier_notebook.py`, `scripts/kaggle_blind_verifier.ipynb`:
  notebook ba cell có source patch.
- Tài liệu đối chiếu Reader, audit JSON và PROJECT_STATUS được cập nhật.
