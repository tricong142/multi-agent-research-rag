# QASPER BM25 vs Dense — audit ngày 2026-10-17

**Kết luận: lượt benchmark hợp lệ, Dense cao hơn BM25 trên 393 câu dev.**
Không có fallback trong lượt Dense. Đây là kết luận về retrieval đoạn văn;
chưa nghiệm thu chất lượng câu trả lời, verifier hoặc E2E toàn dự án.

## 1. Provenance và replay

Run `20261017T053445Z-0d2b6961`, bắt đầu 12:34:45 ngày 17-10-2026, giờ Việt Nam.
ZIP người dùng: `C:/Users/dellcuatri142/Downloads/output (4).zip`.
SHA256: `21c6c3a53ac3be3a3f694dafc8d4248ad5ca7ed89affa09f0f86c03482946669`.

Đã lưu bản gốc tại
`research-runs/colab-qasper-benchmark/20261017T053445Z-0d2b6961/original-output.zip`.
Output được giữ nguyên trong `output/` cạnh ZIP. Không thay index mặc định của
runtime. Không chạy source hoặc unpickle BM25 object trong ZIP.

- CRC hợp lệ; đủ **34 output files + output-manifest.json**. Từng size/hash khớp.
- **13 input files** khớp release đã giao, gồm source benchmark/retrieval/indexing,
  corpus 18.587 đoạn và 393 dev qrels. Corpus, qrels và source SHA256 khớp.
- Cả **12 stage** hoàn tất với exit 0, `pip check` đạt, **4/4 regression trên
  Colab đạt**. Log xác nhận Tesla T4; PyTorch `2.10.0+cu128`, BGE-Large revision
  `d4aa6901d3a41ba39fb536a557fa166f842b0e09`.
- FAISS đọc được là **IndexFlatIP**, **18.587 vector × 1.024 chiều**. Thứ tự
  `doc_id` khớp corpus. Kiểm hết vector: hữu hạn, norm trong khoảng
  **0,9999998808–1,0000001192**, đúng chuẩn hóa cho inner product.
- Đủ **393 trace BM25 + 393 trace Dense**. Requested/actual backend, method
  trên từng chunk, query/order, ID, số lượng, score và latency đều hợp lệ.
  **Fallback=0, failed query=0** ở cả hai phương pháp.
- Chấm lại **786 trace** cho kết quả khớp `summary.json`. Top-5 ID có thứ tự và
  BM25 scores của cả 393 câu còn khớp lượt local ngày 16-10.
- Không có `qrels_test_candidate.jsonl` trong payload; source benchmark chỉ đọc
  dev. **417 test-candidate qrels chưa được chấm trong lượt này**.

File vector vẫn có tên `faiss_arxiv.index` do runtime dùng tên file cố định cũ.
Corpus hash, mapping và toàn bộ 18.587 ID xác nhận đây là index QASPER vừa dựng;
không phải index arXiv mặc định của workspace.

Record kiểm chứng có thể đọc bằng máy:
[qasper-bm25-dense-audit-20261017T053445Z-0d2b6961.json](qasper-bm25-dense-audit-20261017T053445Z-0d2b6961.json).
Helper audit: `research-runs/audit_qasper_colab_20261017.py`.

## 2. Kết quả đã tính lại

Cùng corpus, cùng câu hỏi có thêm tiêu đề bài, cùng k=5, không có retrieval history.

| Metric | BM25 | Dense BGE-Large | Chênh lệch Dense − BM25 |
|---|---:|---:|---:|
| Câu có ít nhất một đoạn gold trong top-5 | 110/393 | 161/393 | +51 câu |
| Hit@5 | 27,99% | **40,97%** | **+12,98 điểm phần trăm** |
| Mean paragraph Recall@5 | 15,97% | **27,07%** | **+11,10 điểm phần trăm** |
| MRR@5 | 0,15895 | **0,23087** | +0,07193 |
| Fallback/error | 0/0 | 0/0 | — |

Hit@5 đo tỷ lệ câu hỏi có ít nhất một đoạn được gán gold trong top-5.
Paragraph Recall@5 là trung bình tỷ lệ các đoạn gold lấy được ở mỗi câu.
MRR@5 đo thứ hạng của đoạn gold xuất hiện đầu tiên. Cả ba không phải accuracy
câu trả lời, độ đúng nhãn verifier hay false support.

Đối chiếu từng câu:

| Tình huống | Số câu |
|---|---:|
| Cả hai tìm được đoạn gold | 89 |
| Chỉ Dense tìm được | 72 |
| Chỉ BM25 tìm được | 21 |
| Cả hai không tìm được đoạn gold | 211 |

Dense vẫn có **232/393 câu không tìm được đoạn gold trong top-5**. Vì annotation
có thể không liệt kê mọi đoạn tương đương, không được đổi kết luận đó thành
“232 câu chắc chắn không có bằng chứng phù hợp”. Nhưng cũng chưa có cơ sở gọi
retrieval đã đủ chất lượng cho dự án. Chưa có ngưỡng nghiệm thu retrieval được
chốt trong protocol này.

21 câu chỉ BM25 có hit là lý do giữ công cụ BM25 để đánh giá tiếp. Chưa chạy
hybrid, reranker hay adaptive policy trong phép so sánh này; không gán điểm của
hai top-5 gộp lại cho một thuật toán hybrid chưa triển khai.

### Latency và chi phí dựng index

| Số đo trên host Colab này | BM25 | Dense |
|---|---:|---:|
| Mean, đủ 393 câu | 112,63 ms | 58,09 ms |
| P95, đủ 393 câu | 183,15 ms | 50,36 ms |
| Câu đầu tiên | 130,16 ms | **6.586,89 ms**, gồm tải encoder |
| Mean bỏ câu đầu, 392 câu | 112,59 ms | 41,43 ms |

Dựng index mất khoảng **792,08 giây** ở stage; phép đo hai phương pháp mất
**70,11 giây**. Loading/kiểm alignment tĩnh 594,76 ms nằm ngoài query timer.
Mean Dense lớn hơn P95 do outlier tải encoder ở câu đầu; không phải lỗi tính.
Một lượt chạy cố định BM25 trước rồi Dense chưa chứng minh SLA hoặc tốc độ
tổng quát. BM25 dùng CPU, encoder Dense trên host có CUDA; đây là so sánh trên
cấu hình được ghi nhận, không phải so sánh hai phương pháp trên cùng loại tài nguyên.

## 3. Giới hạn của kết luận

- Đây là **QASPER-derived global paragraph retrieval trên dev**, không phải
  official QASPER answer score hoặc đánh giá held-out.
- Audit đã chấm lại trace và kiểm vector/index; **không chạy lại encoder Dense
  trên laptop**. ZIP không có query embeddings để replay ranking mà không nạp BGE.
- CUDA preflight và lệnh build đã được kiểm qua source/log; ZIP chưa xuất device
  của encoder từng query hoặc độ dài truncation thực tế.
- ZIP không chứa chính file notebook đã thực thi. Input manifest khớp payload
  của notebook local đã release; không tuyên bố đã so byte notebook đang chạy.
- Không có chạy verifier, Reader OCR hoặc model E2E trong ZIP này.

## 4. Bước làm tiếp theo để hoàn thiện dự án

**Việc tiếp theo là candidate verifier mới; chưa chạy lại full39 v7 hiện tại.**
Claim 007 đã qua probe v7; lỗi còn lại đã chứng minh nằm ở assessment generation,
numeric binding và deadline. Không thêm điều kiện theo ID/câu cụ thể để tăng điểm.

| Bước | Công việc cụ thể | Điều kiện hoàn thành |
|---|---|---|
| 1. Giữ mốc retrieval | Bảo toàn ZIP, corpus/index/model revision, traces và audit này. Chọn Dense làm baseline có kết quả dev tốt hơn để đánh giá tiếp; giữ BM25 như một công cụ. | Hash/replay khớp, không fallback; đã đạt cho lượt này. Chưa tự đổi policy serving. |
| 2. Sửa verifier tổng quát | Candidate mới, dự kiến v8: giới hạn chuỗi assessment; exact-source quote; numeric yêu cầu đủ từng quantity; binding có từ chen như “exactly”; phủ định tường minh; deadline cả khi JSON lỗi và dừng generation theo ngân sách. | Regression từ trace thật và câu mới đạt; không nới evidence guard, sửa gold hoặc tăng timeout để che lỗi. |
| 3. Tách bộ đánh giá | 18 probe và 39 ca cũ là **dev**. Chuẩn bị bộ validation mới, có gold label/evidence/missing-information được người review, kiểm overlap theo claim/context và nhóm tình huống; đóng băng trước đánh giá và không dùng để tune. | Có dataset/criteria/hash và xác nhận annotation. Bộ verifier riêng này **chưa được tạo/gán nhãn**. 417 retrieval qrels không thay bộ verifier. |
| 4. Freeze và smoke | Freeze đồng bộ source, prompt, contract, criteria, notebook cùng model revision/budget. Chạy regression, hai validate-only và smoke assessment có cả support/contradict/NEI, all/some/none, số liệu và scope. | Không crash/JSON cắt/bỏ numeric/timeout mất trace. Smoke không thay kết quả full39. |
| 5. Probe và full39 | Chạy probe mới và review từng mệnh đề; sau khi đủ admission mới chạy trọn 39 ca cùng bộ validation riêng đã chốt. | Gate39 hiện hành: **39 completed, đúng 39 nhãn, false support=0**, không runtime-failed row, review bằng chứng đủ 39. Báo support coverage/precision, confusion matrix, latency/calls/tokens. |
| 6. Reader local | Cài binary Tesseract và chạy smoke scan thật; kiểm tiếp nhiều cột, bảng, ảnh mờ và thứ tự đọc. Mặc định PyMuPDF → local OCR, không dựa vào Gemini free quota. | Smoke Reader đạt trên tất cả fixture đã chốt; kiểm riêng chất lượng layout/OCR. Hiện smoke local còn 7/9 span vì thiếu binary. |
| 7. Tích hợp và E2E | Nối Summarizer → candidate verifier đã đạt → Writer; thay loader FactChecker cũ. Chạy model/adapter thật trên câu hỏi mới có gold answer, claim và citation. | Có hash verifier được nạp, kiểm các nhánh đủ/thiếu evidence, mâu thuẫn, scan, timeout/retry; review câu trả lời/citation đạt tiêu chí chốt trước. |

Các file trọng tâm ở bước 2: `04_factchecker/inference/atomic_decoding.py`,
`atomic_verifier.py`, `numeric_verifier.py`, runner
`research_rag/evaluation/evaluate_atomic_verifier.py` cùng regression/freeze/packaging.
Đã có snapshot v7, không cần thay predictions v7 để phát triển candidate tiếp.

Reader smoke sau khi host tìm thấy Tesseract:

```powershell
tesseract --version
.\.venv\Scripts\python.exe -m research_rag.evaluation.reader_smoke --manifest research_rag/evaluation/reader_smoke_manifest.jsonl
```

**Agent 3/Summarizer, Agent 5/Writer và toàn dự án vẫn chưa Ready với verifier
mới.** Probe v7 18/18 và human review trước đây không thay accuracy nhãn hoặc
false support39. Full39 v7 vẫn dừng ở 22 predictions (21 incomplete, một sai nhãn);
chưa có số đo false support trên đủ 39 ca. Zero false support trên một bộ hữu hạn,
khi đạt, cũng chỉ là kết quả trên bộ đó.
