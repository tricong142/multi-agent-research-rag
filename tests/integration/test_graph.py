"""
Integration Tests cho LangGraph Pipeline.

LƯU Ý: Các test E2E (test_graph_standard_flow, test_graph_pdf_flow) hiện tại
bị SKIP vì các Agent node.py đang là stub rỗng (raise NotImplementedError).
Khi thành viên đã hiện thực xong agent của mình, hãy bỏ decorator @pytest.mark.skip
để kích hoạt lại test.

Test duy nhất chạy được ngay: test_graph_build_success — kiểm tra rằng
graph có thể được build thành công dù các agent chưa hiện thực.
"""
import pytest
from core.graph import build_research_rag_graph


def test_graph_build_success():
    """Kiểm tra graph có thể build thành công (import + khởi tạo agent stub không crash)."""
    app = build_research_rag_graph()
    assert app is not None


@pytest.mark.skip(reason="Agent node.py đang là stub. Bỏ skip khi tất cả agent đã hiện thực xong.")
def test_graph_standard_flow():
    """Kiểm tra luồng chuẩn không có PDF (START -> Retrieval -> Summarizer -> FactCheck -> Writer -> END)"""
    app = build_research_rag_graph()
    initial_state = {
        "query": "What is LoRA?",
        "pdf_path": None,
        "retry_count": 0,
        "reasoning_trace": []
    }
    result = app.invoke(initial_state)
    assert result["fact_check_label"] == "support"
    assert "BÁO CÁO NGHIÊN CỨU" in result["final_report"]
    assert len(result["reasoning_trace"]) >= 4


@pytest.mark.skip(reason="Agent node.py đang là stub. Bỏ skip khi tất cả agent đã hiện thực xong.")
def test_graph_pdf_flow():
    """Kiểm tra luồng có PDF (START -> Retrieval -> Reader -> Summarizer -> FactCheck -> Writer -> END)"""
    app = build_research_rag_graph()
    initial_state = {
        "query": "Phân tích bảng biểu trong báo cáo tài chính",
        "pdf_path": "data/financial_report.pdf",
        "retry_count": 0,
        "reasoning_trace": []
    }
    result = app.invoke(initial_state)
    assert "document_schema" in result
    assert result["document_schema"]["pages"][0]["sections"][0]["type"] == "Title"
    assert "ReaderAgent" in [t.get("agent") for t in result["reasoning_trace"]]


@pytest.mark.skip(reason="Agent node.py đang là stub. Bỏ skip khi tất cả agent đã hiện thực xong.")
def test_graph_escalation_flow():
    """Kiểm tra khi retry vượt quá giới hạn 3 lần -> chuyển sang EscalationNode"""
    app = build_research_rag_graph()
    initial_state = {
        "query": "[test_retry] Câu hỏi không thể trả lời",
        "pdf_path": None,
        "retry_count": 3,
        "fact_check_label": "not_enough_info",
        "reasoning_trace": []
    }
    result = app.invoke(initial_state)
    assert result["confidence"] in ["high", "low"]
