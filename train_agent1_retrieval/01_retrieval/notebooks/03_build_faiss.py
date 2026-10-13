# ============================================================
# CELL 5 — Build FAISS Index với BGE-Large (Dense Tool)
# ============================================================
import json
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("BAAI/bge-large-en-v1.5", device="cuda")

# LƯU Ý QUAN TRỌNG (thiếu trong code gốc, dễ gây lỗi âm thầm):
# bge-large-en-v1.5 cần prefix RIÊNG cho query khi search, nhưng
# KHÔNG dùng prefix khi embed passage/chunk lúc build index.
# Ở bước này (build index) ta KHÔNG thêm prefix - đúng như code gốc.
# Khi viết Retrieval Agent thật (Bước 3), lúc encode CÂU HỎI của user,
# PHẢI thêm prefix:
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
# Bỏ sót điểm này ở lúc query (không phải lúc build) là lỗi phổ biến
# nhất khiến Dense retrieval kém hẳn so với benchmark công bố của BGE.

print(f"Đang embed {len(corpus)} chunks bằng GPU T4...")
embeddings = model.encode(
    corpus,
    batch_size=64,
    show_progress_bar=True,
    normalize_embeddings=True,  # bắt buộc để dùng Inner Product = Cosine similarity
)
embeddings = np.asarray(embeddings, dtype="float32")  # FAISS yêu cầu float32

dimension = embeddings.shape[1]
index = faiss.IndexFlatIP(dimension)
index.add(embeddings)

faiss.write_index(index, "/kaggle/working/faiss_arxiv.index")

# QUAN TRỌNG: FAISS IndexFlatIP chỉ lưu VECTOR, không lưu doc_id/text đi
# kèm. Phải tự lưu mapping "vị trí trong FAISS -> doc_id" riêng, nếu
# không thì search xong chỉ có index số (vd 12345) mà không biết đó là
# chunk nào - đây là lỗi thiếu ở code gốc bạn gửi.
with open("/kaggle/working/faiss_doc_ids.json", "w", encoding="utf-8") as f:
    json.dump(doc_ids, f, ensure_ascii=False)

print(f"Đã lưu FAISS index -> /kaggle/working/faiss_arxiv.index ({index.ntotal} vectors)")
print(f"Đã lưu doc_id mapping -> /kaggle/working/faiss_doc_ids.json")

# Test nhanh CÙNG câu hỏi đã test ở BM25 (Cell 4) để so sánh chéo 2 tool
test_query = "What is RoPE positional encoding?"
query_vec = model.encode(BGE_QUERY_PREFIX + test_query, normalize_embeddings=True)
query_vec = np.asarray([query_vec], dtype="float32")

scores, indices = index.search(query_vec, k=3)
print(f"\nTest query: '{test_query}'")
for rank, (score, idx) in enumerate(zip(scores[0], indices[0]), 1):
    print(f"{rank}. [{score:.4f}] doc_id={doc_ids[idx]}")
    print(f"   {corpus[idx][:150]}...")
