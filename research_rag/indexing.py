"""Build aligned search artifacts in a new directory, preserving existing indices."""
from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import pickle
import time

from .retrieval import EMBEDDING_MODEL, EMBEDDING_REVISION, RetrievalService, tokenize


def build_indices(corpus_path: Path, output_dir: Path, *, dense: bool = False,
                  device: str | None = None, batch_size: int = 16) -> dict:
    if output_dir.exists():
        raise ValueError("Use a new output directory; existing artifacts are never overwritten")
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    started = time.perf_counter()
    with corpus_path.open(encoding="utf-8") as source:
        rows = [json.loads(line) for line in source if line.strip()]
    ids = [row.get("doc_id") for row in rows]
    if (not ids or any(not isinstance(i, str) or not i.strip() for i in ids)
            or len(set(ids)) != len(ids)
            or any(not isinstance(r.get("text"), str) or not r["text"].strip() for r in rows)):
        raise ValueError("Corpus needs unique nonempty string doc_ids and nonempty text")
    from rank_bm25 import BM25Okapi

    texts = [row["text"] for row in rows]
    tokens = [tokenize(text) for text in texts]
    empty_token_chunks = sum(not row for row in tokens)
    if empty_token_chunks == len(tokens):
        raise ValueError("The entire corpus has no lexical tokens")
    bm25 = BM25Okapi(tokens)
    del tokens
    output_dir.mkdir(parents=True)
    with (output_dir / "bm25_index.pkl").open("xb") as target:
        pickle.dump({"bm25": bm25, "doc_ids": ids, "corpus": texts}, target)
    # The runtime uses this ordered mapping for both search modes. This file
    # alone does not mean that a dense index exists.
    (output_dir / "faiss_doc_ids.json").write_text(json.dumps(ids), encoding="utf-8")
    del bm25
    embedding = None
    packages = {"rank-bm25": version("rank-bm25")}
    if dense:
        import faiss
        import numpy as np
        from sentence_transformers import SentenceTransformer

        encoder = SentenceTransformer(EMBEDDING_MODEL, revision=EMBEDDING_REVISION,
                                      device=device, local_files_only=True)
        index = None
        # Encode passages without the query prefix. Add batches to FAISS so a
        # second complete embedding matrix is not held in memory.
        for start in range(0, len(texts), batch_size):
            vectors = np.asarray(encoder.encode(texts[start:start + batch_size],
                                                batch_size=batch_size, normalize_embeddings=True), dtype="float32")
            if vectors.ndim != 2 or not np.isfinite(vectors).all() or vectors.shape[1] != 1024:
                raise ValueError("BGE-Large must return finite 1024-dimensional passage vectors")
            if index is None:
                index = faiss.IndexFlatIP(vectors.shape[1])
            index.add(vectors)
        if index.ntotal != len(ids):
            raise ValueError("FAISS vector count differs from corpus")
        faiss.write_index(index, str(output_dir / "faiss_arxiv.index"))
        embedding = {"model": EMBEDDING_MODEL, "dimension": index.d, "normalized": True,
                     "metric": "inner_product", "query_prefix_required": True,
                     "revision": getattr(encoder[0].auto_model.config, "_commit_hash", None)}
        packages.update({name: version(name) for name in ["sentence-transformers", "faiss-cpu", "torch"]})
    # Exercise the actual runtime's alignment validation before writing a
    # success manifest; failures leave a directory without this manifest.
    RetrievalService(corpus_path=corpus_path, index_dir=output_dir,
                     policy=lambda _q, _h: "bm25")._load_static()
    manifest = {"corpus_sha256": hashlib.sha256(corpus_path.read_bytes()).hexdigest(),
                "chunks": len(ids), "bm25_ready": True, "dense_ready": dense,
                "chunks_without_lexical_tokens": empty_token_chunks,
                "embedding": embedding, "packages": packages,
                "elapsed_seconds": time.perf_counter() - started,
                "artifact_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                    for p in output_dir.iterdir() if p.is_file()}}
    (output_dir / "index_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dense", action="store_true", help="Also build FAISS with cached BGE-Large weights")
    parser.add_argument("--device", help="Encoder device, e.g. cuda:0; used only with --dense")
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()
    print(json.dumps(build_indices(args.corpus, args.output_dir, dense=args.dense,
                                   device=args.device, batch_size=args.batch_size), indent=2))


if __name__ == "__main__":
    main()
