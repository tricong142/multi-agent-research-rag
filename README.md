# Agent 4 — Scientific Fact-Checker

Module này kiểm tra một `claim` chỉ dựa trên `context` được truyền vào. Nó gồm ba
bước tách biệt:

1. `FactCheckJudge` sinh `fact_check_label` và giải thích ngắn.
2. `ConfidenceEstimator` tự đánh giá `confidence_score` cho quyết định đó.
3. Nếu score thấp hơn `CONFIDENCE_THRESHOLD`, `ActionRecommender` chỉ đề xuất
   `expand_context`, `other_source`, hoặc `ask_clarify`.

`FactCheckerNode` không gọi Retrieval, không tự route LangGraph và không sửa
`retry_count` của orchestrator. `MAX_INTERNAL_RETRY` chỉ dùng khi model trả JSON
sai schema hoặc backend inference lỗi.

## Cấu trúc

```text
04_factchecker/
├── README.md
├── config.py
├── generate_training_data.py
├── validate_labels.py
├── data/
├── prompts.py
├── train_factchecker_qlora.py
├── merge_lora_weights.py
├── inference/
│   ├── __init__.py
│   ├── judge.py
│   ├── confidence.py
│   └── action_recommender.py
├── node.py
├── eval_factchecker.py
├── notebooks/00_quick_inference_check.py
└── checkpoints/factchecker_qlora/
```

## Dữ liệu SciFact: điều code thực sự giả định

Nguồn là [allenai/scifact trên Hugging Face](https://huggingface.co/datasets/allenai/scifact)
và [repository chính thức của AllenAI](https://github.com/allenai/scifact).

- Config `corpus` có `doc_id`, `title`, và abstract dạng danh sách câu.
- Config `claims` có claim, document evidence, label và chỉ số các câu rationale.
- Annotation có evidence được ánh xạ `SUPPORT -> support` và
  `CONTRADICT -> contradict`.
- Cited document không có evidence annotation cho claim đó trở thành
  `not_enough_info` ở mức claim-document.
- Public test split không có label. Script chỉ tạo supervised data từ `train` và
  `validation`; không báo metric trên test.

Reasoning target không phải chain-of-thought do con người gán nhãn. Nó chỉ lặp lại
rationale sentence đã được annotation để model học giải thích có căn cứ. SciFact
không cung cấp ground truth cho confidence/action, vì vậy code không tạo confidence
label giả và không train action giả.

## Cài đặt

Khuyến nghị Python 3.10+ và một môi trường ảo riêng:

```bash
pip install torch transformers datasets peft accelerate bitsandbytes
```

`bitsandbytes` và CUDA chỉ bắt buộc cho QLoRA. Sinh/validate data và contract test
có thể chạy CPU.

## Pipeline

Chạy từ thư mục `04_factchecker`:

```bash
python generate_training_data.py
python validate_labels.py
python train_factchecker_qlora.py
python merge_lora_weights.py
python eval_factchecker.py
```

### Train trên Kaggle

Upload `scifact_train.jsonl` và `scifact_dev.jsonl` thành Kaggle Dataset, thêm
Dataset đó vào Notebook, bật **GPU** rồi chạy:

```python
!python /kaggle/input/<dataset-chua-code>/train_factchecker_qlora.py
```

Script tự tìm hai file JSONL trong `/kaggle/input`, dùng một GPU, và ghi adapter
cuối cùng vào:

```text
/kaggle/working/factchecker_qlora/final/
```

Nếu có nhiều Dataset chứa file cùng tên, truyền đường dẫn tuyệt đối để tránh chọn
nhầm:

```python
!python /kaggle/input/<dataset-chua-code>/train_factchecker_qlora.py \
  --train-file /kaggle/input/<dataset-data>/scifact_train.jsonl \
  --dev-file /kaggle/input/<dataset-data>/scifact_dev.jsonl
```

Nếu Kaggle Internet tắt, upload base model thành một Kaggle Dataset và thêm:

```python
  --base-model /kaggle/input/<dataset-model>/<thu-muc-model>
```

Không cần merge LoRA ngay trong lượt train. Hãy lưu/download toàn bộ thư mục
`final/` trước; merge chỉ thực hiện sau khi adapter đã được đánh giá.

Để smoke-test trước khi eval toàn bộ:

```bash
python eval_factchecker.py --limit 20
```

Các giá trị QLoRA trong `config.py` là baseline kỹ thuật, không phải tuyên bố đã
tối ưu. Chọn checkpoint bằng macro-F1 trên dev, đồng thời xem confusion matrix,
đặc biệt lỗi `not_enough_info -> support/contradict`.

## Tích hợp LangGraph

```python
from transformers import AutoModelForCausalLM, AutoTokenizer

from inference import (
    ActionRecommender,
    ConfidenceEstimator,
    FactCheckJudge,
    TransformersJSONBackend,
)
from node import FactCheckerNode

tokenizer = AutoTokenizer.from_pretrained("checkpoints/factchecker_merged")
model = AutoModelForCausalLM.from_pretrained(
    "checkpoints/factchecker_merged", device_map="auto", torch_dtype="auto"
).eval()
backend = TransformersJSONBackend(model, tokenizer)

fact_checker_node = FactCheckerNode(
    FactCheckJudge(backend),
    ConfidenceEstimator(backend),
    ActionRecommender(backend),
)
```

Node mặc định đọc claim theo thứ tự `claim`, `answer`, `final_answer`; context theo
`context`, `evidence_context`, `retrieved_context`. Nên truyền key tường minh trong
constructor nếu `AgentState` của graph dùng tên khác.

State update trả về luôn có các field chính:

```json
{
  "fact_check_label": "support",
  "confidence_score": 0.91,
  "recommended_action": null,
  "fact_check_reasoning": "...",
  "confidence_reasoning": "...",
  "action_reasoning": null,
  "fact_check_attempts": [],
  "fact_check_status": "ok"
}
```

Khi confidence thấp, `recommended_action` có giá trị nhưng chưa được thực thi.
Conditional edge ở graph ngoài mới được phép đọc field này và quyết định route.

## Calibration confidence

`confidence_score` là self-assessment của LLM, không mặc nhiên là xác suất đúng.
Trước production cần tạo calibration set có nhãn đúng/sai, rồi đo reliability
diagram/Brier score hoặc ECE và chọn `CONFIDENCE_THRESHOLD` theo cost của lỗi. Nếu
chưa calibration, coi score là tín hiệu routing thử nghiệm, không phải cam kết SLA.

## Safety và quan sát lỗi

- Label/action ngoài vocabulary, score ngoài `[0, 1]`, reasoning rỗng và JSON lỗi
  đều bị từ chối.
- Mọi lần retry được ghi trong `fact_check_attempts`.
- Nếu judge hỏng sau toàn bộ retry, node trả `not_enough_info`, confidence `0.0`
  và đề xuất `expand_context`; đây là fallback bảo thủ, không phải model prediction.
- `fact_check_raw` giữ output đã parse để audit. Không log context nhạy cảm ở tầng
  production nếu chính sách dữ liệu không cho phép.

## Những gì đã và chưa được kiểm chứng trong repo này

Đã có thể kiểm tra local: compile Python, schema contract, low-confidence branch và
node state update bằng backend giả. Chưa thể khẳng định accuracy/macro-F1, độ
calibration, chi phí hay latency trước khi thực sự tải SciFact, train checkpoint và
chạy `eval_factchecker.py` trên phần cứng mục tiêu.
