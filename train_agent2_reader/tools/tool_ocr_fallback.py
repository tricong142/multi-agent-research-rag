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
    results: List[ExtractedBlock] = []
    scale = _PDF_POINT_DPI / dpi
    with fitz.open(pdf_path) as doc:
        pages = page_numbers if page_numbers is not None else range(len(doc))
        for page_no in pages:
            with render_page_to_image(doc[page_no], dpi=dpi) as image:
                data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT, timeout=60)
            # Preserve paragraph evidence instead of returning isolated word chunks.
            paragraphs = {}
            for i, word in enumerate(data["text"]):
                text = word.strip()
                if not text:
                    continue
                try:
                    confidence = max(0.0, float(data["conf"][i])) / 100.0
                except (ValueError, TypeError):
                    confidence = 0.0
                x, y, w, h = (data[key][i] for key in ("left", "top", "width", "height"))
                bbox = [x * scale, y * scale, (x + w) * scale, (y + h) * scale]
                key = (data["block_num"][i], data["par_num"][i])
                group = paragraphs.setdefault(key, {"words": [], "confidences": [], "bbox": bbox})
                group["words"].append(text)
                group["confidences"].append(confidence)
                previous = group["bbox"]
                group["bbox"] = [min(previous[0], bbox[0]), min(previous[1], bbox[1]),
                                 max(previous[2], bbox[2]), max(previous[3], bbox[3])]
            for group in paragraphs.values():
                results.append(ExtractedBlock(
                    page_no=page_no, text=" ".join(group["words"]), bbox=group["bbox"], label=None,
                    confidence=sum(group["confidences"]) / len(group["confidences"]), source_tool="ocr_fallback"))
    return results


def average_confidence(blocks: List[ExtractedBlock]) -> float:
    """Dung o reader_agent.py cho buoc self-critique bang heuristic."""
    confs = [b.confidence for b in blocks if b.confidence is not None]
    return sum(confs) / len(confs) if confs else 0.0
