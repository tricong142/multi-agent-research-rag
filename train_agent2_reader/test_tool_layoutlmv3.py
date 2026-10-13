"""
test_tool_layoutlmv3.py
=======================
Script kiem thu doc lap (Unit Test) cho LayoutLMv3Tool tren may Local.

Cach chay:
    python test_tool_layoutlmv3.py
Hoac voi file PDF cua ban:
    python test_tool_layoutlmv3.py duong_dan_toi_file.pdf
"""

import os
import sys
import fitz  # PyMuPDF
from tools.tool_layoutlmv3 import LayoutLMv3Tool

MODEL_DIR = "./layoutlmv3_doclaynet_model"


def create_dummy_sample_pdf(output_path="sample.pdf") -> str:
    """Tao 1 file PDF mau neu nguoi dung chua co san file PDF de test."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # Kho A4 chuan
    
    # 1. Header / Title
    page.insert_text((50, 70), "TAP DOAN CONG NGHIEP - VIEN THONG QUAN DOI (VIETTEL)", fontsize=11)
    page.insert_text((50, 110), "BAO CAO KET QUA KINH DOANH QUY 1", fontsize=16)
    
    # 2. Section Header
    page.insert_text((50, 160), "1. TONG QUAN DOANH THU VA LOI NHUAN", fontsize=13)
    
    # 3. Paragraph Text
    page.insert_text((50, 195), "Trong quy 1, tong doanh thu hop nhat cua tap doan dat muc tang truong cao.", fontsize=10)
    page.insert_text((50, 215), "Cac linh vuc giai phap so, ha tang Cloud va Document AI dong gop ty trong lon.", fontsize=10)
    page.insert_text((50, 235), "He thong bóc tach ho so tu dong ReaderAgent hoan thanh xu ly hang trieu trang van ban.", fontsize=10)
    
    # 4. Footer
    page.insert_text((50, 800), "Trang 1 / 1 - Tai lieu luu hanh noi bo", fontsize=9)
    
    doc.save(output_path)
    doc.close()
    print(f"-> Da tao file PDF mau tu dong: {output_path}")
    return output_path


def main():
    print("=" * 65)
    print("   KIEM THU DOC LAP TOOL LAYOUTLMV3 (LOCAL UNIT TEST)")
    print("=" * 65)

    # 1. Kiem tra thu muc model
    if not os.path.exists(MODEL_DIR):
        print(f"[LOI] Khong tim thay thu muc model tai: {MODEL_DIR}")
        print("Hay chac chan ban da giai nen file zip vao dung thu muc nay!")
        return

    # 2. Khoi tao tool
    print(f"\n[1/3] Dang nap mo hinh tu '{MODEL_DIR}'...")
    try:
        tool = LayoutLMv3Tool(model_dir=MODEL_DIR)
        print(f"-> Nap thanh cong! Device dang dung: {tool.device}")
        print(f"-> Danh sach nhan da hoc ({len(tool.id2label)} nhan):")
        for k, v in sorted(tool.id2label.items()):
            print(f"     {k:2d} -> {v}")
    except Exception as e:
        print(f"[LOI khi nap model]: {e}")
        return

    # 3. Xac dinh file PDF de test
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
    else:
        pdf_path = "sample.pdf"
        if not os.path.exists(pdf_path):
            create_dummy_sample_pdf(pdf_path)

    if not os.path.exists(pdf_path):
        print(f"[LOI] Khong tim thay file PDF: {pdf_path}")
        return

    # 4. Trich xuat va phan loai layout
    print(f"\n[2/3] Dang phan tich layout trang 0 cua file '{pdf_path}'...")
    try:
        blocks = tool.extract_page(pdf_path, page_no=0)
        print(f"-> Trich xuat thanh cong {len(blocks)} khoi (blocks)!")
    except Exception as e:
        print(f"[LOI khi trich xuat]: {e}")
        return

    # 5. In ket qua
    print(f"\n[3/3] KET QUA PHAN LOAI BO CUC (LAYOUT CLASSIFICATION):")
    print("-" * 65)
    for i, b in enumerate(blocks, 1):
        clean_text = b.text.strip().replace("\n", " ")
        print(f"{i:2d}. [{b.label.upper():14s}] (Conf: {b.confidence*100:5.1f}%) | {clean_text[:60]}")
    print("-" * 65)
    print("\n[CHUC MUNG] Tool LayoutLMv3 hoat dong hoan hao tren may Local!")


if __name__ == "__main__":
    main()
