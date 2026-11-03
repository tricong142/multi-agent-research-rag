# Audit Cellfix15 — Validation30

Ngày audit: 2026-11-03. Run: `20261102T163553Z-ed00dfbc`.

Pipeline đang kiểm tra claim theo hai bước: phân rã claim thành predicate có scope, sau đó dựng sổ bằng chứng và tính nhãn. Phạm vi audit là một run Kaggle đã hoàn tất, không phải audit toàn bộ hệ thống serving.

## Kết luận

**Validation30 đã chạy đủ, nhưng không đạt: 13/30 đúng (43,33%), 8 incomplete và 9 ca hoàn tất nhưng sai nhãn.** Bốn ca sai nguy hiểm nhất là gold `contradict` nhưng được trả `support`: 005, 008, 026, 029.

Không có bằng chứng đây là lỗi Cell7, thiếu JSON review, timeout hay thiếu token. Cell7 đã cho phép chạy sau admission; việc trả exit code 1 phù hợp với `automated_gate_pass=false`.

- 63 lượt gọi; mỗi lượt có đủ `call_started`, `generation`, `call_finished`.
- 30 `case_finished`; ca lâu nhất 108.840,842 ms, dưới hạn 180.000 ms.
- 8.389 generated tokens; 95.438 prompt tokens. Lượt dài nhất 520 generated tokens, dưới hạn 1.536.
- Tất cả 8 incomplete có `stop_reason=invalid_output_exhausted`: dùng hết hai lượt sửa ở một bước, không phải dùng hết 8 calls/case.
- 7/8 incomplete ở decomposition; 1/8 ở assessment.
- Full39 pass không chứng minh Validation30 pass. Các cấu trúc dưới đây nằm ngoài những trường hợp mà guard hiện tại xử lý đúng.

## Nguồn và kiểm tra tính toàn vẹn

ZIP: `output-cellfix15-kaggle-20261102T163553Z-ed00dfbc (1).zip`, 3.468.732 byte.

SHA256:

```text
ZIP          379e0ef3441e35b625828c2db1a76075cf672c8d8205ae5c081c1e7332a1ba07
predictions  2e7e03413b6a178f4ea6a7cadd223cc1bfffba146c9f50858517b2e19e601fb1
calls        030f9e1f7de7e34e26926ec6414a9205c7bbb26ea34db30898ad5cc68180a971
criteria     95b79b8589980376c9c3ca45780ac3ac1a809bf13c03b84904616ee7da939e69
```

Hai file JSONL rời giống từng byte với `validation30/` trong ZIP. Bản gốc được giữ tại `research-runs/audit-cellfix15-validation30-20261102T163553Z-ed00dfbc/original-output.zip`; nội dung giải nén ở `artifact/`, frozen source ở `workspace/` cùng thư mục.

Đã kiểm tra 154 file output theo manifest, CRC, 140 payload inputs so với release, provenance/model/settings, binding của Validation30, probe/full39 admission và tính lại metrics/classification, khớp hoàn toàn. Cả 63 output thực nhận đi qua parser LMFE; validator chấp nhận 45 lượt và từ chối 18 lượt. Các lỗi từ chối được tái hiện đúng, gồm cả các lượt lỗi sau đó sửa thành công. Kết quả máy đọc được nằm trong `docs/atomic-verifier-cellfix15-validation30-audit-20261102T163553Z-ed00dfbc.json`.

## 8 ca incomplete

Các ID dưới đây có tiền tố `validation-v1:`. Dữ liệu trong `predictions.jsonl` có đúng thứ tự 001–030, nên số ID cũng là số dòng.

| ID | Gold | Bước dừng, lỗi thực nhận | Nguyên nhân từ record và code |
|---|---|---|---|
| 009 | NEI | Decompose ×2: `quantified_population_required` | Claim “simplified each sentence in 20 milliseconds”; model chọn `entity=parametrization`, tức tác nhân đứng trước `each`, thay vì population `sentence`. Retry lặp nguyên output. |
| 010 | Support | `metric_predicate_incomplete` → `uncovered_claim_content` | Lượt đầu tách ba mảnh, trong đó `metric=contains` mất đối tượng, `and 14,769 actions` thiếu predicate và `entity=4,340` là số. Lượt sửa chỉ giữ mệnh đề 1.268 clips, bỏ 14.769 actions và 4.340 visible. Trace chỉ ghi lỗi đầu tiên mỗi lượt; các vấn đề khác là phân tích nội dung record. |
| 011 | Contradict | Assessment: `observation_evidence_unbound` → `incomplete_coverage_ledger` | Lượt đầu member `the actions` không nằm trong quote được chọn: “14,769 actions, 4,340 of which are visible”. Lượt hai coverage liệt kê “The paper makes three main contributions. First, we”, nhưng observation là `14,769 actions`; hai tập member không khớp. Lượt hai còn so 14.769 với chính 14.769, bỏ vai trò “visible=4.340”. |
| 015 | NEI | Decompose ×2: `quantified_population_required` | Part thứ hai chọn `entity=each prediction`. `subject_issue` kiểm tra vị trí bắt đầu entity trước điểm kết thúc `each`, nên chặn cả cụm có lượng từ ở đầu. Retry không sửa. |
| 020 | Contradict | Decompose ×2: `quantified_population_required` | Với “Dataset reserves all 80 events for training”, model chọn entity là Dataset đứng trước `all`, không chọn 80 events. Retry lặp output. |
| 021 | NEI | Decompose ×2: `quantified_population_required` | **Guard chặn nhầm cấu trúc hợp lý:** “news articles … are all written in French”. Entity `news articles` là đúng population nhưng đứng trước lượng từ hậu vị `all`. Quy tắc vị trí không phân biệt được cấu trúc này với tác nhân sai ở 009/020. |
| 023 | Contradict | Decompose ×2: `population_modifier_missing` | Claim có `all eight named-entity categories`, nhưng cả hai lượt bỏ `eight` khỏi entity/condition. Retry chỉ thêm `from the original dataset`; thông báo sửa đã chỉ rõ thiếu `eight`. |
| 025 | Support | Decompose ×2: `subject_comparator_inverted` | Model chọn đối tượng so sánh `the wav2letter Transformer` làm chủ thể, thay vì `proposed model`. Guard chặn đúng; retry tiếp tục chọn sai. |

**Vấn đề chung của decomposition:** `atomic_decoding.decomposition_schema` cấp nhiều substring của claim làm enum cho entity/metric. Quan hệ giữa các field chưa được ràng buộc bằng những kiểm tra như `subject_issue` và `scope_issues` của validator. JSON có thể đi hết đường decoder nhưng vẫn không hợp lệ về decomposition. Hints cho `quantified_population_required` và `subject_comparator_inverted` rơi về hướng dẫn sửa chung; số lượt sửa tăng lên không giải quyết được sự lệch hợp đồng này.

**Không bỏ các guard đúng để cứu score:** 009, 020, 023, 025 thực sự chứa binding sai hoặc mất thông tin. 021 cần sửa quy tắc nhận diện lượng từ, không đổi gold NEI thành nhãn khác. 015 cần chuẩn hóa phạm vi population có/không kèm lượng từ một cách thống nhất.

## 9 ca hoàn tất nhưng sai nhãn

NEI = `not_enough_info`.

| ID | Gold → prediction | Bằng chứng và cơ chế dẫn tới sai nhãn |
|---|---|---|
| 005 | Contradict → Support | Claim nói WMT En-De dùng **tokenized BLEU**; quote được chọn nói **detokenized BLEU**. Model vẫn đặt `truth=true`, validator chấp nhận. Metric `reported BLEU` không giữ thuộc tính tokenized; guard chưa đối chiếu thuộc tính này. |
| 007 | Support → NEI | Nguồn có 41.87 SARI. Model so `41.87 SARI` với `+1.42 gain over previous scores`, nhầm điểm tuyệt đối với mức tăng. Numeric checker trả `unit_mismatch_no_conversion`. Kiểm tra sâu phát hiện bộ lấy quantity đọc `41.87 SARI BIBREF9` thành quote `41.87 SARI BIBREF`, unit `SARI BIBREF`. Record sửa đúng right operand trên cùng source quote được validator trả Support nhưng parser decoder chặn: đây còn là lệch hợp đồng giữa hai phía, không chỉ lỗi chọn số của model. |
| 008 | Contradict → Support | Claim nói **required a modified training objective**; nguồn nói **without requiring … modified training objective**. Decomposition chỉ ghi metric `achieve its WikiLarge score`; observation chọn cửa sổ trích dẫn kết thúc trước phần phủ định. Guard chấp nhận true từ thông tin cải thiện điểm, không kiểm tra yêu cầu training objective. |
| 013 | Support → NEI | Claim và nguồn cùng 0.548 prediction accuracy. Numeric checker trả `qualified_numeric_evidence` vì source_quote chứa “which is **not good enough**”. Nhận xét chất lượng bị xử lý như phủ định/điều kiện làm số đo không chắc chắn. |
| 014 | Contradict → NEI | Claim 0.748, nguồn 0.548. Cùng lỗi `qualified_numeric_evidence` như 013; quan hệ 0.748 ≠ 0.548 không được dùng để trả contradict. |
| 019 | Support → NEI | Nguồn nói 80 events, **each paired with a set of related news articles**. Lượt đầu lỗi `duplicate_coverage_member`. Retry bỏ coverage, đặt `plane crash events=unknown`, quotes rỗng; validator chấp nhận. Bộ nhận diện collective witness hữu hạn không buộc giữ bằng chứng toàn population này. |
| 022 | Support → NEI | Nguồn có **980 annotations in 670 tweets in Turkish**, kèm ngữ cảnh named entities/names. Claim được lấy thành unit `name annotations` và `Turkish tweets`; source thành `annotations` và `tweets`. `numeric_choices` trả `[[], []]`; schema tái tạo **chỉ có truth=unknown** cho part thực nhận. Model không có nhánh true để chọn với part/schema này. Cần bind modifier vào object bằng bằng chứng cục bộ, không chỉ so hai con số hay thêm retry. |
| 026 | Contradict → Support | Claim so với **best hybrid model** trên test-other; nguồn nói **still worse than the best hybrid model**. Record true lại trích câu về kiến trúc/masking và mức gain khác. Comparator không có trong metric `performs better`; guard không yêu cầu evidence gắn đúng comparator, dataset và chiều so sánh. |
| 029 | Contradict → Support | Claim gọi sections 0–1 là **test set**; chính quote được chọn nói **development set for hyperparameter optimization**. Entity được bind đúng nhưng vai trò dataset split không được đối chiếu; true bị chấp nhận. |

### Vì sao 4 false support nguy hiểm hơn JSON không hợp lệ

`assessment_evidence.citation_issue`, `assessment_rules.evidence_issue` và `assessment_decisions` có các quy tắc hữu hạn cho một số predicate. Với thuộc tính/quan hệ không thuộc các mẫu đó, việc có đúng member trong source và quote là substring thật chưa chứng minh claim đúng. Khi không tìm được witness quyết định, `assessment_issue` có thể không trả lỗi; aggregator dùng truth do model chọn để suy ra support.

Do đó, “schema/trace complete” không có nghĩa “evidence entails claim”. Các ca 005 và 029 còn dùng chính quote phản bác claim, cho thấy kiểm tra substring/identity không đủ. Các ca 008 và 026 chọn quote không chứng minh yêu cầu trọng tâm của claim.

## Thử nghiệm chẩn đoán trong bộ nhớ

Đã chạy `scripts/diagnose_atomic_cellfix15_validation30.py`, kết quả lưu ở `research-runs/audit-cellfix15-validation30-20261102T163553Z-ed00dfbc/targeted-diagnostics.json`. Không sửa context/output gốc; các thay đổi dưới đây chỉ nằm trong bản sao dùng để kiểm tra cơ chế.

| Ca | Thử nghiệm | Kết quả thực kiểm tra |
|---|---|---|
| 009/015/020/023/025 | Chỉ sửa entity lần lượt thành `sentence`, `prediction`, `80 events`, `eight named-entity categories`, `proposed model` | Decomposition validator chấp nhận. Điều này không chứng minh các field còn lại đúng ngữ nghĩa hoặc model sẽ tự sinh bản sửa. |
| 021 | Cặp câu tối giản: “The news articles are all written in French.” / “All news articles are written in French.” | `subject_issue` chặn câu đầu và không chặn câu sau dù population/predicate tương đương. |
| 007 | Thay right operand bằng 41.87 SARI, giữ nguyên source_quote thực nhận | Numeric checker trả true; assessment trả Support; parser decoder không chấp nhận record sửa này. Chưa kết luận mọi cách trích dẫn tương đương khác đều bị chặn. |
| 011 | Trong record lượt đầu, đổi member `the actions` thành exact span `14,769 actions`, giữ so sánh 14.769 với 4.340 | Parser chấp nhận; validator trả Contradict. Đường đúng đã biểu diễn được. |
| 013/014 | Chỉ bỏ từ `not` trong “which is not good enough” trên bản sao context và source_quote để cô lập guard | Numeric checker đổi từ unknown thành true ở 013 và false ở 014. Đây là thí nghiệm chỉ ra guard quá rộng, **không phải đề xuất xóa `not` khỏi dữ liệu**. |
| 019 | Collective member `plane crash events`, coverage và observation cùng member, quote nguyên câu “80 … each paired …”, truth=true | Parser chấp nhận; validator trả Support. Đường đúng đã biểu diễn được; lỗi thực tế là chọn/sửa ledger và không buộc giữ witness quyết định. |
| 022 | Liệt kê nhánh truth của schema tái tạo và kết quả `numeric_choices` | Chỉ `unknown`; không có candidate numeric quyết định cho cả q0 và q1. |

## Hướng sửa cho candidate kế tiếp

1. **Ưu tiên chặn false support (005/008/026/029).** Giữ đầy đủ đối tượng của predicate, thuộc tính phân loại, phủ định và comparator. Bắt buộc evidence gắn với cùng quan hệ; `scope_match=matched` chỉ là cùng phạm vi, không phải đồng ý. Nếu chưa chứng minh được, giữ unknown; muốn đạt gold contradict phải biểu diễn được phản chứng cụ thể.
2. **Đồng bộ decomposition decoder–validator.** Sửa `subject_issue` để phân biệt lượng từ trước/sau population và tác nhân của động từ; sau đó dùng cùng luật khi tạo lựa chọn decoder. Giữ `eight`, chủ thể/comparator và toàn bộ nội dung claim. Với 010, phải biểu diễn đủ ba count và quan hệ `of which`.
3. **Sửa chọn và gắn số đo.** Không để marker BIBREF trở thành unit; đồng bộ extractor, operand schema và validator. Phân biệt score với gain; giữ đơn vị/đối tượng đầy đủ; xử lý phủ định đúng predicate, không xóa mọi từ `not`. Xử lý thông tin ngôn ngữ/loại annotation bằng bằng chứng cục bộ, không alias tùy tiện.
4. **Giữ consistency của coverage và collective evidence.** Decoder không nên cho coverage member khác observation member; không ép tạo hàng nghìn member để biểu diễn population lớn. Một phát biểu toàn population phải được bind đúng với quan hệ được khẳng định, không chỉ có từ `each`.
5. **Regression trước GPU.** Dùng output sai thực nhận làm fixture; thêm biến thể tên/số/cách diễn đạt và đối chứng phản bác. Kiểm tra cả đường đúng còn hợp lệ và đường sai bị chặn. Sau đó mới chạy smoke → probe → Full39 → development30 với candidate/output mới và review tương ứng.

Không sửa Cell7, metrics, gold, output cũ hoặc nâng budget để biến run này thành pass. Không hard-code case ID hoặc đáp án vào guard. Giữ member-local absence guard của Cellfix15; trace hiện tại không ghi lỗi `missing_evidence_is_not_false` trong 8 incomplete, nên không có bằng chứng cần gỡ guard đó.

## File code liên quan trực tiếp

Các đường dẫn sau thuộc `research-runs/atomic-cellfix15-candidate/workspace/04_factchecker/inference/`:

- `cellfix14_decomposition.py:34`: `subject_issue`, kiểm tra vị trí population và comparator.
- `atomic_decoding.py:53`: `decomposition_schema`, enum scope còn độc lập.
- `atomic_verifier.py:384`: `scope_issues`, giữ metric/population modifiers.
- `atomic_verifier.py:605`: assessment ledger, numeric truth, coverage và aggregation.
- `assessment_evidence.py:73`: `citation_issue`; `:180`: `population_witness`.
- `assessment_decisions.py:49`: `numeric_choices`; `:216`: kiểm tra quyết định theo witness hữu hạn.
- `numeric_verifier.py:109`: vùng kiểm tra phủ định/qualified evidence; `:149`: `measurement_scope`.
- `cellfix14_quantities.py:19`: lấy quantity/unit và các quy tắc count.
- `assessment_focus.py:178`: guard absence chia sẻ giữa decoder và validator.

## Giới hạn kết luận

- Đây là replay offline của output đã nhận, không phải inference mới, cũng không phải kết quả của bản sửa.
- Các record sửa trong bộ nhớ ở `targeted-diagnostics.json` chỉ dùng khoanh vùng nguyên nhân. Chúng không thay thế predictions và không chứng minh model sẽ tự sinh record đúng.
- Chưa chạy GPU cho candidate mới; không có cơ sở cam kết 30/30 sau bất kỳ thay đổi nào.
- Bộ này được ghi rõ là development regression và đã dùng để tuning. Kể cả đạt 30/30 về sau vẫn cần holdout độc lập để đánh giá khả năng tổng quát.
- Kiểm tra hash và replay chứng minh các file nhất quán với code được freeze, không xác thực phần cứng/máy chủ từ xa. Nhận xét ngữ nghĩa ở đây dựa trên claim/context trong artifact, không xác minh lại paper bên ngoài và không phải chữ ký human review.

**Ưu tiên thực hiện:** sửa cơ chế dẫn đến false support, đồng bộ decomposition và xử lý numeric/coverage; giữ nguyên run đã thất bại làm bằng chứng regression.
