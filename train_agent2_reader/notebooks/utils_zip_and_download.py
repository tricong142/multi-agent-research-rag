"""
utils_zip_and_download.py
=========================
Script ho tro nen thu muc model da train tren Kaggle va tao link tai ve may local.

Cach dung:
1. Chay file nay trong mot cell moi tren Kaggle Notebook sau khi 01_train_layoutlmv3.py chay xong.
2. Hoac chay truc tiep trong terminal Kaggle: python notebooks/utils_zip_and_download.py
3. Sau khi nen xong:
   - Cach 1: Click truc tiep vao link HTML FileLink hien tren output cell.
   - Cach 2: O cot "Output" ben phai man hinh Kaggle (panel Data), re chuot vao file
             layoutlmv3_doclaynet_model.zip, click bieu tuong 3 cham (...) va chon "Download".
"""

import os
import shutil
from IPython.display import HTML, FileLink, display

# ---------------------------------------------------------------------------
# CAU HINH
# ---------------------------------------------------------------------------
SOURCE_DIR = "/kaggle/working/layoutlmv3_doclaynet_model"
OUTPUT_ZIP_BASE = "/kaggle/working/layoutlmv3_doclaynet_model"  # shutil se tu them duoi .zip


def get_dir_size_mb(path: str) -> float:
    """Tinh tong dung luong thu muc theo MB."""
    total_bytes = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if os.path.exists(fp):
                total_bytes += os.path.getsize(fp)
    return total_bytes / (1024 * 1024)


def zip_and_create_download_link():
    # 1. Kiem tra thu muc nguon
    if not os.path.exists(SOURCE_DIR):
        print(f"[LOI] Khong tim thay thu muc: {SOURCE_DIR}")
        print("Hay chac chan rang 01_train_layoutlmv3.py da chay xong va da luu model.")
        return

    files = os.listdir(SOURCE_DIR)
    dir_size = get_dir_size_mb(SOURCE_DIR)
    print(f"=== THU MUC NGUON ===")
    print(f"Duong dan : {SOURCE_DIR}")
    print(f"Dung luong: {dir_size:.2f} MB")
    print(f"So file   : {len(files)} files ({', '.join(files[:6])}...)")

    # 2. Tien hanh nen zip
    zip_file_path = f"{OUTPUT_ZIP_BASE}.zip"
    print(f"\nDang nen thu muc sang file .zip: {zip_file_path} ...")
    shutil.make_archive(
        base_name=OUTPUT_ZIP_BASE,
        format="zip",
        root_dir=SOURCE_DIR,
    )

    zip_size = os.path.getsize(zip_file_path) / (1024 * 1024)
    print(f"-> Nen thanh cong! Dung luong file zip: {zip_size:.2f} MB")

    # 3. Tao download link
    zip_filename = os.path.basename(zip_file_path)
    print(f"\n=== HUONG DAN TAI VE MAY ===")
    print(f"1. Cach 1 (Khuyen dung tren Kaggle):")
    print(f"   Nhin sang cot ben phai (tab 'Data' -> muc 'Output').")
    print(f"   Re chuot vao file '{zip_filename}' -> click dau 3 cham (...) -> chon 'Download'.")
    print(f"\n2. Cach 2: Click vao link ben duoi de tai truc tiep:")

    try:
        display(FileLink(zip_filename))
        display(
            HTML(
                f'<a href="{zip_filename}" download="{zip_filename}" '
                f'style="background-color: #20beff; color: white; padding: 8px 16px; '
                f'text-decoration: none; border-radius: 4px; font-weight: bold; display: inline-block; margin-top: 8px;">'
                f'📥 Click de tai {zip_filename} ({zip_size:.1f} MB)</a>'
            )
        )
    except Exception as e:
        print(f"(Luu y: display HTML chi hoat dong trong moi truong Jupyter Notebook: {e})")


if __name__ == "__main__":
    zip_and_create_download_link()
