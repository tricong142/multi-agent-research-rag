# Đối chiếu confidence trên Kaggle — 20261010T101538Z

## 1. Kết luận và quyết định

**Thí nghiệm hoàn thành; cả bốn cấu hình chưa đạt yêu cầu chất lượng confidence.**
Đây là kết quả của riêng thành phần confidence, chưa phải E2E toàn bộ hệ thống.

- Giữ `repair` làm baseline hiện hành để so sánh; điều này không có nghĩa
  baseline đã đủ tin cậy để phát hành. Không promote backend/prompt mới.
- Không chạy lại cùng notebook/cấu hình chỉ để tìm một lượt đạt. Lượt này đã
  cung cấp đủ ma trận 96 predictions và 99 calls.
- Không sửa threshold hoặc nới tiêu chí theo kết quả vừa xem. Score đúng và
  sai có nhiều giá trị trùng nhau; đổi ngưỡng không giải quyết được yêu cầu hiện tại.
- Bước code tiếp theo nên là một **ứng viên kiểm chứng nhãn độc lập với nhãn
  Judge đầu vào**, thử riêng trước khi thay contract phục vụ. Phần 6 mô tả đề xuất.
- Reader diagnostic bốn cell có thể chạy độc lập ngay sau khi kiểm quota.

## 2. Những gì đã kiểm chứng

ZIP nguồn: `rag-validation-20261010T101538Z.zip`, 52.084 bytes; SHA256:
`7cb9d5d0045962b628efde2a5f1d1a3b9d11cc58c7d9e87892eb6cc58923519d`.

| Kiểm tra | Kết quả |
|---|---|
| Toàn vẹn ZIP | CRC đạt; 36 file gồm manifest; 35/35 file đúng size/hash, không trùng hoặc thừa entry |
| Runtime | 45/45 file trong runtime manifest khớp repo; năm source hash trong provenance khớp |
| Dữ liệu/tiêu chí/prompt | Tiêu chí đúng nguyên bản; 24 cases tái tạo đúng từ 12 contracts; prompt khớp repo |
| So backend | First-attempt messages giống nhau cho cùng case/prompt; tokenizer/config sinh/NF4/FP16/seed/token budget được giữ giống nhau |
| Model | Provenance ghi T4, Torch 2.10.0+cu128; base pin `aa8e72537993ba99e69dfaafa59ed015b17504d1`; hai backend có hash weights khác nhau |
| Môi trường Kaggle | `pip check` đạt; **139 tests đạt trong 3,174 giây** |
| Replay offline | 96/96 predictions được tái hiện từ 99 response đã lưu qua validator/repair code hiện tại; messages và attempts đều khớp |
| Chấm lại | Toàn bộ metrics và summary tái tính khớp; 96 dòng explanation review đúng input/output tương ứng, vẫn pending |

Replay dùng response đã lưu, không chạy model hoặc API mới. Hash chứng minh
tính nhất quán với manifest được nhận, không phải chữ ký độc lập của nhà cung
cấp. Audit không tải lại weights để xác thực nội dung model từ xa.

Provenance có `shared_generation_config.do_sample=true` trong config gốc,
nhưng lời gọi `TransformersJSONBackend.generate_json` truyền rõ `do_sample=False`.
Hai backend dùng cùng cơ chế override này; không suy ra lượt chạy đã sampling
chỉ từ config gốc.

## 3. Kết quả ma trận

Mỗi hàng có 24 lượt: 12 nhãn đề xuất đúng và 12 nhãn đề xuất sai. “Được nhận”
nghĩa là output hợp lệ và score **>= 0.7**. Điều kiện gốc: nhận đủ 12 nhãn đúng,
không nhận nhãn sai nào, không runtime failure.

| Backend + prompt | Nhãn đúng được nhận /12 | Nhãn sai bị nhận /12 | Runtime failure /24 | Calls | Tổng thời gian assess |
|---|---:|---:|---:|---:|---:|
| Fine-tuned + `repair` | 4 | 2 | 0 | 25 | 53,41 s |
| Fine-tuned + `explanation_repair` | 11 | 10 | 1 | 26 | 76,07 s |
| Base instruct + `repair` | 2 | 1 | 0 | 24 | 77,32 s |
| Base instruct + `explanation_repair` | 12 | 9 | 0 | 24 | 125,55 s |

**0/4 cấu hình đạt.** Cấu hình bắt buộc `base_instruct__explanation_repair`
trượt nên stage exit 1. `experiment_completed=true` và `automated_gate_pass=false`
cùng đúng: chương trình hoàn thành đánh giá và ghi nhận chất lượng không đạt.

Tổng 99 calls thay vì 96:

- Fine-tuned `repair`, `cross_sentence:label_correct`: reasoning rỗng ở lần đầu,
  repair thành công ở lần thứ hai, thêm một call.
- Fine-tuned `explanation_repair`, `wrong_units:label_wrong`: ba lần trả text
  dạng `JSON object: [ "confidence_score": ... ]` không phải JSON object hợp lệ;
  dừng đúng giới hạn, thêm hai calls. Score 0.99 trong raw text bị từ chối,
  không được tính là output hợp lệ hoặc confidence dùng được.

Stage mất **434,09 giây (~7 phút 14 giây)** gồm nạp/tải model và inference.
Tổng thời gian `assess` là 332,34 giây. Không có số liệu tiền thực tế;
`cost_usd=null`. Warning Hugging Face chưa đăng nhập không làm thí nghiệm dừng:
cả hai backend và bốn profile đã chạy đủ.

24 nhãn/score/status của từng profile fine-tuned khớp lượt
`20261010T025939Z`. So sánh này chỉ áp dụng cho phần controlled labels, không
đồng nhất số calls của thử nghiệm trước có thêm Judge/Action với lượt hiện tại.

## 4. Phân tích lỗi có bằng chứng

### 4.1 Score cao mâu thuẫn với chính phần giải thích

Trong base + `explanation_repair`:

- `both_supported:label_wrong`: context hỗ trợ toàn claim, nhãn đưa vào là
  `contradict`. Model giải thích nhãn đó sai nhưng vẫn trả **0.95**.
- `wrong_units:label_wrong`: claim nói 12 giây, context nói 12 giờ; nhãn đưa
  vào là `support`. Model nói confidence của nhãn phải thấp nhưng score **0.95**.
  Giải thích còn giả định có thể có thông tin khác chưa cung cấp để bênh nhãn Judge.
- `negation:label_wrong`: context nói không dùng nhãn do người tạo, model nhận
  ra bằng chứng phản bác claim nhưng vẫn trả **0.95** cho nhãn `support`.

Nguồn: [predictions base explanation](../research-runs/kaggle-20261010T101538Z/confidence-backends/base_instruct__explanation_repair.jsonl).

Đây là vi phạm ý nghĩa đầu ra, dù JSON hợp lệ. Validator hiện kiểm kiểu dữ liệu,
khoảng [0,1] và reasoning không rỗng; chưa kiểm được logic giữa label, score và
evidence. Không thể kết luận model đúng chỉ từ `status=ok`.

### 4.2 Có cả lỗi suy luận, không chỉ lỗi score

- `atomic_support:label_wrong`: claim “240 documents”, nguồn “exactly 240
  documents”; model lại gọi hai câu là mâu thuẫn và cho **0.95**.
- `cross_sentence:label_wrong`: nguồn nêu bốn models và hai datasets; model
  giải thích sai rằng claim tương ứng bị phản bác, score **0.95**.
- `partial_accuracy:label_wrong` và `accuracy_conflict:label_wrong` cùng có
  score **0.7** nên được nhận. Model coi hỗ trợ một phần là lý do giữ `support`,
  dù một phần claim còn thiếu hoặc bị phản bác.
- Ngay cả `causality_missing:label_correct` có score 0.95, reasoning vẫn dùng
  từ “contradicts” cho việc chưa xác lập quan hệ nhân quả. Score/label đúng
  không tự động làm explanation đạt chất lượng.

### 4.3 Vì sao chưa nên chỉ đổi backend hoặc threshold?

Prompt cũ trên base chỉ nhận 2/12 nhãn đúng. Prompt mới trên base nhận đủ nhãn
đúng nhưng cũng nhận 75% số nhãn sai trong bộ kiểm tra cân bằng này. Đây không
phải 75% lỗi dự đoán trên production, và cũng không phải accuracy của model Judge:
nhãn đề xuất là đầu vào do diagnostic chủ động cung cấp.

Trong base + prompt mới, bốn cặp có score nhãn đúng bằng score nhãn sai.
Phân tích sau chạy dưới đây chỉ giải thích giới hạn, **không chọn threshold mới**:

| Threshold | Nhãn đúng được nhận /12 | Nhãn sai bị nhận /12 |
|---|---:|---:|
| 0.7 — ngưỡng đã đóng băng | 12 | 9 |
| 0.85 | 12 | 6 |
| 0.95 | 10 | 6 |
| 1.0 | 2 | 0 |

Không có threshold chung nào trên score đã quan sát vừa nhận đủ 12 nhãn đúng
vừa loại toàn bộ nhãn sai. Hiện tượng này tồn tại ở cả bốn profile.

### 4.4 Điều đã biết và điều chưa kết luận được

**Đã chứng minh:** output chưa phân biệt ổn định độ đúng của nhãn đề xuất;
score có thể trái reasoning; có reasoning sai evidence; thay sang base chưa
giải quyết được. `build_training_messages` trong repo tạo target
`fact_check_label`/`reasoning`, chưa có target confidence đúng/sai được hiệu chỉnh.

**Suy luận cần kiểm chứng:** nhãn Judge đưa vào có thể khiến model bám theo
nhãn đó; việc buộc sinh score liên tục trước explanation có thể không phù hợp
với năng lực/tác vụ đã huấn luyện. Đây là giả thuyết để thiết kế thử nghiệm tiếp,
chưa phải nguyên nhân duy nhất đã được xác nhận.

Chưa thể kết luận fine-tuning đã làm model kém đi trên mọi tác vụ, model lớn
hơn chắc chắn giải quyết được, hoặc confidence 0.95 tương ứng xác suất đúng 95%.
Các mẫu đã được xem là development/regression; chưa có calibration độc lập.

## 5. Ảnh hưởng đến runtime hiện tại

`research_rag/graph.py` chỉ tạo candidate từ `label=support`, `status=ok` và
score đạt threshold; đồng thời có chặn conflict, failed review và summary chưa
đạt. Đây là các điều kiện có thật trong code, cần giữ khi sửa.

Tuy nhiên, score cao hiện chưa đủ chứng minh nhãn `support` đúng. Lượt này
kiểm khả năng của confidence khi nhãn đưa vào sai; không chứng minh rằng chính
các claim lỗi đó đã được Writer xuất ra trong một lượt E2E.

Giữ baseline phục vụ cho phát triển/regression; chưa dùng nó làm bằng chứng
toàn dự án đã nghiệm thu. 96 dòng human review vẫn pending; báo cáo này là
phân tích của trợ lý, không thay chữ ký người đánh giá.

## 6. Kế hoạch tiếp theo theo thứ tự

### A. Làm ngay: Reader diagnostic riêng

Chạy [kaggle_reader_diagnostics.ipynb](../scripts/kaggle_reader_diagnostics.ipynb)
theo [hướng dẫn bước 3](COMPONENT_DIAGNOSTICS_20261010.md):

1. Giữ ZIP confidence hiện tại; không cần chạy lại.
2. Kiểm quota và cho notebook truy cập Secret `GEMINI_API_KEY` hiện có.
3. Chạy cell 1–2 để setup; cell 3 thử đúng trang thứ 4 từng lỗi.
4. Nếu probe đạt, chạy cell 4 đọc toàn PDF. Nếu vẫn 429, giữ ZIP log mới và
   xác định quota cụ thể trước lượt tiếp theo.
5. Gửi ZIP Reader; kiểm text/blocks, replay và review nội dung. Replay đúng
   chỉ xác nhận tái tạo được metric đã ghi, không tự làm Reader đạt chất lượng.

### B. Bước code ưu tiên: ứng viên verifier với đầu ra kiểm chứng được

**Đây là đề xuất tiếp theo, chưa được triển khai hoặc đo model thật ở lượt audit này.**
Mục tiêu là thử xem model tự đánh giá claim/context có tốt hơn việc nhìn nhãn
Judge rồi tự cho điểm hay không. Giới hạn thay đổi trong Fact-checker/diagnostic.

1. Thêm một verifier thử nghiệm chỉ nhận `claim + context`, chưa thấy nhãn
   hoặc explanation của Judge. Nó trả `assessed_label`, các trích dẫn bằng
   chứng trong context, thông tin còn thiếu và giải thích ngắn theo schema.
2. Code kiểm schema và trích dẫn có trong nguồn, sau đó mới so nhãn verifier
   với nhãn Judge. Bất đồng, thiếu bằng chứng hoặc lỗi schema phải trả trạng
   thái chưa xác minh; controller có thể tìm thêm trong budget hoặc dừng.
3. Trích dẫn tồn tại trong nguồn chỉ là một điều kiện cần. Vẫn phải đánh giá
   quan hệ suy luận, phạm vi, số/đơn vị và phủ định để tránh câu trích đúng nhưng
   diễn giải sai. Hai model/lượt gọi đồng ý cũng chưa tự bảo đảm sự thật.
4. Giữ runtime baseline và tiêu chí cũ; tạo tiêu chí mới trước inference cho
   ứng viên. Kiểm trên 12 contracts/24 nhãn đã biết và bộ dữ liệu mới được tách
   theo claim/document, có người kiểm nhãn. Ghi đầy đủ đúng/sai/bất đồng/abstain,
   nguồn, calls, latency và failures. Không lẫn những mẫu đã xem vào final test.
5. Chỉ đề xuất tích hợp khi đủ tiêu chí tự động và review evidence. Nếu dùng
   `matches_proposed_label`/`verified`, giữ đây là quyết định rời rạc;
   **không đổi 0/1 thành “xác suất đã calibration”**.

File dự kiến: module verifier trong `04_factchecker/inference/`, diagnostic
và criteria riêng trong `research_rag/evaluation/`, regression tests. Chỉ sau
khi ứng viên đạt mới điều chỉnh `04_factchecker/node.py`, cấu hình loader và
contract nhận kết quả ở `research_rag/graph.py`.

Trade-off: đầu ra dễ kiểm tra hơn và tránh đưa nhãn đề xuất vào bước đánh giá
đầu tiên, nhưng chưa có bằng chứng sẽ đạt tốt hơn. Nếu dùng cùng model, hai
lượt có thể vẫn sai giống nhau; phải đo calls/latency khi thay hoặc thêm stage.

Nếu thí nghiệm này vẫn trượt, lúc đó mới lựa chọn model khác hoặc huấn luyện
bổ sung cho đúng tác vụ. Dữ liệu phải có cả nhãn đúng/sai, evidence và các lỗi
đối chiếu; không gán score 0.95 tùy ý làm target. Nếu cần score xác suất, hiệu
chỉnh trên tập calibration riêng từ kết quả đúng/sai thực và đo cả calibration
lẫn khả năng loại nhãn sai/giữ nhãn đúng. Không train trên final test.

### C. Sau khi hai thành phần đạt

1. Sửa Summarizer `heldout_3` nhầm baseline, giữ kiểm tra nguồn và verbatim;
   thêm regression thể hiện đúng lỗi, không bỏ gate để câu trả lời đi qua.
2. Chuẩn bị đủ base weights/cache cho Summarizer, Writer và retrieval encoder.
   Preflight lượt này chưa thấy các base đó trong cache được kiểm; điều đó
   không làm confidence thất bại nhưng cần giải quyết trước full E2E.
3. Chạy [kaggle_autonomy_validation.ipynb](../scripts/kaggle_autonomy_validation.ipynb)
   với runtime sau tích hợp: sufficient, missing, conflict, pdf_pages, budget,
   heldout_1–3. Yêu cầu tám scenario gates, common safety gates, retrieval-policy
   gate và human review theo tiêu chí; failed/blocked không tính là pass.
4. Hoàn thiện bộ đánh giá độc lập, tài liệu demo/báo cáo: kiến trúc, trace quyết
   định, nguồn, điều kiện dừng, giới hạn và kết quả thực đo. Cách diễn đạt phù
   hợp là “multi-agent được điều phối tự chủ trong phạm vi nhiệm vụ nghiên cứu,
   có ngân sách và bằng chứng”; không khẳng định tự chủ tuyệt đối hoặc chính xác tuyệt đối.

## 7. Artifact audit đã lưu

- [Audit JSON và metrics tính lại](confidence-backend-audit-20261010T101538Z.json).
- [Summary gốc](../research-runs/kaggle-20261010T101538Z/confidence-backends/summary.json).
- [Review template gốc](../research-runs/kaggle-20261010T101538Z/confidence-backends/explanation-review.jsonl).

Audit chỉ đọc kết quả và chạy replay offline; không sửa runtime, prompt,
checkpoint hoặc tiêu chí đã đóng băng. Chưa chạy Reader/full E2E mới và chưa
đóng human sign-off.
