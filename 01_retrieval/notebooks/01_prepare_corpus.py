# ============================================================
# CELL 3 — Chuẩn hoá corpus + gắn doc_id thống nhất
# (BẮT BUỘC chạy trước Cell 4 và 5 - đây là bước bị thiếu trong
#  code gốc, sẽ gây lỗi không thể merge BM25+FAISS ở Retrieval Agent)
# ============================================================

# doc_id xác định (deterministic): "<arxiv_id>::chunk_<so_thu_tu>"
# Dùng chung cho CẢ BM25 lẫn FAISS, để khi Retrieval Agent chạy song song
# 2 tool rồi merge kết quả, biết chính xác đâu là cùng 1 chunk.
doc_ids = [f"{row['id']}::chunk_{row['chunk-id']}" for row in dataset]

# Cột nội dung thật là "chunk", không phải "text"
corpus = [row["chunk"] for row in dataset]

# Lọc chunk rỗng/quá ngắn (artefact của bước chunking gốc) - giữ lại
# index song song với doc_ids và corpus để không bị lệch vị trí.
valid_indices = [i for i, text in enumerate(corpus) if len(text.strip()) >= 20]
doc_ids = [doc_ids[i] for i in valid_indices]
corpus = [corpus[i] for i in valid_indices]
titles = [dataset[i]["title"] for i in valid_indices]

print(f"Số chunk hợp lệ sau khi lọc: {len(corpus)} / {len(dataset)}")
assert len(doc_ids) == len(corpus) == len(titles), "Lệch độ dài - kiểm tra lại bước lọc"

# Lưu corpus.jsonl để phục vụ Bước 2 (sinh synthetic data)
import json
with open("/kaggle/working/corpus.jsonl", "w", encoding="utf-8") as f:
    for doc_id, text, title, idx in zip(doc_ids, corpus, titles, valid_indices):
        paper_id = dataset[idx]["id"]
        row = {
            "doc_id": doc_id,
            "text": text,
            "metadata": {
                "paper_id": paper_id,
                "title": title,
            }
        }
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

print("Đã lưu corpus chuẩn -> /kaggle/working/corpus.jsonl")
