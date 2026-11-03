# Cellfix11 — sửa missing causal, quote metric và scope của unknown

## Trạng thái

Cellfix10 run `20261026T102553Z-54409fed` được giữ làm baseline:
**39/39 nhãn đúng, false support=0 theo gold, runtime=0**, nhưng ba lỗi semantic
chưa đạt. ZIP, toàn bộ 117 output, source release và các file review/audit được
khóa bằng hash trong `atomic-verifier-cellfix10-preserved-before-cellfix11.json`.
Không đổi judgment trượt thành đạt, không sửa predictions hoặc gold cũ.

Candidate mới: `atomic-verifier-constrained-v8-cellfix11`.
Criteria: `e0d6bb116d32f4485e678e635c8e911577148212875c9c24f782b2ed2ad84789`.
110 file candidate, 124 file payload. Chưa có prediction GPU cellfix11 hoặc
human review mới, chưa chạy validation30.

## Nguyên nhân và thay đổi

1. **Thiếu bằng chứng nhân quả.** Trong repo không có module độc lập tên
   `missing_renderer`; logic nằm ở `assessment_reporting.py`, trong
   `missing_reason()` và `missing_text()`. Candidate mới thêm reason
   `causal_relationship` và ghi đầy đủ quan hệ causal trong missing text. Target
   vắng mặt vẫn cần giải quyết identity trước. Một metric không mang causal
   predicate không bị yêu cầu thêm bằng chứng causal. Nhãn không bị renderer sửa.
2. **Quote sai metric khi truth=unknown.** Trước đây decoder và validator giữ
   nhánh unknown khá tự do, cho phép cite recall khi precision chưa đo. Helper mới
   `assessment_focus.py` nhận diện clause nguyên văn trực tiếp nói metric/relation
   hiện tại chưa được đo/báo cáo/thiết lập. Khi có câu absence rõ, không có outcome
   cạnh tranh cùng metric, unknown branch dùng quote đó và validator bắt buộc có
   quote liên quan. Không sửa câu nguồn hoặc tạo citation từ prose. Context có
   các kết quả cạnh tranh giữ ledger chung để xử lý, thay vì chỉ giữ absence.
3. **Observation của nhóm đối lập trong nhánh unknown.** Scope guard áp dụng cho
   cả true/false/unknown. Member phải thuộc local source clause phù hợp với
   condition/time. Source span vượt hai câu, member thuộc explicit opposed group,
   tháng khác, hoặc before/after đối lập bị từ chối và đi vào repair. Context chỉ
   có nhóm khác có thể dùng empty unknown ledger, không cần bịa một member.

`assessment_focus.py` được dùng chung bởi `atomic_verifier.py` và
`atomic_decoding.py`. Sửa behavior trong ba file có sẵn và thêm một helper;
không rewrite pipeline hoặc thêm dependency. Decomposition prompt, tất cả fixture
regression cũ và dữ liệu39 được giữ nguyên bytes. Không có nhánh runtime theo
case ID, Precision hay tên low/high-temperature của ca regression.

Các lựa chọn member có cùng quote constraints được gom chung để không nhân bản
numeric schema theo từng source span. LMFE vẫn dùng schema features đã hỗ trợ.
Mọi raw output/citation/repair trace tiếp tục được lưu.

## Kiểm chứng đã chạy

- **342/342 regression**, gồm 314 test cũ và 28 test mới từ trace thật cùng câu
  mới: conductivity/catalyst causal, specificity/sensitivity, cold/hot-storage,
  wet/dry-season, tháng và before/after. Có test repair thành công trong budget
  cũ và test exhaustion phải incomplete, không biến thành NEI hợp lệ.
- **37/37 đường token filter** với tokenizer Qwen đã pin. Ba serialization sửa
  lỗi có đường token hợp lệ, serialization sai bị chặn. Đây là các đường dựng
  để thử, không phải output inference mới của model.
- Replay **46 assessment cũ trên 39 ca**: đúng ba output lỗi bị từ chối và cần
  repair. Không tạo prediction mới và không gọi score replay đó là accuracy mới.
- **15 test notebook**, **16 test workflow/cell6**, **3 test cell7** đạt, gồm
  exact frozen run helper, status/log collision, hash/review admission, bảo toàn
  review cũ và chặn chạy lại validation30 đã có attempt.
- Cả **bốn validate-only từ payload** đạt. Nó không chạy inference validation30.
- Overlap screen: 70 file development/2.632 chuỗi, 0 cờ. Bộ validation30 giữ
  nguyên gold, input, protocol, human annotation review và lock gốc. Binding mới
  cellfix11-v1 không tạo chữ ký human mới và không dùng held-out outcomes để tune.

Model Qwen2.5-3B-Instruct revision `aa8e72537993ba99e69dfaafa59ed015b17504d1`,
NF4/float16 seed42 do_sample=False, 8 call/case, 2 attempt/stage,
max1536 token/call, 180 giây/case và gate 39/39/zero false support/runtime=0
được giữ nguyên.

Xem `atomic-verifier-cellfix11-validation.json`,
`atomic-verifier-cellfix11-tokenizer-check.json`,
`atomic-verifier-cellfix11-packaging-validation.json` và
`reviews/cellfix11-development/{CODE_DIFF.patch,PRESERVATION_CHECK.json,BASELINE_TRACE_REPLAY.json}`.

## Chạy Colab T4

1. Mở **`scripts/colab_atomic_verifier_cellfix11.ipynb`**, runtime mới, GPU T4.
   Chạy cells 1–5: payload/binding -> môi trường -> regression/validate-only ->
   smoke12 -> probe18. Giữ ZIP cả khi thất bại. Không chạy cell6 của cellfix10
   trong runtime cellfix11 và không thay source của một run đã đóng băng.
2. Probe đạt: review form **của run cellfix11 mới**, đủ 18 claim và từng tiêu chí,
   xuất semantic-review.json. Review cellfix10 không mở gate cho candidate mới.
3. Sau human probe review, bật `RUN_FULL39=True` ở cell6 và upload đúng review.
   Admission có preflight; retry dùng tên stage riêng và bảo toàn review/status/
   log cũ. Full39 đã có attempt sẽ không tự bị chạy đè.
4. Nếu full39 đạt automated gate, review đủ **39 ca** theo label, quote,
   explanation, đủ parts/quantity và missing-information. Ký human chỉ sau khi
   kiểm đúng kết quả mới; không ký trước hoặc tự đổi judgment trượt để qua gate.
5. **Giữ `RUN_VALIDATION30=False`** cho đến khi full39 và human review full39
   của đúng candidate/predictions cùng đạt. Cell7 yêu cầu review full39 riêng,
   kiểm admission trước inference và chặn lặp lại một lượt validation đã có.

## Giới hạn thực tế

Scope/absence/causal recognition là finite English grammar, không phải bộ hiểu
mọi paraphrase/coreference. Guard chặt hơn có thể khiến model cần repair hoặc
abstain; cần đo trên T4 trong budget đã khóa. Renderer nhất quán với ledger chưa
chứng minh ledger hiểu đúng source. Các warning identity của member absent-target
ở baseline không tự biến mất chỉ vì ba lỗi chính được sửa.

Local không có CUDA. **Chưa đo smoke/probe/full39 GPU cellfix11, chưa có human
review sạch mới, chưa mở validation30, chưa promote serving hoặc Reader/Summarizer E2E.**
