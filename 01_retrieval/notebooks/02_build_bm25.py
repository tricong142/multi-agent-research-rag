# ============================================================
# CELL 4 — Build BM25 Index (Sparse Tool)
# ============================================================
import re
import pickle
from rank_bm25 import BM25Okapi

# SỬA LỖI so với code gốc: không cần nltk.download('punkt') rồi lại
# không dùng nó. Dùng regex tokenizer đơn giản nhưng xử lý đúng dấu câu
# dính chữ (vd "RoPE," -> ["rope"] thay vì ["rope,"]) - quan trọng vì
# corpus này có rất nhiều thuật ngữ viết tắt (LoRA, AdamW, RoPE...) mà
# BM25 cần match CHÍNH XÁC ký tự.
_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")

def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())

print("Đang tokenize corpus...")
tokenized_corpus = [tokenize(doc) for doc in corpus]

print("Đang build BM25Okapi index...")
bm25 = BM25Okapi(tokenized_corpus)

# Lưu lại kèm doc_ids để tra cứu ngược khi query - rank_bm25 không tự
# lưu, phải tự pickle để dùng lại giữa các session Kaggle (mỗi lần mở
# lại notebook, RAM bị xoá sạch).
with open("/kaggle/working/bm25_index.pkl", "wb") as f:
    pickle.dump({"bm25": bm25, "doc_ids": doc_ids, "corpus": corpus}, f)

print(f"Đã lưu BM25 index -> /kaggle/working/bm25_index.pkl")

# Test nhanh 1 câu để verify tokenizer hoạt động đúng trước khi đi tiếp
import numpy as np
test_query = "What is RoPE positional encoding?"
scores = np.asarray(bm25.get_scores(tokenize(test_query)))
top1_idx = int(scores.argmax())
print(f"\nTest query: '{test_query}'")
print(f"Top-1 doc_id: {doc_ids[top1_idx]} (score={scores[top1_idx]:.2f})")
print(f"Preview: {corpus[top1_idx][:150]}...")
