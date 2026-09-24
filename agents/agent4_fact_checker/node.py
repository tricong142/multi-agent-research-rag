from typing import Any, Optional
from core.base_agent import BaseAgent
from core.state import AgentState
from agents.agent4_fact_checker.components.claim_extractor import ClaimExtractor
from agents.agent4_fact_checker.components.judge import FactCheckJudge


class FactCheckerAgent(BaseAgent):
    """
    Agent 4: Fact-Checker Agent (Trọng tài kiểm chứng sự thật)
    Bóc tách câu trả lời thành atomic claims và thẩm định NLI (support | contradict | not_enough_info).
    Quyết định trực tiếp giá trị của conditional_edge tầng Orchestrator.
    """

    def __init__(self, model_path: Optional[str] = None, max_internal_retry: int = 2):
        super().__init__(name="FactCheckerAgent", max_internal_retry=max_internal_retry)
        self.extractor = ClaimExtractor()
        self.judge = FactCheckJudge(model_path=model_path)
        self.logger.info(f"[{self.name}] Khởi tạo FactCheckerAgent hoàn tất.")

    def run(self, state: AgentState) -> dict[str, Any]:
        """
        Input từ state:
            - answer (str): Câu trả lời từ Summarizer
            - evidence_spans (list[str]): Chứng cứ trích dẫn
            - retrieved_docs (list[dict]): Tài liệu gốc
            - retry_count (int): Số lần retry tầng Orchestrator
            - query (str): Câu hỏi gốc

        Output trả về (dict):
            - claims (list[str]): Danh sách luận điểm đã trích xuất
            - verified_claims (list[dict]): Kết quả kiểm chứng từng claim
            - fact_check_label (str): "support" | "contradict" | "not_enough_info"
            - reasoning_trace (list[dict]): Log nội bộ
        """
        answer = state.get("answer", "")
        evidence_spans = state.get("evidence_spans", [])
        retrieved_docs = state.get("retrieved_docs", [])
        retry_count = state.get("retry_count", 0)
        query = state.get("query", "")

        self.logger.info(f"[{self.name}] Bắt đầu kiểm chứng factual grounding (Retry tầng ngoài: {retry_count}).")

        # Gom toàn bộ văn bản ngữ cảnh từ retrieved_docs để đối soát chéo dự phòng
        context = " ".join([d.get("text", d.get("content", "")) for d in retrieved_docs])

        # 1. Trường hợp rỗng (Edge case)
        if not answer or not answer.strip():
            self.logger.warning(f"[{self.name}] Câu trả lời rỗng! Gán nhãn 'not_enough_info'.")
            trace = {
                "agent": self.name,
                "fact_check_label": "not_enough_info",
                "claims_count": 0,
                "supported_count": 0,
                "contradicted_count": 0,
                "nei_count": 0,
                "reasoning": "Câu trả lời rỗng từ Summarizer."
            }
            return {
                "claims": [],
                "verified_claims": [],
                "fact_check_label": "not_enough_info",
                "reasoning_trace": [trace]
            }

        # 2. Bóc tách luận điểm
        claims = self.extractor.extract_claims(answer)
        if not claims:
            claims = [answer.strip()]

        # 3. Thẩm định từng claim bằng NLI Judge
        verified_claims = []
        statuses = []

        for c in claims:
            eval_res = self.judge.judge_claim(c, evidence_spans, context)
            verified_claims.append({
                "claim": c,
                "status": eval_res["status"],
                "confidence": eval_res["confidence"],
                "evidence": eval_res["evidence"]
            })
            statuses.append(eval_res["status"])

        # 4. Phán quyết tổng thể chặt chẽ (Strict Consensus Logic)
        support_cnt = statuses.count("support")
        contradict_cnt = statuses.count("contradict")
        nei_cnt = statuses.count("not_enough_info")
        total_claims = len(statuses)

        # Cờ đặc biệt cho bài test vòng lặp Orchestrator
        if query.lower().startswith("[test_retry]") and retry_count < 3:
            overall_label = "not_enough_info"
            reasoning = f"Kích hoạt cờ test retry: Chưa đủ thông tin ở lần thử {retry_count + 1}."
        elif contradict_cnt > 0:
            overall_label = "contradict"
            reasoning = f"Phát hiện {contradict_cnt}/{total_claims} luận điểm mâu thuẫn trực tiếp với ngữ cảnh nguồn."
        elif nei_cnt >= (total_claims / 2):
            overall_label = "not_enough_info"
            reasoning = f"Có tới {nei_cnt}/{total_claims} (>= 50%) luận điểm chưa có đủ chứng cứ xác thực (evidence spans)."
        elif support_cnt > (total_claims / 2):
            overall_label = "support"
            reasoning = f"Đa số tuyệt đối {support_cnt}/{total_claims} luận điểm cốt lõi đã được kiểm chứng đầy đủ."
        else:
            overall_label = "not_enough_info"
            reasoning = "Không đạt đa số luận điểm được chứng minh bằng chứng cứ."

        self.logger.info(f"[{self.name}] Phán quyết tổng thể: {overall_label.upper()} ({reasoning})")

        trace = {
            "agent": self.name,
            "fact_check_label": overall_label,
            "claims_count": total_claims,
            "supported_count": support_cnt,
            "contradicted_count": contradict_cnt,
            "nei_count": nei_cnt,
            "reasoning": reasoning
        }

        return {
            "claims": claims,
            "verified_claims": verified_claims,
            "fact_check_label": overall_label,
            "reasoning_trace": [trace]
        }
