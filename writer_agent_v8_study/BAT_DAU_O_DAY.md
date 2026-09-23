# Agent Writer v8 — bộ học tập

Đây là snapshot v8 đã đánh giá trên Kaggle, không phải bản đã sửa hết lỗi coverage.
Code, adapter và dữ liệu đánh giá đã được đối chiếu SHA256 với manifest lần chạy v8.

## Thư mục

- 05_writer/: toàn bộ code thực thi, tests và dữ liệu.
- 05_writer/checkpoints/writer_qlora/: adapter đã fine-tune và tokenizer; chưa phải full base model.
- evaluation/v8/: 100 predictions, metrics, 5 case chẩn đoán và cấu hình Kaggle.
- evaluation/v7_ai_review/: nhãn do AI hỗ trợ, không phải independent human review.
- evaluation/history/: metrics các phiên bản trước.
- MANIFEST_SHA256.json: danh sách checksum các file đóng gói.
- VALIDATION.txt: kết quả kiểm tra bản đóng gói.

Giữ tên package 05_writer. Do tên bắt đầu bằng số, dùng importlib.import_module("05_writer.node")
thay vì viết import 05_writer trong Python.

## Bước 1: chạy ví dụ CPU

Mở terminal tại thư mục chứa tài liệu này:

    python -m pip install -r 05_writer/requirements.txt
    python 05_writer/notebooks/00_quick_inference_check.py
    python -m unittest discover -s 05_writer/tests -v

Ví dụ CPU dùng claim giả lập và baseline sao chép; KHÔNG load adapter hay chứng minh chất lượng LLM.
Nó giữ warning=True vì chưa đánh giá ngữ nghĩa/coverage.

## Bước 2: đọc luồng inference

Đọc lần lượt:
1. schemas.py: input claims, report, critique, action và output.
2. node.py: nhận state, trả partial state.
3. loop_controller.py: điều khiển generation → critic → action → kiểm tra lại.
4. inference/report_generator.py và prompts.py: tạo report và hợp đồng JSON.
5. inference/critic.py: kết hợp nhận xét model với kiểm tra exact-copy.
6. inference/action_selector.py và actions/: delete, rewrite, reselect trong pool hiện có.
7. report_schema_validator.py: schema, citation, phạm vi action.
8. inference/backend.py: load model/adapter, chat template và greedy generation.

Không có đường quay về Orchestrator để lấy claims mới.
Hết ngân sách retry thì trả kết quả hiện có và cảnh báo.
Code v8 fallback sao chép claims khi mọi lần generation đều thất bại; không chứng minh coverage.

## Bước 3: đọc training

Đọc generate_training_data.py → validate_labels.py → training_utils.py →
train_writer_qlora.py → config.py. merge_lora_weights.py là tiện ích tùy chọn.

Không cần train lại để học luồng hoặc dùng adapter có sẵn.
QLoRA là fine-tune adapter, không cập nhật toàn bộ trọng số base model.
requirements-train.txt là cấu hình lịch sử; môi trường thực tế của lần inference v8
được ghi trong evaluation/v8/writer_v8_run_manifest.json.
Không giả định cài package mới nhất sẽ tái lập kết quả.

Base model: Qwen/Qwen2.5-1.5B-Instruct.
Revision: 989aa7980e4cf806f80c7fef2b1adb7bc71aa306.
Base model không nằm trong gói này; inference LLM cần tải model và có môi trường phù hợp.

## Bước 4: hiểu metrics

Đọc eval_writer.py cùng evaluation/v8/writer_v8_metrics_100.json.
Schema hợp lệ không đồng nghĩa trả lời đúng.
Exact-copy=1.0 chỉ xác nhận sao chép đúng claim, không xác nhận claim đầy đủ hoặc bài báo đúng.
faithfulness_score=null vì không có nhãn đánh giá độc lập cho report v8.
Không chuyển nhãn của report v7 sang v8 sau khi nội dung thay đổi.
Các file có tên human trong lịch sử có thể chứa nhãn AI; xem review_provenance,
independent_human_review trước khi diễn giải.

## Hiện trạng và lỗi đã biết

- V8: 100 case, schema 100%, exact-copy 100%, 137 sentence entries.
- 28 report rỗng đều thuộc nhóm pool rỗng; 72 case có claims đều có report.
- 31 case có warning; giảm warning không tự động là cải thiện.
- 886732... thiếu hybrid model; 940210... thiếu concat22/s-hier.
- 351bf... không đủ bằng chứng fully supervised; fc9... thiếu giá trị F-score.
  Cả bốn vẫn có warning=False.
- 388495... fallback có thông tin annotation và warning=True, nhưng còn fragment "dataset ".
- 003ae... vẫn trùng câu sau repair: dedup hiện mới nằm ở generator.
- Retry cùng prompt greedy có thể tốn thời gian mà không đổi kết quả.
- SFT hiện tạo report từ claims[:2]; nhãn coverage dựa vào pool không rỗng.
  Đây là hạn chế nhãn, không phải ground truth coverage.

## Bài tập tiếp theo

1. Trace 940210... từ input claims đến final report và chỉ ra claim bị bỏ sót.
2. Viết regression test cho duplicate xuất hiện sau rewrite.
3. Phân biệt sentence support, report coverage và pool sufficiency trong thiết kế đánh giá.
4. Đề xuất dữ liệu có claims quan trọng ở cuối pool, câu hỏi thiếu bằng chứng, và báo cáo đúng nhưng thiếu.
5. Giữ tập test mới độc lập; không train trên các case dùng để báo cáo chất lượng.

Các bài tập trên CHƯA được thực hiện trong snapshot này.
Không xem đây là chứng nhận sẵn sàng production.
