# Cellfix14 full39 — run 20261102T120149Z-ca882061

## Kết luận đã kiểm chứng

Cell6 đã nhận đúng review probe, qua admission rồi chạy đủ 39 ca. Exit1 là
quality gate failed: 38 completed đúng nhãn, một incomplete, không phải lỗi
upload, missing run_id, timeout hay bằng chứng Kaggle crash.

- ZIP SHA256: `38eb9b0b779dc0b93b789613580d6942f9b29f0518fd40fabcc8dc6ca9ee6555`.
- 108 output files + manifest và 137 frozen inputs đúng size/hash/release.
- Criteria: `f63345bb14de338432e57bad6644301bb43ef61e1fd6cf5e22376dcab2b19e5e`.
- Source/prompt/model/revision/budget/gate khớp frozen release.
- Replay kết quả và tái tính metrics của smoke12, probe18 và full39 đều khớp.
- Review probe được frozen admission chấp nhận. Điều này kiểm nội dung/metadata
  và hash file, không phải attestation danh tính reviewer.

| Stage | Kết quả |
|---|---|
| Smoke | 12/12 nhãn đúng, không runtime failure |
| Probe | 18/18 decomposition hợp lệ; admission đã qua |
| Full39 | 38/39 nhãn đúng, 38 completed, một invalid_output_exhausted |
| Support / contradict | 12/12 và 12/12 đúng |
| NEI | 14/15 đúng, một incomplete |
| False support / gold support rejected | 0 / 0 |
| Calls / generated / prompt tokens full39 | 86 / 9.350 / 123.910 |
| Validation30 | Chưa chạy trong run này |

## Ca thất bại

ID: `scope:none:not_enough_info`.

Claim: `None of the monitored pumps leaked during the overnight test.`

Context: `Blue, Green and Silver were monitored during the overnight test. Blue
and Green had no leaks, but Silver's leak status was not reported.`

Decomposition hợp lệ: quantifier none, population monitored pumps, metric leaked,
time during the overnight test. Cả hai assessment đều trả:

```json
{
  "member": "Silver's leak status",
  "truth": "false",
  "quotes": ["Blue and Green had no leaks, but Silver's leak status was not reported."],
  "numeric": null
}
```

Lượt đầu missing_information có measurement_unreported; lượt hai bỏ missing
nhưng giữ member/truth sai. Validator từ chối cả hai bằng
`missing_evidence_is_not_false`. Hết hai attempts thì output incomplete, không
có nhãn cuối. Tổng ca 23.887,813 ms, dưới budget 180.000 ms.

Truth là predicate dương leaked, trước NONE: false nghĩa có bằng chứng không
rò rỉ; unknown nghĩa chưa biết. Trạng thái Silver chưa báo cáo phải unknown.
Member là Silver, không phải thuộc tính Silver's leak status. Chưa chứng minh
mọi pump không rò rỉ và cũng chưa có pump rò rỉ để refute NONE: nhãn đúng NEI.

## Root cause và thử nghiệm offline

Giới hạn cụ thể trong source: constrain_focus áp member_absence_quotes cho
nhánh unknown; member_identity_issue bỏ qua nominal-role guard của known
outcomes. Vì vậy status noun phrase + false còn là một lựa chọn token hợp lệ.
Validator phát hiện lỗi absence ở bước sau; repair prompt không loại lựa chọn
sai khỏi decoder, nên model có thể lặp lại nó.

Đã kiểm bằng LMFE thật với tiny tokenizer của regression CPU:

1. Output thực nhận đi qua token filter nhưng bị assess_part từ chối.
2. Record sửa tay member=Silver/truth=unknown đi qua filter và validator trả NEI.
3. Một guard thử trong bộ nhớ áp explicit member absence cho mọi truth, dùng
   chung qua observation_focus_issue, chặn token path sai và giữ path unknown.

Đây là counterfactual kiểm contract, không phải inference, không chứng minh
model đã sinh record sửa tay hoặc full39/Validation30 đã đạt. Chưa thay source,
prompt, criteria, gold hay predictions của Cellfix14; không hot-patch runtime.

## Bước tiếp theo

Giữ ZIP và source Cellfix14 làm baseline. Sửa trong candidate kế tiếp: dùng chung
member-local absence guard cho validator/decoder ở cả known/unknown outcomes,
không loại kết quả known của Blue/Green chỉ vì Silver thiếu thông tin. Thêm
regression từ hai raw outputs này và biến thể tên/entity/predicate mới; giữ
negative controls explicit denial, known no-leak, leaked=true, và conflicting
reports của cùng member. Không hard-code case ID hoặc gán nhãn NEI theo gold.

Sau regression và token-filter tests, freeze source mới rồi mới inference
smoke/probe/full39 và review mới. Giữ RUN_VALIDATION30=False cho run hiện tại.
Không sửa cell6 để đổi exit1 thành pass, không bỏ ca lỗi hoặc tăng attempts để
chọn một output thuận lợi. Bộ30-v1 vẫn là development; cần holdout mới để đo độc lập.

## Bằng chứng và giới hạn

Machine audit: `docs/atomic-verifier-cellfix14-full39-audit-20261102T120149Z-ca882061.json`.
ZIP gốc và raw case: `research-runs/audit-cellfix14-full39-20261102T120149Z-ca882061/`.
Helper: `scripts/audit_atomic_cellfix14_full39.py`.

Không có inference mới trong lượt audit. ZIP xác nhận consistency của payload
và output đã lưu; không chứa notebook UI đã thực thi để attestation byte-for-byte.
Counterfactual chưa được kiểm bằng weights hoặc tokenizer Qwen trên GPU.
