"""
03_summarizer/validate_evidence_span.py

CHẠY Ở: LOCAL — không cần GPU, không cần API key (thuần string matching).
    python validate_evidence_span.py

BẮT BUỘC chạy sau generate_training_data.py, KHÔNG ĐƯỢC SKIP.

TẠI SAO BẮT BUỘC (lặp lại đúng lý do đã nêu, nhấn mạnh vì đây là lỗi
dễ mắc nhất khi làm grounded QA):
GPT-4o khi sinh evidence_span có thể "diễn đạt lại gần đúng" thay vì
copy chính xác nguyên văn từ context, dù prompt đã yêu cầu verbatim.
Nếu để lọt các mẫu này vào tập train, Generator sẽ học SAI thói quen -
học cách viết ra 1 câu "nghe giống" evidence thay vì thực sự TRÍCH DẪN
CHÍNH XÁC câu có trong context. Đây là lỗi phá vỡ đúng mục đích cốt lõi
mà node Summarizer được thiết kế ra (chống hallucination).

CÁCH KIỂM TRA: 2 tầng, từ chặt tới lỏng dần
  1. Exact substring match (case-insensitive, chuẩn hoá khoảng trắng)
     -> nếu khớp, chấp nhận ngay, tin cậy cao nhất.
  2. Fuzzy match (SequenceMatcher ratio >= 0.9) -> chấp nhận nếu gần
     khớp tuyệt đối (thường do khác biệt dấu câu/khoảng trắng nhỏ,
     KHÔNG chấp nhận diễn đạt lại nội dung).
  Dưới 0.9 -> loại, vì ở mức đó thường là GPT-4o đã "paraphrase" chứ
  không còn trích dẫn nguyên văn.
"""

import json
import re
from difflib import SequenceMatcher

import config


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def is_verbatim_match(evidence: str, context: str, fuzzy_threshold: float = 0.9) -> tuple[bool, str]:
    """Trả về (is_valid, method) - method để biết mẫu được chấp nhận qua exact hay fuzzy."""
    norm_evidence = normalize_whitespace(evidence).lower()
    norm_context = normalize_whitespace(context).lower()

    if norm_evidence in norm_context:
        return True, "exact"

    # Fuzzy: tìm cửa sổ trượt trong context có độ dài tương đương evidence,
    # so khớp gần đúng - bắt các trường hợp lệch dấu câu/khoảng trắng nhỏ
    window_size = len(norm_evidence)
    best_ratio = 0.0
    step = max(1, window_size // 4)  # trượt cửa sổ, không cần kiểm tra từng ký tự để tiết kiệm thời gian
    for start in range(0, max(1, len(norm_context) - window_size), step):
        window = norm_context[start : start + window_size]
        ratio = SequenceMatcher(None, norm_evidence, window).ratio()
        best_ratio = max(best_ratio, ratio)
        if best_ratio >= fuzzy_threshold:
            break

    if best_ratio >= fuzzy_threshold:
        return True, f"fuzzy({best_ratio:.2f})"
    return False, f"no_match(best_ratio={best_ratio:.2f})"


def main():
    if not config.RAW_DATA_PATH.exists():
        raise FileNotFoundError(
            f"Không tìm thấy {config.RAW_DATA_PATH}. Chạy generate_training_data.py trước."
        )

    with open(config.RAW_DATA_PATH, "r", encoding="utf-8") as f:
        samples = [json.loads(line) for line in f]

    accepted, rejected = [], []
    stats_by_case = {}

    for sample in samples:
        case_type = sample["case_type"]
        stats_by_case.setdefault(case_type, {"total": 0, "accepted": 0})
        stats_by_case[case_type]["total"] += 1

        # Case C (unanswerable) không có evidence_span thật để kiểm tra -
        # bản chất mục đích của case này là "không có evidence", nên luôn
        # accept miễn context và question thuộc 2 nguồn khác nhau (đã đảm bảo
        # từ lúc sinh ở generate_training_data.py).
        if case_type == "unanswerable":
            accepted.append(sample)
            stats_by_case[case_type]["accepted"] += 1
            continue

        evidence = sample.get("target_evidence_span")
        context = sample.get("context", "")
        if not evidence:
            rejected.append({**sample, "_reject_reason": "empty_evidence_span"})
            continue

        is_valid, method = is_verbatim_match(evidence, context)
        if is_valid:
            sample["_validation_method"] = method
            accepted.append(sample)
            stats_by_case[case_type]["accepted"] += 1
        else:
            rejected.append({**sample, "_reject_reason": method})

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(config.VALIDATED_DATA_PATH, "w", encoding="utf-8") as f:
        for s in accepted:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    with open(config.REJECTED_DATA_PATH, "w", encoding="utf-8") as f:
        for s in rejected:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    print(f"Tổng mẫu: {len(samples)}")
    print(f"  Chấp nhận: {len(accepted)} -> {config.VALIDATED_DATA_PATH}")
    print(f"  Loại bỏ  : {len(rejected)} -> {config.REJECTED_DATA_PATH}")
    print("\nChi tiết theo case:")
    for case_type, stat in stats_by_case.items():
        rate = stat["accepted"] / stat["total"] if stat["total"] else 0
        print(f"  {case_type:20s}: {stat['accepted']}/{stat['total']} ({rate:.1%})")

    overall_rejection_rate = len(rejected) / len(samples) if samples else 0
    if overall_rejection_rate > 0.3:
        print(
            f"\n  CẢNH BÁO: tỷ lệ loại {overall_rejection_rate:.1%} > 30%. "
            f"Đọc thủ công vài mẫu trong {config.REJECTED_DATA_PATH.name} - có thể "
            f"cần chỉnh lại prompt yêu cầu 'verbatim' trong generate_training_data.py "
            f"cho rõ ràng, dứt khoát hơn."
        )


if __name__ == "__main__":
    main()
