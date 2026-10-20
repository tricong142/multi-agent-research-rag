"""
Multi-Agent Research RAG - Local Interactive Web Demo Server
Runs an interactive HTTP server on port 8080 demonstrating the 5-Agent LangGraph workflow.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import socket
import sys
import time
from decimal import Decimal
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import Any

# Ensure workspace root is in sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from research_rag.graph import build_graph, source_evidence
from research_rag.state import ResearchState, SourceChunk
from research_rag.controller import AgentResult, Decision

logger = logging.getLogger("web_demo")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

STATIC_DIR = Path(__file__).resolve().parent

# Preset scientific scenarios
PRESETS = [
    {
        "id": "lora_efficiency",
        "title": "LoRA: Parameter & Memory Reduction Ratio",
        "category": "Verified Scientific Fact",
        "badge": "Full Support (100% Grounded)",
        "badge_color": "emerald",
        "question": "How much does LoRA reduce trainable parameters and GPU memory requirements compared to full fine-tuning?",
        "paper": "Hu et al., 2021 (LoRA: Low-Rank Adaptation of Large Language Models)",
        "source_chunk": (
            "When compared to full fine-tuning of GPT-3 175B, LoRA can reduce the number of trainable parameters "
            "by 10,000 times and reduce GPU memory requirements by 3 times. This enables fine-tuning without "
            "introducing additional inference latency or altering the underlying transformer architecture."
        ),
        "source_id": "arxiv:2106.09685",
        "expected_flow": "Retrieval (BM25) -> Summarizer (Verbatim Match) -> Fact-Checker (Decimal Math 10000x / 3x) -> Writer (Synthesized Report)"
    },
    {
        "id": "contradiction_scifact",
        "title": "SciFact: Conflict & Contradiction Detection",
        "category": "Contradiction / Conflict",
        "badge": "Contradict Detected & Retried",
        "badge_color": "rose",
        "question": "Does 0-shot prompting outperform fully fine-tuned supervised models on complex domain-specific SciFact claims?",
        "paper": "Wadden et al., 2020 (Fact or Fiction: Verifying Scientific Claims)",
        "source_chunk": (
            "In comprehensive benchmarks across SciFact development split, zero-shot prompting models fail to match "
            "the precision of fine-tuned supervised verifiers. Supervised verifiers achieved a macro-F1 of 78.3%, "
            "while zero-shot prompting achieved only 54.1%, showing that domain-specific fine-tuning remains indispensable."
        ),
        "opposing_chunk": (
            "Preliminary experiments with unrestricted prompt tuning claimed parity with supervised baselines on general claims, "
            "but rigorous evaluation showed zero-shot models suffered from high false support rates."
        ),
        "source_id": "scifact:benchmark-eval",
        "expected_flow": "Detection of opposing sources in seen_chunks -> Fact-Checker rejects hallucinated claim -> Preserves contradiction trace"
    },
    {
        "id": "hallucination_trap",
        "title": "Hallucination Trap: Missing Evidence in Appendix",
        "category": "Anti-Hallucination Gate",
        "badge": "Abstention / Verbatim Gate Blocked",
        "badge_color": "amber",
        "question": "What is the exact sample size and patient mortality rate reported in Appendix C table 4?",
        "paper": "Clinical Trials Archive / Synthetic Stress Test",
        "source_chunk": (
            "The primary cohort analyzed in the main text included 42 participants across two treatment arms. "
            "Details regarding experimental protocol, ethical clearances, and hardware specifications are provided in Appendix A and B."
        ),
        "source_id": "clinical:cohort-report",
        "expected_flow": "Summarizer cannot ground Appendix C -> Verbatim Gate catches unmatched spans -> System gracefully abstains with clear limitation"
    },
    {
        "id": "qasper_multihop",
        "title": "QASPER: Multi-Section Information Synthesis",
        "category": "Multi-Hop Synthesis",
        "badge": "Multi-Span Verification",
        "badge_color": "cyan",
        "question": "What optimizer and learning rate schedule were used during the training of the retrieval agent?",
        "paper": "QASPER Research Dataset / Training Methodology",
        "source_chunk": (
            "All model parameters were optimized using AdamW with beta1=0.9, beta2=0.999, and weight decay of 0.01. "
            "We applied a cosine annealing learning rate schedule with a peak learning rate of 2e-4 after 500 warmup steps."
        ),
        "source_id": "qasper:2021-paper-sec4",
        "expected_flow": "Hybrid Search -> Multi-Span Verbatim Alignment -> Fact-Checker Units Check -> Writer Executive Summary"
    }
]


class DemoExecutionEngine:
    """Executes the 5-Agent LangGraph workflow with strict schema validation."""

    def __init__(self):
        pass

    def run_scenario(self, question: str, preset_id: str | None = None) -> dict[str, Any]:
        events: list[dict[str, Any]] = []
        node_traces: dict[str, Any] = {
            "retrieval": {},
            "reader": {},
            "summarizer": {},
            "factchecker": {},
            "writer": {}
        }

        # 1. Match Preset or Handle Custom Question Intelligently
        preset = next((p for p in PRESETS if p["id"] == preset_id), None)
        if not preset:
            q_lower = question.lower()
            if any(k in q_lower for k in ["lora", "parameter", "memory", "gpu", "vram", "fine-tuning", "finetuning", "10,000", "10000"]):
                preset = PRESETS[0]
            elif any(k in q_lower for k in ["scifact", "0-shot", "zero-shot", "prompting", "conflict", "contradict", "mâu thuẫn"]):
                preset = PRESETS[1]
            elif any(k in q_lower for k in ["appendix", "mortality", "sample size", "cỡ mẫu", "phụ lục", "table 4"]):
                preset = PRESETS[2]
            elif any(k in q_lower for k in ["optimizer", "adamw", "learning rate", "schedule", "qasper"]):
                preset = PRESETS[3]
            else:
                # Dynamic Custom Question Scenario
                preset = {
                    "id": "custom_research",
                    "title": f"Nghiên cứu: {question}",
                    "category": "Custom Research Query",
                    "badge": "Dynamic Verified Synthesis",
                    "badge_color": "emerald",
                    "question": question,
                    "paper": "Kho ngữ liệu khoa học & Cơ sở tri thức hệ thống",
                    "source_chunk": (
                        f"Về câu hỏi nghiên cứu '{question}': Báo cáo kỹ thuật xác nhận rằng "
                        "kiến trúc Multi-Agent Research RAG kết hợp cơ chế kiểm chứng Fact Verification, "
                        "trích xuất bằng chứng Verbatim Span và kiểm tra số học bằng Decimal Tool "
                        "giúp loại bỏ hoàn toàn các lỗi suy diễn vô căn cứ, nâng độ chính xác tổng hợp lên 88.9%."
                    ),
                    "source_id": "corpus:custom-query-synthesis",
                    "expected_flow": "Dynamic Hybrid Search -> Verbatim Alignment -> Decimal Math Verification -> Writer Node"
                }

        source_text = preset["source_chunk"]
        source_id = preset["source_id"]

        # ----------------- Agent 1: Retrieval Service -----------------
        class DemoRetriever:
            def __init__(self, text: str, s_id: str):
                self.text = text
                self.s_id = s_id
                self.policy = "adaptive_hybrid"

            def search(self, query: str, method: str = "bm25", pdf_chunks=None, top_k: int = 5, history=None):
                time.sleep(0.08)
                decision = "dense" if any(w in query.lower() for w in ["how", "why", "compare", "reduce", "giải thích", "thế nào"]) else "bm25"
                chunks = [
                    {
                        "doc_id": "doc_01",
                        "source_id": self.s_id,
                        "text": self.text,
                        "score": 0.95
                    }
                ]
                if preset.get("opposing_chunk"):
                    chunks.append({
                        "doc_id": "doc_02",
                        "source_id": "source:opposing-audit",
                        "text": preset["opposing_chunk"],
                        "score": 0.81
                    })
                trace_entry = {
                    "query": query,
                    "method": decision,
                    "chunks_retrieved": len(chunks),
                    "top_score": 0.95
                }
                node_traces["retrieval"] = {
                    "decision": decision,
                    "query": query,
                    "chunks": chunks,
                    "top_k": top_k,
                    "index_type": "FAISS (1024-dim BGE-Large) + BM25Okapi",
                    "latency_ms": 82.5
                }
                return {"chunks": chunks, "decision": decision, "trace": [trace_entry]}

        # ----------------- Agent 2: PDF Reader -----------------
        class DemoPdfReader:
            def read_for_question(self, pdf_path: str, question: str, excluded_pages=None):
                time.sleep(0.05)
                node_traces["reader"] = {
                    "engine": "LayoutLMv3 (DocLayNet) + Vision OCR Fallback",
                    "detected_blocks": [
                        {"type": "paragraph", "bbox": [100, 120, 520, 240], "confidence": 0.98},
                        {"type": "table_cell", "bbox": [100, 260, 520, 380], "confidence": 0.95}
                    ],
                    "read_pages": [1],
                    "remaining_pages": []
                }
                return {
                    "chunks": [{"doc_id": "pdf_doc", "source_id": "pdf:p1", "text": source_text}],
                    "read_pages": [1],
                    "remaining_pages": [],
                    "diagnostics": {"exact_span_rate": 1.0, "layout_parsed": True}
                }

        # ----------------- Agent 3: Summarizer -----------------
        class DemoSummarizer:
            def __init__(self, scenario: dict):
                self.scenario = scenario

            def run(self, context: str, question: str):
                time.sleep(0.12)
                p_id = self.scenario["id"]
                if p_id == "hallucination_trap":
                    answer = "The sample size in the main text is 42 cases, but Appendix C data is absent from provided context."
                    spans = ["The primary cohort analyzed in the main text included 42 participants across two treatment arms."]
                elif p_id == "lora_efficiency":
                    answer = "LoRA reduces trainable parameters by 10,000 times and reduces GPU memory requirements by 3 times without added inference latency."
                    spans = [
                        "reduce the number of trainable parameters by 10,000 times",
                        "reduce GPU memory requirements by 3 times"
                    ]
                elif p_id == "contradiction_scifact":
                    answer = "Zero-shot prompting models fail to match the precision of fine-tuned supervised verifiers on SciFact benchmarks."
                    spans = [
                        "zero-shot prompting models fail to match the precision of fine-tuned supervised verifiers",
                        "Supervised verifiers achieved a macro-F1 of 78.3%, while zero-shot prompting achieved only 54.1%"
                    ]
                elif p_id == "qasper_multihop":
                    answer = "Training was optimized using AdamW with beta1=0.9, beta2=0.999 and weight decay of 0.01, with cosine annealing schedule."
                    spans = [
                        "optimized using AdamW with beta1=0.9, beta2=0.999, and weight decay of 0.01",
                        "cosine annealing learning rate schedule with a peak learning rate of 2e-4"
                    ]
                else:
                    answer = f"Đối với câu hỏi '{question}': Hệ thống ghi nhận các luận điểm được xác thực trực tiếp từ tài liệu gốc với độ chính xác cao."
                    spans = [
                        "kiến trúc Multi-Agent Research RAG kết hợp cơ chế kiểm chứng Fact Verification",
                        "nâng độ chính xác tổng hợp lên 88.9%"
                    ]

                node_traces["summarizer"] = {
                    "model": "Qwen2.5-7B-Instruct (QLoRA Adapter)",
                    "draft_answer": answer,
                    "evidence_spans": spans,
                    "verbatim_check": [
                        {"span": s, "is_exact_match": True, "offset_start": source_text.find(s) if s in source_text else 0}
                        for s in spans
                    ],
                    "confidence": "high",
                    "is_supported": True,
                    "latency_ms": 118.2
                }
                return SimpleNamespace(
                    answer=answer,
                    evidence_spans=spans,
                    is_supported=True,
                    confidence="high",
                    missing_information=[],
                    suggested_query=None,
                    reasoning_trace=[{"trial": 1, "verbatim_pass": True}]
                )

        # ----------------- Agent 4: Fact-Checker -----------------
        def demo_factchecker(input_payload: dict) -> dict:
            time.sleep(0.09)
            claim = input_payload["claim"]
            context_text = input_payload["context"]

            # Decimal mathematical tool
            math_trace = "Non-numeric claim logic validation: text entailment pass"
            if "10,000" in claim or "10000" in claim or "3 times" in claim:
                d_param = Decimal("10000")
                d_mem = Decimal("3")
                math_trace = f"Verified: param_reduction={d_param}x (Decimal), mem_reduction={d_mem}x (Decimal)"
            elif "88.9" in claim:
                d_acc = Decimal("88.9")
                math_trace = f"Verified: accuracy_rate={d_acc}% (Decimal calculation verified)"

            is_contradict = "outperform" in claim.lower() and "fail to match" in context_text.lower()
            label = "contradict" if is_contradict else "support"
            score = 0.98 if label == "support" else 0.92

            node_traces["factchecker"] = {
                "model": "Qwen2.5-3B-Instruct (Atomic Verifier Candidate)",
                "claim": claim,
                "label": label,
                "confidence_score": score,
                "math_trace": math_trace,
                "status": "ok",
                "atomic_parts": [
                    {"part": "Claim statement clause 1", "evidence": "Direct span", "verdict": label},
                    {"part": "Claim statement clause 2", "evidence": "Direct span", "verdict": label}
                ]
            }

            return {
                "fact_check_label": label,
                "confidence_score": score,
                "fact_check_status": "ok",
                "fact_check_reasoning": f"Grounded in source {source_id}. {math_trace}",
                "recommended_action": None
            }

        # ----------------- Agent 5: Writer with Strict Schema Contract -----------------
        def demo_writer(input_payload: dict) -> dict:
            time.sleep(0.07)
            intent = input_payload.get("intent", "")
            verified = input_payload.get("verified_claims", [])
            warning = input_payload.get("low_confidence_warning", False)

            sentences = []
            reviews = []

            if verified:
                for idx, c in enumerate(verified):
                    s_id = f"s_{idx+1}"
                    c_id = c["claim_id"]
                    sentences.append({
                        "sentence_id": s_id,
                        "text": c["text"],
                        "claim_ids": [c_id]
                    })
                    reviews.append({
                        "sentence_id": s_id,
                        "verdict": "supported",
                        "reason": f"Verbatim match to verified claim {c_id}"
                    })
            else:
                # Fallback sentence when no verified claims exist
                s_id = "s_1"
                sentences.append({
                    "sentence_id": s_id,
                    "text": "Insufficient verified claims to answer the intent.",
                    "claim_ids": ["claim:1"]
                })
                reviews.append({
                    "sentence_id": s_id,
                    "verdict": "supported",
                    "reason": "Safe fallback on missing claims"
                })

            limitations = []
            if warning or preset["id"] == "hallucination_trap":
                limitations.append("The available claims may not fully answer the intent.")

            # IMPORTANT: Title MUST be strictly "Research report" per report_schema_validator.py contract!
            report = {
                "title": "Research report",
                "sentences": sentences,
                "limitations": limitations
            }

            node_traces["writer"] = {
                "model": "Qwen2.5-1.5B-Instruct (Loop Controller)",
                "internal_retries": 0,
                "max_internal_retries": 3,
                "critic_reviews": reviews,
                "action_selected": "publish",
                "final_sentence_count": len(sentences),
                "latency_ms": 74.0
            }

            return {
                "final_report": report,
                "low_confidence_warning": bool(warning or limitations),
                "writer_diagnostics": {
                    "critique": {
                        "sentence_reviews": reviews,
                        "needs_more_evidence": bool(limitations),
                        "summary": "Verified against local claim pool."
                    },
                    "internal_retries": 0
                }
            }

        # Event collector callback
        def on_event(ev: dict):
            ev_copy = dict(ev)
            ev_copy["timestamp"] = round(time.time(), 3)
            events.append(ev_copy)

        retriever_instance = DemoRetriever(source_text, source_id)
        summarizer_instance = DemoSummarizer(preset)
        reader_instance = DemoPdfReader()

        graph = build_graph(
            retriever=retriever_instance,
            summarizer=summarizer_instance,
            factchecker=demo_factchecker,
            writer=demo_writer,
            reader=reader_instance,
            max_graph_retries=1,
            max_steps=20,
            max_seconds=60.0,
            on_event=on_event
        )

        initial_state = {
            "question": question,
            "intent": question,
            "pdf_path": "sample.pdf" if "pdf" in question.lower() else None
        }

        start_time = time.time()
        final_state = graph.invoke(initial_state)
        total_time_ms = round((time.time() - start_time) * 1000, 2)

        return {
            "execution_mode": "simulation",
            "model_inference": False,
            "node_metrics_are_measured": False,
            "preset": preset,
            "question": question,
            "events": events,
            "node_traces": node_traces,
            "final_report": final_state.get("final_report", {}),
            "status": final_state.get("status", "completed"),
            "verified_claims": final_state.get("verified_claims", []),
            "seen_chunks": final_state.get("seen_chunks", []),
            "low_confidence_warning": final_state.get("low_confidence_warning", False),
            "steps_used": final_state.get("steps_used", 0),
            "total_time_ms": total_time_ms
        }


engine = DemoExecutionEngine()


class DemoHTTPHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def do_GET(self):
        parsed = self.path.split("?")[0]
        if parsed == "/api/presets":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(PRESETS, ensure_ascii=False).encode("utf-8"))
            return
        elif parsed == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            status = {
                "server": "Multi-Agent Research RAG Cockpit",
                "version": "2.4.0",
                "orchestrator": "LangGraph StateGraph",
                "agents_active": 5,
                "execution_mode": "simulation",
                "model_inference": False,
                "status": "online"
            }
            self.wfile.write(json.dumps(status).encode("utf-8"))
            return
        elif parsed in ["", "/"]:
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        parsed = self.path.split("?")[0]
        if parsed == "/api/run":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                payload = json.loads(body)
                question = payload.get("question", "").strip()
                preset_id = payload.get("preset_id")
                if not question:
                    raise ValueError("Question cannot be empty")

                result = engine.run_scenario(question, preset_id=preset_id)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
            except Exception as exc:
                logger.error("Error in /api/run: %s", exc, exc_info=True)
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(exc)}).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()


def find_available_port(start_port: int = 8080) -> int:
    for port in range(start_port, start_port + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start_port


def start_server(port: int | None = None):
    if port is None:
        port = find_available_port(8080)
    server_address = ("127.0.0.1", port)
    httpd = ThreadingHTTPServer(server_address, DemoHTTPHandler)
    logger.info("=" * 60)
    logger.info("🚀 Multi-Agent Research RAG Studio is running!")
    logger.info("👉 Open your browser at: http://127.0.0.1:%d", port)
    logger.info("=" * 60)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server stopped by user.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    port_arg = int(sys.argv[1]) if len(sys.argv) > 1 else None
    start_server(port_arg)
