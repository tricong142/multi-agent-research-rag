# Cellfix16 holdout30-v2 — bàn giao chuẩn bị offline

Đã tạo packet tại `docs/validation/atomic-cellfix16-holdout30-v2/`: **30 ca / 10 paper**, gồm 10 SUPPORT, 10 CONTRADICT và 10 NEI. Nhãn trong JSON dùng contract `support`, `contradict`, `not_enough_info`. Đây là **gold đề xuất bởi AI, chờ human adjudication**, chưa phải kết quả kiểm định hoặc chứng nhận serving.

## Nguồn và phạm vi độc lập

Toàn bộ nguồn lấy từ QASPER test đã cache local, revision `06806e4608976fc2fac0a090ac425d5b2b29caf4`; không tải bài mới, gọi API hoặc chạy candidate. “Paper mới” nghĩa là khác paper đã biết trong dữ liệu phát triển/đánh giá, không có nghĩa mới xuất bản năm 2026. Attribution và license CC-BY-4.0 theo manifest QASPER local được giữ trong packet.

Đã rà **468 file**, lập registry **4.882 paper ID bị loại** từ dữ liệu train/eval, fixtures/rules, các bộ validation trước, qrels dev, corpus cũ và trace QASPER đã lưu. Trong 169 paper test-candidate có 27 paper còn đủ điều kiện theo các phép kiểm này. Chọn 10 paper để phủ các loại quan hệ trước khi có kết quả model; không chọn theo score candidate.

| Paper ID | Đoạn QASPER | Phạm vi ba ca |
| --- | --- | --- |
| 1804.03839 | 12 | Phân loại occupation, tổng category, số annotator chưa biết |
| 1607.03895 | 6 | Khoảng năm, nhóm nam/nữ, tổng số transcript chưa biết |
| 1905.01347 | 10 | Accuracy của DEX trên APPA-REAL, sai giá trị, recall chưa biết |
| 1802.06053 | 10 | Mboshi5K/test-set role, phủ định, duration khác utterance count |
| 1808.09180 | 27 | LAS/Hindi/Urdu, ngoại lệ của lượng từ all, parameter count |
| 1901.03253 | 21 | Gắn headline count vào đúng satirical/serious corpus, token count |
| 1807.03674 | 3 | Raw Text/physician, phủ định count, subset theo năm |
| 1806.03369 | 11 | Loại hashtag, giữ/loại, causal accuracy gain chưa được đo |
| 1804.00982 | 10 | Split và non-overlap entities, some/none, số ngôn ngữ |
| 2003.12139 | 24 | Active learning/CNN, phủ định theo population, accuracy chưa biết |

**Không trùng dev30 hoặc paper ID đã biết trong registry; zero lexical flags** theo exact normalized text, Jaccard >=0,8 với ít nhất 6 token, hoặc một cụm 8 token liên tiếp chung. Không dùng model/decoder/validator của candidate để thử các ca rồi điều chỉnh lựa chọn. Tests chỉ kiểm integrity và quy trình annotation.

Giới hạn cần giữ khi diễn giải: Summarizer có document ID không đáng tin nên chưa chứng minh được loại trừ paper-level hoàn toàn ngoài registry; kiểm lexical không chứng minh không trùng nghĩa. Corpus QASPER đã được index từ trước và không bảo đảm chưa nằm trong pretraining. Đây là pilot kiểm **claim theo paragraph được cung cấp**, không phải kiểm toàn bài hoặc E2E retrieval. Ba ca cùng paper có tương quan; cần báo kết quả theo 10 paper, không coi là 30 tài liệu độc lập.

## File sử dụng

- `cases.jsonl`: nhãn đề xuất, rationale, thông tin thiếu, evidence có offset và source identity.
- `sources.jsonl`: 10 paragraph nguyên vẹn để đối chiếu; exactness theo QASPER cache, bao gồm BIBREF, không phải PDF vừa tải.
- `inputs.jsonl`: chỉ có `id/claim/context`.
- `criteria.json`: protocol khóa trước inference: 30/30, zero false support/runtime failure, đủ từng paper và trace/budget.
- `exposure-registry.json`, `overlap-report.json`, `source-provenance.json`: phạm vi và hash kiểm trùng.
- `REVIEW.html`, `annotation-review.template.json`: review trực tiếp, không tick sẵn hoặc tự ký human review.
- `review_gate.py`, `annotation_gate_core.py`: kiểm integrity và human annotation admission offline, không cần import model/repo.
- `manifest.json`, `packet-lock.json`: SHA256 của payload và toàn bộ các file chuẩn bị.
- `blind-inputs.zip`: chỉ inputs và model settings, dùng cho phía inference.
- `review-packet.zip`: toàn bộ packet có gold đề xuất, dành cho người đánh giá; không đưa ZIP này vào model prompt.

Runner chỉ truyền `claim/context` vào model; `id` dành cho trace. Không cung cấp nhãn, rationale, phân bố nhãn hoặc sibling-case labels trong prompt.

## Kiểm và review

Từ root repo:

```powershell
.venv\Scripts\python.exe docs/validation/atomic-cellfix16-holdout30-v2/review_gate.py --packet docs/validation/atomic-cellfix16-holdout30-v2
```

Mở `REVIEW.html`, đọc đủ context và xét từng nhãn/span trước khi xem kết quả candidate. Với NEI, evidence là thông tin liên quan, không được coi là bằng chứng rằng toàn paper không có câu trả lời. Xuất JSON bằng form rồi chạy, thay hai đường dẫn output/review bằng file thực tế:

```powershell
.venv\Scripts\python.exe docs/validation/atomic-cellfix16-holdout30-v2/review_gate.py --packet docs/validation/atomic-cellfix16-holdout30-v2 --review PATH/annotation-review.json --lock PATH/holdout-annotation-admission.json
```

Template chưa điền bị từ chối. Nếu người review sửa nhãn hoặc context, tạo packet version mới trước inference; không sửa đè v2. Admission chỉ xác nhận annotation, không cấp promotion hoặc tự chạy holdout. Human signature là self-attestation, không phải chữ ký mật mã.

Cell7 hiện vẫn khóa vào dev30; không thay binding/metrics của cell7 bằng packet mới. Sau các gate của **đúng Cellfix16**, dùng một holdout job riêng với `blind-inputs.zip` và chấm theo `cases.jsonl` đã được human admit. Bộ này chưa kèm một runner inference mới; phần chuẩn bị hiện tại gồm dữ liệu, protocol, archive và admission tool. Kết quả holdout dùng để sửa code thì phải chuyển bộ thành development, rồi lấy holdout mới; giữ mọi outcome, kể cả lỗi và technical rerun.

## Hash và kiểm tra đã chạy

- Candidate criteria: `c025247428698d892e549fb12ad22e19561020b034a2a2276c9dfcaf0cbdc966`.
- Manifest: `9821fcae09302b65d9e393a82e7767e1b1f1466eca4c4d2e5bfaf53d915bfad9`.
- Packet lock: `d6c3399a079dfc65d8b450861d77657dd7655525c8a4d0226388f490216d7d63`.
- Review ZIP: `a253ae17250d10012e893d7a30c6a27752e223d934dddae44bf41fa597345431`.
- Blind ZIP: `05aa9e0605c9e5512132ddf14bd4384f376f5f8d045d743bf330a7184e737dce`.

**22/22 integrity/admission tests đạt**, kiểm source snapshots với corpus thật, exact spans, paper exclusion, blind archive, hash tamper, cấm overwrite và standalone gate. Các approval giả lập chỉ tồn tại trong bộ nhớ test, không tạo human approval cho packet. Không có inference, independent-validation score hoặc serving promotion mới.

Builder: `scripts/prepare_atomic_holdout_v2.py`; tests: `scripts/test_atomic_holdout_v2.py` và `scripts/test_atomic_validation_packet.py`. Report: `docs/atomic-verifier-cellfix16-holdout-v2-preparation.json`; log: `research-runs/holdout-v2-tests.log`.
