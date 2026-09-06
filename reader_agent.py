"""
reader_agent.py
=================
Router + Self-Critique Loop cho pipeline doc tai lieu PDF, ket hop:
  - Heuristic Guardrails: quy tac tat dinh, RE, chay TRUOC de loc cac
    truong hop RO RANG - khong can goi LLM, tiet kiem chi phi/do tre.
  - LLM Chain-of-Thought (Gemini, xem reader_policy.py): chi xu ly cac
    truong hop MO HO ma heuristic don gian khong the quyet dinh chac
    chan, va dung de danh gia chat luong ket qua (critique) khi ket qua
    khong ro rang tot/xau.

LUONG XU LY 1 TRANG PDF:
  1. Trich xuat dac trung heuristic (co text layer khong, so block, ty
     le anh/text...).
  2. QUYET DINH TOOL:
     a. KHONG co text layer -> chac chan la scan -> chon ocr_fallback
        NGAY (Heuristic Guardrail, khong goi LLM).
     b. Co text layer VA layout RO RANG don gian (it block, khong bang/
        hinh) -> chon alt_segmentation NGAY (Heuristic Guardrail).
     c. Con lai (truong hop MO HO) -> goi Gemini Router de quyet dinh
        co Chain-of-Thought.
  3. Chay tool da chon.
  4. SELF-CRITIQUE:
     a. Heuristic Guardrail truoc: ket qua RO RANG loi (rong hoan toan,
        confidence qua thap) -> fallback NGAY sang tool khac, khong can LLM.
     b. Neu khong ro rang tot/xau -> goi Gemini Critique de danh gia va
        quyet dinh accept/retry.
  5. Lap lai toi da MAX_RETRIES lan, log ro ly do moi lan fallback.
"""

import logging
from typing import List, Optional, Tuple

import fitz  # PyMuPDF

from tools.common_schema import ExtractedBlock
from tools.tool_alt_segmentation import extract_with_pymupdf
from tools.tool_ocr_fallback import extract_with_ocr

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("reader_agent")

MAX_RETRIES = 3
SIMPLE_LAYOUT_BLOCK_THRESHOLD = 15  # <= nguong nay coi la layout don gian (Guardrail)
MIN_ACCEPTABLE_CONFIDENCE = 0.15    # < nguong nay coi la ket qua ro rang loi (Guardrail)

# Chuoi fallback mac dinh khi Gemini Critique khong cho goi y cu the
# (vd suggested_action="fail" nhung van con duong khac de thu).
_DEFAULT_FALLBACK_CHAIN = {
    "alt_segmentation": "ocr_fallback",
    "ocr_fallback": "layoutlmv3",
    "layoutlmv3": None,  # het duong fallback
}

_NEXT_TOOL_FROM_ACTION = {
    "retry_with_ocr_fallback": "ocr_fallback",
    "retry_with_layoutlmv3": "layoutlmv3",
    "retry_with_alt_segmentation": "alt_segmentation",
}


class ReaderAgent:
    def __init__(self, layoutlmv3_model_dir: Optional[str] = None):
        self._layoutlmv3_tool = None
        self._layoutlmv3_model_dir = layoutlmv3_model_dir

    def _get_layoutlmv3_tool(self):
        """Lazy-load model LayoutLMv3 - chi load khi thuc su can dung lan dau,
        tranh ton VRAM/thoi gian khoi dong cho cac truong hop khong can den."""
        if self._layoutlmv3_tool is None:
            if not self._layoutlmv3_model_dir:
                raise RuntimeError(
                    "Chua cung cap layoutlmv3_model_dir khi khoi tao ReaderAgent, "
                    "khong the dung tool layoutlmv3."
                )
            from tools.tool_layoutlmv3 import LayoutLMv3Tool

            self._layoutlmv3_tool = LayoutLMv3Tool(self._layoutlmv3_model_dir)
        return self._layoutlmv3_tool

    def _extract_heuristic_features(self, pdf_path: str, page_no: int) -> dict:
        doc = fitz.open(pdf_path)
        page = doc[page_no]
        has_text = len(page.get_text("text").strip()) > 20
        blocks = page.get_text("blocks")
        images = page.get_images(full=True)
        page_area = page.rect.width * page.rect.height

        image_area_ratio = 0.0
        for img in images:
            try:
                bbox = page.get_image_bbox(img)
                image_area_ratio += (bbox.width * bbox.height) / page_area
            except Exception:
                # Mot so anh embed khong lay duoc bbox truc tiep (vd anh
                # dung chung nhieu lan trong file) - bo qua, khong lam
                # hong ca pipeline vi 1 loi nho khi uoc luong heuristic.
                continue

        page_width, page_height = page.rect.width, page.rect.height
        doc.close()
        return {
            "has_text_layer": has_text,
            "avg_block_count": len(blocks),
            "image_area_ratio": round(min(image_area_ratio, 1.0), 3),
            "page_width": page_width,
            "page_height": page_height,
        }

    def _decide_tool(self, features: dict) -> str:
        if not features["has_text_layer"]:
            logger.info("Guardrail: khong co text layer -> chon ocr_fallback (khong goi LLM)")
            return "ocr_fallback"

        if (
            features["avg_block_count"] <= SIMPLE_LAYOUT_BLOCK_THRESHOLD
            and features["image_area_ratio"] < 0.1
        ):
            logger.info("Guardrail: layout don gian -> chon alt_segmentation (khong goi LLM)")
            return "alt_segmentation"

        # Truong hop mo ho -> goi Gemini Router (import cuc bo de tranh
        # phu thuoc google-genai khi khong can dung LLM).
        from reader_policy import get_router_decision

        decision = get_router_decision(features)
        logger.info(
            f"Gemini Router chon '{decision.chosen_tool}' "
            f"(confidence={decision.confidence:.2f}): {decision.reasoning}"
        )
        return decision.chosen_tool

    def _run_tool(self, tool_name: str, pdf_path: str, page_no: int) -> List[ExtractedBlock]:
        if tool_name == "alt_segmentation":
            return extract_with_pymupdf(pdf_path, page_numbers=[page_no])
        elif tool_name == "ocr_fallback":
            return extract_with_ocr(pdf_path, page_numbers=[page_no])
        elif tool_name == "layoutlmv3":
            return self._get_layoutlmv3_tool().extract(pdf_path, page_numbers=[page_no])
        raise ValueError(f"Khong nhan dien duoc tool: {tool_name}")

    def _critique(
        self, tool_name: str, blocks: List[ExtractedBlock], features: dict
    ) -> Tuple[bool, Optional[str], str]:
        """Tra ve (is_acceptable, next_tool_neu_khong_dat, ly_do)."""
        if not blocks:
            return (
                False,
                _DEFAULT_FALLBACK_CHAIN.get(tool_name),
                "Ket qua rong hoan toan (Heuristic Guardrail)",
            )

        confidences = [b.confidence for b in blocks if b.confidence is not None]
        avg_conf = sum(confidences) / len(confidences) if confidences else None

        if avg_conf is not None and avg_conf < MIN_ACCEPTABLE_CONFIDENCE:
            return (
                False,
                _DEFAULT_FALLBACK_CHAIN.get(tool_name),
                f"Confidence trung binh qua thap ({avg_conf:.2f}) (Heuristic Guardrail)",
            )

        # Khong ro rang tot/xau -> goi Gemini Critique
        from reader_policy import get_critique

        summary = {
            "source_tool": tool_name,
            "num_blocks": len(blocks),
            "avg_confidence": avg_conf,
            "sample_texts": [b.text for b in blocks[:5]],
            "page_width": features["page_width"],
            "page_height": features["page_height"],
        }
        result = get_critique(summary)
        logger.info(
            f"Gemini Critique: is_acceptable={result.is_acceptable}, "
            f"suggested_action={result.suggested_action}: {result.reasoning}"
        )

        if result.is_acceptable:
            return True, None, result.reasoning

        next_tool = _NEXT_TOOL_FROM_ACTION.get(result.suggested_action)
        if next_tool is None:
            next_tool = _DEFAULT_FALLBACK_CHAIN.get(tool_name)
        return False, next_tool, result.reasoning

    def process_page(self, pdf_path: str, page_no: int = 0) -> dict:
        features = self._extract_heuristic_features(pdf_path, page_no)
        tool_name = self._decide_tool(features)

        attempts = []
        blocks: List[ExtractedBlock] = []

        for _ in range(MAX_RETRIES):
            blocks = self._run_tool(tool_name, pdf_path, page_no)
            is_acceptable, next_tool, reason = self._critique(tool_name, blocks, features)
            attempts.append({"tool": tool_name, "reason": reason, "accepted": is_acceptable})

            if is_acceptable:
                return {
                    "blocks": blocks,
                    "final_tool": tool_name,
                    "attempts": attempts,
                    "success": True,
                }

            if not next_tool:
                logger.warning(f"Het duong fallback sau tool '{tool_name}'. Dung lai.")
                break

            logger.info(f"Fallback: '{tool_name}' -> '{next_tool}' (ly do: {reason})")
            tool_name = next_tool

        return {
            "blocks": blocks,
            "final_tool": tool_name,
            "attempts": attempts,
            "success": False,
        }


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Cach dung: python reader_agent.py <duong_dan_pdf> [so_trang]")
        sys.exit(1)

    pdf_path_arg = sys.argv[1]
    page_no_arg = int(sys.argv[2]) if len(sys.argv) > 2 else 0

    agent = ReaderAgent(layoutlmv3_model_dir="./layoutlmv3_doclaynet_model")
    result = agent.process_page(pdf_path_arg, page_no_arg)

    print(f"\nKet qua cuoi cung: success={result['success']}, final_tool={result['final_tool']}")
    print(f"So block trich xuat: {len(result['blocks'])}")
    for a in result["attempts"]:
        print(f"  - {a}")
