# Bàn giao đồ án Research RAG với R8 v12

Bản bàn giao dùng **R8 v12 gốc đã khóa** làm verifier. Notebook demo
`table-proof` thêm bước kiểm tra ô theo tọa độ đã đối chiếu cho hai PDF.
Điểm holdout dưới đây đo **R8 v12 gốc**. Bản tích hợp `table-proof` được đo
trên **bộ demo ba câu sau sửa**.

## Kết quả bàn giao

| Chỉ số trên holdout độc lập R8 v12 gốc | Kết quả | Ngưỡng bàn giao | Ngưỡng ban đầu |
| --- | ---: | ---: | ---: |
| False support | 0 | 0 | 0 |
| Support precision | 100% (7/7) | ≥85% | ≥85% |
| Macro-F1 | 80,54% | ≥80,54% | ≥85% |
| Abstention trên ca đủ bằng chứng | 30% (6/20) | ≤30% | ≤15% |

Holdout **24/30**, đạt **4/4 ngưỡng bàn giao** đã thống nhất với giảng viên
và **2/4 ngưỡng ban đầu**. Ngưỡng bàn giao được điều chỉnh sau khi xem
holdout. Bộ chấm đã khóa được chạy lại trong thư mục tạm với mã nguồn
từ gói đã khóa và ghi nhận **0 lỗi trích dẫn**.

Demo Kaggle T4 x2 đạt **3/3** trên hai PDF thật. Ba câu đã được dùng để sửa
demo. Hai báo cáo có đáp án mang trạng thái `partial` do cảnh báo độ tin cậy
từ bước trước, nhưng cả hai trả lời đủ, trích đúng ô và Writer xác nhận
không cần thêm bằng chứng.

## Artifact đã kiểm chứng

Verifier dùng **Qwen2.5-7B-Instruct**, revision
`a09a35458c702b33eeacc393d103063234e8bc28`, NF4/FP16, seed 42 và tối đa
512 token mỗi lượt sinh. Demo dùng dense retrieval, top-k ban đầu 5 và
checkpoint Private `research-rag-kaggle-v2.zip`.

| Artifact | SHA-256 |
| --- | --- |
| [Bản khóa verifier](../artifacts/factcheck-verdict-r8-v12-holdout/candidate-lock.json) | `9adedbb5eb5269a41afb4a0f3a66275e079f49a0772090138c20124858279edd` |
| [Bản khóa holdout](../artifacts/factcheck-verdict-r8-v12-holdout/holdout-lock.json) | `5e4b6b054cc2a559d15a49948f7823e16b2b514468f2157f7485fec57526a6f7` |
| Holdout ZIP `output-verdict-r8-v12-aacl2026-holdout30-v1-7b-20261114T063754Z-8f982a1c.zip` | `95279b8c4d4a8c91e0ed15fa5805ffce5c3c96c65e58692a289f0a52a944a493` |
| [Notebook Kaggle table-proof](../scripts/kaggle_r8_v12_e2e_real_pdf_table_proof.ipynb) | `487ee3dc20790dbe4abc6d09f6ef3da5e785e82cb77bca68301d6f009b3c8bfb` |
| Runtime nhúng trong notebook demo | `f22413f085e4cf4da0c93ba13fc544e8c65d3d4bbed1d1c6d1c13775eaaba43a` |
| Demo ZIP `r8-v12-e2e-real-pdf-table-proof-w3dquqnw.zip` | `d12dff01150ca1d83f9b5479a5fe75ffd186f0415d1bac03401bb14fd8b4ef8d` |

Notebook và ZIP demo khớp manifest, câu hỏi, bản khóa verifier, danh sách
hash checkpoint và hai PDF. Cả hai ZIP kết quả nằm trong thư mục Downloads.

## Chạy demo và mở kết quả ngoại tuyến

1. Import [notebook table-proof](../scripts/kaggle_r8_v12_e2e_real_pdf_table_proof.ipynb)
   vào Kaggle Private. Bật **T4 x2** và **Internet**. Gắn dataset Private chứa
   `research-rag-kaggle-v2.zip`.
2. Chạy **Cell 1–4** theo thứ tự. Cell 1 kiểm tra runtime và checkpoint.
   Cell 2 thiết lập môi trường. Cell 3 chạy ba câu. Cell 4 xuất ZIP
   `r8-v12-e2e-real-pdf-table-proof-*.zip` trong `/kaggle/working`.
3. Để trình bày từ kết quả đã chạy, giải nén ZIP đã chấm vào thư mục riêng
   và mở `review.json`. Tìm từng `id` bên dưới. Mở sẵn
   [KaggleDBQA, trang PDF 7](https://aclanthology.org/2021.acl-long.176.pdf#page=7)
   và [Performance-critical tokens, trang PDF 5](https://arxiv.org/pdf/2401.11323v4#page=5).
   Nếu trình đọc bỏ qua liên kết trang, nhập số trang trong thanh điều hướng PDF.

## Kịch bản bảo vệ 3–5 phút

| Thời gian | Mở và trình bày |
| --- | --- |
| 0:00–0:30 | Mở mục `cases` trong `review.json`. Giới thiệu luồng từ PDF và câu hỏi đến claim, Agent 4 và báo cáo có trích dẫn. |
| 0:30–2:00 | Mở `fires-exact-match`. Đọc `question`, rồi mở `report.sentences[0]` và `r8_reviews[0].label` có giá trị `support`. Từ `report.sentences[0].claim_ids` theo `claim:1` đến `citations[0]`. Chỉ vào **Bảng 4, trang 7**, hàng **(e) RAT-SQL**, cột **Fires**, nhóm **Without fine-tuning** và giá trị **17,33%**. Chỉ thêm ô **30,66%** trong nhóm **With fine-tuning** ở hàng **(a) RAT-SQL**. |
| 2:00–3:15 | Mở `missing-seeds`. Chỉ vào phần chú thích Bảng 4 cho biết có ba lượt chạy với seed khác nhau, rồi mở `report.limitations`. File `missing-seeds/trace.private.jsonl` có `factcheck_calls_used: 0` trong bản ghi `graph_result`. Báo cáo không đưa ra số seed. |
| 3:15–4:00 | Chốt **3/3 E2E sau sửa** và **24/30 holdout của R8 v12 gốc**. Nêu rõ thêm bước kiểm tra ô theo tọa độ trên hai PDF của demo và ngưỡng bàn giao được chốt sau holdout. |

**Ca dự phòng** `temp-sst2-accuracy`. Mở `report.sentences[0]` và
`citations[0]` để trình bày **82,6%**, **Bảng 2, trang PDF 5**, hàng
**Llama 2 7B / +TEMP**, cột **SST2**. Nguồn trích dẫn có ID
`pdf:f25125f6107e47cd:p4:table2:r0-3:c1`.

## Tạo lại notebook bàn giao

Sau khi chuẩn bị hai PDF theo manifest ở mục web local, chạy từ thư mục gốc
trên Windows. Lệnh này ghi lại notebook `table-proof` tại đường dẫn đã khóa.

```powershell
.\.venv\Scripts\python.exe .\scripts\build_kaggle_r8_v12_e2e_real_pdf.py --table-proof
```

Đối chiếu SHA-256 của notebook sinh ra với bảng artifact phía trên.

## Demo web local

Chạy trong PowerShell từ máy có repo và môi trường Python của dự án.

Với bản clone mới, tải hai PDF về đúng vị trí ghi trong manifest. Web
kiểm tra SHA-256 trước khi dùng chúng.

```powershell
$manifest = Get-Content -Raw .\artifacts\r8-v12-e2e-real-pdf\manifest.json | ConvertFrom-Json
foreach ($pdf in $manifest.pdfs.PSObject.Properties.Value) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $pdf.path) | Out-Null
    Invoke-WebRequest -Uri ($pdf.url -split '#')[0] -OutFile $pdf.path
    if ((Get-FileHash -LiteralPath $pdf.path -Algorithm SHA256).Hash -ne $pdf.sha256) {
        throw "PDF hash mismatch: $($pdf.path)"
    }
}
```


```powershell
Set-Location -LiteralPath 'C:\Users\dellcuatri142\Downloads\AI ENGINEER'
.\.venv\Scripts\python.exe .\web_demo\server.py 8080
```

Mở [http://127.0.0.1:8080](http://127.0.0.1:8080). Ô **Tài liệu PDF** nhận
một tệp PDF tối đa 25 MiB và 26 trang cho lượt chạy model. Nút **Xem trước
PDF đã chọn** mở tệp ngay trên máy. Khi bỏ trống ô này, web dùng hai PDF
đã kiểm tra hash ở trên. Trước khi chạy model, web dùng BM25 trên các trang
của thư viện PDF này để chọn tài liệu cho Reader. Demo PDF dùng chỉ mục
tạo từ chính tài liệu được đọc. Corpus chung ở `kb_indexing` phục vụ
đường truy xuất corpus của CLI.

Hai câu để trình bày, có sẵn trên giao diện:

- “Without fine-tuning, what exact-match accuracy did RAT-SQL achieve on the
  Fires database in Table 4?” Trace GPU ghi nhận cả năm agent. Mở
  `claim:1` và nhấn **Mở PDF tại trang nguồn** để kiểm tra trang 7.
- “What were the three exact random seed integers used for the KaggleDBQA
  RAT-SQL experimental runs summarized in Table 4?” Kết quả báo thiếu
  bằng chứng và ghi **0 lượt gọi Agent 4**.

**Chạy trên máy này** cần PyTorch thấy CUDA, GPU NVIDIA đủ bộ nhớ cho
pipeline NF4, các checkpoint Reader/Summarizer/Writer trong repo và các
model nền tương ứng trong bộ nhớ đệm. Thêm `--online-model-downloads` khi
chạy server nếu muốn cho phép tải model nền còn thiếu. Khi kiểm tra trên
máy này, PyTorch `2.6.0+cpu` trả `torch.cuda.is_available() == False`.

**Xem kết quả lưu sẵn** đọc từ ZIP GPU có SHA-256 trong hồ sơ này. Đặt ZIP
đúng tên trong thư mục Downloads hoặc truyền `--archive` cùng đường dẫn
ZIP. Giao diện hiện nhãn **Kết quả GPU lưu sẵn**. Trạng thái từng agent
dựa trên sự kiện của lượt chạy đã lưu. Nhãn **Sẵn sàng chạy demo** cũng
hiện khi máy có thể mở kết quả GPU lưu sẵn.

Phần web nằm trong `web_demo/server.py`, `index.html`, `app.js` và
`styles.css`. Đã chạy 13 kiểm thử CPU, gồm kiểm tra chọn và gửi PDF, luồng gọi
CLI với worker mô phỏng, ràng buộc trích dẫn và kiểm chứng ô bảng bằng
pipeline. Đã kiểm tra trên Chrome với ZIP GPU lưu sẵn. Ca Fires hiển thị
sự kiện của cả năm agent và mở đúng PDF trang 7. Ca thiếu seed không sinh
câu trả lời và hiện 0 lượt gọi Agent 4. Có thể chạy lại kiểm thử CPU bằng
lệnh sau.

```powershell
.\.venv\Scripts\python.exe -m pytest research_rag/tests/test_web_demo.py research_rag/tests/test_r8_pdf_cell_context.py -q
```
