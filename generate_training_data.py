"""
03_summarizer/generate_training_data.py

CHẠY Ở: LOCAL (hoặc bất kỳ máy nào có mạng ra OpenAI / Gemini API) — KHÔNG CẦN GPU.
    python generate_training_data.py -n 30
    python generate_training_data.py

MỤC TIÊU: sinh cặp (context, question, answer, evidence_spans) để train
Generator. TUYỆT ĐỐI không để LLM tự bịa câu hỏi trước rồi mới tìm
context khớp (nguy cơ sinh câu hỏi mà thực ra chunk không trả lời đủ) -
luôn đi theo chiều: CHUNK THẬT có sẵn -> hỏi LLM sinh (question,
answer, evidence_span) tương ứng.

3 LOẠI KỊCH BẢN sinh có chủ đích:
  - Case A (grounded tốt): câu hỏi mà context trả lời ĐẦY ĐỦ, rõ ràng.
    Target: critic phải nói "is_supported: true".
  - Case B (grounded một phần / thiếu evidence): CỐ Ý sinh câu hỏi mà
    context chỉ trả lời được MỘT PHẦN, dạy Critic biết phát hiện hallucination.
  - Case C (không thể trả lời): câu hỏi KHÔNG liên quan gì tới context
    (ghép ngẫu nhiên câu hỏi từ chunk A vào context của chunk B). Target:
    critic phải nói "is_supported: false".
"""

import os
import json
import random
import sys
import time
import re
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from tqdm import tqdm

load_dotenv(Path(__file__).resolve().parent / ".env")
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402

client = None
MODEL_NAME = None

GROQ_MODELS = [
    os.environ.get("MODEL_NAME", "qwen/qwen3.8-27b"),
    "qwen/qwen3.8-27b",
    "groq/compound-mini",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "groq/compound",
]
# Giữ danh sách model duy nhất nhưng bảo toàn thứ tự ưu tiên
GROQ_MODELS = list(dict.fromkeys(GROQ_MODELS))
current_model_idx = 0


def init_client(api_key: str = None, model: str = None):
    global client, MODEL_NAME
    groq_key = os.environ.get("GROQ_API_KEY")
    openai_key = api_key or os.environ.get("OPENAI_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    ollama_url = os.environ.get("OLLAMA_BASE_URL")  # VD: http://localhost:11434/v1

    if groq_key:
        client = OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=groq_key,
        )
        MODEL_NAME = model or GROQ_MODELS[0]
        print(f"-> Đang sử dụng Groq API ({MODEL_NAME} - Siêu nhanh & Miễn phí)")
    elif openai_key:
        client = OpenAI(api_key=openai_key)
        MODEL_NAME = model or config.OPENAI_MODEL_FOR_DATA_GEN
        print(f"[Backend] OpenAI API | Model: {MODEL_NAME}")
    elif gemini_key:
        client = OpenAI(
            api_key=gemini_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        MODEL_NAME = model or "gemini-3.6-flash"
        print(f"[Backend] Gemini API (OpenAI-compat) | Model: {MODEL_NAME}")
    elif ollama_url:
        # Ollama chạy local, không cần API key thật
        client = OpenAI(
            api_key="ollama",  # dummy key, Ollama không xác thực key
            base_url=ollama_url,
        )
        MODEL_NAME = model or "qwen2.5:3b"  # Model mặc định cho 8GB RAM
        print(f"[Backend] Ollama Local | URL: {ollama_url} | Model: {MODEL_NAME}")
        print("         (Đảm bảo Ollama đang chạy: ollama serve)")
    else:
        print("\n" + "=" * 60)
        print("[THÔNG BÁO: CHƯA THIẾT LẬP BACKEND]")
        print("=" * 60)
        print("Vui lòng cấu hình 1 trong 3 backend trong file .env:")
        print("")
        print("  [OpenAI API]:")
        print("       OPENAI_API_KEY=sk-...")
        print("")
        print("  [Gemini API]:")
        print("       GEMINI_API_KEY=AQ...")
        print("")
        print("  [Ollama Local (Miễn phí, chạy model trên máy)]:")
        print("       OLLAMA_BASE_URL=http://localhost:11434/v1")
        print("       # Sau đó chạy: ollama pull qwen2.5:3b")
        print("       # Rồi chạy:    ollama serve")
        print("=" * 60 + "\n")
        sys.exit(1)


def load_corpus(path: Path) -> list[dict]:
    if not path.exists():
        fallback_path = config.DATA_DIR / "corpus.jsonl"
        if fallback_path.exists():
            path = fallback_path
        else:
            raise FileNotFoundError(
                f"Không tìm thấy corpus tại {path} hoặc {fallback_path}.\n"
                f"Vui lòng tạo hoặc đặt file corpus.jsonl vào thư mục {config.DATA_DIR}."
            )
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def clean_json_text(text: str) -> str:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        return match.group(1).strip()
    match_braces = re.search(r"(\{[\s\S]*\})", text)
    if match_braces:
        return match_braces.group(1).strip()
    return text


def call_llm_json(system: str, prompt: str, max_retries: int = 6) -> dict:
    global MODEL_NAME, current_model_idx
    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.7,
                max_tokens=600,
            )
            raw = response.choices[0].message.content
            cleaned = clean_json_text(raw)
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            if attempt < max_retries:
                time.sleep(1.5)
                continue
            raise RuntimeError(f"Không parse được JSON sau {max_retries} lần thử: {e}")
        except Exception as e:
            err_msg = str(e)
            groq_key = os.environ.get("GROQ_API_KEY")
            is_model_err = any(k in err_msg.lower() for k in ["429", "rate_limit", "tpd", "tokens", "404", "model_not_found", "does not exist"])
            if is_model_err and groq_key and len(GROQ_MODELS) > 1:
                current_model_idx = (current_model_idx + 1) % len(GROQ_MODELS)
                new_model = GROQ_MODELS[current_model_idx]
                if new_model != MODEL_NAME:
                    print(f"\n[Model Rotate] Model {MODEL_NAME} gặp sự cố (404/429) → Tự động chuyển sang model Groq mới: {new_model}", flush=True)
                    MODEL_NAME = new_model
                    time.sleep(1.0)
                    continue

            if attempt < max_retries:
                wait_sec = min(60, (2 ** attempt) + random.uniform(1.0, 3.0))
                short_err = err_msg.split("\n")[0][:100]
                print(f"\n  [Cảnh báo tạm thời từ API: {short_err}...]")
                print(f"  -> Đang tự động thử lại sau {wait_sec:.1f}s (Lần {attempt}/{max_retries})...")
                time.sleep(wait_sec)
                continue
            raise


def build_case_a_fully_grounded(chunks: list[dict], n: int, file_handle=None, delay: float = 0.4) -> list[dict]:
    """Case A: câu hỏi mà context trả lời đầy đủ - target is_supported=True."""
    if n <= 0:
        return []
    system = (
        "Bạn là chuyên gia sinh dữ liệu huấn luyện cho hệ thống QA có trích dẫn "
        "bằng chứng (grounded QA)."
    )
    samples = []
    pool = [c for c in chunks if len(c.get("text", "")) >= config.MIN_CHUNK_LENGTH_FOR_QA]
    if not pool:
        return []

    selected_chunks = [random.choice(pool) for _ in range(n)]
    for chunk in tqdm(selected_chunks, desc="  Sinh Case A (fully grounded)", unit="mẫu"):
        prompt = (
            f"Đoạn văn bản sau trích từ 1 paper AI:\n\"\"\"\n{chunk['text']}\n\"\"\"\n\n"
            "Hãy sinh:\n"
            "1. Một câu hỏi (question) mà đoạn văn TRẢ LỜI ĐẦY ĐỦ, RÕ RÀNG.\n"
            "2. Một câu trả lời (answer) NGẮN GỌN cho câu hỏi đó, chỉ dựa trên đoạn văn.\n"
            "3. Evidence span: PHẢI là 1 CÂU NGUYÊN VĂN (verbatim, copy chính xác từng "
            "chữ, không diễn đạt lại) được trích TRỰC TIẾP từ đoạn văn, làm căn cứ cho "
            "câu trả lời.\n\n"
            'Trả về JSON: {"question": "...", "answer": "...", "evidence_span": "..."}'
        )
        result = call_llm_json(system, prompt)
        sample = {
            "context": chunk["text"],
            "question": result.get("question", ""),
            "target_answer": result.get("answer", ""),
            "target_evidence_span": result.get("evidence_span", ""),
            "expected_is_supported": True,
            "source_doc_id": chunk.get("doc_id", "unknown"),
            "case_type": "fully_grounded",
        }
        samples.append(sample)
        if file_handle:
            file_handle.write(json.dumps(sample, ensure_ascii=False) + "\n")
            file_handle.flush()
        if delay > 0:
            time.sleep(delay)
    return samples


def build_case_b_partial_grounding(chunks: list[dict], n: int, file_handle=None, delay: float = 0.4) -> list[dict]:
    """Case B: câu hỏi rộng hơn nội dung context - context chỉ trả lời 1 phần.
    Dạy Critic phát hiện hallucination tinh vi (answer đúng nhưng vượt evidence)."""
    if n <= 0:
        return []
    system = (
        "Bạn là chuyên gia thiết kế bẫy kiểm tra hallucination cho hệ thống QA."
    )
    samples = []
    pool = [c for c in chunks if len(c.get("text", "")) >= config.MIN_CHUNK_LENGTH_FOR_QA]
    if not pool:
        return []

    selected_chunks = [random.choice(pool) for _ in range(n)]
    for chunk in tqdm(selected_chunks, desc="  Sinh Case B (partial ground)", unit="mẫu"):
        prompt = (
            f"Đoạn văn bản sau trích từ 1 paper AI:\n\"\"\"\n{chunk['text']}\n\"\"\"\n\n"
            "Hãy sinh 1 câu hỏi (question) mà đoạn văn CHỈ TRẢ LỜI ĐƯỢC MỘT PHẦN - "
            "ví dụ câu hỏi hỏi về nguyên nhân/so sánh/hệ quả mà đoạn văn không đề cập "
            "đầy đủ, chỉ có 1 phần thông tin liên quan.\n\n"
            "Sau đó, đóng vai một Generator THIẾU CẨN THẬN: sinh answer trả lời ĐẦY ĐỦ "
            "câu hỏi (kể cả phần đoạn văn không hề đề cập, tự suy diễn thêm) - đây là "
            "hành vi ta MUỐN model học cách PHÁT HIỆN, không phải học cách làm theo.\n\n"
            'Trả về JSON: {"question": "...", "overreaching_answer": "...", '
            '"evidence_span_that_exists": "câu trích dẫn thật có trong đoạn văn, chỉ '
            'hỗ trợ MỘT PHẦN câu trả lời", "missing_part_reason": "mô tả ngắn phần nào '
            'của answer KHÔNG có căn cứ trong đoạn văn"}'
        )
        result = call_llm_json(system, prompt)
        sample = {
            "context": chunk["text"],
            "question": result.get("question", ""),
            "target_answer": result.get("overreaching_answer", ""),
            "target_evidence_span": result.get("evidence_span_that_exists", ""),
            "expected_is_supported": False,   # vì answer VƯỢT QUÁ evidence thật
            "expected_critique_reason_hint": result.get("missing_part_reason", ""),
            "source_doc_id": chunk.get("doc_id", "unknown"),
            "case_type": "partial_grounding",
        }
        samples.append(sample)
        if file_handle:
            file_handle.write(json.dumps(sample, ensure_ascii=False) + "\n")
            file_handle.flush()
        if delay > 0:
            time.sleep(delay)
    return samples


def build_case_c_unanswerable(chunks: list[dict], n: int, file_handle=None, delay: float = 0.4) -> list[dict]:
    """Case C: câu hỏi hoàn toàn không liên quan tới context (ghép chéo).
    Dạy model không "gắng gượng" trả lời khi không có căn cứ."""
    if n <= 0:
        return []
    samples = []
    pool = [c for c in chunks if len(c.get("text", "")) >= config.MIN_CHUNK_LENGTH_FOR_QA]
    if len(pool) < 2:
        return samples

    system = "Bạn là chuyên gia sinh câu hỏi cho 1 đoạn văn bản khoa học."
    for _ in tqdm(range(n), desc="  Sinh Case C (unanswerable)", unit="mẫu"):
        context_chunk, question_source_chunk = random.sample(pool, 2)

        prompt = (
            f"Đoạn văn bản:\n\"\"\"\n{question_source_chunk['text']}\n\"\"\"\n\n"
            "Sinh 1 câu hỏi cụ thể, chi tiết mà đoạn văn này trả lời được.\n"
            'Trả về JSON: {"question": "..."}'
        )
        question = call_llm_json(system, prompt).get("question", "")

        sample = {
            "context": context_chunk["text"],   # CỐ Ý dùng context KHÔNG liên quan
            "question": question,
            "target_answer": None,   # không có target answer hợp lệ - dùng để test critic
            "target_evidence_span": None,
            "expected_is_supported": False,
            "source_doc_id": context_chunk.get("doc_id", "unknown"),
            "case_type": "unanswerable",
        }
        samples.append(sample)
        if file_handle:
            file_handle.write(json.dumps(sample, ensure_ascii=False) + "\n")
            file_handle.flush()
        if delay > 0:
            time.sleep(delay)
    return samples


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Sinh dữ liệu huấn luyện cho Summarizer Agent.")
    parser.add_argument(
        "-n", "--num-samples",
        type=int,
        default=config.N_SAMPLES_TO_GENERATE,
        help=f"Số lượng mẫu cần sinh (mặc định: {config.N_SAMPLES_TO_GENERATE})"
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="API Key (OpenAI hoặc Gemini). Nếu không truyền sẽ đọc từ .env hoặc biến môi trường."
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Tên model LLM dùng sinh data (mặc định: gpt-4o hoặc gemini-3.6-flash)"
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Xóa dữ liệu cũ và sinh lại từ đầu thay vì tiếp tục (resume)."
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.4,
        help="Thời gian nghỉ (giây) giữa các lần gọi API để tránh quá tải (mặc định: 0.4s)"
    )
    args = parser.parse_args()

    init_client(api_key=args.api_key, model=args.model)

    random.seed(42)
    chunks = load_corpus(config.CORPUS_PATH)
    print(f"Đã tải {len(chunks)} chunk từ corpus.")

    total = args.num_samples
    if total <= 3:
        n_a, n_b, n_c = 1, 1, max(1, total - 2)
    else:
        n_a = int(total * 0.5)
        n_b = int(total * 0.3)
        n_c = total - n_a - n_b

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Đọc dữ liệu cũ nếu đã tồn tại và không bật --overwrite
    existing_samples = []
    if config.RAW_DATA_PATH.exists() and not args.overwrite:
        with open(config.RAW_DATA_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if line_str:
                    try:
                        existing_samples.append(json.loads(line_str))
                    except Exception:
                        pass

    cnt_a = sum(1 for s in existing_samples if s.get("case_type") == "fully_grounded")
    cnt_b = sum(1 for s in existing_samples if s.get("case_type") == "partial_grounding")
    cnt_c = sum(1 for s in existing_samples if s.get("case_type") == "unanswerable")

    rem_a = max(0, n_a - cnt_a)
    rem_b = max(0, n_b - cnt_b)
    rem_c = max(0, n_c - cnt_c)

    print(f"\nMỤC TIÊU TỔNG: {n_a + n_b + n_c} mẫu (Model: {MODEL_NAME})")
    print(f"  - Case A (fully grounded) : {n_a} (Đã có: {cnt_a} -> Cần sinh thêm: {rem_a})")
    print(f"  - Case B (partial ground) : {n_b} (Đã có: {cnt_b} -> Cần sinh thêm: {rem_b})")
    print(f"  - Case C (unanswerable)   : {n_c} (Đã có: {cnt_c} -> Cần sinh thêm: {rem_c})")

    file_mode = "w" if args.overwrite else "a"
    with open(config.RAW_DATA_PATH, file_mode, encoding="utf-8") as f:
        if rem_a > 0:
            print(f"\n[1/3] Đang sinh Case A ({rem_a} mẫu)...")
            build_case_a_fully_grounded(chunks, rem_a, file_handle=f, delay=args.delay)
        else:
            print("\n[1/3] Case A đã đủ số lượng, bỏ qua.")

        if rem_b > 0:
            print(f"\n[2/3] Đang sinh Case B ({rem_b} mẫu)...")
            build_case_b_partial_grounding(chunks, rem_b, file_handle=f, delay=args.delay)
        else:
            print("\n[2/3] Case B đã đủ số lượng, bỏ qua.")

        if rem_c > 0:
            print(f"\n[3/3] Đang sinh Case C ({rem_c} mẫu)...")
            build_case_c_unanswerable(chunks, rem_c, file_handle=f, delay=args.delay)
        else:
            print("\n[3/3] Case C đã đủ số lượng, bỏ qua.")

    # Đếm lại tổng số mẫu sau khi ghi xong
    final_count = 0
    if config.RAW_DATA_PATH.exists():
        with open(config.RAW_DATA_PATH, "r", encoding="utf-8") as f:
            final_count = sum(1 for line in f if line.strip())

    print("\n" + "=" * 60)
    print(f"HOÀN THÀNH SINH DỮ LIỆU! Tổng cộng: {final_count} mẫu.")
    print(f"Lưu tại: {config.RAW_DATA_PATH}")
    print("=" * 60)
    print("\n[BƯỚC BẮT BUỘC TIẾP THEO] Chạy: python validate_evidence_span.py")


if __name__ == "__main__":
    main()
