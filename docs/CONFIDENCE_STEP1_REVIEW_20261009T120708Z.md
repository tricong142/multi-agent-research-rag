# Đối chiếu bước 1 — lượt Kaggle 20261009T120708Z

## 1. Kết luận

**Phần sửa contract/retry và kiểm chứng model thật đã đạt các gate tự động đã
chốt. Chưa đóng nghiệm thu đầy đủ bước 1:** human review chưa có xác nhận, và
rà nội dung cho thấy phần giải thích/ý nghĩa confidence còn vấn đề.

Giữ `repair` làm cấu hình hiện tại. Chưa có cơ sở đưa
`label_confidence_repair` thành mặc định: nó cho score 1.0 trên cả 47 dòng,
bao gồm 12 nhãn sai theo gold của dev30. Không đổi tiêu chí sau khi thấy kết quả;
cả hai profile vẫn được ghi nhận đúng là đã qua automated gate.

Lượt này là diagnostic riêng của Fact-Checker, chưa phải E2E toàn hệ thống.
Calibration độc lập vẫn là công việc riêng; không dùng việc chưa calibration
để phủ nhận kết quả sửa contract đã đạt.

## 2. Artifact và tính toàn vẹn

- ZIP: `C:/Users/dellcuatri142/Downloads/rag-validation-20261009T120708Z.zip`.
- Dung lượng: 125.848 bytes.
- SHA256: `99139b8e0492a344240103d8bb76f8626271e23a441438e79b6872cfc8d8bb34`.
- 45 file trong ZIP, gồm manifest; **44/44 file dữ liệu đúng size/hash**.
- **36/36 file runtime patch khớp repo**. Hash input, tiêu chí, source và các
  profile khớp bản đã chuẩn bị. Không đổi threshold 0.7 hoặc ngân sách 3 attempts.
- Đã tính lại metric từ 141 predictions, đối chiếu 372 backend calls và tái tạo
  đúng `gate-results.json`. Không chạy code trong ZIP hoặc inference model mới.
- Bản trích xuất giữ nguyên bytes tại `research-runs/kaggle-20261009T120708Z/`.

Kaggle ghi Tesla T4, FP16/NF4, Torch 2.10.0+cu128. Stage confidence exit 0,
thời gian 1.103.819,89 ms, khoảng 18 phút 24 giây gồm load model và diagnostic.
112 contract tests đạt trong 7,274 giây; khác 118 test local vì 6 test đóng gói
notebook không được chuyển lên workspace runtime. `cost_usd=null`: chưa đo USD.

## 3. So sánh cùng dữ liệu

Mỗi profile có 47 predictions = 30 dev + 12 contracts + 5 review lỗi trước đó.
Năm review lỗi chứa bốn cặp claim/context phân biệt, không phải năm mẫu độc lập.

| Chỉ số | `legacy_retry` | `repair` hiện tại | `label_confidence_repair` thử nghiệm |
|---|---:|---:|---:|
| Runtime failure cuối cùng | 7/47 | **0/47** | 0/47 |
| Confidence attempts không hợp lệ | 21 | 7 | 0 |
| Backend calls | 146 | 132 | 94 |
| Attempts tối đa/stage đã quan sát | 3 | 2 | 1 |
| Support được chấp nhận tại 0.7 | 7 | 14 | 14 |
| False support được chấp nhận | 0 | 0 | 0 |
| Tổng latency các prediction | 399,37 s | 367,72 s | 301,87 s |
| Dev30 label accuracy | 18/30 = 60% | 18/30 = 60% | 18/30 = 60% |
| Dev30 macro-F1 | 0,5934 | 0,5934 | 0,5934 |

Label metrics không bị suy giảm; Judge predictions giữ nguyên. Contracts đúng
12/12 nhãn, observed_failures đúng 5/5 nhãn. Cả hai candidate đạt 9/9 checks.
Số 0 false support chỉ mô tả tập nhỏ đã chạy, không chứng minh sai số bằng 0
trên dữ liệu mới. Thời gian trên là một lượt đo, không phải SLA hoặc benchmark
latency đủ để tổng quát hóa.

`legacy_retry` ở đây dùng strict validator mới nhưng tắt feedback. Nó cô lập tác
động retry, không phải chạy lại nguyên byte toàn bộ runtime lịch sử. Điều này
đặc biệt liên quan hai output reasoning=null mà validator cũ từng có thể ép
thành chuỗi `"None"`.

## 4. Bằng chứng retry hoạt động

Đã kiểm từng trace của **7 trường hợp** trong `repair`:

- Lần đầu: 5 output có reasoning rỗng, 2 output có reasoning=null.
- Lần hai: có đúng output trước và lỗi validation trong prompt; cả 7 thành
  công với reasoning không rỗng. Không có trường hợp cần attempt thứ ba.
- Input Judge và input confidence lần đầu khớp baseline trên cả 47 dòng.
- Baseline lặp prompt y hệt khi retry; bản repair thêm feedback có giới hạn.
- Chạy validator local trên output cuối của 47 dòng đều hợp lệ; đây là replay
  validation, không phải model inference mới.

| Example ID | File trace trong `confidence-step1/` | Dòng confidence trước → sau |
|---|---|---|
| `contract:both_supported` | `repair-contracts-calls.jsonl` | 8 → 9 |
| `contract:atomic_support` | `repair-contracts-calls.jsonl` | 30 → 31 |
| `contract:bounded_scope` | `repair-contracts-calls.jsonl` | 33 → 34 |
| `regression:sufficient:0` | `repair-observed_failures-calls.jsonl` | 2 → 3 |
| `regression:conflict:0` | `repair-observed_failures-calls.jsonl` | 5 → 6 |
| `regression:heldout_2:1` | `repair-observed_failures-calls.jsonl` | 10 → 11 |
| `regression:heldout_2:4` | `repair-observed_failures-calls.jsonl` | 13 → 14 |

Bảy explanation sau repair dẫn câu nguồn phù hợp với claim tương ứng trong
phạm vi assistant đã rà; không chỉ điền placeholder để qua schema. Cụm
“annotated evidence” là cách model diễn đạt, không chứng minh có annotation
mới do con người cung cấp trong runtime.

Ca heldout_1 từng lỗi trong E2E trước nay hợp lệ ngay attempt đầu ở cả baseline
và repair. Vì vậy nhóm observed_failures của lượt này là **4/5 → 0/5** lỗi,
không phải 5/5 → 0/5. Ca conflict ở đây chỉ là một review nguồn support; không
chứng minh xử lý mâu thuẫn đa nguồn của graph đã qua E2E mới.

## 5. Phần còn thiếu để chốt nghiệm thu

### A. Explanation của cấu hình hiện tại vẫn có lỗi ngữ nghĩa

Ví dụ `contract:wrong_units`, dòng 10 của `repair-contracts.jsonl`:

- Claim: training mất **12 giây**.
- Context: training mất **12 giờ, không phải 12 giây**.
- Judge: `contradict`, đúng theo nhãn synthetic đã chốt.
- Confidence: **0.0**.
- Reasoning: `The cited context has a supporting annotation.`

Câu này không giải thích vì sao không chắc nhãn contradict và không chỉ ra
xung đột đơn vị. Nó không thỏa mục tiêu explanation có căn cứ/ý nghĩa confidence
của nhãn, dù schema hợp lệ. Ngoài ra, repair có 7/12 contracts được phân loại
đúng nhưng confidence=0; dev30 có 24 dòng score=0, trong đó 12 nhãn đúng.
Đây là bằng chứng không nên diễn giải score như xác suất nhãn đúng đã hiệu chuẩn.

### B. Candidate mới qua gate nhưng quá tự tin

`label_confidence_repair` cho **1.0 ở cả 47/47 dòng**. Trên dev30, 12/30
nhãn sai theo gold vẫn nhận 1.0. ECE dev30=0.4, Brier=0.4; prompt mới chưa
chứng minh đánh giá uncertainty đáng tin cậy. Số calls giảm có phần do score
luôn cao nên không gọi ActionRecommender; không coi đây là cải thiện chất lượng.

Gate hiện tại chủ yếu kiểm contract, không suy giảm nhãn và an toàn support.
Nó không đặt ngưỡng calibration trước inference, nên không đổi kết quả automated
gate thành fail sau khi nhìn thấy ECE. Những vấn đề trên thuộc rà chất lượng.

### C. Human review chưa có xác nhận

`gate-results.json` giữ `human_review=pending`, `overall_pass=false`,
`promoted_to_serving=false` theo thiết kế. Đây không phải lỗi chạy notebook.
Lượt rà soát này do assistant thực hiện; không tự đổi thành xác nhận của người
review hoặc chỉnh kết quả gốc trong ZIP.

## 6. Bước tiếp theo

1. **Giữ bản repair đã kiểm chứng** và ghi nhận hạng mục sửa lỗi schema/retry đã đạt.
2. Giữ prompt candidate ở chế độ thử nghiệm; không promote chỉ vì ít calls hơn.
3. Trước khi đóng nghiệm thu chất lượng bước 1, sửa/đánh giá explanation cho các
   ca thiếu dữ liệu và phản bác, bắt đầu từ `wrong_units`, rồi đo lại đúng bộ
   diagnostic với tiêu chí có phiên bản rõ ràng. Không gán score mặc định hoặc
   sao chép Judge reasoning trong code để giả lập confidence thành công.
4. Người review kiểm explanation theo claim/context và xác nhận phạm vi được
   chấp nhận. Nếu chỉ nghiệm thu contract/retry, ghi rõ phạm vi đó; không ghi
   “confidence đã đáng tin cậy/hiệu chuẩn”.
5. Có thể xử lý **bước 2 Reader/HTTP 503** song song; sau các sửa cần chạy lại
   E2E tám ca. ZIP này không chứa kết quả Reader/Summarizer/Writer mới.

Chi tiết máy đọc: `confidence-step1-audit-20261009T120708Z.json`.
Lượt này chỉ lưu audit và cập nhật tài liệu trạng thái; không sửa runtime,
notebook, threshold hoặc tiêu chí đã chốt.
