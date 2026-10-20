# Trạng thái và thứ tự nghiệm thu — 2026-10-16

> Cập nhật 2026-10-17: [benchmark QASPER mới đã audit](QASPER_BM25_DENSE_REVIEW_20261017.md)
> hợp lệ: Dense393/BM25393, không fallback; FAISS QASPER đã dựng. Mục chờ GPU
> bên dưới giữ lịch sử trước lượt chạy. Verifier39 và E2E vẫn chưa đạt.

**Dự án chưa Ready.** Summarizer (Agent 3) và Writer (Agent 5) chưa được tích
hợp/đánh giá E2E với atomic verifier mới. `research_rag/local.py` vẫn khởi tạo
`FactCheckerNode` cũ. Unit test, demo baseline và chấm lại predictions cũ không
phải bằng chứng nghiệm thu chất lượng model hoặc E2E.

## 1. Retrieval: đã chạy BM25, Dense còn chờ GPU

Lượt mới: `research-runs/qasper-dev-20261016-bm25-preflight/`.
`summary.json`, `provenance.json` và `bm25-traces.jsonl` lưu số đo, hash và
393 truy vấn với backend thực tế. Không đọc `qrels_test_candidate.jsonl`.

| Phép đo trên 393 dev, k=5 | BM25 thực chạy | Dense |
|---|---:|---|
| Số truy vấn | 393/393 | 0, bị chặn ở preflight |
| Hit@5 | 0,2798982188 | Chưa đo |
| Paragraph Recall@5 | 0,1596641625 | Chưa đo |
| MRR@5 | 0,1589482612 | Chưa đo |
| Fallback/error | 0/0 | Chưa có lượt Dense hợp lệ |
| Latency mean/P95 | 860,53 / 2.354,77 ms | Chưa đo |

Latency này đo trên laptop có tải khác, không dùng làm SLA hoặc so với GPU.
Hit/Recall khớp lượt BM25 2026-09-27. Đây là retrieval theo đoạn văn toàn corpus,
với câu hỏi có thêm tiêu đề bài, **không phải official QASPER answer score**.
Không suy ra chất lượng câu trả lời hay verifier từ Recall.

Index `kb_indexing/indices/qasper_bm25_20260927` chưa có FAISS.
`faiss_doc_ids.json` chỉ là ánh xạ; encoder BGE có cache không chứng minh Dense
đã chạy. Runtime nay kiểm FAISS trước encoder. Serving vẫn ghi rõ fallback;
benchmark từ chối tính điểm Dense nếu bất kỳ truy vấn nào chạy BM25 hoặc lỗi.
Kiểm tra một truy vấn dev bằng đường `method="dense"` thật được lưu tại
`dense-fallback-audit.json`; replay toàn bộ trace BM25 tại `replay-validation.json`.

**Chạy tiếp:** mở `scripts/colab_qasper_bm25_dense_dev.ipynb` trên Colab T4,
chạy bốn code cell theo thứ tự và tải ZIP. Notebook có corpus 18.587 đoạn và
393 dev qrels; không chứa 417 test-candidate qrels hoặc verifier cases.
Nó tải BGE-Large revision `d4aa6901d3a41ba39fb536a557fa166f842b0e09`, dựng
FAISS mới, kiểm corpus/hash/mapping/count/dimension/IP, rồi chạy cả hai phương
pháp trên cùng câu hỏi và k. Không dùng FAISS arXiv có sẵn cho QASPER.

Điều kiện công nhận so sánh: đủ 393 BM25 + 393 Dense, `paired_comparison_valid=true`,
zero fallback/error, input/source/index hash khớp. ZIP chứa trace, index, dependency
freeze và log cả lượt thất bại. Thời gian tải encoder ở truy vấn Dense đầu được
ghi riêng. Notebook đã kiểm payload cô lập; **chưa chạy trên GPU** ở lượt này.

## 2. Verifier: giữ v7, sửa nguyên nhân assessment trong candidate kế tiếp

Probe v7 run `20261016T024708Z-a57ee72a` đạt 18/18 **cấu trúc tách mệnh đề**;
tricong đã xác nhận đủ năm tiêu chí cho 18 claim. Kết quả này không đo accuracy
nhãn, false support hoặc E2E. Claim 007 không còn là ca trượt trong probe v7.

Full39 run `20261016T071213Z-7c8c33c6` timeout: 22 predictions được lưu,
21 incomplete, một completed sai nhãn. Không có output support ở phần này;
**false support trên đủ 39 ca chưa đo xong**, không được báo là zero false support.
Xem audit `ATOMIC_VERIFIER_V7_FULL39_REVIEW_20261016T071213Z-7c8c33c6.md`.

Không vá theo ID 007 hoặc sửa gold/budget để đạt điểm. Candidate tiếp theo cần:

1. Giới hạn chuỗi assessment để tránh JSON bị cắt; giữ quote nguyên văn và kiểm
   quan hệ entity/metric/time/condition. Không ép một câu trong context thành
   support chỉ vì nó được trích đúng.
2. Sửa numeric binding đối với predicate đầy đủ và kiểm đủ từng quantity;
   explicit denial và thiếu thông tin phải có quy tắc phân biệt rõ.
3. Deadline phải được kiểm cả khi parse lỗi; generation phải dừng theo ngân
   sách, có watchdog và lưu đầy đủ kết quả lỗi.
4. Regression từ trace thật cùng các biến thể mới; không dùng probe18 làm tập
   đánh giá độc lập. Cả 18 và 39 hiện là **development**, đều đã được xem để sửa.
5. Chuẩn bị bộ validation mới riêng trước lượt candidate, có nhãn người review,
   kiểm overlap theo claim/context và nhóm tình huống; không dùng nó để tune.
   Nếu xem kết quả rồi sửa tiếp thì chuyển các ca đó sang dev, tạo bộ đánh giá mới.
   **Bộ verifier độc lập này chưa được tạo/gán nhãn**, chưa có kết quả để báo.
6. Freeze source/prompt/contract/criteria/notebook cùng model revision và budget;
   validate-only và regression đạt; probe mới đạt và được người đọc; sau đó chạy
   đầy đủ 39 development cases và bộ validation đã chốt riêng.

Gate39 hiện hành vẫn yêu cầu đủ 39 completed, đúng 39 nhãn, false support=0,
không runtime-failed row và review bằng chứng ở cả 39 ca. Không hỗ trợ tất cả
bằng cách abstain cũng không đạt. Báo thêm support coverage/precision và confusion
matrix để zero false support không che việc không nhận ra ca support.

Chưa có candidate verifier mới hoặc GPU inference mới trong lượt chuẩn bị
retrieval này. Không chạy lại v7 39 ca với cùng lỗi đã biết chỉ để tiêu GPU.

Đã snapshot v7 thành 211 file, có manifest và archive SHA256; dùng nguyên
payload notebook đã chạy thay vì các module serving đang sửa trong workspace.
Đã replay cô lập 18 probe + 22 predictions39 và kiểm đủ 26 frozen sources.
Record: `atomic-verifier-v7-preserved-before-next-candidate.json`. Chạy lại v7
từ snapshot này; không dựng lại artifact mang tên v7 từ workspace đã phát triển.

## 3. Reader local và tích hợp cuối

Reader mặc định nay dùng PyMuPDF cho text, Tesseract cho scan hoặc khi parser
rỗng/lỗi. Không gọi Gemini router/critic ở chế độ mặc định; `allow_remote=True`
là lựa chọn rõ ràng cho diagnostic Gemini cũ. Extraction guard chặn text rỗng,
confidence/bbox sai và output bị từ chối; không công nhận semantic/table accuracy.
OCR gom từ thành paragraph có bbox để chunk giữ được câu bằng chứng. Tesseract
có timeout 60 giây/trang; lỗi đóng tài liệu đúng cách và không xuất block bị loại.

Máy này chưa có binary Tesseract; smoke scan thật chưa đạt. Cần cài Tesseract
local rồi chạy `python -m research_rag.evaluation.reader_smoke --manifest
research_rag/evaluation/reader_smoke_manifest.jsonl`. Không thay OCR bằng Gemini
để che lỗi thiếu binary. Smoke fixture chỉ đo span presence; tài liệu nhiều cột,
bảng, ảnh mờ và thứ tự đọc vẫn cần đánh giá riêng.

Smoke local mới thực chạy cả ba PDF: 7/9 expected spans, hai PDF text đạt 7/7,
PDF scan lỗi; `passed=false`. Bảy span text không được trình bày thành tỷ lệ
100% cho toàn Reader. File: `research-runs/reader-local-smoke-20261016.json`.

Chỉ sau khi verifier qua gate mới nối Summarizer → verifier → Writer. E2E cần
model/adapter thật, evidence/citation gold và các nhánh đủ evidence, thiếu
evidence, mâu thuẫn, scan, timeout/retry. Fake-backend test không thay E2E.
Kết quả E2E phải ghi đúng phiên bản/hash verifier đã nạp, không dùng lại nhãn
`verified_claims` từ FactChecker cũ rồi coi là verifier mới.

| Thành phần | Kết luận hiện tại |
|---|---|
| Retrieval | BM25 dev đã đo; Dense benchmark chờ lượt GPU |
| Reader | Có chế độ local và regression; OCR binary/quality còn thiếu |
| Summarizer / Agent 3 | Chưa nghiệm thu với atomic verifier mới |
| Atomic verifier | Probe v7 đạt; full39 không đạt; chưa được promotion |
| Writer / Agent 5 | Chưa nghiệm thu với atomic verifier mới |
| Toàn pipeline | Chưa có E2E đạt với verifier mới; chưa Ready |

## Kiểm tra sau thay đổi

- 310/310 regression CPU đạt, bao gồm FAISS với encoder giả lập, local Reader,
  retry Gemini qua mock transport, graph và payload notebook runtime đã dựng lại.
- 2/2 kiểm thử notebook QASPER đạt: hash/cú pháp và regression chạy từ payload
  cô lập. Đây không phải lượt chạy BGE trên GPU.
- Cả hai validate-only v7 đạt: probe18/max36 calls, verifier39/max312 calls.
- Trace BM25393 replay khớp; Dense request thật xác nhận fallback BM25 mà không
  tải encoder. Snapshot v7 replay18+22 bằng source cô lập đạt.
- Reader smoke thật 7/9 span, scan chưa đạt; không gọi Gemini để chạy smoke này.

Record có số đo/hash và trạng thái chưa đạt:
`production-gates-validation-20261016.json`. Bản report retrieval lưu lâu dài:
`qasper-bm25-dev-20261016.json`. Toàn bộ các kiểm tra trên không thay gate39,
bộ verifier validation riêng hoặc model E2E.
