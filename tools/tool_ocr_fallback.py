"""
tools/tool_ocr_fallback.py
=============================
Cong cu OCR fallback cho PDF dang scan / anh mo, khong co text layer.
Dung PyMuPDF render trang thanh anh (DPI cao de OCR chinh xac hon), roi
dung Tesseract (pytesseract) de nhan dang text tung tu, kem confidence
co san tu Tesseract.

Yeu cau he thong da cai dat Tesseract BINARY (pytesseract chi la python
wrapper, khong tu cai binary):
    Ubuntu/Debian: sudo apt-get install tesseract-ocr
    Kaggle: thuong da co san, kiem tra bang `!which tesseract`

Cai dat python: pip install pytesseract pillow pymupdf
"""

import io
from typing import List, Optional

import fitz  # PyMuPDF
import pytesseract
from PIL import Image

from .common_schema import ExtractedBlock

DEFAULT_DPI = 300  # DPI cao hon -> OCR chinh xac hon nhung cham hon
_PDF_POINT_DPI = 72  # DPI mac dinh cua he toa do point trong PDF


def render_page_to_image(page: "fitz.Page", dpi: int = DEFAULT_DPI) -> Image.Image:
    zoom = dpi / _PDF_POINT_DPI
    matrix = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix)
    return Image.open(io.BytesIO(pix.tobytes("png")))


def extract_with_ocr(
    pdf_path: str,
    page_numbers: Optional[List[int]] = None,
    dpi: int = DEFAULT_DPI,
) -> List[ExtractedBlock]:
    doc = fitz.open(pdf_path)
    results: List[ExtractedBlock] = []
    pages = page_numbers if page_numbers is not None else range(len(doc))
    # He so quy doi toa do pixel (theo DPI render) ve lai he toa do point
    # cua PDF goc, de bbox tra ve nhat quan voi 2 tool con lai.
    scale = _PDF_POINT_DPI / dpi

    for page_no in pages:
        page = doc[page_no]
        image = render_page_to_image(page, dpi=dpi)
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        n = len(data["text"])

        for i in range(n):
            text = data["text"][i].strip()
            if not text:
                continue

            conf_raw = data["conf"][i]
            try:
                # Tesseract tra conf tu 0-100, hoac -1 neu khong xac dinh duoc.
                confidence = max(0.0, float(conf_raw)) / 100.0
            except (ValueError, TypeError):
                confidence = 0.0

            x, y, w, h = (
                data["left"][i],
                data["top"][i],
                data["width"][i],
                data["height"][i],
            )
            bbox = [x * scale, y * scale, (x + w) * scale, (y + h) * scale]

            results.append(
                ExtractedBlock(
                    page_no=page_no,
                    text=text,
                    bbox=bbox,
                    label=None,
                    confidence=confidence,
                    source_tool="ocr_fallback",
                )
            )

    doc.close()
    return results


def average_confidence(blocks: List[ExtractedBlock]) -> float:
    """Dung o reader_agent.py cho buoc self-critique bang heuristic."""
    confs = [b.confidence for b in blocks if b.confidence is not None]
    return sum(confs) / len(confs) if confs else 0.0
