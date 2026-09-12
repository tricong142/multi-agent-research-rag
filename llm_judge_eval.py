"""
03_summarizer/llm_judge_eval.py

CHẠY Ở: LOCAL — không cần GPU, cần OPENAI_API_KEY.
    export OPENAI_API_KEY=sk-...
    python llm_judge_eval.py

TẠI SAO CẦN FILE NÀY (khác với eval_generator_critic.py):
eval_generator_critic.py đo được "evidence có khớp context không"
(Grounding Rate) bằng code thuần - đây là việc CÓ THỂ kiểm tra khách
quan. Nhưng "answer có thực sự trả lời ĐÚNG NỘI DUNG câu hỏi không" là
bài toán KHÔNG có nguồn chân lý tự động - 1 answer có thể grounded hoàn
hảo (evidence khớp 100%) nhưng vẫn trả lời sai trọng tâm câu hỏi (ví dụ
evidence đúng đoạn nhưng answer diễn giải sai ý nghĩa của đoạn đó).

Vì vậy cần 1 LLM MẠNH HƠN VÀ TÁCH BIỆT (GPT-4o) đóng vai giám khảo, so
sánh predicted_answer với expected_answer (do người review chuẩn bị),
chấm điểm theo thang rõ ràng - không thể thay thế bằng
eval_generator_critic.py, và cũng không dùng chính Critic đã fine-tune
để tự chấm (vì Critic đang được đánh giá, không thể vừa đá bóng vừa
thổi còi).

INPUT: file config.EVAL_MANUAL_PATH cần có thêm field "expected_answer"
(câu trả lời mẫu do người review viết, không phải GPT-4o) để so sánh.
"""

import os
import json
import sys
from pathlib import Path

from openai import OpenAI

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402

openai_api_key = os.environ.get("OPENAI_API_KEY")
gemini_api_key = os.environ.get("GEMINI_API_KEY")

if openai_api_key:
    client = OpenAI(api_key=openai_api_key)
    MODEL_NAME = config.OPENAI_MODEL_FOR_DATA_GEN
elif gemini_api_key:
    client = OpenAI(
        api_key=gemini_api_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )
    MODEL_NAME = "gemini-2.0-flash"
else:
    client = OpenAI()
    MODEL_NAME = config.OPENAI_MODEL_FOR_DATA_GEN

JUDGE_SYSTEM_PROMPT = """Bạn là giám khảo chấm điểm hệ thống QA. Bạn sẽ nhận
được: câu hỏi, câu trả lời chuẩn (reference answer) do chuyên gia viết,
và câu trả lời của hệ thống (predicted answer). Chấm điểm predicted
answer theo 3 mức:
- "correct": nội dung đúng, đầy đủ ý chính so với reference answer.
- "partially_correct": đúng một phần, thiếu ý hoặc diễn đạt mơ hồ.
- "incorrect": sai nội dung, hoặc không liên quan tới câu hỏi.

Trả về JSON: {"verdict": "correct"|"partially_correct"|"incorrect", "explanation": "..."}
"""


def judge_answer(question: str, reference_answer: str, predicted_answer: str) -> dict:
    prompt = (
        f"Câu hỏi: {question}\n\n"
        f"Câu trả lời chuẩn (reference): {reference_answer}\n\n"
        f"Câu trả lời của hệ thống (predicted): {predicted_answer}"
    )
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.0,  # judge cần nhất quán, không cần sáng tạo
    )
    return json.loads(response.choices[0].message.content)


def main():
    eval_results_path = config.DATA_DIR / "eval_results.jsonl"
    if not eval_results_path.exists():
        raise FileNotFoundError(
            f"Không tìm thấy {eval_results_path}. Chạy eval_generator_critic.py "
            f"trên Kaggle trước (file đó sinh ra predicted_answer cần chấm ở đây)."
        )

    with open(eval_results_path, "r", encoding="utf-8") as f:
        eval_results = [json.loads(line) for line in f]

    missing_reference = [r for r in eval_results if "expected_answer" not in r]
    if missing_reference:
        print(
            f"CẢNH BÁO: {len(missing_reference)}/{len(eval_results)} mẫu trong "
            f"{config.EVAL_MANUAL_PATH.name} thiếu field 'expected_answer' - "
            f"bổ sung câu trả lời chuẩn do người review viết cho các mẫu này "
            f"trước khi chấm được đầy đủ."
        )

    verdicts = {"correct": 0, "partially_correct": 0, "incorrect": 0}
    judged_results = []

    for r in eval_results:
        if "expected_answer" not in r or not r.get("predicted_answer"):
            continue
        judgment = judge_answer(r["question"], r["expected_answer"], r["predicted_answer"])
        verdicts[judgment["verdict"]] = verdicts.get(judgment["verdict"], 0) + 1
        judged_results.append({**r, "judge_verdict": judgment["verdict"], "judge_explanation": judgment["explanation"]})

    n_judged = sum(verdicts.values())
    print(f"\nTổng số mẫu được chấm: {n_judged}")
    for verdict, count in verdicts.items():
        rate = count / n_judged if n_judged else 0
        print(f"  {verdict:20s}: {count} ({rate:.1%})")

    output_path = config.DATA_DIR / "llm_judge_results.jsonl"
    with open(output_path, "w", encoding="utf-8") as f:
        for r in judged_results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nChi tiết từng mẫu -> {output_path}")


if __name__ == "__main__":
    main()
