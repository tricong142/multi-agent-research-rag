import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from research_rag.evaluate import retrieval_metrics
from research_rag.indexing import build_indices
from research_rag.retrieval import EMBEDDING_MODEL, EMBEDDING_REVISION, IndexMismatchError, RetrievalService


class IndexingTests(unittest.TestCase):
    def test_preflight_can_find_a_snapshot_without_a_main_ref(self):
        from research_rag.preflight import _weight_files

        with tempfile.TemporaryDirectory() as temp:
            weights = Path(temp) / "model.safetensors"
            weights.write_bytes(b"synthetic-weight-file")

            def cached(model, name, *, revision):
                if model == EMBEDDING_MODEL and name == weights.name and revision == EMBEDDING_REVISION:
                    return str(weights)
                return None

            with patch.dict("sys.modules", {"huggingface_hub": SimpleNamespace(try_to_load_from_cache=cached)}):
                self.assertFalse(_weight_files(EMBEDDING_MODEL)["weights_complete"])
                self.assertTrue(_weight_files(EMBEDDING_MODEL, revision=EMBEDDING_REVISION)["weights_complete"])

    def test_index_and_query_load_the_same_pinned_snapshot(self):
        import numpy as np

        class Encoder:
            def encode(self, texts, **kwargs):
                vectors = np.zeros((len(texts), 1024), dtype="float32")
                vectors[:, 0] = 1
                return vectors

            def __getitem__(self, index):
                return SimpleNamespace(auto_model=SimpleNamespace(config=SimpleNamespace(_commit_hash=EMBEDDING_REVISION)))

        factory = Mock(return_value=Encoder())
        with tempfile.TemporaryDirectory() as temp, patch.dict("sys.modules", {
            "sentence_transformers": SimpleNamespace(SentenceTransformer=factory)
        }):
            root = Path(temp)
            corpus = root / "corpus.jsonl"
            corpus.write_text(json.dumps({"doc_id": "one", "text": "Known evidence."}), encoding="utf-8")
            manifest = build_indices(corpus, root / "index", dense=True)
            RetrievalService(corpus, root / "index")._get_encoder()
            self.assertEqual(manifest["embedding"]["revision"], EMBEDDING_REVISION)
            self.assertEqual(factory.call_count, 2)
            for invocation in factory.call_args_list:
                self.assertEqual(invocation.args, (EMBEDDING_MODEL,))
                self.assertEqual(invocation.kwargs["revision"], EMBEDDING_REVISION)
                self.assertTrue(invocation.kwargs["local_files_only"])

    def test_new_corpus_roundtrip_and_refuses_overwrite_or_misalignment(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            corpus = root / "corpus.jsonl"
            rows = [{"doc_id": "one", "text": "Orchids require shade."},
                    {"doc_id": "two", "text": "Metal melts when heated."},
                    {"doc_id": "three", "text": "Satellites orbit Earth."},
                    {"doc_id": "formula", "text": "\u2211 \u2248 \u03bb"}]
            corpus.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
            index_dir = root / "indices"
            manifest = build_indices(corpus, index_dir)
            service = RetrievalService(corpus, index_dir, policy=lambda _q, _h: "bm25")
            metric = retrieval_metrics([{"query": "orchids shade", "relevant_doc_ids": ["one"]}], service, 1)
            self.assertEqual(metric["recall_at_k"], 1.0)
            self.assertFalse(manifest["dense_ready"])
            self.assertEqual(manifest["chunks_without_lexical_tokens"], 1)
            self.assertFalse((index_dir / "faiss_arxiv.index").exists())
            before = (index_dir / "bm25_index.pkl").read_bytes()
            with self.assertRaises(ValueError):
                build_indices(corpus, index_dir)
            self.assertEqual(before, (index_dir / "bm25_index.pkl").read_bytes())
            (index_dir / "faiss_doc_ids.json").write_text('["three", "two", "one"]')
            with self.assertRaises(IndexMismatchError):
                RetrievalService(corpus, index_dir)._load_static()


if __name__ == "__main__":
    unittest.main()
