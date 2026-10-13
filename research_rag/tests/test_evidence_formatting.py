"""Regression for real PDF ligatures/line wraps observed on Kaggle."""
import unittest

from research_rag.graph import build_graph, source_evidence
from research_rag.tests.test_integration import (
    FakeFactchecker, FakeRetriever, FakeSummarizer, WriterNode, chunk,
)


class EvidenceFormattingTests(unittest.TestCase):
    def test_pdf_formatting_recovers_original_source_for_factchecker(self):
        original = "task-speciﬁc\nmodels retain 97%\nof performance."
        span = "task-specific models retain 97% of performance."
        checker = FakeFactchecker(["support"])
        graph = build_graph(
            retriever=FakeRetriever([chunk("Intro. " + original + " Next.")]),
            summarizer=FakeSummarizer("Models retain 97% of performance.", span),
            factchecker=checker, writer=WriterNode(), max_graph_retries=0,
        )
        result = graph.invoke({"question": "How much performance is retained?"})
        self.assertEqual(result["verified_claims"][0]["evidence"], original)
        self.assertEqual(checker.calls[0]["context"], original)
        self.assertEqual(result["summary_diagnostics"]["matched_span_count"], 1)
        self.assertEqual(result["summary_diagnostics"]["reasons"], [])

    def test_content_changes_are_rejected(self):
        source = "The model retains 97% of performance."
        for span in ("The model retains 99% of performance.",
                     "the model retains 97% of performance.",
                     "The model retains 97% of performance!",
                     "The model retains performance."):
            with self.subTest(span=span):
                self.assertIsNone(source_evidence(span, source))

    def test_never_extract_part_of_ligature(self):
        self.assertIsNone(source_evidence("fi", "ﬃ"))
        self.assertEqual(source_evidence("ffi", "ﬃ"), "ﬃ")

    def test_exact_and_whitespace_only(self):
        self.assertEqual(source_evidence("97%", "retains 97%"), "97%")
        self.assertEqual(source_evidence("A B", "A\r\n\tB"), "A\r\n\tB")


if __name__ == "__main__":
    unittest.main()
