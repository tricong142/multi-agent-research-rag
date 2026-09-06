"""
tools/common_schema.py
=========================
Dinh dang du lieu chung ma CA 3 tool (tool_alt_segmentation, tool_ocr_fallback,
tool_layoutlmv3) deu tra ve, de reader_agent.py xu ly dong nhat bat ke tool
nao duoc goi. File nay khong co trong cay thu muc ban dua ban dau, nhung can
thiet de dam bao 3 tool "noi cung 1 ngon ngu" du lieu.
"""
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class ExtractedBlock:
    page_no: int
    text: str
    bbox: List[float]                   # [x0, y0, x1, y1] theo he toa do point cua PDF goc
    label: Optional[str] = None         # ten lop layout - CHI co gia tri tu tool_layoutlmv3
    confidence: Optional[float] = None  # 0.0 - 1.0
    source_tool: str = ""

    def to_dict(self) -> dict:
        return {
            "page_no": self.page_no,
            "text": self.text,
            "bbox": self.bbox,
            "label": self.label,
            "confidence": self.confidence,
            "source_tool": self.source_tool,
        }
