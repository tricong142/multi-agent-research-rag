# Cellfix16 — development candidate

Candidate cô lập tại `research-runs/atomic-cellfix16-candidate/workspace`, được build từ manifest Cellfix15 và kiểm tra hash của release cha. Không chỉnh sửa gold, metrics hoặc output của run Cellfix15.

## Thay đổi

1. Dùng chung explicit witness giữa decoder, validator và quyết định assessment: tokenized/detokenized BLEU; yêu cầu modified training objective; better/worse với đúng comparator và condition; vai trò training/test/development/validation của sections. Không lấy một phủ định của nhãn A để tự suy ra nhãn B. Bằng chứng xung đột không ép thành quyết định.
2. Dùng chung `subject_issue` cho lựa chọn entity của decomposition và validator. Hỗ trợ lượng từ hậu vị và entity có lượng từ ở đầu, giữ count modifier. Các lựa chọn entity được gắn theo quote. AND nối danh sách count không bắt buộc tách thành fragment; mệnh đề có predicate độc lập vẫn tách.
3. BIBREF/TABREF/FIGREF kết thúc unit. Giữ nguyên full unit và source quote trong ledger. Các mẫu đối chiếu annotation/tweet có modifier cần kiểm tra bằng chứng cho modifier trước khi chấp nhận số. Quantity tổng và quantity subset trong quan hệ `of which` có vai trò riêng, không được gắn chéo. “not good enough” là đánh giá chất lượng, không tự phủ định giá trị đã báo cáo. Mẫu “whether actions/events/items are PROPERTY or not” không phủ định count của một object khác; các phủ định liên quan vẫn chịu guard hiện có.
4. Coverage chỉ chọn tên có trong observation candidates. Collective witness “each paired with…” buộc cùng member/quote ở coverage và observation. Quan hệ count tổng–tập con dạng `N objects, M of which are PROPERTY`, với M<N và đúng scope, tạo ledger phản chứng hữu hạn bằng Decimal. Một unknown retry không được vứt witness quyết định này.

`scripts/atomic_cellfix16_rules.py` là nguồn cho module runtime mới. `scripts/build_atomic_cellfix16_candidate.py` ghi lại mọi thay đổi nguồn, contract, policy và hash vào candidate manifest. Tests dùng trace Cellfix15 thực nhận cùng ca đối chứng; runtime không đọc ID/gold của fixture.

Một assertion kế thừa ở test Cellfix14 được đổi từ đếm đúng hai nhánh schema sang kiểm tra tập quantifier, vì schema mới có nhiều nhánh quote/entity. Vẫn giữ kiểm tra token path và normalization ngay trong test đó.

Workflow Cellfix16 nhận bản sửa tương thích metrics producer/admission đã audit ở Cellfix15: chỉ bỏ diagnostic `usage_complete` khỏi bản replay khi producer không ghi field này và replay xác nhận true. Các kiểm tra label, call/token/deadline, provenance và human review vẫn thực hiện.

## Kiểm tra và cách chạy

Các báo cáo kiểm tra được lưu riêng:

- `docs/atomic-verifier-cellfix16-validation.json`: regression và validate-only.
- `docs/atomic-verifier-cellfix16-tokenizer-check.json`: token filter Qwen đã pin, không tải weights.
- `docs/atomic-verifier-cellfix16-packaging-validation.json`: notebook, binding và payload giải nén.
- `docs/atomic-verifier-cellfix16-kaggle-validation.json`: kiểm tra bản port Kaggle.
- `docs/atomic-verifier-cellfix16-release.json`: manifest bản phát hành, chỉ tạo sau khi các kiểm tra đạt.

Regression cuối đã đạt **422/422**, trên criteria SHA256 `c025247428698d892e549fb12ad22e19561020b034a2a2276c9dfcaf0cbdc966`. Validate-only xác nhận cấu hình smoke12/probe18/full39; đây không phải số ca inference pass.

Bản release đã đóng băng sau khi đạt **139/139 đường token Qwen**, **38/38 packaging tests** và validate-only từ đúng payload giải nén cho cả smoke/probe/full39/development30. Payload có 144 inputs; release catalog khóa 23 file. Hash release cha Cellfix14/15 đã được kiểm tra lại và giữ nguyên.

Kaggle notebook SHA256: `05aa83b16c4c93b917d61a7c94cc0d242adc5f3e0f28c68f159c3546599be34b`.

Notebook đích: `scripts/kaggle_atomic_verifier_cellfix16.ipynb`. Dùng runtime mới; chạy cells 1–5, review probe mới rồi mới bật Full39 ở cell 6. Sau khi Full39 mới pass và được review, đặt đường dẫn review tương ứng ở cell 7 và bật `RUN_VALIDATION30`. Không dùng lại semantic review của Cellfix15 vì hash source/predictions đã đổi. Cells 6/7 mặc định tắt.

## Giới hạn

Các guard là grammar hữu hạn cho những quan hệ đã nêu; không phải bộ suy luận ngữ nghĩa tổng quát. Coverage được thu hẹp bằng observation candidates và ép đồng bộ cho witness đã nhận diện; mọi ledger còn lại vẫn cần validator kiểm tra equality/duplicate/closure.

Tests offline và record sửa trong bộ nhớ không chứng minh model tự sinh đáp án đúng. Chưa có inference GPU, Full39 mới hoặc score development30 mới. Không cam kết 30/30 trước khi có artifact từ run mới. Development30 đã dùng để sửa; cần holdout khác paper để đo tổng quát hóa. Candidate chưa được tích hợp serving.
