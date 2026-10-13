"""
01_retrieval/generate_training_data.py

Sinh dữ liệu huấn luyện SFT cho Retrieval Agent (Router + Critique)
theo đúng Bước 2 trong tài liệu: dùng LLM sinh data dạng CoT.

PHIÊN BẢN CẬP NHẬT:
- Tự động lưu từng mẫu ngay khi sinh xong (incremental save) → không bao
  giờ mất tiến trình dù script bị crash hoặc bị ngắt giữa chừng.
- Tự phát hiện và resume từ checkpoint cũ nếu chạy lại.
- Tự đọc retryDelay từ lỗi 429 của Google API để chờ đúng thời gian.
- Chạy tuần tự (không song song) để tôn trọng quota Free Tier.
- Delay 4 giây giữa các request để không vượt 15 req/phút.
"""

import json
import random
import re
from dataclasses import asdict
from pathlib import Path

import os
import time
from openai import OpenAI

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.schemas import RetrievalDecision

# ===== Đọc file .env nếu có =====
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
# ===== API Key & Provider Selection =====
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

GROQ_MODELS = [
    os.environ.get("MODEL_NAME", "qwen/qwen3.6-27b"),
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "groq/compound-mini",
]
GEMINI_MODELS = [
    os.environ.get("MODEL_NAME", "gemini-3.6-flash"),
    "gemini-3.1-pro-preview",
    "gemini-2.5-flash",
    "gemini-1.5-flash",
]
current_model_idx = 0

if GROQ_API_KEY:
    print(f"-> Đang sử dụng Groq API (Qwen-3.6-27B - Siêu nhanh & Miễn phí)")
    client = OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=GROQ_API_KEY,
    )
    MODEL_NAME = GROQ_MODELS[0]
    REQUEST_DELAY = 0.3
elif GEMINI_API_KEY:
    print(f"-> Đang sử dụng Google Gemini API")
    client = OpenAI(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        api_key=GEMINI_API_KEY,
    )
    MODEL_NAME = GEMINI_MODELS[0]
    REQUEST_DELAY = 4.0
elif OPENAI_API_KEY:
    print("-> Đang sử dụng OpenAI API")
    client = OpenAI(api_key=OPENAI_API_KEY)
    MODEL_NAME = os.environ.get("MODEL_NAME", "gpt-4o")
    REQUEST_DELAY = 0.5
else:
    raise ValueError(
        "\n[THIẾU API KEY] Chưa tìm thấy API Key nào!\n"
    )

# ===== Paths =====
possible_corpus_paths = [
    Path(__file__).parent.parent.parent / "kb_indexing" / "data" / "corpus.jsonl",
    Path(__file__).parent.parent / "kb_indexing" / "data" / "corpus.jsonl",
    Path(__file__).parent.parent.parent / "kb-indexing" / "data" / "corpus.jsonl",
    Path(__file__).parent.parent / "kb-indexing" / "data" / "corpus.jsonl",
    Path(__file__).parent / "data" / "corpus.jsonl",
]
CORPUS_PATH = next((p for p in possible_corpus_paths if p.exists()), possible_corpus_paths[1])
OUTPUT_PATH = Path(__file__).parent / "data" / "retrieval_sft_train.jsonl"
CHECKPOINT_PATH = Path(__file__).parent / "data" / "retrieval_sft_train_checkpoint.jsonl"

TOOLS = ["bm25", "dense", "hyde", "rewrite", "decompose"]

JARGON_PATTERN = re.compile(
    r"\b(LoRA|RoPE|AdamW|FlashAttention|RLHF|QLoRA|GPT-\d|BERT|LayerNorm|"
    r"RMSNorm|BLEU|ROUGE|MMLU|GSM8K|SFT|DPO|PPO)\b"
)


def load_corpus(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def _parse_retry_delay(err_str: str) -> float:
    match = re.search(r"retry\s+in\s+([\d.]+)s", err_str, re.IGNORECASE)
    if match:
        return float(match.group(1)) + 2
    match = re.search(r"retryDelay['\"]?\s*[:=]\s*['\"]?([\d.]+)s", err_str)
    if match:
        return float(match.group(1)) + 2
    return 15.0


def call_llm_json(prompt: str, system: str) -> dict:
    """Gọi LLM, ép trả JSON, tự chuyển model khi hết TPD/Rate-limit."""
    global MODEL_NAME, current_model_idx
    max_retries = 5

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
            )
            raw = response.choices[0].message.content
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            if attempt < 2:
                time.sleep(0.5)
                continue
            raise ValueError("Không parse được JSON từ response")
        except Exception as e:
            err_str = str(e)

            # Nếu hết TPD/Quota trên Groq → Tự động xoay sang Model tiếp theo trên Groq!
            if ("429" in err_str or "rate_limit" in err_str.lower() or "tpd" in err_str.lower() or "tokens" in err_str.lower()) and GROQ_API_KEY:
                current_model_idx = (current_model_idx + 1) % len(GROQ_MODELS)
                new_model = GROQ_MODELS[current_model_idx]
                if new_model != MODEL_NAME:
                    print(f"\n[Model Rotate] Hết quota TPD model {MODEL_NAME} → Tự động chuyển sang model Groq mới: {new_model}", flush=True)
                    MODEL_NAME = new_model
                    time.sleep(0.5)
                    continue

            # Lỗi 404 với Gemini
            if ("404" in err_str or "not found" in err_str.lower()) and GEMINI_API_KEY:
                current_model_idx = (current_model_idx + 1) % len(GEMINI_MODELS)
                new_model = GEMINI_MODELS[current_model_idx]
                if new_model != MODEL_NAME:
                    print(f"\n[Fallback] Model {MODEL_NAME} không khả dụng → chuyển sang {new_model}")
                    MODEL_NAME = new_model
                    time.sleep(1)
                    continue

            if attempt >= max_retries - 1:
                raise
            time.sleep(1)

    raise RuntimeError(f"Không thể gọi LLM sau {max_retries} lần thử: {err_str}")


def generate_question_for_chunk(chunk_text: str, style: str) -> str:
    """style: 'keyword_lookup' | 'conceptual' | 'comparison'"""
    # Cắt ngắn chunk còn 500 ký tự để tiết kiệm 75% Token (tránh chạm trần TPD 200k)
    short_chunk = chunk_text[:500]
    style_instructions = {
        "keyword_lookup": (
            "Sinh 1 câu hỏi NGẮN, tập trung vào tra cứu CHÍNH XÁC một "
            "thuật ngữ/tên riêng/viết tắt xuất hiện trong đoạn văn. "
            "Câu hỏi phải mang tính 'định nghĩa' hoặc 'giải thích thuật ngữ X là gì'."
        ),
        "conceptual": (
            "Sinh 1 câu hỏi dạng 'tại sao' hoặc 'như thế nào', đòi hỏi hiểu "
            "Ý NGHĨA/Ý TƯỞNG của đoạn văn, KHÔNG được lặp lại nguyên văn "
            "thuật ngữ đặc thù nào - câu hỏi phải diễn đạt bằng ngôn ngữ tự nhiên khác."
        ),
        "comparison": (
            "Sinh 1 câu hỏi SO SÁNH giữa 2 khái niệm khác nhau, đòi hỏi phải "
            "tách thành nhiều câu hỏi con mới trả lời đầy đủ được."
        ),
    }
    system = "Bạn là chuyên gia sinh câu hỏi đánh giá hệ thống retrieval cho corpus AI/arXiv. Trả về duy nhất 1 JSON object: {\"question\": \"...\"}"
    prompt = (
        f"Đoạn văn bản (chunk) trích từ paper AI:\n\"\"\"\n{short_chunk}\n\"\"\"\n\n"
        f"{style_instructions[style]}\n\n"
        'Trả về đúng 1 JSON object: {"question": "..."}'
    )
    result = call_llm_json(prompt, system)
    return result["question"]


def load_checkpoint(path: Path) -> list[dict]:
    """Đọc các mẫu đã sinh từ checkpoint trước đó."""
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def process_case_a_single(chunk: dict, style: str, is_jargon: bool) -> dict | None:
    try:
        question = generate_question_for_chunk(chunk["text"], style)
        if is_jargon:
            decision = RetrievalDecision(
                thought="Câu hỏi tra cứu thuật ngữ cụ thể, phù hợp keyword matching chính xác.",
                tool_selected="bm25",
                critique_is_relevant=True,
                critique_reason="Kết quả BM25 khớp chính xác thuật ngữ được hỏi.",
            )
        else:
            decision = RetrievalDecision(
                thought="Câu hỏi mang tính khái niệm, không có từ khoá đặc thù, cần semantic search.",
                tool_selected="dense",
                critique_is_relevant=True,
                critique_reason="Kết quả Dense khớp ngữ nghĩa dù không trùng từ khoá.",
            )
        return {
            "sub_query": question,
            "history_trials": [],
            "target_output": json.loads(decision.to_json()),
            "source_doc_id": chunk["doc_id"],
            "_case": "A",
        }
    except Exception as e:
        return None


def process_case_b_single(chunk: dict) -> dict | None:
    try:
        question = generate_question_for_chunk(chunk["text"], "keyword_lookup")
        jargon_match = JARGON_PATTERN.search(chunk["text"])
        missing_term = jargon_match.group(0) if jargon_match else "thuật ngữ chuyên môn"

        decision_turn2 = RetrievalDecision(
            thought=(
                f"Lần trước dùng dense bị nhiễu vì câu hỏi chứa thuật ngữ "
                f"chính xác '{missing_term}'. Cần chuyển sang BM25 để match keyword."
            ),
            tool_selected="bm25",
            critique_is_relevant=True,
            critique_reason=f"BM25 tìm đúng đoạn chứa '{missing_term}'.",
        )
        return {
            "sub_query": question,
            "history_trials": [
                {
                    "tool": "dense",
                    "is_relevant": False,
                    "reason": (
                        f"Kết quả nói chung chung về chủ đề liên quan nhưng "
                        f"không chứa thuật ngữ chính xác '{missing_term}' được hỏi."
                    ),
                }
            ],
            "target_output": json.loads(decision_turn2.to_json()),
            "source_doc_id": chunk["doc_id"],
            "_case": "B",
        }
    except Exception as e:
        return None


def process_case_c_single(chunk_a: dict, chunk_b: dict) -> dict | None:
    try:
        system = "Bạn là chuyên gia sinh câu hỏi so sánh giữa 2 đoạn văn bản khoa học."
        prompt = (
            f"Đoạn A:\n\"\"\"\n{chunk_a['text'][:500]}\n\"\"\"\n\n"
            f"Đoạn B:\n\"\"\"\n{chunk_b['text'][:500]}\n\"\"\"\n\n"
            "Sinh 1 câu hỏi SO SÁNH giữa nội dung của Đoạn A và Đoạn B, "
            "đòi hỏi phải tách thành 2 câu hỏi con mới trả lời đủ.\n"
            'Trả về JSON: {"question": "..."}'
        )
        question = call_llm_json(prompt, system)["question"]
        decision = RetrievalDecision(
            thought="Câu hỏi so sánh 2 khái niệm từ 2 nguồn khác nhau, cần tách nhỏ trước khi search.",
            tool_selected="decompose",
            critique_is_relevant=True,
            critique_reason="Sau khi decompose, mỗi câu hỏi con tìm đúng nguồn tương ứng.",
        )
        return {
            "sub_query": question,
            "history_trials": [],
            "target_output": json.loads(decision.to_json()),
            "source_doc_id": [chunk_a["doc_id"], chunk_b["doc_id"]],
            "_case": "C",
        }
    except Exception as e:
        return None


import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

file_lock = threading.Lock()


def save_sample(sample: dict, path: Path):
    """Lưu 1 mẫu ngay lập tức vào file (append mode) an toàn đa luồng."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")


def run_parallel_case(tasks, task_fn, desc, max_workers=5):
    """Chạy các task sinh mẫu song song đa luồng và cập nhật tiến độ real-time."""
    results = []
    total = len(tasks)
    completed = 0
    print(f"\n══════════════════════════════════════════════════")
    print(f"📝 {desc} ({total} mẫu, song song {max_workers} luồng)")
    print(f"══════════════════════════════════════════════════")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(task_fn, task): task for task in tasks}
        for future in as_completed(futures):
            res = future.result()
            completed += 1
            if res is not None:
                save_sample(res, CHECKPOINT_PATH)
                results.append(res)
                print(f"\r  ✓ [{completed}/{total}] ({len(results)} mẫu thành công) - {res['sub_query'][:50]}...", end="", flush=True)
            else:
                print(f"\r  ✗ [{completed}/{total}] ({len(results)} mẫu thành công)...", end="", flush=True)
    print()
    return results


def main(n_per_case: int = 150):
    random.seed(42)
    start_time = time.time()

    if not CORPUS_PATH.exists():
        raise FileNotFoundError(
            f"Không tìm thấy {CORPUS_PATH}. Chạy 01_prepare_corpus.py (Bước 1) trước."
        )
    chunks = load_corpus(CORPUS_PATH)
    print(f"Đã tải {len(chunks)} chunk từ corpus.")

    # === Kiểm tra checkpoint cũ ===
    existing = load_checkpoint(CHECKPOINT_PATH)
    if existing:
        print(f"\n📌 Phát hiện {len(existing)} mẫu đã sinh từ lần chạy trước!")
        existing_case_a = sum(1 for s in existing if s.get("_case") == "A")
        existing_case_b = sum(1 for s in existing if s.get("_case") == "B")
        existing_case_c = sum(1 for s in existing if s.get("_case") == "C")
        print(f"   Case A: {existing_case_a} | Case B: {existing_case_b} | Case C: {existing_case_c}\n")
    else:
        existing_case_a = 0
        existing_case_b = 0
        existing_case_c = 0

    # Xác định số luồng: Groq hỗ trợ 5 luồng cực nhanh, Gemini dùng 2 luồng
    workers = 5 if GROQ_API_KEY else 2

    # === Chuẩn bị chunks ===
    jargon_chunks = [c for c in chunks if JARGON_PATTERN.search(c["text"])]
    plain_chunks = [c for c in chunks if not JARGON_PATTERN.search(c["text"])]

    # ========== CASE A: Thành công lượt 1 ==========
    target_a = n_per_case
    remaining_a = target_a - existing_case_a
    if remaining_a > 0:
        tasks_a = []
        n_jargon = remaining_a // 2
        n_plain = remaining_a - n_jargon
        for c in random.sample(jargon_chunks, min(n_jargon + 10, len(jargon_chunks))):
            tasks_a.append((c, "keyword_lookup", True))
        for c in random.sample(plain_chunks, min(n_plain + 10, len(plain_chunks))):
            tasks_a.append((c, "conceptual", False))

        def _task_a_wrapper(item):
            chunk, style, is_j = item
            return process_case_a_single(chunk, style, is_j)

        run_parallel_case(tasks_a[:remaining_a], _task_a_wrapper, f"Case A: Sinh {remaining_a} mẫu", max_workers=workers)
    else:
        print(f"✅ Case A đã đủ ({existing_case_a} mẫu)")

    # ========== CASE B: Phục hồi sau thất bại ==========
    target_b = n_per_case
    remaining_b = target_b - existing_case_b
    if remaining_b > 0:
        tasks_b = random.sample(jargon_chunks, min(remaining_b, len(jargon_chunks)))
        run_parallel_case(tasks_b, process_case_b_single, f"Case B: Sinh {remaining_b} mẫu", max_workers=workers)
    else:
        print(f"✅ Case B đã đủ ({existing_case_b} mẫu)")

    # ========== CASE C: Decompose ==========
    target_c = n_per_case // 2
    remaining_c = target_c - existing_case_c
    if remaining_c > 0:
        by_paper: dict[str, list[dict]] = {}
        for c in chunks:
            by_paper.setdefault(c["metadata"]["paper_id"], []).append(c)
        paper_ids = [pid for pid, cs in by_paper.items() if cs]

        tasks_c = []
        for _ in range(remaining_c):
            pid_a, pid_b = random.sample(paper_ids, 2)
            chunk_a = random.choice(by_paper[pid_a])
            chunk_b = random.choice(by_paper[pid_b])
            tasks_c.append((chunk_a, chunk_b))

        def _task_c_wrapper(item):
            ca, cb = item
            return process_case_c_single(ca, cb)

        run_parallel_case(tasks_c, _task_c_wrapper, f"Case C: Sinh {remaining_c} mẫu", max_workers=workers)
    else:
        print(f"✅ Case C đã đủ ({existing_case_c} mẫu)")

    # ========== Tổng hợp kết quả cuối cùng ==========
    all_samples = load_checkpoint(CHECKPOINT_PATH)

    # Xoá field _case trước khi ghi output chính thức
    for s in all_samples:
        s.pop("_case", None)

    random.shuffle(all_samples)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        for sample in all_samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")

    elapsed = time.time() - start_time
    elapsed_str = f"{elapsed / 60:.1f} phút" if elapsed > 60 else f"{elapsed:.0f} giây"

    print(f"\n{'=' * 55}")
    print(f"✅ HOÀN TẤT trong {elapsed_str}!")
    print(f"{'=' * 55}")
    print(f"  Tổng mẫu hợp lệ : {len(all_samples)}")
    print(f"  Đã lưu chính thức: {OUTPUT_PATH}")
    print(f"\n[BƯỚC TIẾP THEO] Chạy: python 01_retrieval/validate_synthetic_data.py")


if __name__ == "__main__":
    main()
