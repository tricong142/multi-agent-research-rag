import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from research_rag.evaluation.qasper_benchmark import dense_preflight, run, score_traces
from research_rag.indexing import build_indices
from research_rag.retrieval import EMBEDDING_REVISION, RetrievalService


class QasperBenchmarkTests(unittest.TestCase):
    def fixture(self, root):
        (root / "corpus.jsonl").write_text('\n'.join(json.dumps(r) for r in (
            {"doc_id": "one", "text": "Orchids need shade."},
            {"doc_id": "two", "text": "Metals melt when heated."})), encoding="utf-8")
        (root / "qrels_dev.jsonl").write_text(json.dumps(
            {"query": "orchids shade", "relevant_doc_ids": ["one"]}), encoding="utf-8")
        (root / "qrels_test_candidate.jsonl").write_text('MUST NOT READ', encoding="utf-8")
        return root / "corpus.jsonl", root / "index"

    def test_missing_faiss_fallback_never_loads_encoder(self):
        with tempfile.TemporaryDirectory() as tmp:
            corpus, index = self.fixture(Path(tmp))
            build_indices(corpus, index)
            service = RetrievalService(corpus, index)
            with patch.object(service, "_get_encoder", side_effect=AssertionError("must not load")) as encoder:
                result = service.search("orchids", method="dense")
            encoder.assert_not_called()
            self.assertEqual(result["decision"], "bm25")
            self.assertIn("dense_unavailable", result["warning"])

    def test_bm25_scores_but_missing_dense_is_null_and_test_split_unread(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus, index = self.fixture(root)
            build_indices(corpus, index)
            report = run(root, index, root / "run")
            self.assertEqual(report["results"]["bm25"]["metrics"]["hit_at_k"], 1)
            self.assertIsNone(report["results"]["dense"]["metrics"])
            self.assertFalse(report["paired_comparison_valid"])
            with self.assertRaises(FileExistsError):
                run(root, index, root / "run")

    def test_even_one_disguised_fallback_invalidates_dense_metrics(self):
        rows = [{"query": "x", "relevant_doc_ids": ["one"]}]
        trace = {"ordinal": 0, "query": "x", "requested_method": "dense", "actual_method": "dense",
                 "doc_ids": ["one"], "chunk_methods": ["bm25"], "elapsed_ms": 1}
        self.assertIsNone(score_traces(rows, [trace], "dense", 5)["metrics"])
        trace.update(actual_method="bm25", chunk_methods=["bm25"], warning="dense_unavailable")
        self.assertEqual(score_traces(rows, [trace], "dense", 5)["fallback_queries"], 1)
        with self.assertRaises(ValueError):
            score_traces(rows, [], "dense", 5)

    def test_real_faiss_roundtrip_with_synthetic_encoder_and_tamper_rejection(self):
        import numpy as np

        class Encoder:
            def encode(self, texts, **kwargs):
                values = [texts] if isinstance(texts, str) else texts
                result = np.zeros((len(values), 1024), dtype="float32")
                for i, text in enumerate(values):
                    result[i, 0 if "orchid" in text.lower() else 1] = 1
                return result

            def __getitem__(self, index):
                return SimpleNamespace(auto_model=SimpleNamespace(config=SimpleNamespace(_commit_hash=EMBEDDING_REVISION)))

        with tempfile.TemporaryDirectory() as tmp, patch.dict("sys.modules", {
            "sentence_transformers": SimpleNamespace(SentenceTransformer=lambda *a, **k: Encoder())
        }):
            root = Path(tmp)
            corpus, index = self.fixture(root)
            build_indices(corpus, index, dense=True)
            service = RetrievalService(corpus, index, encoder=Encoder())
            report = run(root, index, root / "run", service=service)
            self.assertTrue(report["paired_comparison_valid"])
            self.assertEqual(report["results"]["dense"]["actual_backends"], {"dense": 1})
            (index / "faiss_doc_ids.json").write_text('["two","one"]')
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                dense_preflight(service)


if __name__ == "__main__":
    unittest.main()
