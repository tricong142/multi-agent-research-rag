from typing import Literal, Any
from langgraph.graph import StateGraph, START, END

from core.state import AgentState
from core.config import settings
from utils.logger import logger

# =====================================================================
# LAZY IMPORT: Các Agent class được import tại đây nhưng KHÔNG khởi tạo
# singleton tại module level. Việc khởi tạo chỉ xảy ra khi gọi
# build_research_rag_graph(), cho phép project import được ngay cả khi
# các node.py vẫn là stub (raise NotImplementedError).
# =====================================================================

from agents.agent1_retrieval.node import RetrievalAgent
from agents.agent2_reader.node import ReaderAgent
from agents.agent3_summarizer.node import SummarizerAgent
from agents.agent4_fact_checker.node import FactCheckerAgent
from agents.agent5_writer.node import WriterAgent


# ===================== NODE FUNCTIONS =====================

def orchestrator_router_node(state: AgentState) -> dict[str, Any]:
    """
    Orchestrator Router Node:
    Đọc query, xác định intent và chuẩn bị state ban đầu cho đồ thị.
    """
    query = state.get("query", "")
    retry_count = state.get("retry_count", 0)
    logger.info(f"[Orchestrator] Khởi động luồng cho query: '{query}' (retry_count: {retry_count})")
    
    intent = "academic_research"
    trace = {
        "node": "Orchestrator",
        "action": "route_to_retrieval",
        "intent": intent,
        "retry_count": retry_count
    }
    return {
        "intent": intent,
        "retry_count": retry_count,
        "reasoning_trace": [trace]
    }


def retrieval_node(state: AgentState) -> dict[str, Any]:
    return _agents["retrieval"].run(state)


def reader_node(state: AgentState) -> dict[str, Any]:
    return _agents["reader"].run(state)


def summarizer_node(state: AgentState) -> dict[str, Any]:
    return _agents["summarizer"].run(state)


def fact_checker_node(state: AgentState) -> dict[str, Any]:
    return _agents["fact_checker"].run(state)


def retry_loop_node(state: AgentState) -> dict[str, Any]:
    """
    Node trung gian xử lý vòng lặp tầng ngoài:
    Tăng retry_count += 1 khi Fact-Checker trả về contradict hoặc not_enough_info.
    """
    current_retry = state.get("retry_count", 0) + 1
    logger.warning(f"[Orchestrator Self-Correction] Phát hiện phản biện! Tăng retry_count lên {current_retry}/3")
    
    trace = {
        "node": "Orchestrator_SelfCorrection",
        "action": "increment_retry",
        "new_retry_count": current_retry
    }
    return {
        "retry_count": current_retry,
        "reasoning_trace": [trace]
    }


def escalation_node(state: AgentState) -> dict[str, Any]:
    """
    Escalation Node (Lối thoát an toàn):
    Kích hoạt khi retry_count >= 3 mà vẫn không đạt kiểm chứng factual grounding.
    Trả về câu trả lời tốt nhất hiện có kèm cảnh báo độ tin cậy thấp.
    """
    logger.error("[Escalation] Đã chạm giới hạn retry (3 lần). Kích hoạt cảnh báo độ tin cậy thấp!")
    answer = state.get("answer", "Không thể tìm thấy đủ tài liệu hỗ trợ.")
    warning_report = (
        f"# CẢNH BÁO ĐỘ TIN CẬY THẤP (LOW CONFIDENCE REPORT)\n\n"
        f"> **Lưu ý:** Câu trả lời dưới đây chưa vượt qua được vòng kiểm chứng Fact-Check sau 3 lần thử lại.\n\n"
        f"### Nội dung sơ bộ:\n{answer}\n\n"
        f"### Khuyến nghị:\nCần cung cấp thêm tài liệu hoặc thu hẹp phạm vi câu hỏi."
    )
    
    trace = {
        "node": "EscalationNode",
        "action": "escalate_with_warning",
        "confidence": "low"
    }
    return {
        "confidence": "low",
        "final_report": warning_report,
        "reasoning_trace": [trace]
    }


def writer_node(state: AgentState) -> dict[str, Any]:
    return _agents["writer"].run(state)


# ===================== CONDITIONAL EDGES =====================

def route_after_retrieval(state: AgentState) -> Literal["reader_node", "summarizer_node"]:
    """
    Rẽ nhánh: Nếu truy vấn có kèm file PDF thì qua Reader Agent, ngược lại đi thẳng tới Summarizer.
    """
    if state.get("pdf_path"):
        logger.info("[Routing] Phát hiện file PDF -> Chuyển hướng tới Reader Agent.")
        return "reader_node"
    logger.info("[Routing] Không có PDF -> Đi thẳng tới Summarizer Agent.")
    return "summarizer_node"


def route_after_fact_check(state: AgentState) -> Literal["writer_node", "retry_loop_node", "escalation_node"]:
    """
    Rẽ nhánh điều kiện tầng Orchestrator:
    - Nếu support -> Sang Writer Agent
    - Nếu contradict / not_enough_info:
        + Nếu retry_count >= 3 -> Sang Escalation node
        + Ngược lại -> Tăng retry và quay về Retrieval Agent
    """
    label = state.get("fact_check_label", "not_enough_info")
    retry_count = state.get("retry_count", 0)
    
    if label == "support":
        logger.info("[Routing] Fact-check: SUPPORT -> Tiến hành viết báo cáo cuối cùng.")
        return "writer_node"
        
    if retry_count >= settings.MAX_ORCHESTRATOR_RETRY:
        logger.warning(f"[Routing] Đã retry {retry_count} lần -> Chuyển sang Escalation Node.")
        return "escalation_node"
        
    logger.info(f"[Routing] Fact-check: {label} (retry {retry_count}/3) -> Quay lại Retrieval Agent.")
    return "retry_loop_node"


# ===================== BUILD GRAPH =====================

# Registry chứa các agent singleton — chỉ được populate khi gọi build_research_rag_graph()
_agents: dict[str, Any] = {}


def build_research_rag_graph():
    """
    Xây dựng và biên dịch đồ thị LangGraph.

    LƯU Ý: Hàm này sẽ khởi tạo tất cả 5 Agent singleton. Nếu bất kỳ agent nào
    vẫn là stub (raise NotImplementedError), hàm này sẽ vẫn chạy được vì
    NotImplementedError chỉ raise khi gọi agent.run(), không phải khi __init__().
    Tuy nhiên, khi chạy graph thực tế, node sẽ crash tại agent chưa hiện thực.
    """
    # Khởi tạo agents (lazy — chỉ tại thời điểm build graph, không phải module load)
    _agents["retrieval"] = RetrievalAgent()
    _agents["reader"] = ReaderAgent()
    _agents["summarizer"] = SummarizerAgent()
    _agents["fact_checker"] = FactCheckerAgent()
    _agents["writer"] = WriterAgent()

    workflow = StateGraph(AgentState)
    
    # Thêm các Node
    workflow.add_node("orchestrator_router", orchestrator_router_node)
    workflow.add_node("retrieval_node", retrieval_node)
    workflow.add_node("reader_node", reader_node)
    workflow.add_node("summarizer_node", summarizer_node)
    workflow.add_node("fact_checker_node", fact_checker_node)
    workflow.add_node("retry_loop_node", retry_loop_node)
    workflow.add_node("escalation_node", escalation_node)
    workflow.add_node("writer_node", writer_node)
    
    # Thêm các Edge cố định và có điều kiện
    workflow.add_edge(START, "orchestrator_router")
    workflow.add_edge("orchestrator_router", "retrieval_node")
    
    # Retrieval -> (Reader hoặc Summarizer)
    workflow.add_conditional_edges(
        "retrieval_node",
        route_after_retrieval,
        {
            "reader_node": "reader_node",
            "summarizer_node": "summarizer_node"
        }
    )
    
    workflow.add_edge("reader_node", "summarizer_node")
    workflow.add_edge("summarizer_node", "fact_checker_node")
    
    # Fact-Checker -> (Writer, Retry Loop, hoặc Escalation)
    workflow.add_conditional_edges(
        "fact_checker_node",
        route_after_fact_check,
        {
            "writer_node": "writer_node",
            "retry_loop_node": "retry_loop_node",
            "escalation_node": "escalation_node"
        }
    )
    
    # Vòng lặp phản hồi quay lại Retrieval
    workflow.add_edge("retry_loop_node", "retrieval_node")
    
    # Kết thúc
    workflow.add_edge("writer_node", END)
    workflow.add_edge("escalation_node", END)
    
    return workflow.compile()
