"""
01_process_doclaynet.py
=========================
GIAI DOAN B - XU LY FULL DATASET.

Da duoc cap nhat theo SCHEMA THAT xac nhan tu output chay thu tren Kaggle
(khong con la gia dinh). Schema thuc te cua split 'train':

    id                 : string
    texts              : list[string]           - text cua tung dong
    bboxes_block       : list[list[int]]         - bbox cua CA KHOI cha (x,y,w,h)
    bboxes_line        : list[list[int]]         - bbox cua TUNG DONG rieng (x,y,w,h)
    categories         : list[ClassLabel(11 lop)]- nhan cho tung dong
    image              : PIL Image (1025x1025, kich thuoc COCO da resize)
    page_hash          : string
    original_filename  : string
    page_no            : int32
    num_pages          : int32
    original_width     : int32   <-- QUAN TRONG: bboxes theo thang nay
    original_height    : int32   <-- QUAN TRONG: bboxes theo thang nay, KHONG PHAI theo image.size
    coco_width          : int32  (= kich thuoc image, 1025)
    coco_height         : int32  (= kich thuoc image, 1025)
    collection         : string
    doc_category       : string

LUU Y QUAN TRONG DA XAC NHAN BANG DOI CHIEU DU LIEU THAT:
    bboxes_block / bboxes_line co toa do theo thang (original_width,
    original_height) CUA TRANG GOC, KHONG PHAI theo kich thuoc anh
    'image' (1025x1025 la anh COCO da resize). Neu normalize nham theo
    image.size, toa do se SAI HOAN TOAN. Da kiem chung: bbox dau tien
    (y=30, h=14) tren original_height=793 nam sat mep tren trang (~4%),
    khop voi nhan categories=5 (Page-header) cua chinh dong do.

CHON bboxes_line LAM MAC DINH (khong phai bboxes_block) vi no bam sat
vi tri that cua tung doan text hon - phu hop hon cho LayoutLMv3 token
classification. Neu muon dung bboxes_block, doi COLUMN_BBOXES ben duoi.

Chay tren Kaggle Notebook. Cai dat truoc (neu chua chay o file 00):
    !pip install -q -U datasets huggingface_hub pillow
"""

import os
import json
from huggingface_hub import HfApi
from datasets import load_dataset

# ---------------------------------------------------------------------------
# CAU HINH CHUNG
# ---------------------------------------------------------------------------
DATASET_NAME = "pierreguillou/DocLayNet-base"
PARQUET_REVISION = "refs/convert/parquet"  # nhanh auto-convert cua HF Datasets Server
OUTPUT_DIR = "/kaggle/working/doclaynet_processed"   # doi neu chay ngoai Kaggle
LAYOUTLM_COORD_SCALE = 1000  # LayoutLMv3 yeu cau bbox chuan hoa ve thang 0-1000

# ---------------------------------------------------------------------------
# CAU HINH TEN COT - DA XAC NHAN THAT TU OUTPUT KAGGLE, KHONG CON LA GIA DINH
# ---------------------------------------------------------------------------
COLUMN_IMAGE = "image"
COLUMN_BBOXES = "bboxes_line"   # doi thanh "bboxes_block" neu muon dung box ca khoi
COLUMN_CATEGORIES = "categories"
COLUMN_TEXTS = "texts"
COLUMN_ORIG_WIDTH = "original_width"
COLUMN_ORIG_HEIGHT = "original_height"


def discover_parquet_files():
    """Liet ke file .parquet that trong nhanh refs/convert/parquet (giong file 00)."""
    api = HfApi()
    all_files = api.list_repo_files(
        DATASET_NAME, repo_type="dataset", revision=PARQUET_REVISION
    )
    parquet_files = [f for f in all_files if f.endswith(".parquet")]

    if not parquet_files:
        raise RuntimeError(
            f"Khong tim thay file .parquet nao trong repo '{DATASET_NAME}' "
            f"o nhanh '{PARQUET_REVISION}'."
        )

    data_files = {"train": [], "validation": [], "test": []}
    for f in parquet_files:
        lower = f.lower()
        url = f"https://huggingface.co/datasets/{DATASET_NAME}/resolve/{PARQUET_REVISION}/{f}"
        if "train" in lower:
            data_files["train"].append(url)
        elif "valid" in lower or "-val" in lower or "_val" in lower:
            data_files["validation"].append(url)
        elif "test" in lower:
            data_files["test"].append(url)

    data_files = {split: files for split, files in data_files.items() if files}
    return data_files


def convert_box_xywh_to_xyxy(box):
    """Convert (x, y, width, height) -> (x0, y0, x1, y1)."""
    x, y, w, h = box
    return [x, y, x + w, y + h]


def normalize_box(box, orig_width, orig_height):
    """
    Chuan hoa bbox pixel ve thang 0-1000 theo yeu cau cua LayoutLMv3.

    QUAN TRONG: dung orig_width/orig_height (kich thuoc trang GOC di kem
    tung sample), TUYET DOI KHONG dung image.size (1025x1025 la anh COCO
    da resize, khac he toa do voi bboxes).
    """
    x0, y0, x1, y1 = box
    return [
        int(LAYOUTLM_COORD_SCALE * (x0 / orig_width)),
        int(LAYOUTLM_COORD_SCALE * (y0 / orig_height)),
        int(LAYOUTLM_COORD_SCALE * (x1 / orig_width)),
        int(LAYOUTLM_COORD_SCALE * (y1 / orig_height)),
    ]


def process_example(example):
    orig_w = example[COLUMN_ORIG_WIDTH]
    orig_h = example[COLUMN_ORIG_HEIGHT]

    raw_boxes = example[COLUMN_BBOXES]
    xyxy_boxes = [convert_box_xywh_to_xyxy(b) for b in raw_boxes]
    norm_boxes = [normalize_box(b, orig_w, orig_h) for b in xyxy_boxes]

    return {
        "words": example[COLUMN_TEXTS],       # moi phan tu = 1 "dong" text, dung nhu 1 "tu" don gian hoa
        "bboxes_normalized": norm_boxes,
        "ner_tags": example[COLUMN_CATEGORIES],
    }


def process_and_save():
    print("Dang liet ke va load dataset tu nhanh refs/convert/parquet...")
    data_files = discover_parquet_files()
    dataset = load_dataset("parquet", data_files=data_files)

    print("Dang xu ly bbox (line-level) + normalize toa do theo original_width/height...")
    processed = {}
    for split in dataset.keys():
        processed[split] = dataset[split].map(
            process_example,
            desc=f"Processing split={split}",
        )

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for split, ds in processed.items():
        save_path = os.path.join(OUTPUT_DIR, split)
        ds.save_to_disk(save_path)
        print(f"Da luu split '{split}' ({len(ds)} mau) vao: {save_path}")

    # 'categories' van giu nguyen ClassLabel voi day du ten 11 lop (da xac
    # nhan qua output thuc te), nen lay ten lop truc tiep tu day, khong can
    # anh xa thu cong.
    names = dataset["train"].features[COLUMN_CATEGORIES].feature.names
    id2label = {str(i): name for i, name in enumerate(names)}
    label2id = {name: i for i, name in enumerate(names)}
    with open(os.path.join(OUTPUT_DIR, "label_map.json"), "w", encoding="utf-8") as f:
        json.dump({"id2label": id2label, "label2id": label2id}, f, ensure_ascii=False, indent=2)
    print(f"Da luu label_map.json voi {len(names)} lop: {names}")

    print("\nHoan tat Giai doan B. Dataset da san sang cho 02_train_layoutlmv3.py.")
    print(f"Duong dan: {OUTPUT_DIR}")
    return processed


if __name__ == "__main__":
    process_and_save()
