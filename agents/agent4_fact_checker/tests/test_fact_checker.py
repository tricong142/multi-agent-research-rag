import pytest
from agents.agent4_fact_checker.components.claim_extractor import ClaimExtractor
from agents.agent4_fact_checker.components.judge import FactCheckJudge
from agents.agent4_fact_checker.node import FactCheckerAgent


def test_claim_extractor():
    extractor = ClaimExtractor(min_claim_length=15)
    text = (
        "Theo tài liệu nghiên cứu, LoRA giúp đóng băng toàn bộ trọng số mô hình gốc. "
        "Đồng thời, nó chèn các ma trận phân rã hạng thấp vào các tầng Transformer. "
        "Ngoài ra, LoRA giảm 10,000 lần số lượng tham số có thể huấn luyện."
    )
    claims = extractor.extract_claims(text)
    assert len(claims) >= 2
    # Kiểm tra đã loại bỏ cụm từ mở đầu "Theo tài liệu nghiên cứu"
    assert not any(c.startswith("Theo tài liệu nghiên cứu") for c in claims)
    assert any("LoRA giúp đóng băng" in c or "đóng băng toàn bộ trọng số" in c for c in claims)


def test_claim_extractor_markdown_and_abbrev():
    """Kiểm tra xử lý Markdown đầu mục và bảo vệ từ viết tắt v.v. không bị ngắt câu sai."""
    extractor = ClaimExtractor(min_claim_length=15)
    text = (
        "- **[Luận điểm 1]:** Mô hình ứng dụng cho các tác vụ như dịch máy, tóm tắt v.v. một cách hiệu quả.\n"
        "2. **Kết quả:** Độ chính xác đạt 95% trên tập benchmark e.g. GLUE."
    )
    claims = extractor.extract_claims(text)
    assert len(claims) == 2
    # Không được chứa prefix markdown
    assert not any("**[Luận điểm 1]:**" in c for c in claims)
    assert not any("2. **Kết quả:**" in c for c in claims)
    # Từ viết tắt v.v. và e.g. không làm câu bị chặt đứt
    assert any("v.v." in c for c in claims)
    assert any("e.g." in c for c in claims)


def test_judge_supported_claim():
    judge = FactCheckJudge()
    claim = "LoRA giúp giảm số lượng tham số huấn luyện đi 10,000 lần."
    evidence_spans = [
        "Compared to fine-tuning, LoRA reduces trainable parameters by 10,000 times."
    ]
    res = judge.judge_claim(claim, evidence_spans)
    assert res["status"] == "support"
    assert res["confidence"] > 0.5


def test_judge_contradicted_claim():
    judge = FactCheckJudge()
    claim = "LoRA không thể áp dụng cho các mô hình ngôn ngữ lớn."
    evidence_spans = [
        "LoRA is successfully applied to large language models like GPT-3 175B."
    ]
    res = judge.judge_claim(claim, evidence_spans)
    assert res["status"] == "contradict"


def test_judge_not_enough_info():
    judge = FactCheckJudge()
    claim = "Mô hình ResNet50 đạt độ chính xác 85% trên ImageNet."
    evidence_spans = [
        "We evaluate LoRA on RoBERTa, DeBERTa, and GPT-2."
    ]
    res = judge.judge_claim(claim, evidence_spans)
    assert res["status"] == "not_enough_info"


def test_agent_node_support_flow():
    agent = FactCheckerAgent()
    state = {
        "query": "LoRA là gì?",
        "answer": "LoRA đóng băng trọng số gốc và giảm 10,000 lần tham số.",
        "evidence_spans": [
            "LoRA freezes pre-trained weights and reduces trainable parameters by 10,000 times."
        ],
        "retrieved_docs": [{"doc_id": "doc_1", "text": "LoRA paper abstract."}],
        "retry_count": 0
    }
    result = agent.run(state)
    assert "claims" in result
    assert "verified_claims" in result
    assert result["fact_check_label"] == "support"
    assert len(result["reasoning_trace"]) == 1
    assert result["reasoning_trace"][0]["fact_check_label"] == "support"


def test_agent_node_contradict_flow():
    agent = FactCheckerAgent()
    state = {
        "query": "LoRA có tăng tham số không?",
        "answer": "LoRA không thể làm giảm tham số và làm tăng chi phí huấn luyện.",
        "evidence_spans": [
            "LoRA greatly reduces the number of trainable parameters for downstream tasks."
        ],
        "retrieved_docs": [],
        "retry_count": 0
    }
    result = agent.run(state)
    assert result["fact_check_label"] == "contradict"


def test_agent_node_strict_consensus():
    """Kiểm tra logic đồng thuận nghiêm ngặt: Nếu 50% claims thiếu chứng cứ -> not_enough_info."""
    agent = FactCheckerAgent()
    state = {
        "query": "Đánh giá LoRA và ResNet",
        # Claim 1: có evidence, Claim 2: hoàn toàn không có trong context
        "answer": (
            "LoRA giảm 10,000 lần số lượng tham số huấn luyện.\n"
            "Mô hình ResNet50 đạt 98% độ chính xác trong y tế."
        ),
        "evidence_spans": [
            "LoRA reduces trainable parameters by 10,000 times."
        ],
        "retrieved_docs": [],
        "retry_count": 0
    }
    result = agent.run(state)
    # Vì 1/2 claim là not_enough_info, hệ thống an toàn gán not_enough_info để Orchestrator tìm thêm dữ liệu
    assert result["fact_check_label"] == "not_enough_info"


def test_agent_node_empty_answer():
    agent = FactCheckerAgent()
    state = {
        "query": "Câu hỏi bất kỳ",
        "answer": "",
        "evidence_spans": [],
        "retrieved_docs": [],
        "retry_count": 0
    }
    result = agent.run(state)
    assert result["fact_check_label"] == "not_enough_info"
    assert result["claims"] == []
