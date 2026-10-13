# Bước 2 — kiểm chứng scope_v2 bằng regression mở rộng

Đã chuẩn bị notebook ba cell để chạy candidate base verifier trên 39 cases:
12 contracts cũ và 27 cases mới. Đây là synthetic development regression;
independent annotation/semantic review vẫn pending. Chưa có kết quả model thật
cho prompt scope_v2, chưa tích hợp candidate vào serving.

## Chạy trên Kaggle

1. Tạo notebook Kaggle **mới, Private** và import
   `scripts/kaggle_blind_verifier_scope_regression.ipynb`.
2. Bật **GPU T4/T4 x2** và **Internet**. Dùng hai dataset workspace và
   runtime diagnostics **v2** hiện có của tài khoản, như lượt verifier trước.
   Notebook đã đóng gói source và dữ liệu mới; không cần upload lại dataset.
   Phép thử này không cần Gemini Secret.
3. **Cell 1:** mount dataset.
4. **Cell 2:** tạo workspace mới, xác thực manifests/source, cài môi trường,
   chạy tests và preflight. Chờ `SETUP COMPLETE`. Nếu lỗi, giữ ZIP setup và dừng.
   Runner dùng venv --without-pip và cài wrapt như lượt GPU đã chạy thành công.
5. **Cell 3:** chạy experiment **một lần**, đọc summary/metrics và hai mốc
   lịch sử. Save Version **with Output**, tải ZIP `rag-validation-…zip` được in
   ở cuối, kể cả khi gate trượt. Dừng GPU session sau khi đã lưu.

Dùng bản **scope_regression** cho bước này; bản scope_v2 của bước 1 chỉ có
12 contracts cũ. Không chạy thêm notebook baseline/confidence/Reader trong
phiên này và không chạy lại cùng stage vào output đã có.

## Bộ dữ liệu đã đóng băng

| Nhóm | Cases | Nội dung |
| --- | ---: | --- |
| original_contracts | 12 | Claim nhiều vế, thiếu evidence, phủ định, nhân quả, đơn vị, phạm vi và ghép evidence qua hai câu. |
| scope_regression | 27 | Chín contrast sets, mỗi set có support/contradict/not_enough_info. |

Chín families mới: universal, existential, none, entity, time, direction,
metric, conjunction, condition. Mỗi set giữ cùng claim và thay đổi context
để kiểm trường hợp hỗ trợ đủ, phản bác và thiếu bằng chứng. Dữ liệu tổng có
13 cases cho mỗi nhãn. Tên/thông số trong các cases mới là giả lập; nguồn
được ghi rõ là assistant-authored và chưa được người khác kiểm nhãn độc lập.

Cases mới có annotation_rationale giúp review nhãn trước/chốt sau inference.
Gold label, rationale, family và source chỉ dùng ở evaluator/review; model
chỉ nhận claim/context, cả ở first call và repair. Prompt không chứa nguyên
claim/context của các cases. Prompt scope_v2 đã được sửa trước khi tạo cases.

Hash prompt, contracts cũ, cases mới và hai snapshot baseline nằm trong criteria;
code kiểm chúng trước khi nạp model. Duplicate IDs, group counts sai, input
sai hoặc budget sai đều dừng trước inference. Criteria được ghi vào output
trước calls, không sửa gate dựa trên kết quả.

## Cấu hình và điều kiện đạt

- Chỉ `base_instruct`, Qwen2.5-3B-Instruct revision
  `aa8e72537993ba99e69dfaafa59ed015b17504d1`, prompt scope_v2.
- Giữ 384 output tokens/call; tối đa hai attempts cho lỗi cấu trúc;
  tối đa **78 calls** cho 39 predictions. Backend failure không được retry như JSON.
- Gate tự động: đủ 39 ID duy nhất, **12/12 ca cũ và 27/27 ca mới đúng**, không
  false support, không runtime failure, không đồng ý bất kỳ nhãn sai nào và
  attempts trong budget. Không tự promote hoặc tích hợp candidate.
- Chấm cả ba proposed labels cho từng prediction sau inference: một đúng,
  hai sai. 117 comparisons chỉ dùng 39 predictions, không phải 117 mẫu độc lập.
- Metrics có accuracy/macro-F1/per-label/confusion, từng dataset group và từng
  family. Missing/runtime-failed cases không được bỏ khỏi mẫu số classification.
  Gate kiểm cả tập ca đầy đủ, không dùng metric cao trên output thiếu làm pass.

Không cần điều chỉnh API key, quota Gemini hay model Reader để chạy bước này.

## Hai mốc lịch sử được dùng đúng phạm vi

1. Confidence repair từ run 20261010T101538Z: 24 controlled labels, nhận 4/12
   nhãn đúng và 2/12 nhãn sai ở threshold 0,7. Chỉ áp dụng cho 12 contracts cũ.
2. Base verifier v1 từ run 20261012T101333Z: đúng 11/12, một lỗi scope và zero
   false support. Được chấm lại bằng all-labels policy nên có một wrong-label
   agreement, bao gồm nhãn NEI sai mà policy cũ không đếm.

Không gọi model mới để tái tạo hai baseline. Baseline base giữ hash artifact,
hash ZIP nguồn và metadata. Trước calls mới, loader phải khớp weights/tokenizer,
revision, dtype, quantization, seed, sampling và output budget. Nếu khác,
runner lưu provenance rồi dừng, tránh quy chênh lệch không tương đương cho prompt.
Audit của snapshot dựa trên hash/log nhận được, không phải chứng thực độc lập
từ nhà cung cấp. Baseline không có kết quả cho 27 cases mới.

## Đọc output

| Artifact | Cần kiểm |
| --- | --- |
| status.json | Stage blind-verifier completed/exit 0 hay failed/exit 1; setup/preflight phải completed. |
| blind-verifier/summary.json | experiment_completed, prediction_count=39, calls<=78, automated_gate_pass; human_review vẫn pending. |
| metrics.json | dataset_groups: ca cũ 12/12, mới 27/27; false_support/runtime failures zero; breakdown families và classification. |
| historical-verifier-metrics.json | Mốc v1 11/12 được chấm bằng cùng all-labels policy trên ca cũ. |
| baseline-metrics.json | Mốc confidence repair; không nhầm confidence threshold với nhãn rời rạc. |
| provenance.json | Prompt/profile, input/source hashes, model metadata và historical_verifier_pairing. |
| base_instruct-calls.jsonl | Actual messages/outputs, lỗi cấu trúc nếu có, elapsed/token budget. |
| evidence-review.jsonl | 39 rows để người đánh giá kiểm nhãn, quote, suy luận, độ phủ claim và thông tin thiếu. |

`experiment_completed=true` nhưng `automated_gate_pass=false` nghĩa là đã
chấm xong và candidate trượt; exit 1 là chủ ý. Summary thiếu nghĩa là chưa có
bằng chứng hoàn thành, cần giữ status/stderr. `automated_gate_pass=true`
chưa thay thế review bằng người hoặc đánh giá độc lập.

Sau khi tải ZIP, đối chiếu/replay output trước khi quyết định tích hợp. Nếu đạt
automation thì hoàn thiện semantic/human review và bộ đánh giá độc lập; nếu
trượt thì sửa đúng loại lỗi được trace chỉ ra. Không hạ gate hoặc chạy lặp
không đổi cấu hình. Reader/Summarizer/E2E toàn hệ vẫn là các gate sau đó.

## Kiểm tra local và file thay đổi

19 focused tests local đạt: 9 verifier tests cũ, 7 tests cho regression/hashes,
pairing/budget/gate/classification/blinding và 3 tests notebook/source/setup.
Models trong tests giả lập, chưa chạy candidate mới trên Kaggle.

- Thêm `blind_verifier_scope_regression_cases.jsonl` và criterion tương ứng
  trong `research_rag/evaluation`; thêm `blind_verifier_base_v1_baseline.json`.
- Sửa `research_rag/evaluation/compare_blind_verifier.py`: frozen inputs,
  supplemental cases, all-labels policy, groups/classification và historical pairing.
- Thêm `research_rag/tests/test_blind_verifier_regression.py`; cập nhật
  `test_validation_notebook.py` để kiểm artifact mới.
- Sửa `scripts/build_blind_verifier_notebook.py` và sinh
  `kaggle_blind_verifier_scope_regression.ipynb`; notebook baseline/step-1
  được sinh lại để source hash khớp code chung, criteria cũ giữ nguyên.
- Cập nhật PROJECT_STATUS và [bản ghi validation local](blind-verifier-scope-regression-local-validation.json).
