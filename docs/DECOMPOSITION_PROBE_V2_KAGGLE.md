# Probe decomposition v2 — hướng dẫn chạy và điều kiện đi tiếp

**Lượt v2 đã chạy, đạt 12/18 và trượt gate.** Xem
[đối chiếu](DECOMPOSITION_PROBE_REVIEW_20261013T131400Z-b05a83bd.md).
Lượt tiếp theo dùng [notebook v3](../scripts/kaggle_decomposition_probe_v3.ipynb)
và [hướng dẫn v3](DECOMPOSITION_PROBE_V3_KAGGLE.md). Trang này giữ lịch sử bàn giao v2.

Phiên bản `atomic-verifier-quotes-v2-20261013`, policy `atomic-verifier-quotes-v2`.
Đã sửa code và chuẩn bị notebook; **chưa có kết quả model thật v2**.
Run setup2 trước đó trượt cả 39 decomposition. Các ZIP và criteria cũ được giữ
nguyên để đối chiếu; không dùng kết quả test giả lập làm bằng chứng chất lượng model.

## 1. Thay đổi đã thực hiện

- Model chỉ trả `quote`, `quantifier`, `scope`; `scope` là object có bốn string:
  `entity`, `metric`, `time`, `condition`. Prompt có ba ví dụ JSON tổng quát,
  không dùng câu/gold của 18 claim để làm ví dụ.
- Code tìm trích đoạn khớp nguyên văn và xuất hiện duy nhất để tính `start/end`.
  Sai nguồn, vị trí mơ hồ, đảo thứ tự, chồng lấn, bỏ sót từ/số/đơn vị, tách giữa
  token, sai quantifier và thiếu scope bắt buộc đều bị từ chối.
- Repair nhận output trước đó (tối đa 6.000 ký tự) và hướng dẫn theo mã lỗi:
  chẳng hạn sửa `scope` thành object đủ trường hoặc đặt dấu ngoặc kép cho key.
  Không suy đoán offset, sửa nhãn hoặc dùng gold để ép kết quả đạt.
- Probe dùng cùng phần decomposition của verifier, sau đó dừng. Không gọi
  assessment, không kiểm context, không phát ra nhãn support/contradict/NEI.
- CLI chạy 39 ca yêu cầu probe hoàn tất, đúng frozen criteria/model/provenance,
  replay đạt và phiếu review đủ 18 ca gắn với SHA256 của predictions.

Các file chính:
[candidate](../04_factchecker/inference/atomic_verifier.py),
[runner](../research_rag/evaluation/evaluate_atomic_verifier.py),
[contract v2](../research_rag/evaluation/atomic_verifier_contract_v2.json),
[criteria v2](../research_rag/evaluation/atomic_verifier_criteria_v2.json),
[18 claim](../research_rag/evaluation/decomposition_probe_claims_v2.jsonl).
Hai test module runtime và test đóng gói local được cập nhật cùng caller.
Serving và baseline `repair` chưa được tích hợp candidate này.

Bản cuối đạt **75/75 test local** (backend giả lập), gồm dựng lại workspace
từ payload notebook để kiểm file thiếu, replay, gate review, budget và lỗi
checkpoint. Ghi summary có retry tối đa bốn lần riêng cho Windows WinError 5;
lỗi kéo dài vẫn báo thất bại và giữ snapshot cũ. Kaggle/Linux giữ atomic replace.
Xem [validation](decomposition-v2-validation.json) và
[test log](decomposition-v2-tests.log). Đây chưa phải đo năng lực model thật.

## 2. Chạy đúng notebook mới

Dùng [kaggle_decomposition_probe_v2.ipynb](../scripts/kaggle_decomposition_probe_v2.ipynb).
SHA256:
`0ff6d9b7ec29e3870a4655ede92e132ab09e539a441602bce833cd8605e89a37`.

1. Tạo notebook Kaggle mới, import file trên. Bật Internet và GPU T4.
   Notebook có **ba code cell**. Hai dataset workspace/runtime hiện có vẫn được dùng.
2. Chạy **cell 1** để lấy dataset. Không cần Gemini Secret cho thí nghiệm này.
3. Chạy **cell 2** đến khi hiện:

   ```text
   SETUP COMPLETE: atomic-verifier-quotes-v2-20261013; runtime tests, preflight and freeze check passed
   ```

   Freeze check phải báo `freeze_valid: true`, `cases: 18`, `maximum_calls: 36`.
   Cell này dựng venv, cài dependency, áp patch đúng hash, chạy test và preflight.
   Nếu setup lỗi, giữ ZIP được in ra và gửi lại; chưa chạy cell 3.
4. Chạy **cell 3 một lần**. Cell chỉ gọi model cho 18 claim, lưu trace và kết quả.
   Cuối cell có đường dẫn ZIP. Gate trượt vẫn có ZIP để chẩn đoán.
5. Save Version **WITH Output**, tải đúng ZIP ở cuối cell, gửi lại để đối chiếu
   và review decomposition; sau đó tắt GPU. Giữ ZIP gốc nguyên vẹn.

Không chạy lại cell 3 vào cùng output. Nếu cần lượt mới, tạo run mới và giữ
lượt trước làm bằng chứng. Không chạy notebook setup2 39 ca với policy cũ nữa.

## 3. Ngân sách và tiêu chí đã chốt trước inference

| Mục | Probe 18 claim | Lượt 39 ca sau gate probe |
|---|---:|---:|
| Lần gọi tối đa mỗi claim | 2 | 8 |
| Số lần thử mỗi stage | 2 | 2 |
| Output tokens tối đa mỗi call | 1.536 | 1.536 |
| Tổng lần gọi tối đa | 36 | 312 |
| Tổng generated tokens tối đa | 55.296 | 479.232 |
| Deadline mỗi claim | 180 giây | 180 giây |
| Hard timeout cả worker, gồm tải/load model | 2.400 giây | 5.400 giây |

Notebook probe có watchdog ngoài 2.520 giây. Đây là giới hạn, không phải thời
gian/cost dự đoán. Model giữ Qwen2.5-3B-Instruct revision
`aa8e72537993ba99e69dfaafa59ed015b17504d1`, NF4, float16, seed 42,
`do_sample=false`. Ghi số call/token/độ trễ thực tế; USD vẫn null khi backend
không đo. Không đổi backend hoặc fine-tune trong lần sửa này.

Gate tự động probe:

```text
stage decomposition-probe: state=completed, exit_code=0
summary: experiment_completed=true, automated_gate_pass=true
metrics: n=18, valid_decompositions=18, incomplete=0
```

Gate tự động chưa đủ để chạy 39 ca. `human_review=pending` và `overall_pass=false`
được giữ cho đến review; không sửa các trường đó để tạo kết quả pass.
Exit 1 là gate chất lượng trượt; 124 là timeout. Nếu trượt, phân tích ZIP trước
khi đổi prompt/budget; mọi thay đổi cần đóng băng phiên bản tiếp theo.

## 4. Review đủ 18 claim, không chỉ kiểm JSON

Trong `decomposition-probe/`:

- `predictions.jsonl`: raw model output, canonical parts có offset và trace repair.
- `calls.jsonl`: call-start, generation/token và kết thúc từng call.
- `evidence-review.jsonl`: claim, kết quả và các tiêu chí để đọc đối chiếu.
- `semantic-review.json`: phiếu có sẵn 18 hàng, judgments ban đầu null.
- `criteria.json`, `contract.json`, `provenance.json`, `metrics.json`, `summary.json`:
  cấu hình, nguồn, thống kê và trạng thái để replay/audit.

Với từng claim, đọc câu gốc và từng part; kiểm năm tiêu chí:

1. **factual_predicates_not_fragments:** mỗi part chứa một vị ngữ có thể kiểm
   chứng. Một tên model, một số hoặc một điều kiện đứng riêng không phải mệnh đề.
   Các vế AND phải tách; chủ ngữ lược ở vế sau phải được giữ trong scope.
2. **all_requirements_preserved:** không bỏ mất phủ định, số lượng, đơn vị,
   quan hệ nhân quả, baseline hoặc điều kiện. Các tham số của cùng một quan hệ
   cũng phải được giữ và kiểm đủ khi đánh giá bằng chứng về sau.
3. **quantifier_preserved:** mọi/một số/không có đúng phạm vi. Phần trăm không
   đồng nghĩa với lượng từ “một số”; không đổi lượng từ ở vế dùng chung chủ ngữ.
4. **entity_metric_binding_correct:** entity đúng đối tượng, metric đúng thuộc
   tính của part. Việc string xuất hiện trong claim chưa chứng minh liên kết đúng.
5. **time_condition_scope_correct:** giữ đầy đủ mốc thời gian, tập dữ liệu,
   nhóm thử nghiệm và điều kiện, kể cả khi chúng được dùng chung giữa hai vế.

Trong **bản sao làm việc** của output, người review điền `reviewer`,
`reviewer_kind="human"`, `review_completed=true` sau khi đọc đủ, và từng
judgment true/false kèm `notes` cụ thể cho từng claim. Giữ nguyên hai SHA256
trong phiếu. Code yêu cầu cả năm tiêu chí true ở cả 18 ca mới cho đi tiếp.
Một mục sai thì gate không đạt; không điền hàng loạt true để vượt chốt.

Assistant có thể triage/review trước, nhưng không tự nhận là reviewer người.
Đây là 18 câu đã thấy trong bộ development 39 ca; không phải held-out độc lập.
Đánh giá model trên dataset độc lập vẫn cần thực hiện trước nghiệm thu toàn hệ.

## 5. Thứ tự còn lại

**Sau probe và review đạt:** dùng cùng frozen v2 để chạy đủ 39 ca. Entry point
`research_rag.evaluation.evaluate_atomic_verifier` yêu cầu `--probe-dir`
trỏ tới output probe đã review; thiếu file, hash sai, output dở dang, model sai,
replay sai hoặc một judgment chưa đạt đều chặn trước khi load model mới.
Lượt 39 ca phải giữ gate 39/39 nhãn đúng, zero false support, zero runtime failed,
review evidence/giải thích/thiếu thông tin/từng part và numeric tool.
Nếu sửa candidate sau probe, phải đóng băng và chạy lại probe cho candidate mới.

**Sau gate verifier và review cần thiết:** mới tích hợp Fact-checker/controller,
hoàn thiện Reader PDF, sửa Summarizer `heldout_3`, chạy đủ tám ca E2E và review
câu trả lời/trích dẫn. Tài liệu bảo vệ chỉ ghi kết quả thực đo. JSON hợp lệ,
test giả lập pass hay một probe pass đều chưa chứng minh dự án đã hoàn thành.

Việc cần làm ngay: chạy ba cell của notebook probe v2 và gửi ZIP; chưa chạy 39 ca
hoặc toàn hệ trước khi có kết quả và review của probe.
