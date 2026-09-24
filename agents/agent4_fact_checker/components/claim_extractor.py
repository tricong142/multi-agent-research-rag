import re
from typing import Optional, Callable


class ClaimExtractor:
    """
    Bộ bóc tách luận điểm nguyên tử (Atomic Claim Extractor).
    Chuyển đổi văn bản câu trả lời thành danh sách các mệnh đề chân lý độc lập (truth-evaluable propositions).
    Hỗ trợ xử lý câu ghép phức, liên từ đối lập, loại bỏ markdown và bảo vệ từ viết tắt.
    """

    # Danh sách các từ viết tắt học thuật và tiếng Việt thông dụng
    ABBREVIATIONS = (
        r"\b(?:e\.g|i\.e|et al|fig|no|vs|dr|prof|tp|th|ts|đh|v\.v|approx|dept|vol)\."
    )

    # Các liên từ dùng để tách vế câu ghép độc lập
    CONJUNCTION_SPLITTERS = [
        # Tiếng Việt
        r"\s+(?:đồng thời|ngoài ra|hơn nữa|mặt khác|tuy nhiên|ngược lại)\s+",
        r"(?<=[,;])\s+(?:nhưng|song|mà)\s+",
        r"\s+(?:mặc dù|dẫu rằng)\s+([^,;]+)[,;]\s*(?:nhưng|song)?\s*",
        # Tiếng Anh
        r"\s+(?:furthermore|additionally|moreover|on the other hand|however|nevertheless)\s+",
        r"(?<=[,;])\s+(?:but|yet|while|whereas)\s+",
    ]

    def __init__(self, min_claim_length: int = 15, llm_decomposer: Optional[Callable[[str], list[str]]] = None):
        self.min_claim_length = min_claim_length
        self.llm_decomposer = llm_decomposer

        # Các mẫu câu mở đầu giao tiếp, dẫn dắt cần loại bỏ
        self.intro_patterns = [
            r"^(dưới đây là|theo như|như đã biết|tổng hợp lại|cụ thể là|có thể thấy|tóm lại)[,:\s]*",
            r"^(theo tài liệu|dựa trên văn bản|nghiên cứu chỉ ra rằng|kết quả nghiên cứu cho thấy|tài liệu cho biết)[,:\s]*",
            r"^(based on the document|according to|in conclusion|specifically|the results show that|it is known that)[,:\s]*",
        ]

    def clean_sentence(self, sentence: str) -> str:
        """Làm sạch câu, loại bỏ markdown bold/bullet và các từ mở đầu sáo rỗng."""
        text = sentence.strip()
        
        # 1. Loại bỏ các ký tự markdown danh sách, tiêu đề và đầu mục
        text = re.sub(r"^(?:\s*[-*•#>]+\s*)+", "", text)
        text = re.sub(r"^\*{1,2}(?:\[[Cc]?\d+\]|[Ll]uận [đd]iểm \d+|\d+[\.\)])\*{1,2}[:\s]*", "", text)
        text = re.sub(r"^(?:\[[Cc]?\d+\]|[Ll]uận [đd]iểm \d+|\d+[\.\)])[:\s]*", "", text)
        
        # 2. Loại bỏ các từ mở đầu giao tiếp
        for pattern in self.intro_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)
            
        return text.strip()

    def _decompose_complex_sentence(self, sentence: str) -> list[str]:
        """Phân rã câu ghép phức chứa các liên từ nhượng bộ/đẳng lập thành các vế độc lập."""
        current_clauses = [sentence]
        for pattern in self.CONJUNCTION_SPLITTERS:
            new_clauses = []
            for clause in current_clauses:
                parts = re.split(pattern, clause, flags=re.IGNORECASE)
                for p in parts:
                    clean_p = p.strip().rstrip(".,;")
                    if len(clean_p) >= self.min_claim_length:
                        new_clauses.append(clean_p)
            current_clauses = new_clauses
        return current_clauses

    def extract_claims(self, text: str) -> list[str]:
        """
        Phân tách đoạn văn bản thành danh sách các claims độc lập.
        Nếu có cung cấp llm_decomposer, ưu tiên dùng LLM; ngược lại dùng bộ tách cú pháp tối ưu.
        """
        if not text or not text.strip():
            return []

        # Nếu có hook LLM Decomposer chuyên dụng
        if self.llm_decomposer is not None:
            try:
                llm_claims = self.llm_decomposer(text)
                if llm_claims:
                    return [self.clean_sentence(c) for c in llm_claims if len(c.strip()) >= self.min_claim_length]
            except Exception:
                pass  # Fallback về bộ phân tích cú pháp

        # Bảo vệ các từ viết tắt trước khi tách câu
        protected_text = re.sub(
            self.ABBREVIATIONS,
            lambda m: m.group(0).replace(".", "<DOT>"),
            text,
            flags=re.IGNORECASE
        )

        # 1. Tách câu mức độ 1: Dựa trên dấu chấm, ngắt dòng
        raw_sentences = re.split(r"(?<=[.?!])\s+|\n+", protected_text)
        claims = []

        for raw_s in raw_sentences:
            raw_s = raw_s.replace("<DOT>", ".")
            cleaned = self.clean_sentence(raw_s)
            
            if len(cleaned) < self.min_claim_length:
                continue

            if cleaned.endswith("?") or cleaned.endswith("!"):
                continue

            # 2. Tách câu mức độ 2: Phân rã câu ghép phức
            atomic_clauses = self._decompose_complex_sentence(cleaned)
            for cl in atomic_clauses:
                cl_cleaned = self.clean_sentence(cl).rstrip(".,;")
                if len(cl_cleaned) >= self.min_claim_length and cl_cleaned not in claims:
                    claims.append(cl_cleaned)

        # Fallback an toàn nếu văn bản hợp lệ nhưng không qua được các bộ lọc
        if not claims and len(text.strip()) >= self.min_claim_length:
            claims.append(self.clean_sentence(text.strip()).rstrip(".,;"))

        return claims
