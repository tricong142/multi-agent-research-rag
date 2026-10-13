"""
tools/tool_layoutlmv3.py
===========================
Cong cu phan loai layout dung model LayoutLMv3 da fine-tune tren DocLayNet
(xem notebooks/01_train_layoutlmv3.py). Dung cho PDF co layout PHUC TAP
(nhieu cot, bang, hinh xen ke van ban) - noi tool_alt_segmentation.py qua
don gian de phan loai dung cac vung layout.

THIET KE QUAN TRONG (suy ra truc tiep tu schema dataset thuc te da xu ly o
01_process_doclaynet.py, KHONG bia dat): moi "word" dua vao processor luc
train THUC CHAT LA CA MOT DONG TEXT (line-level, tu cot 'texts' cua
DocLayNet-base), KHONG PHAI tung tu rieng le. Vi vay o buoc inference nay,
BAT BUOC phai gom cac tu PyMuPDF trich duoc thanh tung DONG (group theo
block_no + line_no) truoc khi dua vao model, thay vi dua tung tu don le -
neu khong, phan phoi du lieu dau vao se lech so voi luc train va model se
cho ket qua kem chinh xac han nhieu.

Cai dat: pip install pymupdf torch transformers pillow
"""

import io
import json
import os
from collections import defaultdict
from typing import List, Optional, Tuple

import fitz  # PyMuPDF
import torch
from PIL import Image
from transformers import LayoutLMv3ForTokenClassification, LayoutLMv3Processor

from .common_schema import ExtractedBlock

RENDER_DPI = 150  # du de model "nhin" bo cuc trang, khong can cao nhu OCR
_PDF_POINT_DPI = 72
_COORD_SCALE = 1000  # LayoutLMv3 yeu cau bbox chuan hoa ve thang 0-1000


class LayoutLMv3Tool:
    def __init__(self, model_dir: str, device: Optional[str] = None):
        """
        model_dir: thu muc chua model + processor da luu tu
                   trainer.save_model() / processor.save_pretrained()
                   o notebooks/01_train_layoutlmv3.py (sau khi tai zip ve
                   tu Kaggle va giai nen ra local, xem utils_zip_and_download.py).
        """
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.processor = LayoutLMv3Processor.from_pretrained(model_dir, apply_ocr=False)
        self.model = LayoutLMv3ForTokenClassification.from_pretrained(model_dir).to(
            self.device
        )
        self.model.eval()
        self.id2label = self._load_id2label(model_dir)

    def _load_id2label(self, model_dir: str) -> dict:
        label_map_path = os.path.join(model_dir, "label_map.json")
        if os.path.exists(label_map_path):
            with open(label_map_path, "r", encoding="utf-8") as f:
                label_map = json.load(f)
            return {int(k): v for k, v in label_map["id2label"].items()}
        # Fallback: Trainer thuong tu luu id2label vao config.json khi model
        # duoc khoi tao voi tham so id2label o buoc train.
        return self.model.config.id2label

    def _render_page_image(self, page: "fitz.Page", dpi: int = RENDER_DPI) -> Image.Image:
        zoom = dpi / _PDF_POINT_DPI
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        return Image.open(io.BytesIO(pix.tobytes("png")))

    def _extract_lines(
        self, page: "fitz.Page"
    ) -> Tuple[List[str], List[List[float]]]:
        """Gom tu PyMuPDF thanh tung DONG (line-level) de khop cach train."""
        words = page.get_text("words")  # (x0,y0,x1,y1,word,block_no,line_no,word_no)
        lines = defaultdict(list)
        for x0, y0, x1, y1, word, block_no, line_no, word_no in words:
            lines[(block_no, line_no)].append((x0, y0, x1, y1, word_no, word))

        line_texts, line_boxes = [], []
        for key in sorted(lines.keys()):
            items = sorted(lines[key], key=lambda t: t[4])  # sap theo word_no trong dong
            text = " ".join(item[5] for item in items)
            x0 = min(item[0] for item in items)
            y0 = min(item[1] for item in items)
            x1 = max(item[2] for item in items)
            y1 = max(item[3] for item in items)
            line_texts.append(text)
            line_boxes.append([x0, y0, x1, y1])
        return line_texts, line_boxes

    def _normalize_boxes(
        self, boxes: List[List[float]], page_width: float, page_height: float
    ) -> List[List[int]]:
        page_width = max(page_width, 1.0)
        page_height = max(page_height, 1.0)
        norm = []
        for x0, y0, x1, y1 in boxes:
            nx0 = min(max(int(_COORD_SCALE * (x0 / page_width)), 0), 1000)
            ny0 = min(max(int(_COORD_SCALE * (y0 / page_height)), 0), 1000)
            nx1 = min(max(int(_COORD_SCALE * (x1 / page_width)), 0), 1000)
            ny1 = min(max(int(_COORD_SCALE * (y1 / page_height)), 0), 1000)
            if nx1 < nx0:
                nx0, nx1 = nx1, nx0
            if ny1 < ny0:
                ny0, ny1 = ny1, ny0
            norm.append([nx0, ny0, nx1, ny1])
        return norm

    def extract(
        self, pdf_path: str, page_numbers: Optional[List[int]] = None
    ) -> List[ExtractedBlock]:
        doc = fitz.open(pdf_path)
        results: List[ExtractedBlock] = []
        pages = page_numbers if page_numbers is not None else range(len(doc))

        for page_no in pages:
            page = doc[page_no]
            page_width, page_height = page.rect.width, page.rect.height

            texts, boxes = self._extract_lines(page)
            if not texts:
                continue

            image = self._render_page_image(page)
            norm_boxes = self._normalize_boxes(boxes, page_width, page_height)

            encoding = self.processor(
                image,
                texts,
                boxes=norm_boxes,
                truncation=True,
                padding="max_length",
                max_length=512,
                stride=64,
                return_overflowing_tokens=True,
                return_offsets_mapping=True,
                return_tensors="pt",
            )
            seen_word_idx = set()
            for window in range(len(encoding["input_ids"])):
                word_ids = encoding.word_ids(batch_index=window)
                # Run one window at a time. Metadata is not a model input;
                # the processor repeats pixel_values for each overflow window.
                model_inputs = {k: encoding[k][window:window + 1].to(self.device)
                                for k in ("input_ids", "attention_mask", "bbox", "token_type_ids")
                                if k in encoding}
                model_inputs["pixel_values"] = encoding["pixel_values"][window].unsqueeze(0).to(self.device)
                with torch.no_grad():
                    outputs = self.model(**model_inputs)
                probs = torch.softmax(outputs.logits[0], dim=-1)
                pred_ids = probs.argmax(dim=-1).tolist()
                confidences = probs.max(dim=-1).values.tolist()
                for token_idx, w_idx in enumerate(word_ids):
                    # Keep the first sub-token prediction per original line,
                    # including lines appearing in overlapping windows.
                    if w_idx is None or w_idx in seen_word_idx:
                        continue
                    if not 0 <= w_idx < len(texts):
                        raise RuntimeError("LayoutLMv3 tokenizer returned an invalid line index")
                    seen_word_idx.add(w_idx)
                    label_id = pred_ids[token_idx]
                    results.append(
                        ExtractedBlock(
                            page_no=page_no,
                            text=texts[w_idx],
                            bbox=boxes[w_idx],
                            label=self.id2label.get(label_id, str(label_id)),
                            confidence=confidences[token_idx],
                            source_tool="layoutlmv3",
                        )
                    )
            if len(seen_word_idx) != len(texts):
                doc.close()
                raise RuntimeError("LayoutLMv3 did not cover every input line")

        doc.close()
        return results

    def extract_page(self, pdf_path: str, page_no: int = 0) -> List[ExtractedBlock]:
        """Tien ich rut gon de trich xuat 1 trang don le."""
        return self.extract(pdf_path, page_numbers=[page_no])
