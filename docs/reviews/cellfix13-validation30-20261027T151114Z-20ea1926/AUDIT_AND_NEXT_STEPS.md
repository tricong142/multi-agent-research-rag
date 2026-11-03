# Audit Cellfix13 Validation30 — 2026-10-28

**Validation30 chưa đạt. Giữ candidate hiện tại làm baseline thất bại; chưa chuyển sang acceptance tích hợp Reader/Summarizer hoặc serving.**

Run `20261027T151114Z-20ea1926`, khác run full39 `20261027T113721Z-18c80dae` đã audit trước đó. Đã kiểm chính review và predictions của run mới; không chuyển chữ ký giữa hai run.

## Kết quả và provenance

| Hạng mục | Đã kiểm |
|---|---|
| Manifest/output | 151 file, đủ, không trùng, size/SHA256 khớp |
| Input/payload | 131 input trùng release Cellfix13; source/prompt/criteria/model/budget/gate không bị đổi |
| Regression và validate-only | 385 regression; cả bốn validate-only đạt |
| Smoke / probe / full39 | 12/12 nhãn; 18/18 decomposition; 39/39 nhãn, false support=0, runtime=0 |
| Admission human | Probe 18 ca/90 tiêu chí và full39 39 ca/195 tiêu chí, reviewer Trí Công, đủ notes, đúng hash; gate frozen chấp nhận |
| Validation30 | **10/30 đúng nhãn (33,3%)**, 16 ca hoàn tất nhưng sai nhãn, 4 ca incomplete |
| False support | **0/20 ca gold không phải support** trong bộ này; không phải bảo đảm an toàn ngoài bộ30 |
| Support | Chỉ nhận đúng **3/10** gold support; support recall 30% |
| Contradict | **0/10** gold contradict được nhận đúng; chín NEI và một incomplete |
| Prediction distribution | Support 3, contradict 2, NEI 21, incomplete 4 |
| Validation calls | 64 starts/64 finishes, nhưng chỉ 62 generation events |
| Token usage | 6.942 generated / 90.917 prompt đã đo; thiếu usage của hai call timeout nên chỉ là lower bound |
| Gate tự động | Failed: labels, runtime, group completeness, measured-token trace và structured-decoding trace |
| Human validation review | Pending; không thể ký human để cứu automated gate đang trượt |

Tái tính khớp metrics/classification bằng source frozen. Đã replay stored outputs và các raw/parsed/normalized traces của bốn stage. Hai call timeout không có raw generation nên không thể replay token usage của chúng. Tổng pipeline có 195 call starts/finishes, 193 generation events. Kiểm hash chứng minh consistency nội bộ artifact, không phải attestation máy Colab.

## Các nguyên nhân đã có bằng chứng

1. **Deadline không được thực thi như giới hạn cứng.** Ca 009 mất 2.722,166 giây (~45 phút 22 giây), trong budget 180 giây; riêng call assessment mất 2.716,593 giây dù trace chỉ còn 174,427 giây. Ca 011 mất 187,761 giây. Có `cooperative_deadline=true` nhưng không bảo đảm wall-clock bound. `generation_options()` chỉ kiểm thời gian tại các điểm trước/sau dựng schema và dùng stopping criteria; cần đo riêng schema build, token filtering và generation để định vị hot spot. Chưa có profiler trace để kết luận bước cụ thể gây 45 phút.
2. **Decoder/validator không đồng bộ về lượng từ.** Ca 015: decoder enum `all` ở cả hai alternatives; validator chấp nhận part accuracy `atomic`, part each-prediction latency `all`. Output có quantifier đúng bị decoder loại. Đã kiểm bằng hàm frozen và một counterfactual, không chạy model hoặc thay prediction. Bằng chứng: `QUANTIFIER_SCHEMA_DIAGNOSIS.json`.
3. **Quantity contract quá hẹp.** Ca 001–003 đọc số 4 của model ID E-4 thành `4 achieved`/`4 used`. Ca 028–029 coi section IDs 0-1 là measurement, kể cả unit `were`. Ca 010 có `4,340 are`; ca 016–017 chỉ biểu diễn `120 half`/`120 two`, chưa giữ đủ count + duration + đối tượng. Ca 022 có unit `name`/`Turkish` thay object đầy đủ. Đây là lỗi contract có thể tái hiện trực tiếp từ normalized plans.
4. **Binding quá hẹp ở một số chỗ và sai vai trò ở chỗ khác.** WMT shared-head list, CALLHOME apposition, proposed/our model và PDTB sections qua câu bị coi thiếu target. Ca 025 còn chọn comparator `wav2letter Transformer` làm entity của claim nói proposed model, đảo vai trò so sánh và cho nhãn sai.
5. **Unknown/polarity/identity vẫn lọt lỗi.** Ca 021 nguồn không nói language nhưng ledger cho `written in French=false`, tạo false refutation. Ca 019 đúng nhãn nhưng member/coverage là clause fragment `Dataset BIBREF15 is a small data set consisting`. Guard member hiện tập trung vào unknown nên known outcomes vẫn có đường lọt fragment. Ca 008 bỏ explicit `without requiring ... modified training objective`; một số ca bỏ subset counterevidence đang có.
6. **Decomposition và missing-information chưa đủ tổng quát.** Ca 010 chấp nhận fragment/count làm entity; ca 028 tách AND nối hai mục đích thành part thiếu factual predicate. Nhiều missing messages nói thiếu binding/measurement dù nguồn đã có dữ kiện quyết định. Ca 027 cần nêu rõ thiếu experimental/causal certainty, không chỉ generic scoped evidence.

`within_measured_token_budget=false` **không chứng minh đã vượt token cap**: tổng token được log nhỏ hơn cap, nhưng mất hai generation events. Giữ trạng thái failed vì không đủ trace để chứng nhận usage; không điền số 0 hoặc nới gate để qua.

## Thứ tự thực hiện tiếp theo

1. **Bảo toàn baseline này.** ZIP nguyên bản nằm trong `research-runs/audit-cellfix13-validation30-20261027T151114Z-20ea1926/original-output.zip`; source, predictions, calls, review human và annotation lock được giữ nguyên. Không sửa gold/review/metrics để nâng điểm.
2. **Candidate mới trước khi tốn GPU thêm.** Ưu tiên deadline + usage logging; đồng bộ lượng từ theo từng part giữa validator/decoder; phân biệt model/section ID với measurement và biểu diễn quantity/object/duration đủ quan hệ. Sau đó xử lý subject/comparator, reference/alias có chứng cứ, member identity cho cả known/unknown, và absence-property phải unknown thay vì false. Giữ model/revision/budget/gate để so sánh; không tăng budget nhằm che timeout.
3. **Thêm regression từ trace này và câu mới.** Có cặp support/contradict/NEI, model IDs khác, section ranges khác, duration/count khác, shared heads, coreference, comparator đảo vai, unreported-property vs explicit denial, AND predicates vs AND noun phrases. Kiểm token filter thật và repair trong ngân sách, không chỉ validator hoặc handcrafted schema paths.
4. **Chuẩn bị holdout mới trước lần đánh giá độc lập tiếp theo.** Bộ30 v1 đã lộ kết quả. Nếu dùng findings/traces để sửa candidate, chuyển nó thành development regression; giữ nguyên 10/30 là kết quả independent đầu tiên của Cellfix13. Bộ mới phải khác claim/context và disjoint theo paper với bộ dùng để sửa, có gold/evidence/notes được human review và khóa version/hash trước inference. Không đổi tên bộ30 cũ rồi coi là independent mới.
5. **Đánh giá candidate mới:** regression + validate-only → smoke → probe18 + review mới → full39 + evidence review mới → development validation30-v1 để đo sửa lỗi → holdout mới đã khóa + evidence review. Chỉ khi acceptance thực sự đạt mới chốt bản verifier để tích hợp Reader/Summarizer và chạy E2E. Human review không biến một automated failure thành pass.

Hiện có thể mở `HUMAN_REVIEW_WITH_AI_NOTES.html` để đọc 30 ca và xác nhận/chỉnh findings. Form giữ 150 checkbox trống và 30 notes trống. Đây là hỗ trợ phân loại lỗi; không cần tích tất cả thành true để được phép phát triển candidate mới.

## Hash quan trọng

- ZIP: `95e391e1e41b505c4211d16fe3e9cd79d98f9d9c611d95eee30c9b4126c1dd51`
- Criteria: `fc4d4a8f7baaf88886cbd3047819125752867e7cdb2f2a8fb850f4be293abb4c`
- Validation predictions: `d9b77f1687e1b6e201a53d9b723c0e91ecc8618077ab87055603e09272e9bf7f`
- Full39 predictions của chính run này: `7de46b2a0efe9931d46bb17d3a4105bd7ef20c093ce4df5fcf8f8deb4f4d10fb`

Machine audit: `docs/atomic-verifier-cellfix13-validation30-audit-20261027T151114Z-20ea1926.json`.
Chi tiết từng ca: `EVIDENCE_REVIEW_30.md`, `AI_DIAGNOSTIC_REVIEW.json`.
Không sửa inference source/Colab notebook/release trong lượt audit này; không chạy inference mới.

## Bản Kaggle theo yêu cầu chuyển môi trường trước đó

Đã tạo `scripts/kaggle_atomic_verifier_cellfix13.ipynb`, bảy code cells,
payload 131 input giữ nguyên. Bỏ Colab upload/download, đọc review bằng explicit
Kaggle path và xuất link file trong `/kaggle/working`; runtime/cache ở `/tmp`.
Cells 6/7 vẫn mặc định tắt. Đây không phải bản sửa các lỗi Validation30 ở trên.
Chỉ có compile/payload/I/O checks offline; chưa chạy inference hoặc kiểm link
download bằng trình duyệt Kaggle. Không chạy lặp bộ validation đã lộ để chọn
kết quả thuận lợi.
