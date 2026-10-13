from __future__ import annotations

import importlib
import json
import pickle
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from research_rag.adapters import PdfReader
from research_rag.graph import build_graph
from research_rag.observe import run_with_metrics
from research_rag.evaluate import confidence_metrics, factchecker_metrics, retrieval_metrics, summarizer_evidence_metrics
from research_rag.retrieval import IndexMismatchError, RetrievalService, QUERY_PREFIX


WriterNode = importlib.import_module("05_writer.node").WriterNode


def chunk(text: str, source: str = "paper:1") -> dict:
    return {"doc_id": source, "source_id": source, "text": text, "metadata": {}, "score": 1.0, "method": "bm25"}


class FakeRetriever:
    def __init__(self, source_chunks: list[dict]) -> None:
        self.source_chunks = source_chunks
        self.calls = []

    def search(self, query, *, pdf_chunks=None, top_k=5, history=None, method=None):
        self.calls.append({"query": query, "method": method, "pdf_chunks": pdf_chunks, "top_k": top_k, "history": history})
        return {"chunks": pdf_chunks if pdf_chunks is not None else self.source_chunks,
                "decision": "bm25", "warning": None}


class FakeSummarizer:
    def __init__(self, answer: str, evidence: str, supported: bool = True):
        self.answer, self.evidence, self.supported = answer, evidence, supported

    def run(self, *, context: str, question: str):
        return SimpleNamespace(answer=self.answer, evidence_spans=[self.evidence],
                               is_supported=self.supported, confidence="high" if self.supported else "low")


class FakeFactchecker:
    def __init__(self, labels: list[str]):
        self.labels = labels
        self.calls = []

    def __call__(self, state):
        self.calls.append(state)
        label = self.labels[min(len(self.calls) - 1, len(self.labels) - 1)]
        return {"fact_check_label": label, "confidence_score": 0.9,
                "fact_check_status": "ok", "fact_check_reasoning": "fixture"}


class GraphIntegrationTests(unittest.TestCase):
    def test_no_evidence_stops_after_retry_budget(self):
        retriever = FakeRetriever([])
        graph = build_graph(retriever=retriever, summarizer=FakeSummarizer("", ""),
                            factchecker=FakeFactchecker(["support"]), writer=WriterNode(), max_graph_retries=1)
        result = graph.invoke({"question": "No corpus evidence?"})
        self.assertEqual(result["retry_count"], 1)
        self.assertEqual(len(retriever.calls), 2)
        self.assertEqual(result["verified_claims"], [])
        self.assertEqual(result["final_report"]["sentences"], [])

    def test_multiple_claims_keep_source_links(self):
        evidence = "The study used five folds. The sample had 42 cases."
        graph = build_graph(retriever=FakeRetriever([chunk(evidence, "paper:42")]),
                            summarizer=FakeSummarizer(evidence, evidence),
                            factchecker=FakeFactchecker(["support"]), writer=WriterNode(), max_graph_retries=0)
        result = graph.invoke({"question": "Describe the study."})
        self.assertEqual(len(result["verified_claims"]), 2)
        self.assertEqual({claim["source_id"] for claim in result["verified_claims"]}, {"paper:42"})

    def test_reader_failure_fails_closed(self):
        class BrokenReader:
            def read_for_question(self, path, **kwargs):
                raise TimeoutError("private document text")

        graph = build_graph(reader=BrokenReader(), retriever=FakeRetriever([chunk("irrelevant")]),
                            summarizer=FakeSummarizer("", ""), factchecker=FakeFactchecker(["support"]),
                            writer=WriterNode(), max_graph_retries=0)
        result, metrics = run_with_metrics(graph, {"question": "Question", "pdf_path": "private.pdf"})
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertEqual(result["verified_claims"], [])
        self.assertIn("reader:TimeoutError", result["errors"])
        self.assertNotIn("private document text", json.dumps(metrics))
        self.assertNotIn("Question", json.dumps(metrics))

    def test_verified_claim_keeps_exact_evidence_and_source(self):
        evidence = "Evaluation used five folds."
        checker = FakeFactchecker(["support"])
        graph = build_graph(retriever=FakeRetriever([chunk(evidence)]),
                            summarizer=FakeSummarizer(evidence, evidence),
                            factchecker=checker, writer=WriterNode(), max_graph_retries=0)
        result = graph.invoke({"question": "How was evaluation done?"})
        self.assertEqual(result["verified_claims"][0]["source_id"], "paper:1")
        self.assertEqual(result["verified_claims"][0]["evidence"], evidence)
        self.assertEqual(checker.calls[0]["context"], evidence)
        self.assertTrue(result["final_report"]["sentences"])
        self.assertEqual(result["final_report"]["sentences"][0]["claim_ids"], ["claim:1"])
        self.assertEqual(result["summary_diagnostics"]["reasons"], [])
        self.assertEqual(result["summary_diagnostics"]["matched_span_count"], 1)

    def test_unmatched_evidence_never_becomes_verified(self):
        checker = FakeFactchecker(["support"])
        graph = build_graph(retriever=FakeRetriever([chunk("The paper used five folds.")]),
                            summarizer=FakeSummarizer("The paper used five folds.", "Invented citation."),
                            factchecker=checker, writer=WriterNode(), max_graph_retries=1)
        result = graph.invoke({"question": "How was evaluation done?"})
        self.assertEqual(result["retry_count"], 1)
        self.assertEqual(result["verified_claims"], [])
        self.assertEqual(checker.calls, [])
        self.assertEqual(result["final_report"]["sentences"], [])
        self.assertTrue(result["low_confidence_warning"])
        self.assertEqual(result["summary_diagnostics"]["reasons"], ["no_verbatim_evidence"])

    def test_critic_rejection_diagnostic_keeps_factchecker_blocked(self):
        evidence = "Evaluation used five folds."
        checker = FakeFactchecker(["support"])
        graph = build_graph(retriever=FakeRetriever([chunk(evidence)]),
                            summarizer=FakeSummarizer(evidence, evidence, supported=False),
                            factchecker=checker, writer=WriterNode(), max_graph_retries=0)
        result, metrics = run_with_metrics(graph, {"question": "How?"})
        self.assertEqual(result["summary_diagnostics"]["matched_span_count"], 1)
        self.assertIn("critic_not_supported", result["summary_diagnostics"]["reasons"])
        self.assertEqual(checker.calls, [])
        self.assertNotIn(evidence, json.dumps(metrics))

    def test_factcheck_retry_is_bounded_and_changes_history(self):
        evidence = "The intervention reduced mortality."
        class ExpandingRetriever(FakeRetriever):
            def search(self, query, **kwargs):
                result = super().search(query, **kwargs)
                result["chunks"] = [chunk(evidence, f"paper:{len(self.calls)}")]
                return result
        retriever = ExpandingRetriever([chunk(evidence)])
        graph = build_graph(retriever=retriever,
                            summarizer=FakeSummarizer(evidence, evidence),
                            factchecker=FakeFactchecker(["not_enough_info", "support"]),
                            writer=WriterNode(), max_graph_retries=1)
        result = graph.invoke({"question": "What happened?"})
        self.assertEqual(result["retry_count"], 1)
        self.assertEqual(len(retriever.calls), 2)
        self.assertEqual(retriever.calls[1]["history"][0]["tool"], "bm25")
        self.assertEqual(retriever.calls[1]["history"][0]["doc_ids"], ["paper:1"])
        self.assertEqual(len(result["verified_claims"]), 1)

    def test_contradictory_source_blocks_claim(self):
        evidence = "The reported effect was positive."
        retriever = FakeRetriever([chunk(evidence, "paper:1"), chunk(evidence, "paper:2")])
        graph = build_graph(retriever=retriever,
                            summarizer=FakeSummarizer(evidence, evidence),
                            factchecker=FakeFactchecker(["support", "contradict"]),
                            writer=WriterNode(), max_graph_retries=0)
        result = graph.invoke({"question": "What was the effect?"})
        self.assertEqual(result["verified_claims"], [])
        self.assertEqual(len(result["fact_check_results"]), 2)

    def test_uncited_retrieved_chunk_can_block_claim(self):
        supporting = "The intervention improved survival."
        opposing = "The intervention did not improve survival."
        checker = FakeFactchecker(["support", "contradict"])
        graph = build_graph(retriever=FakeRetriever([chunk(supporting, "paper:1"),
                                                    chunk(opposing, "paper:2")]),
                            summarizer=FakeSummarizer(supporting, supporting),
                            factchecker=checker, writer=WriterNode(), max_graph_retries=0)
        result = graph.invoke({"question": "What was the effect?"})
        self.assertEqual([call["context"] for call in checker.calls], [supporting, opposing])
        self.assertEqual([review["scope"] for review in result["fact_check_results"]],
                         ["evidence", "chunk"])
        self.assertEqual(result["verified_claims"], [])

    def test_factcheck_call_budget_fails_closed(self):
        supporting = "The intervention improved survival."
        checker = FakeFactchecker(["support"])
        graph = build_graph(retriever=FakeRetriever([chunk(supporting, "paper:1"),
                                                    chunk("Another paper discussed survival.", "paper:2")]),
                            summarizer=FakeSummarizer(supporting, supporting),
                            factchecker=checker, writer=WriterNode(), max_graph_retries=0,
                            max_factcheck_calls=1)
        result = graph.invoke({"question": "What was the effect?"})
        self.assertEqual(checker.calls, [])
        self.assertEqual(result["verified_claims"], [])
        self.assertIn("factchecker:call_budget_exceeded", result["errors"])

    def test_pdf_branch_preserves_page_and_source(self):
        class Reader:
            def read_for_question(self, path, *, question, excluded_pages):
                self.path = path
                return {"chunks": [chunk("The table reports 42 cases.", "pdf:abc:p2:b1:c0")],
                        "read_pages": [2], "remaining_pages": [], "diagnostics": {}}

        reader, retriever = Reader(), FakeRetriever([])
        graph = build_graph(reader=reader, retriever=retriever,
                            summarizer=FakeSummarizer("The table reports 42 cases.", "The table reports 42 cases."),
                            factchecker=FakeFactchecker(["support"]), writer=WriterNode(), max_graph_retries=0)
        result = graph.invoke({"question": "How many cases?", "pdf_path": "sample.pdf"})
        self.assertEqual(reader.path, "sample.pdf")
        self.assertEqual(retriever.calls[0]["pdf_chunks"][0]["source_id"], "pdf:abc:p2:b1:c0")
        self.assertEqual(result["verified_claims"][0]["source_id"], "pdf:abc:p2:b1:c0")

    def test_factcheck_service_error_returns_warning(self):
        class BrokenFactchecker:
            def __call__(self, state):
                raise TimeoutError("fixture timeout")

        evidence = "Evaluation used five folds."
        graph = build_graph(retriever=FakeRetriever([chunk(evidence)]),
                            summarizer=FakeSummarizer(evidence, evidence),
                            factchecker=BrokenFactchecker(), writer=WriterNode(), max_graph_retries=0)
        result = graph.invoke({"question": "How?"})
        self.assertEqual(result["verified_claims"], [])
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertTrue(any("factchecker:TimeoutError" in error for error in result["errors"]))

    def test_evidence_from_chunk_outside_context_is_rejected(self):
        evidence = "The experiment used five folds."
        first = chunk("Unrelated text. " * 8, "paper:1")
        second = chunk(evidence, "paper:2")
        graph = build_graph(retriever=FakeRetriever([first, second]),
                            summarizer=FakeSummarizer(evidence, evidence),
                            factchecker=FakeFactchecker(["support"]), writer=WriterNode(),
                            max_graph_retries=0, max_context_chars=150)
        result = graph.invoke({"question": "How was evaluation done?"})
        self.assertEqual(result["context_source_ids"], ["paper:1"])
        self.assertEqual(result["verified_claims"], [])


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        import faiss
        import numpy as np
        from rank_bm25 import BM25Okapi
        from research_rag.retrieval import tokenize

        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.rows = [
            {"doc_id": "p:1", "text": "Five fold cross validation was used.", "metadata": {"paper_id": "p"}},
            {"doc_id": "p:2", "text": "The model uses attention layers.", "metadata": {"paper_id": "p"}},
        ]
        (root / "indices").mkdir()
        with (root / "corpus.jsonl").open("w", encoding="utf-8") as f:
            for row in self.rows:
                f.write(json.dumps(row) + "\n")
        bm25 = BM25Okapi([tokenize(r["text"]) for r in self.rows])
        with (root / "indices" / "bm25_index.pkl").open("wb") as f:
            pickle.dump({"bm25": bm25, "doc_ids": [r["doc_id"] for r in self.rows],
                         "corpus": [r["text"] for r in self.rows]}, f)
        (root / "indices" / "faiss_doc_ids.json").write_text('["p:1", "p:2"]', encoding="utf-8")
        index = faiss.IndexFlatIP(2)
        index.add(np.asarray([[1, 0], [0, 1]], dtype="float32"))
        faiss.write_index(index, str(root / "indices" / "faiss_arxiv.index"))
        self.root = root

    def test_dense_search_uses_index_mapping(self):
        class Encoder:
            def encode(self, text, *, normalize_embeddings):
                if isinstance(text, str):
                    self.query = text
                    return [1, 0]
                return [[1, 0], [0, 1]]

        encoder = Encoder()
        service = RetrievalService(self.root / "corpus.jsonl", self.root / "indices",
                                   encoder=encoder, policy=lambda q, h: "dense")
        result = service.search("five folds", top_k=1)
        self.assertEqual(result["chunks"][0]["source_id"], "p:1")
        self.assertEqual(encoder.query, QUERY_PREFIX + "five folds")

    def test_mismatched_id_map_fails_closed(self):
        (self.root / "indices" / "faiss_doc_ids.json").write_text('["p:2", "p:1"]', encoding="utf-8")
        service = RetrievalService(self.root / "corpus.jsonl", self.root / "indices", policy=lambda q, h: "bm25")
        with self.assertRaises(IndexMismatchError):
            service.search("five fold")

    def test_single_pdf_chunk_with_negative_bm25_score_is_retrieved(self):
        service = RetrievalService(self.root / "corpus.jsonl", self.root / "indices", policy=lambda q, h: "bm25")
        result = service.search("evaluation folds", pdf_chunks=[chunk("Evaluation used five folds.", "pdf:1")])
        self.assertEqual(result["chunks"][0]["source_id"], "pdf:1")

    def test_unimplemented_policy_is_rejected_and_dense_fallback_is_truthful(self):
        class BrokenEncoder:
            def encode(self, *args, **kwargs):
                raise OSError("fixture model unavailable")

        service = RetrievalService(self.root / "corpus.jsonl", self.root / "indices",
                                   encoder=BrokenEncoder(), policy=lambda q, h: "hyde")
        with self.assertRaisesRegex(ValueError, "Unimplemented"):
            service.search("evaluation folds", pdf_chunks=[chunk("Evaluation used five folds.", "pdf:1")])
        result = service.search("evaluation folds", method="dense", pdf_chunks=[chunk("Evaluation used five folds.", "pdf:1")])
        self.assertEqual(result["chunks"][0]["method"], "bm25")
        self.assertEqual(result["decision"], "bm25")
        self.assertEqual(result["requested_method"], "dense")
        self.assertIn("dense_unavailable:OSError", result["warning"])

    def test_retrieval_qrels_metric_uses_real_doc_ids(self):
        service = RetrievalService(self.root / "corpus.jsonl", self.root / "indices",
                                   policy=lambda q, h: "bm25")
        metric = retrieval_metrics([{"query": "attention layers", "relevant_doc_ids": ["p:2"]}], service, 1)
        self.assertEqual(metric["hit_at_k"], 1.0)
        self.assertEqual(metric["recall_at_k"], 1.0)
        with self.assertRaisesRegex(ValueError, "absent"):
            retrieval_metrics([{"query": "attention", "relevant_doc_ids": ["invented"]}], service, 1)


class EvaluationTests(unittest.TestCase):
    def test_confidence_metric_requires_real_scores(self):
        rows = [{"gold_label": "support", "predicted_label": "support", "confidence_score": 0.8},
                {"gold_label": "support", "predicted_label": "contradict", "confidence_score": 0.2}]
        result = confidence_metrics(rows, bins=2)
        self.assertAlmostEqual(result["brier_score"], 0.04)
        with self.assertRaisesRegex(ValueError, "confidence_score"):
            confidence_metrics([{"gold_label": "support", "predicted_label": "support"}])

    def test_factchecker_and_evidence_metrics_are_distinct(self):
        labels = [{"gold_label": "support", "predicted_label": "support"},
                  {"gold_label": "contradict", "predicted_label": "not_enough_info"}]
        fact = factchecker_metrics(labels)
        self.assertEqual(fact["accuracy"], 0.5)
        summary = summarizer_evidence_metrics([
            {"context": "Exact evidence.", "predicted_evidence": ["Exact evidence."],
             "expected_is_answerable": True, "is_supported_final": True},
            {"context": "Other.", "predicted_evidence": ["Invented."],
             "expected_is_answerable": False, "is_supported_final": False},
        ])
        self.assertEqual(summary["verbatim_span_rate"], 0.5)


class ReaderAdapterTests(unittest.TestCase):
    def test_real_reader_extracts_text_pdf_without_remote_critique(self):
        import fitz
        from train_agent2_reader.reader_agent import ReaderAgent

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "paper.pdf"
            document = fitz.open()
            page = document.new_page()
            page.insert_text((72, 72), "The evaluation used five folds and reports forty two cases.")
            document.save(path)
            document.close()
            response = SimpleNamespace(is_acceptable=True, suggested_action="accept", reasoning="private document text")
            with patch("train_agent2_reader.reader_policy.get_critique", return_value=response):
                with self.assertLogs("reader_agent", level="INFO") as captured:
                    chunks = PdfReader(ReaderAgent()).read(str(path))
        self.assertTrue(any("five folds" in item["text"] for item in chunks))
        self.assertNotIn("private document text", "\n".join(captured.output))
        self.assertTrue(all(item["metadata"]["page_no"] == 0 for item in chunks))
        self.assertTrue(all(item["metadata"]["source_tool"] == "alt_segmentation" for item in chunks))

    def test_pdf_chunk_has_page_and_bbox(self):
        import fitz
        from train_agent2_reader.tools.common_schema import ExtractedBlock

        class Reader:
            def process_page(self, path, page_no):
                return {"success": True, "blocks": [ExtractedBlock(
                    page_no=page_no, text="Evidence from page one.", bbox=[1, 2, 3, 4], source_tool="alt_segmentation"
                )]}

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "paper.pdf"
            doc = fitz.open()
            doc.new_page()
            doc.save(path)
            doc.close()
            chunks = PdfReader(Reader()).read(str(path))
        self.assertEqual(chunks[0]["metadata"]["page_no"], 0)
        self.assertEqual(chunks[0]["metadata"]["bbox"], [1, 2, 3, 4])
        self.assertTrue(chunks[0]["source_id"].startswith("pdf:"))


if __name__ == "__main__":
    unittest.main()
