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
                return_tensors="pt",
            )
            # PHAI lay word_ids TRUOC khi tach encoding ra dict thuong va
            # chuyen sang device, vi word_ids() la method cua BatchEncoding,
            # khong con dung duoc sau khi da .items() ra dict + Tensor.to().
            word_ids = encoding.word_ids(batch_index=0)
            model_inputs = {k: v.to(self.device) for k, v in encoding.items()}

            with torch.no_grad():
                outputs = self.model(**model_inputs)
            logits = outputs.logits[0]  # (seq_len, num_labels)
            probs = torch.softmax(logits, dim=-1)
            pred_ids = probs.argmax(dim=-1).tolist()
            confidences = probs.max(dim=-1).values.tolist()

            seen_word_idx = set()
            for token_idx, w_idx in enumerate(word_ids):
                # w_idx la None cho token dac biet ([CLS], [SEP], padding).
                # Moi dong (word) co the bi tach thanh nhieu sub-token - chi
                # lay nhan cua SUB-TOKEN DAU TIEN cho moi dong (quy uoc pho
                # bien trong token classification).
                if w_idx is None or w_idx in seen_word_idx:
                    continue
                seen_word_idx.add(w_idx)
                if w_idx >= len(texts):
                    continue

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

        doc.close()
        return results

    def extract_page(self, pdf_path: str, page_no: int = 0) -> List[ExtractedBlock]:
        """Tien ich rut gon de trich xuat 1 trang don le."""
        return self.extract(pdf_path, page_numbers=[page_no])

