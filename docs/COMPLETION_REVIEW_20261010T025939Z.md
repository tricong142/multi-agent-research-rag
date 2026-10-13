# Đối chiếu lượt Kaggle 20261010T025939Z

## 1. Kết luận

**Chưa nghiệm thu toàn bộ bước 1/2.** Các cell đã thực thi, nhưng hai diagnostic
trả exit code 1: confidence explanation và Reader PDF thật. Đây là kết quả
đánh giá thất bại được lưu đúng, không phải thiếu thao tác chạy cell.

Giữ `repair` làm cấu hình phục vụ. Không promote `explanation_repair` hoặc
`label_confidence_repair`, không hạ threshold, không sửa tiêu chí sau kết quả.
Lượt này chưa chạy đủ graph/controller và tám ca E2E.

| Hạng mục | Kết quả trong ZIP | Quyết định |
|---|---|---|
| Cài đặt, pip check, preflight | Exit 0; 130 contract tests đạt | Đủ để chạy các diagnostic thành phần đã thực hiện |
| Confidence: 47 ca thông thường/profile | Cả hai profile 0 runtime failure; candidate đạt 9 gate cũ | Giữ bằng chứng sửa contract/retry; chưa chứng minh ý nghĩa confidence |
| Confidence: 24 ca nhãn có kiểm soát/profile | Candidate tin 10/12 nhãn sai; một runtime failure | Candidate trượt gate mới, chưa promote |
| Reader trang từng lỗi | 1/1 span, 2 API attempts thành công | Automated gate đạt |
| Reader smoke | 9/9 spans, 3 PDF, có retry 503 thành công | Automated gate đạt |
| Reader PDF thật | Dừng ở page_no=3 vì 429 ba lần | Chưa đạt, chưa đánh giá đủ PDF |
| Human review | 71 explanation rows còn pending; Reader pending | Chưa có người ký xác nhận |

## 2. Tính toàn vẹn và môi trường

- ZIP `C:/Users/dellcuatri142/Downloads/rag-validation-20261010T025939Z.zip`:
  **142.555 bytes**, SHA256
  `f145b591d9db195cb96d1d910cbcf794e33ed19de5df11a63d7b8e9802fef202`.
- 64 file gồm manifest; **63/63 file đúng size/hash**, không có file ngoài
  manifest. Kiểm CRC ZIP đạt. Không phát hiện các mẫu credential đã kiểm tra;
  đây không phải chứng nhận rằng mọi dạng secret đều được loại trừ.
- **42/42 runtime patch khớp code hiện tại**; đã trích xuất nguyên bytes vào
  `research-runs/kaggle-20261010T025939Z/`, không thực thi code trong ZIP.
- Tiêu chí v2, source/input hashes và prompt được đối chiếu với repo. Không
  thay dữ liệu hoặc scoring để đạt gate.
- Đã tính lại đúng toàn bộ metric/gate confidence từ 142 predictions, đối
  chiếu 312 calls, 71 review rows và tái tính cả ba API summary Reader từ
  attempt logs. Các con số tái tính khớp JSON gốc; giới hạn về Reader text
  được trình bày ở mục 4.
- Log Kaggle: **130 tests đạt trong 3.095 giây**. Bảy test notebook chỉ chạy
  local nên khác tổng 137 đã báo trước đây. Preflight ghi hai Tesla T4;
  Fact-checker dùng Torch 2.10.0+cu128, checkpoint merged local.
- `preflight` exit 0 không có nghĩa mọi base weight đã sẵn sàng cho E2E:
  cache được kiểm tra của Summarizer/Writer/BGE báo chưa đủ. Notebook autonomy
  có tùy chọn online model downloads; cần xác nhận tải/nạp đúng model ở lần
  E2E sau. Diagnostic hiện tại chỉ cần Fact-checker merged và Reader.

Bằng chứng định lượng được lưu trong
[completion-audit-20261010T025939Z.json](completion-audit-20261010T025939Z.json).

## 3. Confidence: kết quả và nguyên nhân cần xử lý

Có đủ **142 predictions** và **312 backend calls thực**. Mỗi profile đánh giá
47 ca thông thường, rồi 24 nhãn có kiểm soát. Nhãn ở 24 ca được cấp sẵn để
thử ConfidenceEstimator; không phải prediction do model Judge tạo ra.

| Chỉ số | `repair` | `explanation_repair` |
|---|---:|---:|
| Runtime failure trên 47 ca thông thường | 0 | 0 |
| Invalid confidence attempts trên 47 ca | 7 | 0 |
| Dev30 accuracy | 18/30 = 60% | 18/30 = 60% |
| Dev30 macro-F1 | 0.593371 | 0.593371 |
| Support đúng được nhận trên 47 ca | 14 | 14 |
| False support được nhận trên 47 ca | 0 | 0 |
| Nhãn đúng được tin trong controlled set | 4/12 | 11/12 |
| Nhãn sai vẫn được tin trong controlled set | 2/12 | **10/12** |
| Runtime failure trên controlled set | 0/24 | **1/24** |
| Backend calls toàn bộ 71 prediction | 175 | 137 |

Controlled gate yêu cầu 12/12 nhãn đúng được tin, 0/12 nhãn sai được tin và
0 runtime failure. Cả baseline và candidate không đạt thử thách này; candidate
tăng mức tin nhãn đúng nhưng cũng tăng mức tin nhãn sai. Không thể dùng số
calls ít hơn hoặc qua 9 gate cũ để kết luận candidate tốt hơn.

Ví dụ cụ thể từ `explanation-review.jsonl`:

- `contract:negation:label_wrong`: claim nói nghiên cứu dùng nhãn con người;
  context nói không dùng, toàn bộ nhãn tự động. Nhãn đề xuất cố ý là `support`,
  candidate vẫn cho **1.0** và chỉ trích câu phủ định.
- `contract:partial_accuracy:label_wrong`: context chỉ cho biết giảm bộ nhớ,
  không có accuracy 94%; nhãn support vẫn nhận **0.98**.
- `contract:partial_accuracy:label_correct`: nhãn `not_enough_info` đúng nhưng
  score **0.0**, explanation nói chung chung về annotation, không nêu accuracy
  còn thiếu.
- `contract:wrong_units` thông thường đã trích đúng “12 hours, not 12 seconds”.
  Tuy nhiên `contract:wrong_units:label_wrong` lỗi cả ba lần: model trả cấu trúc
  bắt đầu bằng `[` thay vì JSON object, gây `ModelOutputError`. Validator giữ
  `confidence_score=null`, không tự nhận score từ text lỗi.

### Điều đã chứng minh và giả thuyết

Đã chứng minh: model confidence chưa đánh giá đúng **tính đúng của nhãn đề
xuất**, và không ổn định về schema ở ca phản ví dụ. Một số câu giải thích có
trích nguồn nhưng không giải thích vì sao nhãn đề xuất sai.

Code hiện tại dùng cùng checkpoint fine-tuned cho Judge và ConfidenceEstimator.
`train_factchecker_qlora.py:build_training_messages` chỉ tạo target
`fact_check_label` + `reasoning`, không có target confidence. Trong
`generate_training_data.py`, reasoning được tạo bằng mẫu “The annotated
evidence states ...” hoặc “no annotated evidence ...”; các mẫu này còn xuất
hiện trong output mới dù prompt yêu cầu khác.

**Giả thuyết cần kiểm chứng:** checkpoint học mẫu Judge/annotation và không
tổng quát tốt sang nhiệm vụ đánh giá một nhãn có thể sai. Sự trùng mẫu là
bằng chứng liên quan, chưa chứng minh quan hệ nhân quả. Chưa có thí nghiệm so
base instruct với checkpoint fine-tuned để kết luận do fine-tuning.

### Việc sửa tiếp theo cho confidence

1. Giữ nguyên baseline và lưu các ca trên làm regression development; không
   biến chúng thành tập test độc lập sau khi đã dùng để sửa.
2. Trước khi đổi serving hoặc train lại, chạy diagnostic nhỏ so backend
   confidence hiện tại với base instruct tương ứng, giữ cùng claim/context,
   nhãn đề xuất, tiêu chí và giới hạn. Đây là thí nghiệm xác định nguyên nhân,
   chưa phải khuyến nghị thay model đã được kiểm chứng.
3. Nhiệm vụ verifier cần kiểm độc lập bằng chứng cho/đối lập/thiếu của claim
   rồi đánh giá nhãn đề xuất. Schema/evidence checks cần chặn giải thích không
   có căn cứ. Không tự chuyển mọi support thành score 1, NEI thành score 0,
   hoặc sửa JSON lỗi để chấp nhận một quyết định chưa được kiểm chứng.
4. Nếu cần dữ liệu huấn luyện verifier, phải có nhãn đúng/sai và giải thích
   được rà soát, tách theo claim/paper. Không tự bịa target xác suất confidence;
   calibration phải dùng dữ liệu phù hợp và độc lập với chọn prompt/ngưỡng.
5. Chạy lại diagnostic sau thay đổi. Chỉ khi automated gates đạt mới làm
   review nghiệm thu đầy đủ và quyết định promotion riêng. 71 dòng hiện tại
   có thể dùng phân tích lỗi; không điền pass để đóng bước 1.

## 4. Reader: 503 đã hồi phục, PDF thật bị chặn bởi 429

Ba Reader stage có tổng **18 transport attempts**:
11 thành công, 4 trả HTTP 503, 3 trả HTTP 429. Cả bốn 503 đều thành công ở
attempt thứ hai. Khoảng cách giữa các retry được ghi nhận xấp xỉ 61 giây,
không có call quá 3 attempts. Đây là bằng chứng model/API thật cho cơ chế
phục hồi 503 trong lượt này; không có nghĩa dịch vụ không bao giờ trả 503 nữa.

PDF thật `qasper_2021.pdf`:

| Trang theo chỉ số code | Số trang khi đọc PDF | Kết quả |
|---|---:|---|
| 0 | 1 | Thành công, layoutlmv3, 135 blocks |
| 1 | 2 | Thành công, alt_segmentation, 12 blocks |
| 2 | 3 | Critique gặp 503 rồi hồi phục; 15 blocks |
| 3 | 4 | Router gặp 503 rồi hồi phục; critique trả 429 ở cả 3 attempts, dừng |
| 4–11 | 5–12 | Chưa được xử lý trong lượt này |

`ReaderBatchError` làm scorer không nhận một PDF hoàn chỉnh, vì vậy báo
`evaluated_pdf_count=0`, `overall_exact_span_rate=0`. **Không được diễn giải
đây là OCR sai 100%**: ba trang trước đó đã thành công, nhưng toàn PDF chưa đủ
điều kiện chấm và chưa trả về chunks cho scorer. Stage dừng do API failure,
không phải vượt timeout 5.400 giây; thời gian stage khoảng 9 phút 12 giây.

Nguyên nhân trực tiếp đã rõ: 429 tại critique trang thứ 4, hết 3 attempts.
Nguyên nhân quota cụ thể chưa rõ: log có HTTP status nhưng không có quota
metric/reason chi tiết; `retry_after_ms=0` không chứng minh quota đã phục hồi.

### Việc bạn cần làm với tài khoản Gemini

1. Vào mục rate limits/usage trong Google AI Studio của **project đang cấp
   key cho notebook**, kiểm đúng model `gemini-3.6-flash`.
2. Ghi lại giới hạn, mức dùng, loại giới hạn đã chạm và thời điểm có thể chạy
   lại. Khi chia sẻ ảnh, che key và thông tin tài khoản không cần thiết.
3. Kiểm các notebook/process khác đang dùng cùng project. Các giới hạn có
   thể tính theo requests/phút, input tokens/phút và requests/ngày, áp dụng
   ở project; thay key cùng project không tạo quota mới. Xem
   [tài liệu rate limits chính thức](https://ai.google.dev/gemini-api/docs/rate-limits).
4. Xử lý theo giới hạn thực tế: giảm tải/đợi cửa sổ giới hạn hồi phục, hoặc
   quyết định quota/billing nếu bạn muốn. Không có dữ liệu để khuyên mua gói
   nào hoặc tăng số lần retry ở đây. Retry có giới hạn là hành vi cần giữ;
   [Google cũng hướng dẫn backoff và giới hạn retries](https://ai.google.dev/gemini-api/docs/troubleshooting).

### Bổ sung code trước lượt Reader tiếp theo

- Ghi có chọn lọc error reason/quota detail/retry delay nếu API cung cấp,
  loại bỏ key, headers và dữ liệu nhạy cảm. Hiện chỉ biết 429 nên chưa thể
  phân loại nguyên nhân chính xác hơn.
- Xuất text/blocks hoặc chunks đã trích xuất kèm trang, tool và nguồn để
  người đọc so PDF và chấm lại offline. ZIP hiện chỉ giữ số blocks, tool,
  critique và metric; **không chứa nội dung text đầy đủ để audit lại các
  phrase matches**. Vì vậy đối chiếu hiện tại tái tính API counters và gate
  từ summary, chưa thể tái tính metric phrase trực tiếp từ text.
- Sau khi quota phù hợp, ưu tiên diagnostic Reader riêng với cùng PDF/hash/
  criteria/model. Chưa cần chạy lại confidence và toàn bộ 6 cell chỉ để thử
  API. Nếu đổi model, ghi thành cấu hình khác để so sánh rõ ràng.
- Điều kiện đạt: đọc đủ PDF, đủ 9 expected spans theo scorer, không terminal
  API failure, attempts/budget đúng; tiếp theo review text và thứ tự đọc/bảng.
  Không bỏ trang lỗi hoặc lấy một phần kết quả để tuyên bố toàn PDF đạt.

## 5. Thứ tự để hoàn thành dự án

1. **Ngay bây giờ:** giữ ZIP và baseline `repair`; kiểm quota Gemini. Chưa
   chạy lại nguyên notebook với cấu hình cũ khi chưa xử lý hai nguyên nhân.
2. **Lượt sửa tiếp:** bổ sung Reader quota diagnostics + text export, đồng thời
   thiết kế thí nghiệm confidence có nhãn sai. Hai việc có thể triển khai độc lập.
3. **Chạy lại đúng thành phần đã sửa**, đối chiếu tiêu chí trước inference;
   không coi việc cell chạy hết hoặc exit 0 của setup là nghiệm thu chất lượng.
4. **Sửa Summarizer `heldout_3`**, phân biệt baseline và phương pháp được hỏi;
   giữ kiểm evidence span khớp nguồn. Lượt ZIP này không chạy Summarizer nên
   chưa có bằng chứng mới về lỗi đó.
5. **Chạy đủ 8 ca E2E** với runtime cuối, ghi controller decisions, agent/tool
   calls, evidence, stop reason, latency và chi phí nếu đo được. Xác nhận
   model weights đã tải/nạp trước khi suy ra thiếu năng lực từ lỗi môi trường.
6. **Nghiệm thu cuối:** human review thực sự, dữ liệu đánh giá độc lập, báo cáo
   thất bại/giới hạn và demo tái lập. Không gọi bộ regression đã xem là test
   chưa từng dùng, hoặc dùng confidence hiện tại như xác suất đúng đã calibration.

Lượt rà soát này chỉ kiểm dữ liệu đã lưu và cập nhật báo cáo; không chạy API,
không inference model mới, không đổi runtime/threshold/prompt hoặc quota.
