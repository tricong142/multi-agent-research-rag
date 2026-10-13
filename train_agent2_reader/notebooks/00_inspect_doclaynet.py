"""
00_inspect_doclaynet.py
=========================
GIAI DOAN A - CHI INSPECT, KHONG XU LY.

Muc dich duy nhat cua file nay: tai dataset pierreguillou/DocLayNet-base
va IN RA toan bo schema that (features + 1 sample mau), de ban xac nhan
dung ten cot truoc khi chay sang file 01_process_doclaynet.py.

Vi tai lieu cong khai cua dataset nay khong liet ke day du, chinh xac
ten tung cot da xu ly san (mot phan README chi mo ta file COCO goc,
khong phai ban da xu ly cua pierreguillou), KHONG duoc gia dinh ten cot
ma phai xac nhan bang mat thuong qua output cua file nay.

Chay tren Kaggle Notebook (co GPU T4 + internet). Cai dat truoc:
    !pip install -q -U datasets huggingface_hub pillow

GHI CHU VE LOI "Dataset scripts are no longer supported":
    Repo pierreguillou/DocLayNet-base con luu lai file loading script kieu cu
    (DocLayNet-base.py). HuggingFace da ngung ho tro co che nay (ly do bao mat:
    script co the chay code tuy y khi load_dataset() duoc goi). Cac phien ban
    `datasets` moi tren Kaggle se bao loi RuntimeError khi gap truong hop nay,
    khong co cach nao bat lai duoc bang tham so.

    Giai phap: KHONG goi load_dataset(DATASET_NAME) truc tiep, va CUNG KHONG
    tim file parquet o nhanh "main" (nhanh main chi co script .py bi chan,
    khong co parquet). HuggingFace Datasets Server tu dong convert MOI
    dataset con dung loading script sang Parquet va publish vao MOT NHANH
    RIENG ten "refs/convert/parquet" tren cung repo (nhanh nay khong hien
    tren giao dien Files mac dinh, phai chi dinh revision moi thay duoc).
    Do do can chi dinh revision="refs/convert/parquet" khi liet ke file
    VA khi load_dataset, thi moi thay duoc cac file .parquet that.
"""

from huggingface_hub import HfApi
from datasets import load_dataset

DATASET_NAME = "pierreguillou/DocLayNet-base"
PARQUET_REVISION = "refs/convert/parquet"  # nhanh auto-convert cua HF Datasets Server


def discover_parquet_files():
    """
    Liet ke chinh xac cac file .parquet that su co trong nhanh
    "refs/convert/parquet" qua HfApi, khong doan duong dan. Sau do phan loai
    theo split (train/validation/test) dua tren ten file, va tra ve dict
    data_files de dua vao load_dataset().
    """
    api = HfApi()
    all_files = api.list_repo_files(
        DATASET_NAME, repo_type="dataset", revision=PARQUET_REVISION
    )
    parquet_files = [f for f in all_files if f.endswith(".parquet")]

    print(f"=== TAT CA FILE .parquet TIM THAY O NHANH '{PARQUET_REVISION}' ===")
    for f in parquet_files:
        print(f"  {f}")

    if not parquet_files:
        raise RuntimeError(
            f"Khong tim thay file .parquet nao trong repo '{DATASET_NAME}' "
            f"o nhanh '{PARQUET_REVISION}'. Co the HF chua convert xong, hoac "
            "dataset nay khong duoc auto-convert. Hay vao "
            f"https://huggingface.co/datasets/{DATASET_NAME}/tree/{PARQUET_REVISION} "
            "de kiem tra truc tiep va bao lai."
        )

    data_files = {"train": [], "validation": [], "test": []}
    for f in parquet_files:
        lower = f.lower()
        # URL phai tro dung nhanh refs/convert/parquet, khong phai main
        url = f"https://huggingface.co/datasets/{DATASET_NAME}/resolve/{PARQUET_REVISION}/{f}"
        if "train" in lower:
            data_files["train"].append(url)
        elif "valid" in lower or "-val" in lower or "_val" in lower:
            data_files["validation"].append(url)
        elif "test" in lower:
            data_files["test"].append(url)
        else:
            print(f"  [CANH BAO] Khong xac dinh duoc split cho file: {f} "
                  "(ten file khong chua 'train'/'valid'/'test'). Bo qua file nay, "
                  "kiem tra thu cong neu can.")

    # Bo cac split rong (vi du neu repo khong co tap validation rieng)
    data_files = {split: files for split, files in data_files.items() if files}

    print("\n=== PHAN LOAI SPLIT ===")
    for split, files in data_files.items():
        print(f"  {split}: {len(files)} file")

    return data_files


def inspect_dataset():
    data_files = discover_parquet_files()

    print(f"\nDang load dataset tu cac file parquet da phat hien "
          f"(nhanh {PARQUET_REVISION})...")
    # Luu y: khi data_files da la URL day du (https://.../resolve/<revision>/...),
    # tham so revision o day khong bat buoc nua vi URL da tro dung noi roi,
    # nhung van truyen vao cho ro rang va phong truong hop can thiet.
    dataset = load_dataset("parquet", data_files=data_files)

    print("\n=== CAC SPLIT CO SAN ===")
    print(list(dataset.keys()))

    print("\n=== SCHEMA (features) CUA SPLIT 'train' ===")
    print(dataset["train"].features)

    print("\n=== 1 SAMPLE MAU (de xem cau truc that cua du lieu) ===")
    sample = dataset["train"][0]
    for key, value in sample.items():
        if key == "image":
            print(f"  {key}: <PIL Image, size={value.size if hasattr(value, 'size') else '?'}>")
        elif isinstance(value, (list, tuple)) and len(value) > 5:
            print(f"  {key}: list do dai {len(value)}, 3 phan tu dau = {value[:3]}")
        else:
            print(f"  {key}: {value}")

    # LUU Y QUAN TRONG: khi load truc tiep tu file parquet (thay vi qua
    # loading script goc), ten 11 lop nhan (vd "Text", "Title", "Table"...)
    # thuong duoc dinh nghia BEN TRONG loading script (DocLayNet-base.py)
    # ma chung ta dang KHONG dung (vi bi chan). Do do cot 'categories' rat
    # co the chi con la so nguyen tho (int64), KHONG con ten lop kem theo.
    if "categories" in dataset["train"].features:
        feature = dataset["train"].features["categories"]
        try:
            names = feature.feature.names
            print("\n=== 11 LOP NHAN (id2label) - lay duoc tu ClassLabel ===")
            for idx, name in enumerate(names):
                print(f"  {idx}: {name}")
        except AttributeError:
            print(
                "\n[CANH BAO QUAN TRONG] Cot 'categories' chi la so nguyen tho, "
                "KHONG con giu ten 11 lop (day la he qua cua viec load truc tiep "
                "tu parquet, bo qua loading script goc noi dinh nghia ten lop).\n"
                "Gia tri so cot 'categories' cho sample dau tien la: "
                f"{sample.get('categories')}\n"
                "Can anh xa lai id2label THU CONG. Theo paper goc DocLayNet "
                "(Pfitzmann et al., 2022), thu tu 11 lop CHUAN nhu sau (can doi "
                "chieu voi gia tri so thuc te ban thay o tren de xac nhan dung "
                "thu tu, vi thu tu co the khac giua cac phien ban xu ly):\n"
                "  1: Caption, 2: Footnote, 3: Formula, 4: List-item, "
                "5: Page-footer, 6: Page-header, 7: Picture, 8: Section-header, "
                "9: Table, 10: Text, 11: Title"
            )
    else:
        print("\n[CANH BAO] Khong tim thay cot 'categories'. Xem danh sach features "
              "o tren de tim ten cot nhan thuc te (co the la 'category_id', "
              "'labels', v.v.).")

    print(
        "\n>>> BUOC TIEP THEO: doi chieu ten cot ban vua thay o tren voi cac "
        "bien COLUMN_* dau file 01_process_doclaynet.py. Neu khac, sua lai "
        "COLUMN_* truoc khi chay file do."
    )

    return dataset


if __name__ == "__main__":
    inspect_dataset()
