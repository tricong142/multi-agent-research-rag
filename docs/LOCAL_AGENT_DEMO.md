# Demo kiểm tra từng agent trên local — 2026-10-14

> Diagnostic lịch sử, không phải nghiệm thu model/E2E. Agent 3 và Agent 5 chưa
> được nghiệm thu với atomic verifier mới; probe18 không đo accuracy nhãn hoặc
> false support. Xem [gate hiện hành](PRODUCTION_GATES_20261016.md).

Đã chạy thành công runner trên máy hiện tại. Kết quả chi tiết nằm tại
`research-runs/local-agent-demo/20261014T035034Z-c6098a53/report.html` và
`summary.json`. Có 94 test logic được chọn cho năm agent đạt; bốn test kiểm
runner/report cũng đạt. Đây chưa phải kết quả chạy toàn bộ năm model fine-tune.

## Chạy lại khi demo

Mở PowerShell tại thư mục `AI ENGINEER`, chạy:

```powershell
.\.venv\Scripts\python.exe -m research_rag.evaluation.local_demo --agent all
```

Hoặc nhấp đúp `run_agent_tests.bat`. Mỗi lượt tạo một thư mục mới, không ghi đè
kết quả cũ. Runner chạy các subprocess tuần tự để giải phóng RAM sau từng stage;
mỗi stage có timeout 180 giây và lưu stdout/stderr. Không tải model hoặc gọi API.

Chạy riêng từng agent khi thầy muốn xem:

```powershell
.\.venv\Scripts\python.exe -m research_rag.evaluation.local_demo --agent retrieval
.\.venv\Scripts\python.exe -m research_rag.evaluation.local_demo --agent reader
.\.venv\Scripts\python.exe -m research_rag.evaluation.local_demo --agent summarizer
.\.venv\Scripts\python.exe -m research_rag.evaluation.local_demo --agent factchecker
.\.venv\Scripts\python.exe -m research_rag.evaluation.local_demo --agent writer
```

Mở đường dẫn `REPORT:` được in cuối lệnh bằng trình duyệt. Các nút trong bảng
mở metrics, test log và predictions/extractions. JSON metrics ghi mode thực thi,
hash dữ liệu đầu vào và số mẫu; summary ghi trạng thái/exit code từng stage.
Exit 0 nghĩa là các stage diagnostic hoàn tất, không phải mọi model đạt chất lượng.

## Kết quả đo được ở lượt local này

| Agent | Test logic | Nguồn số đo | Metrics | Phần chưa được chứng minh |
|---|---:|---|---|---|
| Retrieval | 6/6 | Chạy `RetrievalAgent` với BM25 trên corpus thật, 10 câu hỏi | Known-positive Hit@5 = 0,70; thời gian tìm trung bình 839,51 ms, P95 1.378,57 ms; tải artifact 7.531,97 ms riêng | Dense và LoRA router chưa chạy. Qrels chỉ có positive đã xác nhận, không đầy đủ hoặc độc lập. |
| Reader | 22/22 | Công cụ PyMuPDF chạy trên ba PDF fixture | 7/7 span của hai PDF text khớp; toàn bộ ba PDF = 7/9 = 77,78%; scan không có text layer | Chưa chạy router/critic Gemini, LayoutLMv3 hoặc OCR. Phrase presence không đánh giá thứ tự đọc/bảng. |
| Summarizer | 8/8 | Chấm lại 18 predictions có sẵn | Evidence span nguyên văn = 86,67%; tự báo supported trên câu không trả lời được = 16,67% | Không có inference mới. Supported là quyết định của critic, chưa phải nhãn đúng/sai độc lập về câu trả lời. |
| Fact-checker | 13/13 | Chấm lại 468 predictions có sẵn | Accuracy = 79,91%; macro-F1 = 0,78308; invalid label = 0 | Không có inference mới hoặc phép đo confidence/calibration mới. Dev từng dùng trước đây và có overlap; không coi là final held-out. |
| Writer | 45/45 | Chạy `WriterNode` baseline bảo thủ, không dùng LLM, 100 candidate cases | Schema = 100%; exact-copy proxy = 100%; cảnh báo = 100%; report rỗng = 28%; human faithfulness = null | Đầu vào là candidate claims, không phải gold đã kiểm chứng độc lập. Chưa chạy checkpoint Writer. |

Thời gian phụ thuộc tài nguyên lúc chạy; không dùng một lượt local làm SLA.
Không gộp các metrics này thành một accuracy chung vì chúng đo các mục tiêu khác nhau.

## Trình bày trong buổi bảo vệ

1. Chạy agent được hỏi; mở `report.html` của lượt vừa chạy.
2. Chỉ rõ `execution_mode` trước khi nói số đo. Mở `tests.detail.log` để giải thích
   ca kiểm tra và `predictions.jsonl`/`extractions.jsonl` để xem input/output.
3. Với Retrieval, xem `trace.choice`, `actual_tool`, `source_ids` và các chunk thật.
   Hit@5 đếm câu có positive đã gán nhãn trong năm kết quả đầu.
4. Với Reader, đối chiếu PDF với text và `metadata.page_no` (đánh số từ 0).
   Scan thiếu OCR vẫn được giữ trong mẫu số; không chỉ đưa tỷ lệ 100% của PDF text.
5. Với Writer, mở report có citation; giải thích vì sao schema đúng vẫn có thể
   cảnh báo thiếu coverage. `faithfulness_score=null` nghĩa là chưa có nhãn người.
6. Với Summarizer/Fact-checker, nói rõ đây là chấm lại output lưu trong repository.
   Test backend giả kiểm retry/schema/bằng chứng, không thay thế model evaluation.

Bạn có thể nói: “Em đã kiểm thử logic riêng của năm thành phần; demo này đo trực
tiếp BM25, công cụ đọc PDF và Writer baseline. Chất lượng model được trình bày
bằng predictions có provenance riêng. Em chưa khẳng định cả năm checkpoint chạy
được trên laptop hiện tại.”

## Điều kiện để chạy đúng checkpoint trên local

Preflight lượt này: RAM tổng 7,69 GiB, RAM trống khoảng 0,48 GiB,
PyTorch `2.6.0+cpu`, `cuda_available=false`; FAISS có 41.549 vectors, 1.024 chiều,
mapping khớp. Không có Tesseract hoặc `GEMINI_API_KEY` trong môi trường chạy.

- Summarizer có hai adapter nhưng thiếu base weights Qwen2.5-7B trong cache.
- Writer có adapter nhưng thiếu base weights Qwen2.5-1.5B trong cache.
- Fact-checker có đủ hai shard merged, tổng 6.171.926.544 byte; máy hiện tại
  không có CUDA và RAM trống rất thấp. Lượt này chưa thử load checkpoint.
- Encoder BGE có weights, nhưng dense inference chưa chạy; không gắn metrics
  BM25 thành metrics dense.

Nếu cần demo inference của đúng các model đã train, dùng host có đủ tài nguyên
và artifact, chạy từng component rồi chuyển predictions/log về laptop để trình
bày. Kaggle GPU đang dùng là một host khác; kết quả đó phải ghi là inference trên
Kaggle. Runner local không đổi sang model nhỏ hơn rồi coi đó là checkpoint đã train.

`run_demo.bat`/`web_demo` hiện là mô phỏng workflow, có nhãn rõ trên giao diện và
API. Những số minh họa ở đó không được đưa vào bảng đánh giá luận văn. Sử dụng
runner trong tài liệu này cho các số đo vừa kiểm chứng.

Atomic verifier đang có bản sửa v5 chưa đóng băng và chưa chạy model. Bộ test demo
được chọn riêng cho serving contracts; nó không thay gate probe 18/18, 39 ca hoặc
E2E toàn hệ. Các công việc đó vẫn cần hoàn thiện trước nghiệm thu dự án.
