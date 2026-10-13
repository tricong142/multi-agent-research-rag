"""Freeze, run and score real-model autonomy experiments; never substitute fake agents."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

from research_rag.planning import create_plan

ROOT = Path(__file__).resolve().parents[2]
CRITERIA = Path(__file__).with_name("autonomy_criteria.json")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def prepare(directory: Path) -> dict:
    """Freeze criteria, cases and source hashes before any model inference."""
    import fitz
    directory.mkdir(parents=True, exist_ok=False)
    criteria = json.loads(CRITERIA.read_text(encoding="utf-8"))
    save(directory / "criteria.json", criteria)
    source = ROOT / "kb_indexing/data/qasper_eval_20260926"
    qrels = [json.loads(line) for line in (source / "qrels_test_candidate.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    selected = sorted(qrels, key=lambda q: hashlib.sha256(q["query"].encode()).hexdigest())[:3]
    source_manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    for name in ("corpus.jsonl", "qrels_test_candidate.jsonl"):
        if digest(source / name) != source_manifest["output_hashes"][name]:
            raise ValueError("QASPER source differs from recorded provenance")
    # The original audit reports remaining semantic overlap uncertainty: retain it.
    save(directory / "source-provenance.json", source_manifest)
    docs = [json.loads(line) for line in (source / "corpus.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    corpus_files = {}
    def corpus(name, texts):
        path = directory / (name + ".jsonl")
        rows = [{"doc_id": f"{name}:{i}", "source_id": f"{name}:{i}", "text": text, "metadata": {"origin": "controlled_fixture"}} for i, text in enumerate(texts)]
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        corpus_files[name] = path.name
        return rows
    background = ["Venus is a planet.", "The instrument measured temperature.", "The archive contains maps."]
    corpus("sufficient", ["The Orion trial enrolled 42 participants.", *background])
    corpus("missing", ["Orion trial sample size: the sample size is reported in the appendix.",
                       "Appendix. Forty-two participants were enrolled in Orion.", *background])
    corpus("conflict", ["The Orion trial enrolled 42 participants.", "The Orion trial enrolled 71 participants.", *background])
    pdf = fitz.open()
    for text in ["Orion trial sample size: see the appendix for the final count.",
                 "Orion trial sample size collection protocol describes recruitment.",
                 "Orion trial sample size procedures cover participant eligibility.",
                 "Appendix: The participant count was 42."]:
        pdf.new_page().insert_text((50, 90), text, fontsize=12)
    pdf.save(directory / "extra-pages.pdf")
    pdf.close()
    cases = [
        {"id": "sufficient", "question": "How many participants did the Orion trial enroll?", "corpus": "sufficient.jsonl", "top_k": 5},
        {"id": "missing", "question": "What is the Orion trial sample size?", "corpus": "missing.jsonl", "top_k": 1},
        {"id": "conflict", "question": "How many participants did the Orion trial enroll?", "corpus": "conflict.jsonl", "top_k": 5},
        {"id": "pdf_pages", "question": "What is the Orion trial sample size?", "pdf": "extra-pages.pdf", "corpus": "sufficient.jsonl", "top_k": 5},
        {"id": "budget", "question": "How many participants did the Orion trial enroll?", "corpus": "sufficient.jsonl", "top_k": 5, "max_steps": 1},
    ]
    # Use all paragraphs from each held-out paper; never insert the gold answer into a prompt.
    for index, query in enumerate(selected, 1):
        case_id = f"heldout_{index}"
        prefix = "qasper:" + query["paper_id"] + ":"
        paper_docs = [row for row in docs if row["doc_id"].startswith(prefix)]
        path = directory / (case_id + ".jsonl")
        path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in paper_docs), encoding="utf-8")
        cases.append({"id": case_id, "question": query["query"], "query_id": query["query_id"],
                      "gold_doc_ids": query["relevant_doc_ids"], "corpus": path.name, "top_k": 5,
                      "scope": "paper-scoped held-out candidate; semantic overlap audit remains incomplete"})
    save(directory / "cases.json", cases)
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "real_inference_started": False,
                "files": {p.name: digest(p) for p in directory.iterdir() if p.is_file()},
                "criteria_version": criteria["version"], "independent_test_proven": False}
    save(directory / "frozen-manifest.json", manifest)
    return manifest


def verify_frozen(directory: Path) -> tuple[dict, list[dict]]:
    manifest = json.loads((directory / "frozen-manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest["files"].items():
        if Path(name).name != name or digest(directory / name) != expected:
            raise ValueError("Frozen evaluation changed: " + name)
    return manifest, json.loads((directory / "cases.json").read_text(encoding="utf-8"))


def score_case(case: dict, state: dict, *, elapsed_ms: float | None = None) -> dict:
    claims = {c["claim_id"]: c for c in state.get("verified_claims", [])}
    sentences = state.get("final_report", {}).get("sentences", [])
    sources = state.get("seen_chunks", [])
    citations_ok = all(s.get("claim_ids") and set(s["claim_ids"]) <= claims.keys() for s in sentences)
    evidence_ok = all(any(c["source_id"] == s["source_id"] and c["evidence"] in s["text"] for s in sources) for c in claims.values())
    history = state.get("action_history", [])
    trace_ok = len(state.get("agent_cycles", [])) == len(history) and all(
        all(key in cycle for key in ("observation", "delegation", "local_execution", "evaluation", "handoff_to"))
        for cycle in state.get("agent_cycles", []))
    budget = state.get("budget", {})
    budget_checks = {
        "steps": state.get("steps_used", 0) <= budget.get("max_steps", 0),
        "searches": state.get("search_count", 0) <= budget.get("max_searches", 0),
        "factchecks": state.get("factcheck_calls_used", 0) <= budget.get("policy", {}).get("max_factcheck_calls", 0),
        "time": elapsed_ms <= budget.get("max_seconds", 0) * 1000 if elapsed_ms is not None else None,
        "cost_reservation": (state.get("reserved_cost_usd", 0) <= budget["max_cost_usd"]
                             if budget.get("max_cost_usd") is not None else None),
    }
    safe = (bool(state.get("stop_reason")) and citations_ok and evidence_ok and trace_ok
            and all(value is not False for value in budget_checks.values()))
    complete = state.get("status") == "completed" and bool(sentences) and all(t["status"] == "complete" for t in state.get("research_plan", {}).get("tasks", []))
    scenario = case["id"]
    if scenario == "sufficient":
        passed = complete
    elif scenario == "missing":
        passed = state.get("search_count", 0) >= 2 and (complete or state.get("status") in {"partial", "insufficient_evidence", "needs_input"})
    elif scenario == "conflict":
        conflict_claims = {r["claim"] for r in state.get("fact_check_results", []) if r["label"] == "contradict"}
        observed = {s["doc_id"] for s in sources}
        passed = {"conflict:0", "conflict:1"} <= observed and bool(conflict_claims) and not conflict_claims.intersection(c["text"] for c in claims.values())
    elif scenario == "pdf_pages":
        passed = sum(h["action"] == "read" for h in history) >= 2 and any(":p3:" in c["source_id"] for c in claims.values())
    elif scenario == "budget":
        passed = state.get("stop_reason") == "step_budget_exhausted" and state.get("steps_used") == 1 and len(history) == 1
    else:
        cited_ids = {cid for sentence in sentences for cid in sentence["claim_ids"]}
        used_sources = {claims[cid]["source_id"] for cid in cited_ids if cid in claims}
        used_docs = {s["doc_id"] for s in sources if s["source_id"] in used_sources}
        passed = complete and bool(used_docs.intersection(case["gold_doc_ids"]))
    return {"automated_gate_pass": safe and bool(passed), "safety_gate_pass": safe,
            "budget_checks": budget_checks,
            "human_review": "pending", "overall_pass": False, "stop_reason": state.get("stop_reason"),
            "status": state.get("status"), "steps": state.get("steps_used"), "search_calls": state.get("search_count"),
            "factcheck_calls": state.get("factcheck_calls_used"), "cost_usd": None, "token_usage": None}


def summarize_results(results: dict, policy_rows: list[dict], *, independent_test_proven: bool) -> dict:
    averages = {}
    for mode in ("adaptive", "bm25", "dense"):
        values = [r["union_recall"] for r in policy_rows if r["policy"] == mode]
        averages[mode] = sum(values) / len(values) if values else None
    expected = {(f"heldout_{i}", mode) for i in range(1, 4) for mode in averages}
    policy_pass = (len(policy_rows) == 9 and {(r["case"], r["policy"]) for r in policy_rows} == expected
                   and averages["adaptive"] >= averages["bm25"]
                   and not any(row["fallback_count"] for row in policy_rows))
    required = {"sufficient", "missing", "conflict", "pdf_pages", "budget", "heldout_1", "heldout_2", "heldout_3"}
    all_pass = set(results) == required and all(r["automated_gate_pass"] for r in results.values()) and policy_pass
    return {"status": "awaiting_human_review" if all_pass else "automated_gates_failed",
            "real_model_cases_run": len(results), "scorer_version": 2,
            "automated_passes": sum(r["automated_gate_pass"] for r in results.values()),
            "retrieval_policy_gate_pass": policy_pass, "mean_union_recall": averages,
            "overall_pass": False, "independent_test_proven": independent_test_proven}


def run(directory: Path, *, online: bool = False) -> dict:
    from research_rag.local import build_local_graph
    from research_rag.preflight import inspect_host, inspect_models
    from research_rag.retrieval import RetrievalAgent, RetrievalService
    from research_rag.indexing import build_indices
    from research_rag.observe import run_with_metrics
    from sentence_transformers import SentenceTransformer
    from research_rag.retrieval import EMBEDDING_MODEL, EMBEDDING_REVISION
    manifest, cases = verify_frozen(directory)
    output = directory / "results"
    output.mkdir(exist_ok=False)
    host = inspect_host()
    save(output / "preflight.json", {"host": host, "models": inspect_models()})
    code = {str(p.relative_to(ROOT)).replace("\\", "/"): digest(p) for folder in ("research_rag", "train_agent2_reader", "train_agent3_summarizer", "04_factchecker", "05_writer") for p in (ROOT / folder).rglob("*.py") if ".venv" not in p.parts}
    save(output / "run-manifest.json", {"started_at": datetime.now(timezone.utc).isoformat(), "frozen_manifest_sha256": digest(directory / "frozen-manifest.json"), "code_sha256": code})
    if not host["cuda_available"]:
        result = {"status": "blocked", "reason": "no_cuda", "real_model_cases_run": 0, "overall_pass": False}
        save(output / "summary.json", result)
        return result
    current_case = ["model_loading"]
    def generation(event):
        with (output / "generations.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"case": current_case[0], **event}, ensure_ascii=False) + "\n")
    try:
        agents = build_local_graph(offline=not online, quantize_4bit=True, components_only=True, on_generation=generation)
        # A single encoder on CPU avoids competing with four decoder models for GPU memory.
        encoder = SentenceTransformer(EMBEDDING_MODEL, revision=EMBEDDING_REVISION, local_files_only=not online, device="cpu")
    except Exception as exc:
        result = {"status": "blocked", "reason": "model_loading:" + type(exc).__name__, "real_model_cases_run": 0, "overall_pass": False}
        save(output / "summary.json", result)
        raise
    results = {}
    policy_rows = []
    for case in cases:
        current_case[0] = case["id"]
        events = []
        case_dir = output / case["id"]
        case_dir.mkdir()
        corpus = directory / case["corpus"]
        index = output / (corpus.stem + "-index")
        if not index.exists():
            build_indices(corpus, index)
        service = RetrievalService(corpus, index, encoder=encoder, offline=not online)
        # Build the exact BGE FAISS artifacts using the already loaded encoder.
        service._load_static()
        import faiss
        import numpy as np
        vectors = np.asarray(encoder.encode([r["text"] for r in service._rows], normalize_embeddings=True), dtype="float32")
        service._faiss_index = faiss.IndexFlatIP(vectors.shape[1])
        service._faiss_index.add(vectors)
        configured = dict(agents, retriever=RetrievalAgent(service))
        def event(record):
            events.append(record)
            with (case_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record) + "\n")
        # Reader processes pages synchronously and the API is rate limited to
        # one request start per 61 seconds. Four PDF pages need a longer task
        # deadline even before model inference. The one-step budget case keeps
        # its original limit.
        deadline = 900 if case.get("pdf") else 300
        graph = build_local_graph(agents=configured, initial_top_k=case["top_k"], max_graph_retries=3,
                                  max_steps=case.get("max_steps", 30), max_seconds=deadline, on_event=event)
        inputs = {"question": case["question"]}
        if case.get("pdf"):
            inputs["pdf_path"] = str(directory / case["pdf"])
        try:
            state, metrics = run_with_metrics(graph, inputs)
            save(case_dir / "state.json", state)
            save(case_dir / "metrics.json", metrics)
            results[case["id"]] = score_case(case, state, elapsed_ms=metrics["total_ms"]) | {"total_ms": metrics["total_ms"]}
        except Exception as exc:
            results[case["id"]] = {"automated_gate_pass": False, "overall_pass": False, "status": "error", "error_type": type(exc).__name__}
        save(output / "case-results.json", results)
        print(json.dumps({"case": case["id"], **results[case["id"]]}), flush=True)
        if case.get("gold_doc_ids"):
            for mode in ("adaptive", "bm25", "dense"):
                agent = RetrievalAgent(service, policy=mode)
                state = {"question": case["question"], "research_plan": create_plan(case["question"]), "active_task_id": "t1",
                         "search_count": 0, "budget": {"max_searches": 2}, "retrieval_history": [], "agent_result": {}}
                hits, fallback, started = set(), 0, time.perf_counter()
                first_hit = False
                for iteration in range(2):
                    response = agent.run(state=state, top_k=5)
                    ids = [c["doc_id"] for c in response["chunks"]]
                    hits.update(ids)
                    if iteration == 0:
                        first_hit = bool(hits.intersection(case["gold_doc_ids"]))
                    fallback += bool(response.get("warning"))
                    state["search_count"] += 1
                    state["retrieval_history"].append({"task_id": "t1", "query": response.get("query"), "requested_method": response.get("requested_method"), "tool": response["decision"], "top_k": 5, "doc_ids": ids, "has_hits": bool(ids)})
                    state["agent_result"] = {"missing_information": ["Coverage probe after initial retrieval"]}
                policy_rows.append({"case": case["id"], "policy": mode, "hit_at_5": first_hit,
                                    "union_recall": len(hits.intersection(case["gold_doc_ids"])) / len(case["gold_doc_ids"]),
                                    "fallback_count": fallback, "latency_ms": (time.perf_counter() - started) * 1000})
            save(output / "retrieval-policy.json", policy_rows)
    result = summarize_results(results, policy_rows, independent_test_proven=manifest["independent_test_proven"])
    save(output / "summary.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "run"])
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--online-model-downloads", action="store_true")
    args = parser.parse_args()
    result = prepare(args.directory) if args.mode == "prepare" else run(args.directory, online=args.online_model_downloads)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.mode == "run" and result["status"] != "awaiting_human_review":
        raise SystemExit(2 if result["status"] == "blocked" else 1)


if __name__ == "__main__":
    main()
