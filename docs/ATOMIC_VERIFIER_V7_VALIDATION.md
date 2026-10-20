# Candidate v7 — validation offline và cập nhật probe T4

Ngày 2026-10-16. Version `atomic-verifier-constrained-v7-20261016`;
decoder policy `atomic-schema-decoding-v4`. Đây là bản sửa đã kiểm thử và đóng
gói trước inference. Sau đó [probe T4](DECOMPOSITION_PROBE_REVIEW_20261016T024708Z-a57ee72a.md)
đã đạt18/18, human reviewer tricong đã xác nhận và admission đạt. **Full39 đã
chạy nhưng timeout;21/22 predictions incomplete, một completed sai nhãn.**
[Audit full39](ATOMIC_VERIFIER_V7_FULL39_REVIEW_20261016T071213Z-7c8c33c6.md).
Các số đo offline dưới đây giữ làm lịch sử chuẩn bị; không chứng minh chất lượng39.

## Thay đổi và lý do

Run v6 `20261015T155608Z-9262cfd5` chứng minh validator/repair chưa đủ: 007 lặp
metric `took` hai lần, 008 repair từ `contained` sang `240 documents` rồi được
chấp nhận dù thiếu full predicate. Decoder v6 vẫn cho phép cả hai kiểu fragment.

V7 lấy yêu cầu metric trực tiếp từ source của từng clause, độc lập với entity,
condition hoặc metric do model chọn. Validator và enum metric của đúng schema
alternative dùng chung yêu cầu đó. Trong grammar mới được hỗ trợ, full predicate
phải còn nguyên; model không thể lách bằng quantity-only hoặc sao chép metric
của vế khác. Guard v6 tiếp tục xử lý bare verb của các mẫu không có số liệu.

Grammar mới chỉ bao gồm active `take/takes/took` với một quantity và đơn vị
thời lượng, và `contain/use/evaluate` với một quantity cùng một count noun/unit
ngay sau động từ. Time/dataset restriction được xác định từ source và tách
đúng vế; leading shared prefix vẫn được giữ. Percent/comparative, compound
object như `two gigabytes of memory` và named properties không bị cưỡng ép
sang metric mới. Các dạng numeric được nhận diện nhưng có modal/negation hoặc
relative clause không biểu diễn rõ sẽ dừng `unsupported_metric_structure`
trước model call. Đây là finite grammar, không phải semantic parser tổng quát.

Không đổi base prompts, model/revision, NF4/dtype, seed/sampling, dữ liệu hoặc
ngân sách. Có thay đổi repair hint vì quantity/object fragment cũng phải sửa.
Repair vẫn tối đa hai attempts; không sửa predictions sau generation để đạt gate.

## Bảo toàn v6

[Biên bản snapshot](atomic-verifier-v6-preserved-before-v7.json): 140 file, gồm
source/prompt/criteria/contract/data/tokenizer/notebook/build/test tools, ZIP và
outputs/logs/audit. Snapshot độc lập replay cả 18 predictions và giữ gate false.
Model weight bytes không được đưa vào snapshot; giữ pinned revision/hashes.

Snapshot ZIP SHA256:
`8afb6afe2c0bc793d1d65318103ba05419f920ff28dda86bbf3132513ca3dd36`.
Notebook, criteria, contract, original ZIP, predictions và human template v6
được kiểm hash; không ghi đè khi build v7. Snapshot v5 vẫn replay được.

## Kiểm tra đã chạy

| Kiểm tra | Bằng chứng |
| --- | --- |
| 14 regression metric v7 | Có mặt trong full suite và frozen payload |
| Toàn bộ research_rag/tests | **299/299 đạt**, unittest 98,175 giây; [log](atomic-verifier-v7-full-tests.log) |
| Packaging Kaggle/Colab | **7/7 đạt**, unittest 77,039 giây; [log](atomic-verifier-v7-packaging-tests.log) |
| Exact Colab payload | Giải nén riêng, so khớp bytes/hash, chạy đủ **101 frozen tests** và hai validate-only |
| Probe validate-only | Đạt, 18 cases / max36 calls; [log](atomic-verifier-v7-probe-validate-only.log) |
| Verifier validate-only | Đạt, 39 cases / max312 calls; [log](atomic-verifier-v7-verifier-validate-only.log) |
| Admission | Kiểm human review/hashes/trace vẫn bắt buộc; probe v5/v6 không admission v7 |
| Snapshot v5/v6 | Kiểm toàn bộ manifest/archive hashes, replay mỗi run đủ18 bằng source tương ứng |
| Tokenizer Qwen thật + LMFE | 18 fixture đầy đủ được phép; cả4 draft lỗi thật v6 bị chặn; [bằng chứng](atomic-verifier-v7-tokenizer-check.json) |

101 frozen tests là tập con của 299, không cộng hai số này thành số test độc lập.
Full suite và packaging là **306 test độc lập**. Các test model dùng backend giả
được ghi rõ trong source; không phải inference Qwen/CUDA. LMFE token-filter tests
chạy implementation thật với tiny tokenizer. Kiểm tra bổ sung dùng tokenizer
Qwen local thật: lấy draft v6 làm input fixture, thay metric theo requirement
v7 rồi kiểm từng token cùng EOS. Cả18 fixture được phép và cả4 draft lỗi v6 bị
chặn. Đây là counterfactual fixtures, không lưu thành predictions v7 và không
chứng minh 18/18 inference. Script kiểm tra dùng render chat template thành text
rồi tokenize như backend; không tải model weights hoặc gọi generation.

Regression mới bao gồm: các draft lỗi thật 007/008; câu mới và inflections;
quantity-only, object-only và cross-clause metric bị từ chối; full predicate
được phép; repair thành công hoặc hết ngân sách đúng; scope do model chọn không
che được source requirement; named properties/percentage/compound memory không
bị ảnh hưởng; all/some/none; shared/local time; decimal duration; động từ nằm
trong time restriction; hai count cần đủ hai evidence checks; unsupported
negative duration dừng trước call và replay khớp.

## Artifact đóng băng

Criteria SHA256:
`3e9a61616903e99f3c767e45c2ba361b44f6ea6c65732598ac3166b6cf23af7f`.

- [Criteria v7](../research_rag/evaluation/atomic_verifier_criteria_v7.json): 26 source files.
- [Contract v7](../research_rag/evaluation/atomic_verifier_contract_v7.json).
- [Colab v7](../scripts/colab_decomposition_probe_v7.ipynb): bốn code cell, 69 payload files.
- [Kaggle v7](../scripts/kaggle_decomposition_probe_v7.ipynb): ba code cell.
- [Release Colab](atomic-verifier-v7-colab-release.json), [release Kaggle](atomic-verifier-v7-release.json).
- [Lệnh đo và kết quả máy đọc được](atomic-verifier-v7-validation.json).

Thay đổi runtime: `04_factchecker/inference/atomic_verifier.py`,
`atomic_decoding.py`, `research_rag/evaluation/evaluate_atomic_verifier.py`.
Thay đổi test fixture: `test_atomic_experiment.py` dùng required metric của
source để backend giả hợp lệ theo contract mới; assertions/gate giữ nguyên.
Thêm `test_atomic_metric_v7.py`; cập nhật builders/packaging tests, thêm script
freeze v7 và artifact mới. Không rewrite kiến trúc hoặc thêm dependency.

## Việc còn lại

Probe và human admission đã hoàn tất trên run `20261016T024708Z-a57ee72a`.
Đã chuẩn bị [notebook39 cùng hướng dẫn](ATOMIC_VERIFIER_V7_FULL39_RUN_GUIDE.md),
nhúng human review đúng hash; bốn packaging/admission tests mới đạt. Lượt39 đã
audit và chưa đạt; cần sửa assessment generation/grounding/numeric/deadline rồi
freeze candidate tiếp theo. Những seen development cases này
không chứng minh generalization hoặc đủ điều kiện triển khai production.
