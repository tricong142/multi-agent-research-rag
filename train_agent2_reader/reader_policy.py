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
import math
import json
import logging
import random
import re
import threading
import time
import uuid
from email.utils import parsedate_to_datetime
from typing import List, Literal

import httpx
from pydantic import BaseModel, Field
from google import genai
from google.genai import errors

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")

_client = None
_request_lock = threading.Lock()
_last_request_at = None
logger = logging.getLogger("reader_api")
RETRYABLE_HTTP_CODES = frozenset({408, 429, 500, 502, 503, 504})


class ReaderApiBudgetExceeded(TimeoutError):
    """The logical API call exhausted its deadline; no extracted text is accepted."""


def request_policy() -> dict:
    interval = float(os.environ.get("GEMINI_REQUEST_INTERVAL_SECONDS", "0"))
    budget = float(os.environ.get("GEMINI_CALL_BUDGET_SECONDS", "240"))
    if not math.isfinite(interval) or interval < 0:
        raise ValueError("GEMINI_REQUEST_INTERVAL_SECONDS must be finite and nonnegative")
    if not math.isfinite(budget) or budget <= 0:
        raise ValueError("GEMINI_CALL_BUDGET_SECONDS must be finite and positive")
    return {"max_attempts": 3, "request_timeout_seconds": 30.0,
            "call_budget_seconds": budget, "request_interval_seconds": interval,
            "backoff_initial_seconds": 1.0, "backoff_max_seconds": 4.0,
            "sdk_attempts": 1}


def get_client() -> "genai.Client":
    global _client
    if _client is None:
        _client = genai.Client(
            api_key=os.environ.get("GEMINI_API_KEY"),
            http_options={
                "timeout": 30_000,  # milliseconds per request, not the whole PDF
                "retry_options": {
                    "attempts": 1,  # reader_policy owns the one total retry budget
                },
            },
        )
    return _client


def _retry_after(exc) -> float:
    response = getattr(exc, "response", None)
    value = getattr(response, "headers", {}).get("Retry-After")
    if value is None:
        return 0.0
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        try:
            seconds = parsedate_to_datetime(value).timestamp() - time.time()
        except (TypeError, ValueError, OverflowError):
            return 0.0
    return max(0.0, seconds) if math.isfinite(seconds) else 0.0


def safe_error_details(exc) -> dict:
    """Allowlist structured quota metadata; never log messages or arbitrary metadata."""
    payload = getattr(exc, "details", None)  # google-genai 2.22 APIError response JSON
    if not isinstance(payload, dict):
        return {}
    error = payload.get("error", payload)
    if not isinstance(error, dict):
        return {}

    def identifier(value):
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,160}", value):
            return None
        secrets = [os.environ.get(name) for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "HF_TOKEN")]
        if any(secret and secret in value for secret in secrets) or re.search(
                r"AIza|hf_|gh[pousr]_|projects/|users/|@|https?:", value):
            return None
        return value

    result = {}
    status = identifier(error.get("status"))
    if status:
        result["status"] = status
    details = error.get("details", [])
    for detail in details[:20] if isinstance(details, list) else []:
        if not isinstance(detail, dict):
            continue
        kind = detail.get("@type")
        if kind == "type.googleapis.com/google.rpc.ErrorInfo":
            info = {key: identifier(detail.get(key)) for key in ("reason", "domain")}
            result["error_info"] = {k: v for k, v in info.items() if v is not None}
        elif kind == "type.googleapis.com/google.rpc.QuotaFailure":
            violations = detail.get("violations", [])
            clean = []
            for violation in violations[:20] if isinstance(violations, list) else []:
                if not isinstance(violation, dict):
                    continue
                item = {key: identifier(violation.get(key)) for key in ("quotaMetric", "quotaId")}
                value = violation.get("quotaValue")
                if type(value) in (int, float) and 0 <= value <= 10**16 and math.isfinite(value):
                    item["quotaValue"] = value
                elif isinstance(value, str) and re.fullmatch(r"[0-9]{1,16}", value):
                    item["quotaValue"] = value
                dimensions = violation.get("quotaDimensions", {})
                if isinstance(dimensions, dict):
                    item["quotaDimensions"] = {k: v for k in ("model", "location")
                                                if (v := identifier(dimensions.get(k))) is not None}
                clean.append({k: v for k, v in item.items() if v is not None})
            result["quota_violations"] = clean
        elif kind == "type.googleapis.com/google.rpc.RetryInfo":
            duration = detail.get("retryDelay")
            if isinstance(duration, str) and re.fullmatch(r"[0-9]{1,9}(?:\.[0-9]{1,9})?s", duration):
                result["retry_delay_seconds"] = max(result.get("retry_delay_seconds", 0), float(duration[:-1]))
    return result


def _emit(event, on_attempt):
    # Do not include prompts, response bodies, URLs, headers or exception messages.
    logger.info("%s", json.dumps(event, sort_keys=True))
    if on_attempt is not None:
        on_attempt(dict(event))


def _generate_content(*, stage, on_attempt=None, **kwargs):
    """One retry owner, shared pacing for every transport attempt, safe metadata.

    The synchronous SDK uses HTTPX phase timeouts, not hard wall-clock cancellation.
    The deadline prevents new attempts and rejects late responses; the outer worker
    timeout remains necessary for a stalled native/network call.
    """
    global _last_request_at
    policy = request_policy()
    started = time.monotonic()
    deadline = started + policy["call_budget_seconds"]
    call_id = uuid.uuid4().hex
    client = get_client()
    retry_at = started
    previous_code = None

    def budget_exceeded(attempts):
        _emit({"event": "reader_api_stop", "call_id": call_id, "stage": stage,
               "model": kwargs["model"], "attempt_count": attempts,
               "http_status": previous_code, "outcome": "deadline_exceeded",
               "total_elapsed_ms": round((time.monotonic() - started) * 1000, 3)}, on_attempt)
        exc = ReaderApiBudgetExceeded("Reader API call deadline exceeded")
        if previous_code is not None:
            exc.code = previous_code
        raise exc

    for attempt in range(1, policy["max_attempts"] + 1):
        wait_started = time.monotonic()
        remaining = deadline - wait_started
        if remaining <= 0 or not _request_lock.acquire(timeout=remaining):
            budget_exceeded(attempt - 1)
        try:
            now = time.monotonic()
            pacing_at = (_last_request_at + policy["request_interval_seconds"]
                         if _last_request_at is not None else now)
            eligible_at = max(now, pacing_at, retry_at)
            if eligible_at >= deadline:
                budget_exceeded(attempt - 1)
            if eligible_at > now:
                time.sleep(eligible_at - now)
            request_started = time.monotonic()
            if request_started >= deadline:
                budget_exceeded(attempt - 1)
            _last_request_at = request_started
        finally:
            _request_lock.release()
        timeout_ms = max(1, int(min(policy["request_timeout_seconds"],
                                    deadline - request_started) * 1000))
        config = dict(kwargs.get("config", {}))
        config["http_options"] = {"timeout": timeout_ms, "retry_options": {"attempts": 1}}
        event = {"event": "reader_api_attempt", "call_id": call_id, "stage": stage,
                 "model": kwargs["model"], "attempt": attempt, "timeout_ms": timeout_ms,
                 "wait_ms": round((request_started - wait_started) * 1000, 3),
                 "started_elapsed_ms": round((request_started - started) * 1000, 3)}
        try:
            response = client.models.generate_content(**{**kwargs, "config": config})
        except Exception as exc:
            code = getattr(exc, "code", None)
            previous_code = code if type(code) is int else None
            now = time.monotonic()
            retryable = ((isinstance(exc, errors.APIError) and code in RETRYABLE_HTTP_CODES)
                         or isinstance(exc, httpx.TransportError))
            exhausted = attempt == policy["max_attempts"]
            backoff = min(policy["backoff_max_seconds"],
                          policy["backoff_initial_seconds"] * 2 ** (attempt - 1)
                          + random.uniform(0.0, 1.0))
            error_details = safe_error_details(exc)
            retry_after = max(_retry_after(exc), error_details.get("retry_delay_seconds", 0)) if retryable else 0.0
            retry_at = now + max(backoff, retry_after)
            outcome = ("deadline_exceeded" if now >= deadline or (retryable and retry_at >= deadline)
                       else "non_retryable" if not retryable
                       else "exhausted" if exhausted else "retry")
            event.update(http_status=previous_code, error_type=type(exc).__name__, outcome=outcome,
                         error_details=error_details,
                         elapsed_ms=round((now - request_started) * 1000, 3),
                         total_elapsed_ms=round((now - started) * 1000, 3),
                         retry_after_ms=round(retry_after * 1000, 3),
                         next_backoff_ms=round(backoff * 1000, 3) if outcome == "retry" else 0.0)
            _emit(event, on_attempt)
            if outcome == "deadline_exceeded":
                budget_exceeded(attempt)
            if outcome != "retry":
                raise
            continue
        now = time.monotonic()
        # SDK 2.22.0 exposes response headers but not the successful HTTP status.
        previous_code = None
        event.update(http_status=None, outcome="success" if now < deadline else "deadline_exceeded",
                     elapsed_ms=round((now - request_started) * 1000, 3),
                     total_elapsed_ms=round((now - started) * 1000, 3))
        _emit(event, on_attempt)
        if now >= deadline:
            budget_exceeded(attempt)
        return response


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


def get_router_decision(heuristic_features: dict, *, on_attempt=None) -> RouterDecision:
    """
    heuristic_features vi du:
        {"has_text_layer": True, "avg_block_count": 42,
         "image_area_ratio": 0.05, "page_width": 609, "page_height": 793}
    """
    prompt = (
        f"{ROUTER_SYSTEM_PROMPT}\n\n"
        f"Dac trung heuristic cua trang can quyet dinh:\n{heuristic_features}"
    )
    response = _generate_content(
        stage="router", on_attempt=on_attempt,
        model=GEMINI_MODEL,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": RouterDecision,
        },
    )
    return response.parsed


def get_critique(extraction_summary: dict, *, on_attempt=None) -> CritiqueResult:
    """
    extraction_summary vi du:
        {"source_tool": "ocr_fallback", "num_blocks": 12,
         "avg_confidence": 0.42, "sample_texts": ["...", "..."],
         "page_width": 609, "page_height": 793}
    """
    prompt = (
        f"{CRITIQUE_SYSTEM_PROMPT}\n\n"
        f"Tom tat ket qua trich xuat can danh gia:\n{extraction_summary}"
    )
    response = _generate_content(
        stage="critique", on_attempt=on_attempt,
        model=GEMINI_MODEL,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": CritiqueResult,
        },
    )
    return response.parsed
