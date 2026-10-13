"""Regenerate three original PDF fixtures and their page-level expected text."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import fitz
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parent
PDF_DIR = ROOT / "pdfs"


def draw_header(page: canvas.Canvas, title: str) -> None:
    page.setFont("Helvetica-Bold", 18)
    page.drawString(48, 790, title)
    page.setStrokeColorRGB(0.2, 0.35, 0.55)
    page.line(48, 776, 547, 776)


def make_text_pdf() -> None:
    page = canvas.Canvas(str(PDF_DIR / "simple_text.pdf"), pagesize=A4)
    draw_header(page, "Reader evaluation: text PDF")
    page.setFont("Helvetica", 13)
    page.drawString(48, 725, "The Aster trial enrolled 48 participants.")
    page.drawString(48, 700, "The study used four-fold cross-validation.")
    page.drawString(48, 675, "The treatment was evaluated against a control group.")
    page.showPage()
    draw_header(page, "Reader evaluation: second page")
    page.setFont("Helvetica", 13)
    page.drawString(48, 725, "Median inference latency was 210 milliseconds.")
    page.drawString(48, 700, "Results were measured on a held-out test set.")
    page.showPage()
    page.save()


def make_layout_pdf() -> None:
    page = canvas.Canvas(str(PDF_DIR / "two_columns_table.pdf"), pagesize=A4)
    draw_header(page, "Reader evaluation: two columns and table")
    page.setFont("Helvetica-Bold", 12)
    page.drawString(48, 742, "Treatment arm")
    page.drawString(310, 742, "Control arm")
    page.setFont("Helvetica", 10)
    left = ["Treatment group contained 24 participants.",
            "Participants received the active treatment."]
    right = ["Control group contained 24 participants.",
             "Participants received a placebo treatment."]
    left += [f"Treatment observation {i:02d}." for i in range(1, 9)]
    right += [f"Control observation {i:02d}." for i in range(1, 9)]
    for number, (left_line, right_line) in enumerate(zip(left, right)):
        y = 713 - number * 25
        page.drawString(48, y, left_line)
        page.drawString(310, y, right_line)
    page.setStrokeColorRGB(0.3, 0.3, 0.3)
    page.rect(48, 282, 499, 95)
    page.line(48, 345, 547, 345)
    page.line(48, 313, 547, 313)
    page.line(298, 282, 298, 377)
    page.setFont("Helvetica-Bold", 11)
    page.drawString(62, 354, "Metric")
    page.drawString(312, 354, "Value")
    page.setFont("Helvetica", 11)
    page.drawString(62, 322, "Model accuracy")
    page.drawString(312, 322, "0.82")
    page.drawString(62, 291, "Median latency")
    page.drawString(312, 291, "210 milliseconds")
    page.showPage()
    page.save()


def make_scan_pdf() -> None:
    with tempfile.TemporaryDirectory() as temp:
        source = Path(temp) / "source.pdf"
        page = canvas.Canvas(str(source), pagesize=A4)
        draw_header(page, "Reader evaluation: scanned page")
        page.setFont("Helvetica", 18)
        page.drawString(48, 705, "The scanned invoice total is 275 dollars.")
        page.drawString(48, 667, "The invoice date is 14 April 2025.")
        page.showPage()
        page.save()
        with fitz.open(source) as document:
            pixels = document[0].get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False)
            image = pixels.tobytes("png")
        with fitz.open() as scanned:
            target = scanned.new_page(width=A4[0], height=A4[1])
            target.insert_image(target.rect, stream=image)
            scanned.save(PDF_DIR / "scanned_page.pdf")


def main() -> None:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    make_text_pdf()
    make_layout_pdf()
    make_scan_pdf()
    rows = [
        {"pdf_path": "pdfs/simple_text.pdf", "layout": "simple_text", "expected_spans": [
            {"page_no": 0, "text": "The Aster trial enrolled 48 participants."},
            {"page_no": 0, "text": "The study used four-fold cross-validation."},
            {"page_no": 1, "text": "Median inference latency was 210 milliseconds."},
        ]},
        {"pdf_path": "pdfs/two_columns_table.pdf", "layout": "two_columns_table", "expected_spans": [
            {"page_no": 0, "text": "Treatment group contained 24 participants."},
            {"page_no": 0, "text": "Control group contained 24 participants."},
            {"page_no": 0, "text": "Model accuracy"},
            {"page_no": 0, "text": "0.82"},
        ]},
        {"pdf_path": "pdfs/scanned_page.pdf", "layout": "scan", "expected_spans": [
            {"page_no": 0, "text": "The scanned invoice total is 275 dollars."},
            {"page_no": 0, "text": "The invoice date is 14 April 2025."},
        ]},
    ]
    (ROOT / "reader_smoke_manifest.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
    with fitz.open(PDF_DIR / "scanned_page.pdf") as document:
        assert not document[0].get_text("text").strip(), "Scan fixture has an unexpected text layer"
    print(f"Generated {len(rows)} PDF fixtures in {PDF_DIR}")


if __name__ == "__main__":
    main()
