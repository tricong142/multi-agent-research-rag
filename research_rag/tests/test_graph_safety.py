"""Fail-closed graph regressions; synthetic backends, no model-quality claims."""
import importlib
import unittest
from types import SimpleNamespace

from research_rag.graph import build_graph
from research_rag.tests.test_integration import chunk, FakeRetriever, FakeSummarizer, FakeFactchecker


WriterNode = importlib.import_module("05_writer.node").WriterNode


class GraphSafetyTests(unittest.TestCase):
    def test_opposing_source_survives_retrieval_retry(self):
        supporting = "The treatment improves survival."
        opposing = "The treatment does not improve survival."

        class Retriever:
            def search(self, query, *, history, **kwargs):
                rows = [chunk(supporting, "new-source")] if history else [
                    chunk(supporting, "initial-source"), chunk(opposing, "opposing-source")]
                return {"chunks": rows, "decision": "bm25"}

        contexts = []

        def checker(state):
            contexts.append(state["context"])
            return {"fact_check_label": "contradict" if state["context"] == opposing else "support",
                    "confidence_score": 0.9, "fact_check_status": "ok"}

        graph = build_graph(retriever=Retriever(), summarizer=FakeSummarizer(supporting, supporting),
                            factchecker=checker, writer=WriterNode(), max_graph_retries=1)
        result = graph.invoke({"question": "Does the treatment work?"})
        self.assertEqual(result["retry_count"], 1)
        self.assertEqual(result["verified_claims"], [])
        self.assertEqual(result["final_report"]["sentences"], [])
        self.assertEqual(contexts.count(opposing), 2)

    def test_mixed_real_and_invented_evidence_is_rejected(self):
        evidence = "The sample contained 42 cases."
        summarizer = SimpleNamespace(run=lambda **kwargs: SimpleNamespace(
            answer=evidence, evidence_spans=[evidence, "An invented source span."],
            is_supported=True, confidence="high"))
        checker = FakeFactchecker(["support"])
        result = build_graph(retriever=FakeRetriever([chunk(evidence)]), summarizer=summarizer,
                             factchecker=checker, writer=WriterNode(), max_graph_retries=0).invoke(
                                 {"question": "What was the sample size?"})
        self.assertEqual(checker.calls, [])
        self.assertEqual(result["verified_claims"], [])
        self.assertIn("unmatched_evidence_spans", result["summary_diagnostics"]["reasons"])

    def test_malformed_review_cannot_hide_an_unchecked_source(self):
        supporting = "The sample contained 42 cases."
        invalid_reviews = [None, {}, {"fact_check_label": "unknown", "confidence_score": 0.9,
                                    "fact_check_status": "ok"}]
        for score in (float("nan"), float("inf"), True, "0.9", -0.1, 1.1):
            invalid_reviews.append({"fact_check_label": "not_enough_info", "confidence_score": score,
                                    "fact_check_status": "ok"})
        for invalid in invalid_reviews:
            with self.subTest(invalid=invalid):
                def checker(state):
                    if state["context"] != supporting:
                        return invalid
                    return {"fact_check_label": "support", "confidence_score": 0.9,
                            "fact_check_status": "ok"}

                result = build_graph(retriever=FakeRetriever([chunk(supporting), chunk("Other evidence", "p:2")]),
                                     summarizer=FakeSummarizer(supporting, supporting), factchecker=checker,
                                     writer=WriterNode(), max_graph_retries=0).invoke({"question": "Sample size?"})
                self.assertEqual(result["verified_claims"], [])
                self.assertIn("factchecker:ValueError", result["errors"])

    def test_identical_evidence_is_not_rechecked_until_confidence_changes(self):
        evidence = "The sample contained 42 cases."
        retriever = FakeRetriever([chunk(evidence)])
        result = build_graph(retriever=retriever, summarizer=FakeSummarizer(evidence, evidence),
                             factchecker=FakeFactchecker(["not_enough_info"]), writer=WriterNode(),
                             max_graph_retries=5, max_factcheck_calls=1).invoke({"question": "Sample size?"})
        self.assertEqual(result["retry_count"], 5)
        self.assertEqual(len(retriever.calls), 6)
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertEqual(result["factcheck_calls_used"], 1)
        self.assertNotIn("factchecker:call_budget_exceeded", result["errors"])


if __name__ == "__main__":
    unittest.main()
