"""Build paragraph qrels from QASPER's human annotations, with leakage checks.

This prepares a separate benchmark; it never overwrites the arXiv corpus/index.
The final split is a candidate until unresolved training provenance is reviewed.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib
import json
from pathlib import Path
import re
import unicodedata


def normalize(text):
    return " ".join(unicodedata.normalize("NFKC", text).split())


def shingles(text):
    words = re.findall(r"[a-z0-9]+", normalize(text).lower())
    return {tuple(words[i:i + 12]) for i in range(max(0, len(words) - 11))}


def paper_records(paper):
    """Map annotated evidence exactly; reject incomplete or visual mappings."""
    helper = importlib.import_module("05_writer.generate_training_data")
    paragraphs = helper._paragraphs(paper)
    lookup = {}
    corpus = []
    for index, text in enumerate(paragraphs):
        if not text.strip():
            continue
        doc_id = f"qasper:{paper['id']}:paragraph:{index}"
        lookup.setdefault(normalize(text), []).append(doc_id)
        corpus.append({"doc_id": doc_id, "source_id": doc_id, "text": text,
                       "metadata": {"paper_id": paper["id"], "title": paper["title"],
                                    "paragraph_index": index, "dataset": "allenai/qasper", "license": "CC-BY-4.0"}})
    qrels, rejected = [], Counter()
    for question in helper.columnar_records(paper["qas"], "question"):
        answers = helper.normalize_answers(question)
        if not answers or any(a.get("unanswerable", False) for a in answers):
            rejected["unanswerable_or_disagreement"] += 1
            continue
        polarities = {a.get("yes_no") for a in answers if a.get("yes_no") is not None}
        if len(polarities) > 1:
            rejected["answer_disagreement"] += 1
            continue
        evidence = {normalize(e) for a in answers for e in a.get("evidence", []) if e.strip()}
        if not evidence or any(e not in lookup for e in evidence):
            rejected["missing_visual_or_unmatched_evidence"] += 1
            continue
        qrels.append({"query_id": question["question_id"], "paper_id": paper["id"],
                      "query": f"In the paper '{paper['title']}', {question['question']}",
                      "original_question": question["question"],
                      "relevant_doc_ids": sorted({doc_id for e in evidence for doc_id in lookup[e]}),
                      "label_origin": "QASPER human evidence annotations; union across answerers",
                      "query_adaptation": "Paper title prefixed to disambiguate corpus-wide retrieval"})
    return corpus, qrels, rejected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arrow-test", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise ValueError("Use a new output directory to preserve the frozen benchmark")
    cache_info = args.arrow_test.parent / "dataset_info.json"
    expected_source = "hf://datasets/allenai/qasper@06806e4608976fc2fac0a090ac425d5b2b29caf4/qasper/test/0000.parquet"
    if args.arrow_test.name != "parquet-test.arrow" or expected_source not in json.loads(cache_info.read_text())["download_checksums"]:
        raise ValueError("Input cache must identify the pinned QASPER test source")
    import pyarrow as pa

    root = Path(__file__).resolve().parents[2]
    exclusions = [root / "05_writer/data/writer_sft_validated.jsonl",
                  root / "05_writer/data/writer_eval_candidates.jsonl",
                  root / "05_writer/data/writer_eval_manual.jsonl"]
    summary_files = [root / "train_agent3_summarizer/data/summarizer_sft_validated.jsonl",
                     root / "train_agent3_summarizer/data/summarizer_eval_manual.jsonl"]
    seen_papers, training_shingles = set(), set()
    for path in exclusions:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                seen_papers.add(str(json.loads(line)["paper_id"]))
    for path in summary_files:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                training_shingles.update(shingles(json.loads(line)["context"]))
    with pa.memory_map(str(args.arrow_test), "r") as stream:
        papers = pa.ipc.open_stream(stream).read_all().to_pylist()
    corpus, partitions, rejected, excluded = [], {"dev": [], "test_candidate": []}, Counter(), {}
    for paper in papers:
        rows, qrels, skipped = paper_records(paper)
        if paper["id"] in seen_papers:
            excluded[paper["id"]] = "writer_train_validation_or_development_test_candidates"
            continue
        if any(shingles(row["text"]) & training_shingles for row in rows):
            excluded[paper["id"]] = "summarizer_context_12_token_overlap"
            continue
        rejected.update(skipped)
        corpus.extend(rows)
        split = "dev" if int(hashlib.sha256(paper["id"].encode()).hexdigest()[:8], 16) % 2 == 0 else "test_candidate"
        partitions[split].extend(qrels)
    ids = {row["doc_id"] for row in corpus}
    assert len(ids) == len(corpus)
    assert all(set(q["relevant_doc_ids"]) <= ids for rows in partitions.values() for q in rows)
    assert not ({r["paper_id"] for r in partitions["dev"]} & {r["paper_id"] for r in partitions["test_candidate"]})
    args.output_dir.mkdir(parents=True)
    for name, rows in {"corpus": corpus, **{f"qrels_{k}": v for k, v in partitions.items()}}.items():
        with (args.output_dir / f"{name}.jsonl").open("x", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    manifest = {
        "source": "allenai/qasper", "native_split": "test",
        "source_revision": "06806e4608976fc2fac0a090ac425d5b2b29caf4",
        "cache_provenance_verified": True,
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "source_card": "https://huggingface.co/datasets/allenai/qasper",
        "attribution": "Dasigi, Lo, Beltagy, Cohan, Smith and Gardner (2021), A Dataset of Information-Seeking Questions and Answers Anchored in Research Papers",
        "transformations": "One original paragraph per chunk; exact normalized evidence mapping; union annotations; paper title prefix; deterministic paper-level split",
        "input_hashes": {str(p.relative_to(root)) if p.is_relative_to(root) else p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in [args.arrow_test, cache_info, *exclusions, *summary_files]},
        "excluded_papers": excluded, "rejected_questions": dict(rejected), "corpus_chunks": len(corpus),
        "qrels": {k: len(v) for k, v in partitions.items()},
        "output_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in args.output_dir.glob("*.jsonl")},
        "independent_end_to_end_test": False,
        "remaining_review": "Summarizer source_doc_id values are not reliable paper IDs. Token overlap screening cannot prove semantic non-overlap. Base-model pretraining exposure is unknown. Confirm provenance before final-test use.",
        "metric_scope": "Recall of annotated text paragraphs; omitted unanswerable, disagreeing, visual or unmatched questions. Not exhaustive relevance outside annotations.",
        "indices_built": False,
    }
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ["corpus_chunks", "qrels", "rejected_questions", "independent_end_to_end_test"]}, indent=2))
    print("Excluded papers:", len(excluded))


if __name__ == "__main__":
    main()
