"""
shared/schemas.py

Định nghĩa DUY NHẤT các schema JSON output mà 5 agent phải học theo.
TẤT CẢ script sinh data (generate_*.py) và script train (train_*.py) của
5 agent PHẢI import từ file này, không tự định nghĩa lại field riêng.

LÝ DO: nếu mỗi agent tự định nghĩa JSON schema trong file riêng, rất dễ
xảy ra lệch tên field giữa lúc sinh data và lúc parse output khi serving
(vd sinh data dùng "is_relevant", nhưng code Retrieval Agent khi chạy
thật lại đọc "is_sufficient") -> lỗi âm thầm, khó phát hiện.
"""

from dataclasses import dataclass, asdict, field
import json


# ============ Agent 1: Retrieval ============
@dataclass
class RetrievalDecision:
    thought: str                 # chuỗi suy luận ngắn (Chain-of-Thought)
    tool_selected: str           # "bm25" | "dense" | "hyde" | "rewrite" | "decompose"
    critique_is_relevant: bool
    critique_reason: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


# ============ Agent 2: Reader ============
# Reader KHÔNG dùng JSON tự do như 4 agent còn lại - nó là bài toán
# token classification (gán nhãn cho từng token/box trong trang PDF).
# Nhãn cố định theo chuẩn DocBank/LayoutLMv3 (13 lớp gốc, rút gọn còn các
# lớp thực sự cần cho pipeline này):
READER_LABELS = [
    "O", "B-Title", "I-Title", "B-Abstract", "I-Abstract",
    "B-Table", "I-Table", "B-Figure", "I-Figure",
    "B-Equation", "I-Equation", "B-Reference", "I-Reference",
]


# ============ Agent 3: Summarizer ============
@dataclass
class SummarizerOutput:
    answer: str
    evidence_spans: list[str]
    critique_is_supported: bool
    critique_reason: str
    action_if_not_supported: str  # "rewrite" | "request_more_context" | "lower_confidence" | ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


# ============ Agent 4: Fact-Checker ============
FACTCHECK_LABELS = ["support", "contradict", "not_enough_info"]


@dataclass
class FactCheckOutput:
    label: str                    # 1 trong FACTCHECK_LABELS
    reasoning: str
    confidence_self_assessed: float  # 0.0-1.0, model tự đánh giá độ chắc chắn
    action_if_uncertain: str      # "expand_context" | "other_source" | "ask_retrieval" | ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


# ============ Agent 5: Writer ============
@dataclass
class WriterCritique:
    sentence: str
    grounded_in_claim_id: str | None   # id của verified_claim tương ứng, None nếu "mồ côi"
    action: str                        # "keep" | "delete" | "rewrite" | "request_new_claim"

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)
