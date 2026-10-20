"""Paired QASPER development retrieval; a BM25 fallback never scores as Dense."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import math
from pathlib import Path
import platform
import statistics
import time

from research_rag.retrieval import (EMBEDDING_MODEL, EMBEDDING_REVISION,
                                    QUERY_PREFIX, RetrievalService)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA = ROOT / "kb_indexing/data/qasper_eval_20260926"


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def dense_preflight(service):
    """Verify provenance before loading the encoder. No network or model loading."""
    manifest_path = service.index_dir / "index_manifest.json"
    if not manifest_path.is_file():
        raise ValueError("Dense requires a completed index build manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    embedding = manifest.get("embedding") or {}
    if (manifest.get("dense_ready") is not True
            or manifest.get("corpus_sha256") != sha(service.corpus_path)
            or embedding.get("model") != EMBEDDING_MODEL
            or embedding.get("revision") != EMBEDDING_REVISION
            or embedding.get("normalized") is not True
            or embedding.get("metric") != "inner_product"
            or embedding.get("query_prefix_required") is not True
            or embedding.get("dimension") != 1024):
        raise ValueError("Dense index provenance/model/revision does not match this benchmark")
    for name in ("bm25_index.pkl", "faiss_doc_ids.json", "faiss_arxiv.index"):
        if manifest.get("artifact_sha256", {}).get(name) != sha(service.index_dir / name):
            raise ValueError("Dense artifact hash mismatch: " + name)
    service._load_static()
    index = service._get_faiss_index()
    import faiss
    if (index.ntotal != manifest.get("chunks") or index.d != 1024
            or index.metric_type != faiss.METRIC_INNER_PRODUCT):
        raise ValueError("FAISS dimensions/count/metric mismatch")
    return {"passed": True, "vectors": index.ntotal, "dimension": index.d,
            "manifest_sha256": sha(manifest_path)}


def score_traces(rows, traces, method, top_k):
    """Recompute metrics from every query, including failures; never drop rows."""
    if not rows or len(rows) != len(traces):
        raise ValueError("Incomplete retrieval trace")
    backends = Counter()
    hits, recalls, reciprocal_ranks, latencies = [], [], [], []
    valid = True
    for ordinal, (row, trace) in enumerate(zip(rows, traces)):
        if trace["ordinal"] != ordinal or trace["query"] != row["query"]:
            raise ValueError("Trace/qrel order mismatch")
        ids = trace["doc_ids"]
        if len(ids) != len(set(ids)) or len(ids) > top_k:
            raise ValueError("Duplicate or excessive retrieved IDs")
        expected = set(row["relevant_doc_ids"])
        backends[trace["actual_method"]] += 1
        valid &= (trace["requested_method"] == method and trace["actual_method"] == method
                  and not trace.get("warning") and not trace.get("error_type")
                  and all(tool == method for tool in trace["chunk_methods"]))
        hits.append(bool(set(ids) & expected))
        recalls.append(len(set(ids) & expected) / len(expected))
        reciprocal_ranks.append(next((1 / (i + 1) for i, doc in enumerate(ids) if doc in expected), 0))
        latencies.append(trace["elapsed_ms"])
    metrics = {"hit_at_k": statistics.mean(hits), "paragraph_recall_at_k": statistics.mean(recalls),
               "mrr_at_k": statistics.mean(reciprocal_ranks)} if valid else None
    return {"requested_method": method, "n": len(rows), "top_k": top_k,
            "valid_backend_run": bool(valid), "actual_backends": dict(backends),
            "fallback_queries": sum(t["actual_method"] != method for t in traces),
            "failed_queries": sum(bool(t.get("error_type")) for t in traces),
            "metrics": metrics, "latency_ms_mean": statistics.mean(latencies),
            "latency_ms_p95": sorted(latencies)[math.ceil(.95 * len(latencies)) - 1],
            "first_query_ms": latencies[0]}


def run(data_dir, index_dir, output_dir, *, mode="paired", top_k=5, service=None):
    if mode not in {"bm25", "dense", "paired"} or not 1 <= top_k <= 50:
        raise ValueError("Invalid mode/top_k")
    data_dir, index_dir, output_dir = map(Path, (data_dir, index_dir, output_dir))
    if output_dir.exists():
        raise FileExistsError("Preserve previous output; use a new run directory")
    # Only the existing development split is read. Test candidate stays sealed.
    qrels = data_dir / "qrels_dev.jsonl"
    corpus = data_dir / "corpus.jsonl"
    rows = read_rows(qrels)
    if not rows:
        raise ValueError("Empty QASPER development set")
    service = service or RetrievalService(corpus, index_dir)
    started = time.perf_counter()
    service._load_static()
    load_ms = (time.perf_counter() - started) * 1000
    corpus_ids = {row["doc_id"] for row in service._rows}
    for row in rows:
        if (not isinstance(row.get("query"), str) or not row["query"].strip()
                or not isinstance(row.get("relevant_doc_ids"), list) or not row["relevant_doc_ids"]
                or any(doc not in corpus_ids for doc in row["relevant_doc_ids"])):
            raise ValueError("Invalid qrel or evidence absent from corpus")
    packages = {}
    for name in ("rank-bm25", "sentence-transformers", "faiss-cpu", "torch", "transformers"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    provenance = {"corpus_sha256": sha(corpus), "qrels_dev_sha256": sha(qrels),
                  "corpus_chunks": len(corpus_ids), "dev_queries": len(rows),
                  "embedding_model": EMBEDDING_MODEL, "embedding_revision": EMBEDDING_REVISION,
                  "query_prefix": QUERY_PREFIX, "packages": packages,
                  "python": platform.python_version(), "platform": platform.platform(),
                  "index_sha256": {p.name: sha(p) for p in sorted(index_dir.glob("*")) if p.is_file()},
                  "source_sha256": {p.relative_to(ROOT).as_posix(): sha(p) for p in (
                      Path(__file__).resolve(), ROOT / "research_rag/retrieval.py", ROOT / "research_rag/indexing.py")}}
    output_dir.mkdir(parents=True)
    (output_dir / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    results = {}
    methods = ("bm25", "dense") if mode == "paired" else (mode,)
    for method in methods:
        if method == "dense":
            try:
                preflight = dense_preflight(service)
            except (ValueError, OSError, RuntimeError, ImportError) as exc:
                results[method] = {"valid_backend_run": False, "metrics": None, "n": 0,
                                   "preflight": {"passed": False, "error_type": type(exc).__name__,
                                                 "reason": str(exc)}, "status": "blocked_before_encoder_load"}
                continue
        else:
            preflight = {"passed": True}
        traces = []
        with (output_dir / (method + "-traces.jsonl")).open("x", encoding="utf-8") as stream:
            for ordinal, row in enumerate(rows):
                started = time.perf_counter()
                try:
                    result = service.search(row["query"], method=method, top_k=top_k, history=[])
                    chunks = result["chunks"]
                    trace = {"ordinal": ordinal, "query": row["query"], "requested_method": method,
                             "actual_method": result["decision"], "warning": result.get("warning"),
                             "doc_ids": [c["doc_id"] for c in chunks],
                             "chunk_methods": [c["method"] for c in chunks],
                             "scores": [c["score"] for c in chunks]}
                    if any(doc not in corpus_ids for doc in trace["doc_ids"]):
                        raise ValueError("Retrieved ID outside corpus")
                except Exception as exc:
                    trace = {"ordinal": ordinal, "query": row["query"], "requested_method": method,
                             "actual_method": "failed", "error_type": type(exc).__name__,
                             "doc_ids": [], "chunk_methods": [], "scores": []}
                trace["elapsed_ms"] = (time.perf_counter() - started) * 1000
                traces.append(trace)
                stream.write(json.dumps(trace, ensure_ascii=False) + "\n")
                stream.flush()
                if (ordinal + 1) % 25 == 0:
                    print(f"{method}: {ordinal + 1}/{len(rows)}", flush=True)
        results[method] = score_traces(rows, traces, method, top_k) | {"preflight": preflight}
    comparable = all(results.get(m, {}).get("valid_backend_run") for m in ("bm25", "dense"))
    report = {"benchmark": "QASPER-derived global paragraph retrieval, development only",
              "official_qasper_score": False, "test_candidate_evaluated": False,
              "static_load_ms": load_ms, "results": results, "paired_comparison_valid": comparable,
              "delta_dense_minus_bm25": {key: results["dense"]["metrics"][key] - results["bm25"]["metrics"][key]
                                         for key in results["bm25"]["metrics"]} if comparable else None,
              "timing_note": "Static alignment load excluded; first Dense query includes encoder load. Query order fixed; no retrieval history.",
              "quality_note": "Paragraph retrieval scores do not measure answer accuracy, verifier false support or E2E quality."}
    (output_dir / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--index-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--mode", choices=("bm25", "dense", "paired"), default="paired")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    result = run(args.data_dir, args.index_dir, args.output_dir, mode=args.mode, top_k=args.top_k)
    print(json.dumps(result, indent=2))
    expected = ("bm25", "dense") if args.mode == "paired" else (args.mode,)
    raise SystemExit(0 if all(result["results"][m]["valid_backend_run"] for m in expected) else 2)


if __name__ == "__main__":
    main()
