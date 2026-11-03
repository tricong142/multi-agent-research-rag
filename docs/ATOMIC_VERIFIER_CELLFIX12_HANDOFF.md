# Cellfix12 — binding, decisive witness và thiếu phép đo

Candidate: `atomic-verifier-constrained-v8-cellfix12`.
Criteria SHA256: `e147868fc5826a1f10e5a5132e1ea0fb0517e16b66b229c2ad163e71f64146f7`.
Notebook: `scripts/colab_atomic_verifier_cellfix12.ipynb`.
Đây là candidate chờ đo trên T4, chưa phải bản phát hành serving.
Đã đóng băng 113 input candidate/127 input payload, notebook 7 code cell.
Notebook SHA256: `3f09c406e82719bf26089440a7479787e9974a938f0e31133e9d9d138dcf440d`.

## Mốc được bảo toàn

Cellfix11 run `20261026T150123Z-615bf4eb`: **36/39 nhãn đúng,
false support=0, runtime=0**, automated gate trượt. Giữ nguyên ZIP `(3)`,
source, predictions và review/audit. Manifest bảo toàn:
`atomic-verifier-cellfix11-preserved-before-cellfix12.json`.
Không đổi gold hoặc sửa prediction cũ để tính lại thành kết quả đạt.

## Nguyên nhân và bản sửa

- `assessment_focus.member_scope_issue()` kiểm quote/member kể cả unknown:
  không cho quote của named target khác hoặc clause không gắn với member quay
  về bằng chứng ở toàn context. Hai đường đã có được giữ: quote absence trực
  tiếp của metric/relation có thể không lặp event subject, và numeric ledger
  đã bind các quantity qua hai câu của cùng evaluation. Không suy diễn alias.
- `assessment_decisions._legacy_decision_evidence()` phân biệt atomic target
  và qualified population. `atomic_property_truth()` chỉ đọc cấu trúc root
  subject + đúng property + direction, kể cả possessive; không ép nhãn từ
  modal, câu thuật lại, điều kiện, mâu thuẫn, quantity hoặc causal relation.
  Prefix `non-/un` không làm bằng chứng cho qualified target.
- `assessment_rules._MISSING` nhận thêm `no … changes were measured/reported/
  evaluated/recorded`. `observation_focus_issue()` áp thiếu phép đo trước
  true/false; không dùng một clause thiếu phép đo làm member. `No changes`
  được báo cáo như kết quả hoặc `remained unchanged` vẫn khác thiếu phép đo.
- `assessment_focus.constrain_focus()` dùng cùng guard observation với
  validator để lọc tổ hợp member/quote/truth. Repair vẫn có giới hạn; lặp
  output sai phải incomplete, không tự biến thành NEI hợp lệ.

Source behavior thay đổi trong năm module của **workspace candidate riêng**:
`assessment_rules.py`, `assessment_decisions.py`, `assessment_focus.py`,
`atomic_verifier.py`, `atomic_decoding.py`. Không thay code serving/main hoặc
source Cellfix11 đã phát hành, không thêm dependency, không rewrite pipeline.

Model Qwen/Qwen2.5-3B-Instruct revision
`aa8e72537993ba99e69dfaafa59ed015b17504d1`, NF4/float16/seed42,
do_sample=False, 8 calls/case, 2 attempts/stage, 1536 token/call, 180s/case
và gate được giữ nguyên. Decomposition prompt và bộ39 không đổi.

## Regression và giới hạn kiểm chứng

Regression mới dùng ba trace sai, thêm trace NONE dùng clause làm member,
và câu mới về Amber/Violet repeater, conductivity, dry/wet-season, các dạng
thiếu phép đo, unchanged, named target dạng suffix, scope, modal và conflict.
Có đường repair thành công và exhaustion. Đây là development, không phải
tập đánh giá độc lập.

Hai assertion cũ được đổi trong bản copy candidate, giữ nguyên bản gốc:
wrong-metric numeric citation nay phải repair; test foreign unknown member
chuyển reason-code sang kết quả của renderer mới trước khi kiểm scope.
Không bỏ test, không thay fixture/gold gốc hoặc hạ gate để qua test.

Các báo cáo của manifest cuối:

- `atomic-verifier-cellfix12-validation.json`: regression và ba validate-only.
- `atomic-verifier-cellfix12-tokenizer-check.json`: đường token dựng bằng
  tokenizer Qwen đã ghim; không tải weights, không tạo prediction mới.
- `atomic-verifier-cellfix12-packaging-validation.json`: notebook, retry/gate,
  exact payload và bốn validate-only, gồm validation30 không inference.
- `reviews/cellfix12-development/BASELINE_TRACE_REPLAY.json`: ledger cũ nào bị
  guard mới từ chối; đây không phải accuracy mới.
- `atomic-verifier-cellfix12-validation-overlap.json`: kiểm overlap development,
  không xem outcome Validation30 để tune. Gold/input/protocol/review/lock gốc
  giữ nguyên; binding candidate mới không tạo chữ ký human mới.

Đã kiểm trên manifest cuối: **363/363 regression** (342 test kế thừa và 21
method mới có nhiều subcase); **64/64 đường token filter** với tokenizer Qwen;
ba validate-only của source đạt. Replay 46 ledger cũ: 42 qua guard, bốn bị
từ chối (ba lỗi nhãn đã biết và NONE dùng cả clause làm member). Các đường
sửa của cả bốn ledger có test validator/decoder; không ghi đè prediction cũ.
Overlap: 73 file development/2.977 chuỗi, không có cờ theo protocol đã khóa.
**34/34 test notebook/workflow/retry/gate** đạt (15 + 6 + 10 + 3).
**Bốn validate-only từ exact payload** đạt; validation30 ở đây chỉ kiểm
binding/cấu hình, không gọi model hoặc đo kết quả held-out. Catalog release
và toàn bộ input candidate đã được kiểm hash sau đóng băng.

## Chạy trên Colab T4

1. **Runtime mới**, chọn GPU T4, mở notebook Cellfix12. Chạy **cell 1–5**:
   payload/binding → environment → regression/validate-only → smoke12 →
   probe18. Smoke trượt thì dừng, giữ ZIP diagnostic. Không chạy tiếp cell6
   hoặc dùng runtime/cell của Cellfix11.
2. Probe đạt automated gate: mở **HUMAN_REVIEW.html của run mới**, review đủ
   18 claim/từng tiêu chí và xuất semantic-review.json. Review Cellfix11
   không có hiệu lực cho predictions Cellfix12.
   Probe đo decomposition và review ngữ nghĩa, không đo độ chính xác nhãn.
3. Bật `RUN_FULL39 = True` ở **cell6**, upload review probe mới. Preflight
   kiểm criteria/predictions hash trước khi chạy. Retry admission bảo toàn
   review/status/log cũ; không chạy đè một full39 đã có attempt.
4. Nếu full39 đạt **39/39, false support=0, runtime=0, budget/trace đạt**,
   review đủ 39 prediction/evidence/explanation/missing-information bằng form
   mới rồi xuất review full39 riêng. Không ký trước hoặc đổi ca trượt thành đạt.
5. **Giữ `RUN_VALIDATION30 = False`** cho đến khi automated gate và human
   review full39 đúng candidate/predictions cùng đạt. Sau đó cell7 nhận review
   full39, replay admission và chạy validation30 đã khóa. Không tune bằng
   kết quả này rồi tiếp tục gọi nó là independent validation.

## Điều chưa thể kết luận

Kiểm offline không chứng minh model sinh đúng trong ngân sách T4. Chưa có
smoke/probe/full39 inference mới, human review mới hoặc Validation30 mới của
Cellfix12. Không công bố accuracy/zero false support cho candidate này.
Các guard dùng finite English grammar, chưa bao phủ mọi paraphrase/coreference;
có thể tăng repair/abstention. Chưa kiểm Reader/Summarizer E2E hoặc promote.
