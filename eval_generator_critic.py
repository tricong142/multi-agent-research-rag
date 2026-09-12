"""
03_summarizer/eval_generator_critic.py

CHẠY Ở: KAGGLE NOTEBOOK (cần GPU để load 2 model đã merge).
    python eval_generator_critic.py

Đo 2 chỉ số quyết định model có "dùng được" chưa, dùng ngưỡng đã khai
báo trong config.py (MIN_GROUNDING_RATE, MIN_CRITIC_PRECISION):

  - Grounding Rate (Generator): % câu trả lời có evidence_span thực sự
    khớp verbatim/gần verbatim trong context (kiểm tra bằng CODE, dùng
    lại đúng hàm is_verbatim_match từ validate_evidence_span.py - không
    viết lại logic lần 2 để tránh lệch tiêu chuẩn).

  - Critique Precision (Critic): trong số các lần Critic nói
    "is_supported=false", bao nhiêu lần điều đó ĐÚNG theo nhãn thật của
    tập eval_manual.jsonl (viết tay, KHÔNG phải do GPT-4o sinh - lý do
    đã giải thích ở Retrieval Agent: tránh đo trúng "khả năng bắt chước
    văn phong GPT-4o" thay vì khả năng tổng quát hoá thật).

QUAN TRỌNG: eval_manual.jsonl PHẢI được người review tự viết tay
(khuyến nghị 50-100 mẫu), KHÔNG dùng lại summarizer_sft_validated.jsonl
(đó là tập train/eval nội bộ lúc SFT, không đại diện đủ cho câu hỏi
thật của người dùng cuối).
"""

import json
import sys
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402
from node import SummarizerNode  # noqa: E402
from validate_evidence_span import is_verbatim_match  # noqa: E402


def load_merged_model(model_dir: Path):
    if not model_dir.exists():
        raise FileNotFoundError(
            f"Không tìm thấy model đã merge tại {model_dir}. Chạy merge_lora_weights.py trước."
        )
    tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
    model = AutoModelForCausalLM.from_pretrained(
        str(model_dir), torch_dtype=torch.bfloat16, device_map="auto"
    )
    model.eval()
    return model, tokenizer


def main():
    if not config.EVAL_MANUAL_PATH.exists():
        raise FileNotFoundError(
            f"Chưa có {config.EVAL_MANUAL_PATH}. Đây PHẢI là tập viết tay, format mỗi dòng:\n"
            '{"context": "...", "question": "...", "expected_is_answerable": true/false}\n'
            f"Tạo file này (khuyến nghị 50-100 mẫu) trước khi eval."
        )

    print("Đang tải Generator và Critic đã merge...")
    generator_model, generator_tokenizer = load_merged_model(config.GENERATOR_MERGED_DIR)
    critic_model, critic_tokenizer = load_merged_model(config.CRITIC_MERGED_DIR)

    node = SummarizerNode(generator_model, generator_tokenizer, critic_model, critic_tokenizer)

    with open(config.EVAL_MANUAL_PATH, "r", encoding="utf-8") as f:
        eval_samples = [json.loads(line) for line in f]

    n_total = len(eval_samples)
    n_grounded = 0
    n_predicted_unsupported = 0
    n_predicted_unsupported_correct = 0
    results = []

    for sample in eval_samples:
        result = node.run(context=sample["context"], question=sample["question"])

        # --- Grounding Rate: kiểm tra evidence có khớp thật trong context ---
        is_grounded = True
        if result.evidence_spans:
            for span in result.evidence_spans:
                valid, _ = is_verbatim_match(span, sample["context"])
                if not valid:
                    is_grounded = False
                    break
        elif sample["expected_is_answerable"]:
            # Câu hỏi đáng lẽ trả lời được nhưng model không đưa evidence nào -> không grounded
            is_grounded = False
        n_grounded += int(is_grounded)

        # --- Critique Precision: model cuối cùng có is_supported=False không,
        # và điều đó có khớp thực tế (câu hỏi có thực sự không trả lời được) ---
        final_trial = result.reasoning_trace[-1] if result.reasoning_trace else None
        if final_trial and not final_trial.is_supported:
            n_predicted_unsupported += 1
            if not sample["expected_is_answerable"]:
                n_predicted_unsupported_correct += 1

        results.append({
            **sample,
            "predicted_answer": result.answer,
            "predicted_evidence": result.evidence_spans,
            "is_supported_final": result.is_supported,
            "confidence": result.confidence,
            "n_internal_retries": len(result.reasoning_trace),
            "is_grounded": is_grounded,
        })

    grounding_rate = n_grounded / n_total if n_total else 0
    critique_precision = (
        n_predicted_unsupported_correct / n_predicted_unsupported
        if n_predicted_unsupported else float("nan")
    )

    print(f"\nTổng số mẫu eval: {n_total}")
    print(f"Grounding Rate      : {grounding_rate:.1%}  (ngưỡng tối thiểu: {config.MIN_GROUNDING_RATE:.0%})")
    print(f"Critique Precision  : {critique_precision:.1%}  (trên {n_predicted_unsupported} lần "
          f"critic báo 'không hỗ trợ', ngưỡng tối thiểu: {config.MIN_CRITIC_PRECISION:.0%})")

    if grounding_rate < config.MIN_GROUNDING_RATE:
        print("\n  CẢNH BÁO: Grounding Rate dưới ngưỡng - Generator có thể vẫn sinh "
              "evidence không khớp verbatim. Xem lại data train hoặc tăng epoch.")
    if critique_precision < config.MIN_CRITIC_PRECISION:
        print("\n  CẢNH BÁO: Critique Precision dưới ngưỡng - Critic bỏ lọt hoặc báo "
              "sai nhiều. Xem lại Case B (partial_grounding) trong data train.")

    output_path = config.DATA_DIR / "eval_results.jsonl"
    with open(output_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nChi tiết từng mẫu -> {output_path}")


if __name__ == "__main__":
    main()
