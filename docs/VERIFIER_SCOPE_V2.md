# Bước 1 đã triển khai: candidate base verifier scope_v2

Prompt profile `scope_v2` bổ sung quy tắc tổng quát cho lỗi phạm vi khẳng định
đã quan sát ở lượt base verifier 11/12. Chưa có inference mới chứng minh prompt
v2 sửa được nhãn sai; đây là candidate cần kiểm chứng.

## Quy tắc mới

| Phạm vi hoặc bằng chứng | Cách đánh giá yêu cầu trong prompt |
| --- | --- |
| Tất cả/mỗi phần tử | Một phản ví dụ trong đúng phạm vi đủ cho contradict; support cần bằng chứng phủ toàn bộ phạm vi. |
| Một số/ít nhất một | Một trường hợp dương tính trong đúng phạm vi đủ cho support; một trường hợp âm tính chưa đủ phản bác. |
| Không có phần tử nào | Một trường hợp dương tính trong đúng phạm vi đủ phản bác; thiếu đề cập không tự chứng minh sự vắng mặt. |
| Hướng thay đổi đã được nêu | Dùng thông tin trở nên tốt hơn/kém hơn/không đổi khi chủ thể, metric, điều kiện và thời điểm khớp; không yêu cầu số đo tuyệt đối một cách máy móc. |
| Chỉ có số đo hiện tại | Không suy ra thay đổi nếu chưa có đối chiếu phù hợp. |
| Claim nhiều vế AND | Support cần đủ mọi vế; một vế bị phản bác dẫn đến contradict; vế thiếu bằng chứng dẫn đến NEI nếu chưa có vế bị phản bác. |

Prompt yêu cầu quote phù hợp cho độ phủ, trường hợp chứng minh hoặc phản ví dụ.
Explanation cần nêu quan hệ với phạm vi claim; thông tin thiếu phải cụ thể và
không hỏi lại thông tin context đã cho. Không chứa ID, claim/context nguyên bản
hoặc đáp án của 12 cases đã dùng. Validator vẫn kiểm schema và quote; nó không
tự chứng minh semantic entailment từ việc quote có trong context.

## Chọn candidate và ghi nhận bằng chứng

`BlindVerifier(backend, prompt_profile='scope_v2')` chọn prompt mới.
Profile mặc định `baseline_v1` giữ nguyên prompt đã được dùng ở lượt audit.
Profile không hợp lệ bị chặn trước inference. Repair dùng lại profile đã chọn
và chỉ nhận claim/context; không nhận nhãn hoặc reasoning Judge.

Evaluator có tham số `--criteria`; criterion mới
`research_rag/evaluation/blind_verifier_scope_criteria.json` chọn chỉ backend
`base_instruct` và profile `scope_v2`. Model/revision, budget 384 tokens, tối đa
hai attempts, 12 cases gốc và gate 12/12 được giữ làm mốc. Tối đa 24 calls.
Provenance lưu đúng profile và toàn bộ prompt trước khi nạp model.

Đã đóng gói `scripts/kaggle_blind_verifier_scope_v2.ipynb` gồm ba cell cho
phép thử candidate base riêng. Notebook baseline cũng được sinh lại để source
hash khớp code mới, nhưng tiếp tục chọn profile baseline_v1. Các ZIP và kết quả
đã chạy giữ nguyên lịch sử; source hash mới không đồng nhất revision đã audit.

Notebook v2 hiện chỉ có 12 contracts cũ. Bước 2 mở rộng regression và đánh giá
độc lập vẫn chưa làm; chưa dùng notebook này làm bằng chứng nghiệm thu. Khi
chạy riêng candidate trên các contracts cũ, dùng notebook Kaggle mới Private,
GPU T4 và Internet, hai dataset workspace/diagnostics v2 như lượt trước; chạy
cell 1 mount, cell 2 setup, cell 3 experiment; giữ ZIP kể cả khi gate trượt.
Không cần Gemini Secret. Mỗi stage chỉ chạy một lần trong run mới.

## Kiểm tra thực hiện

- 11 focused tests local đạt: chọn profile trên first/repair call, giữ blinding,
  không nhúng cases, chặn profile lỗi, base-only routing, provenance, schema,
  retry budget, gate, source payload notebook và prerequisite setup.
- So với artifact đã audit: prompt baseline v1 và bytes criteria v1 không đổi;
  candidate giữ model revision, token/retry budget và ngưỡng chất lượng.
- Model trong tests giả lập; chưa chạy scope_v2 với weights thật trên Kaggle,
  chưa chứng minh khả năng tổng quát hoặc đủ điều kiện tích hợp serving.
- [Bản ghi kiểm tra local](blind-verifier-scope-v2-local-validation.json).

## File thay đổi

- `04_factchecker/inference/verifier.py`: prompt scope_v2 và profile selection.
- `research_rag/evaluation/compare_blind_verifier.py`: criteria selection và
  ghi profile/prompt thực dùng trong provenance.
- `research_rag/evaluation/blind_verifier_scope_criteria.json`: candidate base.
- `scripts/build_blind_verifier_notebook.py`: thêm chế độ sinh `--scope-v2`.
- `scripts/kaggle_blind_verifier.ipynb`, `scripts/kaggle_blind_verifier_scope_v2.ipynb`:
  payload hiện hành cho baseline và candidate.
- `research_rag/tests/test_blind_verifier.py`, `test_validation_notebook.py`:
  regression về profile, routing và source/setup guards.
- Tài liệu này, PROJECT_STATUS và bản ghi validation local được cập nhật.
