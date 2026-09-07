"""
reader_policy.py
==================
Prompt (Chain-of-Thought) + Schema du lieu (Pydantic) cho 2 vai tro cua
Google Gemini API trong reader_agent.py:
  1. LLM Router   - quyet dinh dung tool nao (layoutlmv3 / ocr_fallback /
     alt_segmentation) cho cac TRUONG HOP KHONG the quyet dinh chac chan
     chi bang heuristic don gian (xem reader_agent.py de biet khi nao
     agent goi den day thay vi tu quyet dinh).
  2. LLM Critique - danh gia chat luong ket qua trich xuat, quyet dinh
     accept hay retry voi tool khac.

SDK DANG DUNG: google-genai (SDK MOI cua Google, thay the goi
google-generativeai da bi deprecated). Cai dat:
    pip install -U google-genai

Xac thuc: dat bien moi truong GEMINI_API_KEY, client se tu dong doc:
    export GEMINI_API_KEY="..."

LUU Y VE TEN MODEL: danh sach model Gemini thay doi theo thoi gian. Bien
GEMINI_MODEL ben duoi doc tu bien moi truong de ban de dang doi model moi
nhat ma khong can sua code - kiem tra model hien co tai
https://ai.google.dev truoc khi chay.
"""

import os
from typing import List, Literal

from pydantic import BaseModel, Field
from google import genai

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")

_client = None


def get_client() -> "genai.Client":
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    return _client


# ---------------------------------------------------------------------------
# SCHEMA (Pydantic) - google-genai SDK ho tro truyen thang class Pydantic
# vao response_schema de ep model tra ve dung cau truc JSON, truy cap ket
# qua da parse san qua response.parsed.
# ---------------------------------------------------------------------------
class RouterDecision(BaseModel):
    chosen_tool: Literal["layoutlmv3", "ocr_fallback", "alt_segmentation"] = Field(
        description="Cong cu duoc chon de xu ly trang PDF nay"
    )
    reasoning: str = Field(
        description=(
            "Giai thich ngan gon (chain-of-thought) tai sao chon cong cu nay, "
            "dua tren cac dac trung heuristic da cung cap"
        )
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Do tin cay cua quyet dinh, tu 0.0 den 1.0"
    )


class CritiqueResult(BaseModel):
    is_acceptable: bool = Field(
        description="Ket qua trich xuat co dat chat luong chap nhan duoc khong"
    )
    issues: List[str] = Field(
        default_factory=list,
        description="Danh sach van de phat hien duoc (rong neu is_acceptable=True)",
    )
    suggested_action: Literal[
        "accept",
        "retry_with_ocr_fallback",
        "retry_with_layoutlmv3",
        "retry_with_alt_segmentation",
        "fail",
    ] = Field(description="Hanh dong de xuat tiep theo")
    reasoning: str = Field(
        description="Giai thich ngan gon (chain-of-thought) cho quyet dinh tren"
    )


# ---------------------------------------------------------------------------
# PROMPT (Chain-of-Thought)
# ---------------------------------------------------------------------------
ROUTER_SYSTEM_PROMPT = """Ban la mot ky su he thong dieu phoi (router) cho pipeline
trich xuat noi dung tai lieu PDF. Nhiem vu cua ban la chon 1 trong 3 cong cu
phu hop nhat cho 1 trang PDF, dua tren cac dac trung heuristic duoc cung cap.

3 cong cu san co:
- "alt_segmentation": PyMuPDF block parser, RE, NHANH, khong can GPU. Chi
  hieu qua khi trang co text layer sach VA layout DON GIAN (it cot, it
  bang, it hinh xen ke).
- "ocr_fallback": Tesseract OCR. BAT BUOC dung khi trang KHONG co text
  layer (file scan/anh). Cham hon alt_segmentation, do chinh xac phu
  thuoc chat luong anh scan.
- "layoutlmv3": Model Deep Learning da fine-tune tren DocLayNet, CHAM va
  TON GPU nhat nhung phan loai duoc CA cau truc layout (Table, Title,
  Section-header...). Chi nen dung khi layout PHUC TAP (nhieu cot, bang,
  hinh xen ke van ban) VA trang van CO text layer (model khong tu OCR anh).

Hay suy nghi tung buoc (chain-of-thought) truoc khi quyet dinh:
1. Trang co text layer khong?
2. Neu co, layout co don gian khong (dua tren so block, ty le anh/text)?
3. Dua tren 2 buoc tren, cong cu nao phu hop nhat?

Tra ve KET QUA CUOI CUNG dung theo dinh dang JSON schema da cho, KHONG tra
ve gi khac ngoai JSON."""


CRITIQUE_SYSTEM_PROMPT = """Ban la mot ky su QA (quality assurance) cho pipeline
trich xuat noi dung tai lieu PDF. Nhiem vu cua ban la danh gia xem ket qua
trich xuat (do 1 trong 3 cong cu tra ve) co dat chat luong chap nhan duoc
khong, dua tren cac chi so va mau du lieu duoc cung cap.

Cac dau hieu ket qua KEM chat luong can chu y:
- Van ban rong hoac qua it so voi kich thuoc trang.
- Do tin cay trung binh (confidence) qua thap.
- Van ban chua nhieu ky tu la/loi encoding (dau hieu OCR/parse sai).
- Bbox bat thuong (vd tat ca bbox trung nhau, hoac vuot ra ngoai trang).

Hay suy nghi tung buoc (chain-of-thought) truoc khi quyet dinh:
1. Cac chi so dinh luong (confidence trung binh, so luong block) co on khong?
2. Noi dung text mau co hop ly, doc duoc khong?
3. Neu co van de, nen retry voi cong cu nao se khac phuc duoc van de do?

Tra ve KET QUA CUOI CUNG dung theo dinh dang JSON schema da cho, KHONG tra
ve gi khac ngoai JSON."""


def get_router_decision(heuristic_features: dict) -> RouterDecision:
    """
    heuristic_features vi du:
        {"has_text_layer": True, "avg_block_count": 42,
         "image_area_ratio": 0.05, "page_width": 609, "page_height": 793}
    """
    client = get_client()
    prompt = (
        f"{ROUTER_SYSTEM_PROMPT}\n\n"
        f"Dac trung heuristic cua trang can quyet dinh:\n{heuristic_features}"
    )
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": RouterDecision,
        },
    )
    return response.parsed


def get_critique(extraction_summary: dict) -> CritiqueResult:
    """
    extraction_summary vi du:
        {"source_tool": "ocr_fallback", "num_blocks": 12,
         "avg_confidence": 0.42, "sample_texts": ["...", "..."],
         "page_width": 609, "page_height": 793}
    """
    client = get_client()
    prompt = (
        f"{CRITIQUE_SYSTEM_PROMPT}\n\n"
        f"Tom tat ket qua trich xuat can danh gia:\n{extraction_summary}"
    )
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": CritiqueResult,
        },
    )
    return response.parsed
