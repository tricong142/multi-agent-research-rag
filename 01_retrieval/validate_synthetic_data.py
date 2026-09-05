"""
01_retrieval/validate_synthetic_data.py

BƯỚC BẮT BUỘC sau generate_training_data.py, KHÔNG ĐƯỢC SKIP.

TẠI SAO BẮT BUỘC:
GPT-4o khi sinh Case A/B có thể gán nhãn "tool_selected": "bm25" cho 1
câu hỏi, nhưng thực tế khi chạy BM25 thật trên corpus, top-1 kết quả lại
KHÔNG PHẢI chunk gốc đã dùng để sinh câu hỏi đó (có thể do BM25 thật
không mạnh như GPT-4o tưởng, hoặc câu hỏi sinh ra mơ hồ hơn dự tính).
Nếu không lọc bước này, model SFT sẽ học phải các cặp (câu hỏi, nhãn)
sai, làm giảm chất lượng Router thay vì cải thiện.

CÁCH LÀM: với mỗi mẫu, chạy LẠI đúng tool đã được gán nhãn trên BM25
index / FAISS index THẬT (đã build ở Bước 1), kiểm tra xem
source_doc_id có nằm trong top-K kết quả không. Nếu không -> loại mẫu
khỏi tập train (không sửa nhãn, vì có thể câu hỏi tự nó có vấn đề, an
toàn hơn là bỏ hẳn).
"""

import json
import pickle
import re
import sys
import warnings
from pathlib import Path

# Vô hiệu hoá import torchaudio bị lỗi DLL trên Windows
sys.modules["torchaudio"] = None
warnings.filterwarnings("ignore")

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

INPUT_PATH = Path(__file__).parent / "data" / "retrieval_sft_train.jsonl"
OUTPUT_PATH = Path(__file__).parent / "data" / "retrieval_sft_train_validated.jsonl"
REJECTED_PATH = Path(__file__).parent / "data" / "retrieval_sft_train_rejected.jsonl"

possible_bm25 = [
    Path(__file__).parent.parent.parent / "kb_indexing" / "indices" / "bm25_index.pkl",
    Path(__file__).parent.parent / "kb_indexing" / "indices" / "bm25_index.pkl",
    Path(__file__).parent.parent.parent / "kb-indexing" / "indices" / "bm25_index.pkl",
    Path(__file__).parent.parent / "kb-indexing" / "indices" / "bm25_index.pkl",
    Path(__file__).parent / "indices" / "bm25_index.pkl",
]
BM25_INDEX_PATH = next((p for p in possible_bm25 if p.exists()), possible_bm25[1])

possible_faiss = [
    Path(__file__).parent.parent.parent / "kb_indexing" / "indices" / "faiss_arxiv.index",
    Path(__file__).parent.parent / "kb_indexing" / "indices" / "faiss_arxiv.index",
    Path(__file__).parent.parent.parent / "kb-indexing" / "indices" / "faiss_arxiv.index",
    Path(__file__).parent.parent / "kb-indexing" / "indices" / "faiss_arxiv.index",
    Path(__file__).parent / "indices" / "faiss_arxiv.index",
]
FAISS_INDEX_PATH = next((p for p in possible_faiss if p.exists()), possible_faiss[1])

TOP_K_CHECK = 10  # chấp nhận nếu source_doc_id nằm trong top-10, không nhất thiết top-1
                   # (top-1 quá khắt khe, vì mục tiêu là "tool này có khả năng tìm ra",
                   # bước rerank ở Retrieval Agent thật sẽ lo phần xếp hạng chính xác)

_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def check_bm25(query: str, target_doc_id: str, bm25_data: dict) -> bool:
    scores = np.asarray(bm25_data["bm25"].get_scores(tokenize(query)))
    top_k_indices = np.argsort(scores)[::-1][:TOP_K_CHECK]
    top_k_doc_ids = {bm25_data["doc_ids"][i] for i in top_k_indices}
    return target_doc_id in top_k_doc_ids


def check_dense(query: str, target_doc_id: str, faiss_index, embedder, doc_ids: list[str]) -> bool:
    query_vec = embedder.encode(BGE_QUERY_PREFIX + query, normalize_embeddings=True)
    query_vec = np.asarray([query_vec], dtype="float32")
    _, indices = faiss_index.search(query_vec, TOP_K_CHECK)
    top_k_doc_ids = {doc_ids[i] for i in indices[0]}
    return target_doc_id in top_k_doc_ids


def main():
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Không tìm thấy {INPUT_PATH}. Chạy generate_training_data.py trước.")
    if not BM25_INDEX_PATH.exists() or not FAISS_INDEX_PATH.exists():
        raise FileNotFoundError(
            "Chưa có BM25/FAISS index thật. Chạy xong Bước 1 (kb_indexing) trước khi validate."
        )

    with open(BM25_INDEX_PATH, "rb") as f:
        bm25_data = pickle.load(f)
    faiss_index = faiss.read_index(str(FAISS_INDEX_PATH))
    # doc_ids của FAISS phải load từ file JSON đi kèm (xem 03_build_faiss.py Cell 5)
    faiss_doc_ids_path = FAISS_INDEX_PATH.parent / "faiss_doc_ids.json"
    with open(faiss_doc_ids_path, "r", encoding="utf-8") as f:
        faiss_doc_ids = json.load(f)

    import gc
    gc.collect()

    print("Đang tải embedding model để encode query lúc validate...")
    embedder = SentenceTransformer(
        "BAAI/bge-large-en-v1.5",
        model_kwargs={"low_cpu_mem_usage": True},
    )

    accepted, rejected = [], []
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        samples = [json.loads(line) for line in f]

    for sample in samples:
        tool = sample["target_output"]["tool_selected"]
        target_id = sample["source_doc_id"]

        # Case C (decompose) có source_doc_id là list, không validate bằng
        # 1 tool đơn - bỏ qua bước check tự động, để review thủ công riêng.
        if isinstance(target_id, list):
            accepted.append(sample)
            continue

        if tool == "bm25":
            is_valid = check_bm25(sample["sub_query"], target_id, bm25_data)
        elif tool == "dense":
            is_valid = check_dense(sample["sub_query"], target_id, faiss_index, embedder, faiss_doc_ids)
        else:
            # hyde/rewrite dùng lại Dense/BM25 bên dưới sau khi biến đổi câu hỏi -
            # không validate tự động ở đây vì cần bước biến đổi LLM riêng, review thủ công.
            accepted.append(sample)
            continue

        if is_valid:
            accepted.append(sample)
        else:
            rejected.append(sample)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        for s in accepted:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    with open(REJECTED_PATH, "w", encoding="utf-8") as f:
        for s in rejected:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    print(f"\nTổng mẫu: {len(samples)}")
    print(f"  Chấp nhận: {len(accepted)} -> {OUTPUT_PATH}")
    print(f"  Loại bỏ  : {len(rejected)} -> {REJECTED_PATH}")
    rejection_rate = len(rejected) / len(samples) if samples else 0
    print(f"  Tỷ lệ loại: {rejection_rate:.1%}")
    if rejection_rate > 0.3:
        print("\n  CẢNH BÁO: tỷ lệ loại > 30%. Nên đọc thủ công vài mẫu trong "
              "file rejected để hiểu vì sao (prompt sinh câu hỏi có thể cần chỉnh lại) "
              "trước khi đem tập 'validated' đi train.")


if __name__ == "__main__":
    main()
