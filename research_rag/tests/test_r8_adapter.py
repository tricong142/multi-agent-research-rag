import json
from contextlib import nullcontext
from pathlib import Path

from research_rag.adapters import PdfReader
from research_rag.local import build_local_graph
from research_rag.r8_adapter import R8_POLICY_ID, R8FactCheckerNode, load_r8_runtime
from research_rag.tests.test_autonomy import CompleteWriter
from research_rag.tests.test_integration import FakeRetriever, FakeSummarizer


def test_locked_r8_writes_a_cited_pdf_claim():
    pdf = Path(__file__).resolve().parents[1] / "evaluation/pdfs/simple_text.pdf"
    reader = PdfReader()
    evidence = "The treatment was evaluated against a control group."
    source = next(chunk for chunk in reader.read(str(pdf)) if chunk["text"] == evidence)
    runtime = load_r8_runtime()
    verdict = runtime.assess.__globals__["verdict"]
    trace = []

    class Retriever(FakeRetriever):
        def search(self, *args, **kwargs):
            result = super().search(*args, **kwargs)
            result["chunks"] = [chunk for chunk in result["chunks"] if chunk["source_id"] == source["source_id"]]
            return result

    class Backend:
        generation_deadline = staticmethod(nullcontext)

        def generate_json(self, messages, *, max_new_tokens):
            assert max_new_tokens == runtime.config["max_new_tokens"]
            prompt = messages[0]["content"]
            payload = json.loads(messages[-1]["content"])
            if prompt == verdict.SOURCE_ID_PROMPT:
                evidence_ids = [key for key, text in payload["segments"].items() if evidence in text]
                label = "support" if evidence_ids else "not_enough_info"
                return dict(label=label, evidence_ids=evidence_ids, confidence=None, reasoning="Source check.")
            if prompt == verdict.EVIDENCE_CHECK_PROMPT:
                return dict(label="support", reasoning="Same treatment and control group.")
            raise AssertionError("Unexpected model prompt in the smoke fixture")

    checker = R8FactCheckerNode(Backend(), runtime, trace.append)
    graph = build_local_graph(verifier="r8-v12", max_graph_retries=0, agents=dict(
        reader=reader, retriever=Retriever([]), summarizer=FakeSummarizer(evidence, evidence),
        factchecker=checker, writer=CompleteWriter(),
    ))
    result = graph.invoke({"question": "Was there a control group?", "pdf_path": str(pdf)})
    assert result["status"] == "completed", result["fact_check_results"]
    verified, = result["verified_claims"]
    assert verified["source_id"] == source["source_id"]
    assert verified["evidence"] == evidence
    assert result["final_report"]["sentences"][0]["claim_ids"] == [verified["claim_id"]]
    assert any(event["label"] == "support" and event["verifier_policy"] == R8_POLICY_ID for event in trace)


def test_invalid_source_id_fails_closed():
    class Backend:
        generation_deadline = staticmethod(nullcontext)

        def generate_json(self, messages, *, max_new_tokens):
            return dict(label="support", evidence_ids=["S99"], confidence=None, reasoning="Unknown source.")

    checker = R8FactCheckerNode(Backend(), load_r8_runtime())
    result = checker({"claim": "The study evaluated the revised protocol.",
                      "context": "The study evaluated the revised protocol."})
    assert result["fact_check_label"] == "not_enough_info"
    assert result["fact_check_status"] == "incomplete"
    assert result["confidence_score"] == 0.0
