# ============================================================
# CELL 1 — Cài đặt thư viện
# Chạy trên Kaggle Notebook, bật Accelerator: GPU T4 x2
# ============================================================
!pip install -q datasets sentence-transformers faiss-gpu rank-bm25
# Lưu ý: dùng faiss-gpu (không phải faiss-cpu) vì Kaggle có sẵn GPU T4 x2
# -> tận dụng GPU cho cả bước search sau này, nhanh hơn faiss-cpu đáng kể
# khi corpus 41.5K vector x 1024-dim.

# ============================================================
# CELL 2 — Tải Dataset trực tiếp trên Cloud
# ============================================================
from datasets import load_dataset

dataset = load_dataset("jamescalam/ai-arxiv-chunked", split="train")
print(f"Tổng số chunks: {len(dataset)}")
print(f"Các cột có sẵn: {dataset.column_names}")

# QUAN TRỌNG: cột chứa nội dung text là "chunk", KHÔNG PHẢI "text".
# In thử 1 dòng để xác nhận trước khi build index - tránh lỗi KeyError
# lúc đã embed xong 41.5K chunk (rất tốn thời gian GPU nếu phải chạy lại).
print("\n--- Mẫu dòng đầu tiên ---")
sample = dataset[0]
for key, value in sample.items():
    preview = str(value)[:100]
    print(f"  {key}: {preview}")
