"""
tools/tool_alt_segmentation.py
=================================
Cong cu trich xuat don gian danh cho PDF co text layer sach (khong phai
scan), layout don gian (it cot, it bang, it hinh xen ke). Dung PyMuPDF
(fitz) doc block text truc tiep tu PDF - khong OCR, khong GPU, rat nhanh.

KHONG thuc hien phan loai layout (khong gan nhan Table/Title/Text...).
Neu can phan loai, dung tools/tool_layoutlmv3.py.

Cai dat: pip install pymupdf
"""

import fitz  # PyMuPDF
from typing import List, Optional
from .common_schema import ExtractedBlock


def extract_with_pymupdf(
    pdf_path: str, page_numbers: Optional[List[int]] = None
) -> List[ExtractedBlock]:
    """Trich block text tho tu PDF, khong phan loai layout."""
    doc = fitz.open(pdf_path)
    results: List[ExtractedBlock] = []
    pages = page_numbers if page_numbers is not None else range(len(doc))

    for page_no in pages:
        page = doc[page_no]
        blocks = page.get_text("blocks")  # (x0,y0,x1,y1,text,block_no,block_type)
        for b in blocks:
            x0, y0, x1, y1, text = b[0], b[1], b[2], b[3], b[4]
            text = text.strip()
            if not text:
                continue
            results.append(
                ExtractedBlock(
                    page_no=page_no,
                    text=text,
                    bbox=[x0, y0, x1, y1],
                    label=None,
                    # Text layer PDF (khong phai OCR) nen tin cay noi dung
                    # text la tuyet doi - khong co khai niem "do nhieu" o day.
                    confidence=1.0,
                    source_tool="alt_segmentation",
                )
            )

    doc.close()
    return results


def has_native_text_layer(pdf_path: str, min_chars: int = 20) -> bool:
    """
    Heuristic dung o reader_agent.py de quyet dinh PDF co can OCR khong.
    Tra ve True neu tim thay it nhat `min_chars` ky tu text trong bat ky
    trang nao (dung cho ca PDF nhieu trang, dung sau khi tim thay du).
    """
    doc = fitz.open(pdf_path)
    total_chars = 0
    for page in doc:
        total_chars += len(page.get_text("text").strip())
        if total_chars >= min_chars:
            doc.close()
            return True
    doc.close()
    return False
