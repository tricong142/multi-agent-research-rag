"""Prepare a paper-disjoint, review-pending holdout offline, without model calls."""
import ast
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import io
import zipfile

from scripts.atomic_validation_review import CHECKS, digest, json_bytes, write_once
from scripts.prepare_atomic_validation_v1 import lines, strings, tokens, grams, near, review_html

ROOT = Path(__file__).resolve().parents[1]
QASPER = ROOT / "kb_indexing/data/qasper_eval_20260926"
DEST = ROOT / "docs/validation/atomic-cellfix16-holdout30-v2"
AUTHORING = ROOT / "scripts/fixtures/atomic_holdout_v2_authoring.json"
ARXIV = re.compile(r"(?<![\w.])\d{2}(?:0[1-9]|1[0-2])\.\d{4,5}(?:v\d+)?(?!\d)")


def values(path):
    if path.suffix == ".py":
        return (n.value for n in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig")))
                if isinstance(n, ast.Constant) and isinstance(n.value, str))
    if path.suffix == ".jsonl":
        return (s for row in lines(path) for s in strings(row))
    return strings(json.loads(path.read_bytes()))


def inventory():
    upstream = json.loads((QASPER / "manifest.json").read_bytes())
    for name, expected in upstream["output_hashes"].items():
        if digest((QASPER / name).read_bytes()) != expected:
            raise ValueError("QASPER source changed: " + name)
    paths = set()
    for folder in ("research_rag/evaluation", "research_rag/tests", "04_factchecker/data",
                   "05_writer/data", "train_agent3_summarizer/data", "train_agent1_retrieval/data"):
        paths.update(p for p in (ROOT / folder).rglob("*") if p.suffix in (".py", ".json", ".jsonl"))
    paths.discard(ROOT / "research_rag/tests/test_atomic_holdout_v2.py")
    # Include source rules and previous scripts/fixtures, never the new authoring or outputs.
    paths.update((ROOT / "04_factchecker/inference").glob("*.py"))
    paths.update(p for p in (ROOT / "scripts").glob("*cellfix*.py"))
    paths.update((ROOT / "scripts/fixtures").glob("*cellfix*.json"))
    for p in (ROOT / "docs/validation").rglob("cases.jsonl"):
        if not p.is_relative_to(DEST):
            paths.add(p)
    paths.add(ROOT / "kb_indexing/data/corpus.jsonl")
    paths.add(QASPER / "qrels_dev.jsonl")
    for base in ("research-runs/colab-qasper-benchmark", "research-runs/qasper-dev-20261016-bm25-preflight",
                 "research-runs/qasper_eval_20260926"):
        paths.update(p for p in (ROOT / base).rglob("*.jsonl"))
    candidate = json.loads((ROOT / "docs/atomic-verifier-cellfix16-candidate.json").read_bytes())
    source = ROOT / "research-runs/atomic-cellfix16-candidate/workspace"
    paths.update(source / name for name in candidate["input_manifest"]
                 if name.endswith((".py", ".json", ".jsonl")) and
                 name.startswith(("research_rag/evaluation/", "research_rag/tests/", "04_factchecker/inference/")))
    blocked, hashes = defaultdict(set), {}
    for path in sorted(paths):
        hashes[path.relative_to(ROOT).as_posix()] = digest(path.read_bytes())
        for value in values(path):
            for match in ARXIV.finditer(value):
                blocked[match.group().split("v")[0]].add(path.relative_to(ROOT).as_posix())
    test = {r["paper_id"] for r in lines(QASPER / "qrels_test_candidate.jsonl")}
    return upstream, sorted(paths), dict(blocked), hashes, test


def inspect():
    upstream, paths, blocked, hashes, test = inventory()
    eligible = test - set(blocked)
    corpus = list(lines(QASPER / "corpus.jsonl"))
    by_paper = defaultdict(list)
    qrel_docs = {d for r in lines(QASPER / "qrels_test_candidate.jsonl") for d in r["relevant_doc_ids"]}
    for row in corpus:
        if row["metadata"]["paper_id"] in eligible and row["doc_id"] in qrel_docs:
            text = row["text"]
            if 35 <= len(text.split()) <= 200 and not re.search(r"[\\$]|INLINEFORM|DISPLAYFORM", text):
                by_paper[row["metadata"]["paper_id"]].append(row)
    ordered = sorted(by_paper, key=lambda p: hashlib.sha256(("holdout-v2:" + p).encode()).hexdigest())
    report = {"source": upstream["source"], "scanned_files": len(paths), "blocked_papers": len(blocked),
              "test_papers": len(test), "eligible_papers": len(eligible),
              "paragraphs": [row for paper in ordered[:22] for row in by_paper[paper][:2]]}
    target = ROOT / "research-runs/holdout-v2-source-inspection.json"
    target.write_bytes(json_bytes(report))
    print(json.dumps({k: v for k, v in report.items() if k != "paragraphs"}))


def archive(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, raw in sorted(files.items()):
            item = zipfile.ZipInfo(name, (2026, 11, 3, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(item, raw)
    return stream.getvalue()


def screen(rows, paths, blocked, hashes, test):
    targets = {r["id"] + ":claim": tokens(r["claim"]) for r in rows}
    targets.update({r["source"]["doc_id"]: tokens(r["context"]) for r in rows})
    index = defaultdict(set)
    for key, words in targets.items():
        for gram in grams(words):
            index[gram].add(key)
    sets = {key: set(words) for key, words in targets.items()}
    flags, count = [], 0
    for path in paths:
        seen = set()
        for value in values(path):
            words = tokens(value)
            if len(words) < 6 or tuple(words) in seen:
                continue
            seen.add(tuple(words))
            count += 1
            hits, ws = set(), set(words)
            for gram in grams(words):
                hits.update(index.get(gram, ()))
            for key, ts in sets.items():
                if len(ws & ts) / max(1, len(ws | ts)) >= .8:
                    hits.add(key)
            for key in sorted(hits):
                found, similarity, shared = near(targets[key], words)
                if found:
                    flags.append({"target": key, "file": path.relative_to(ROOT).as_posix(),
                                  "text_sha256": digest(value.encode()), "token_jaccard": similarity,
                                  "shared_eight_tokens": [" ".join(g) for g in sorted(shared)[:3]]})
    papers = {r["group_id"] for r in rows}
    return {"flags": flags, "document_overlap": sorted(papers & set(blocked)),
            "selected_papers": sorted(papers), "selected_in_test_candidate": papers <= test,
            "scanned_files_sha256": hashes, "scanned_strings": count,
            "normalization": "NFKC; lowercase alphanumeric tokens",
            "flag_rules": ["exact normalized text", "token-set Jaccard >= 0.8 with >=6 tokens",
                           "any shared contiguous eight-token phrase"],
            "model_outputs_on_holdout_used": False,
            "limitations": ["Lexical checks cannot prove semantic non-overlap.",
                            "Unreliable Summarizer document IDs prevent a complete paper-level training exclusion proof.",
                            "The cached QASPER corpus was previously indexed; this is not an unseen-corpus retrieval benchmark.",
                            "Base-model pretraining exposure is unknown."]}


README = """# Cellfix16 holdout30-v2 — frozen, pending human annotation

30 assistant-authored claims, 10 previously unexposed arXiv papers in the cached
QASPER test corpus; 10 SUPPORT / 10 CONTRADICT / 10 NEI. Internal labels are
support / contradict / not_enough_info. New means new to known project exposure,
not newly published in 2026. Annotation is AI-proposed, not human-certified gold.

Open REVIEW.html offline, read every supplied paragraph, review the labels and
spans, then export annotation-review.json. There are no pre-approved checks.
NEI is relative to the supplied paragraph; a related quote is not proof that a
fact is absent from the complete paper. Sources retain the original cached
QASPER text, including BIBREF markers; exactness is against that text, not a
freshly downloaded PDF. Source URLs are attribution links, not network requests.

Verify offline from the repository root:

    python docs/validation/atomic-cellfix16-holdout30-v2/review_gate.py --packet docs/validation/atomic-cellfix16-holdout30-v2

After direct human annotation, admit without model inference:

    python docs/validation/atomic-cellfix16-holdout30-v2/review_gate.py --packet docs/validation/atomic-cellfix16-holdout30-v2 --review PATH/annotation-review.json --lock PATH/holdout-annotation-admission.json

The lock covers source snapshots, claims, proposed labels, exact offsets, blind
inputs, protocol, exposure screen and review tooling. Do not edit a locked packet;
annotation corrections need a new version before any candidate outcomes are seen.
The admission JSON binds the normalized review content to this packet/candidate.

blind-inputs.zip contains only inputs.jsonl (id/claim/context) and model-settings.json;
give only that ZIP to model inference. Keep cases.jsonl and the full review packet
on the evaluation side. Do not use the new labels/claims to repair Cellfix16 rules.
If outcomes inform tuning, retire this packet to development and create another
holdout. Preserve all outcomes and technical reruns. Ten paper clusters with
three contrast siblings each are a small purposive pilot, not 30 independent
documents, a population guarantee, or end-to-end serving certification.

Before inference require human annotation admission, the same Cellfix16
smoke/probe/full39 gates and the preregistered dev30 result. The existing notebook
cell7 is bound to development30; this packet does not replace that cell or change
its metrics/gates. No holdout inference or promotion has been performed by this
preparation script. Use a separate one-shot holdout job on the blind inputs and
score against the locked cases with the protocol in criteria.json.
"""


def build():
    upstream, paths, blocked, hashes, test = inventory()
    release_path = ROOT / "docs/atomic-verifier-cellfix16-release.json"
    release = json.loads(release_path.read_bytes())
    from scripts.atomic_holdout_review import CRITERIA_SHA256, verify
    if release["criteria_sha256"] != CRITERIA_SHA256:
        raise ValueError("Freeze a separate holdout for a different candidate")
    for name, expected in release["files"].items():
        if digest((ROOT / name).read_bytes()) != expected:
            raise ValueError("Frozen candidate release changed: " + name)
    corpus = {r["doc_id"]: r for r in lines(QASPER / "corpus.jsonl")}
    qrel_docs = {d for r in lines(QASPER / "qrels_test_candidate.jsonl") for d in r["relevant_doc_ids"]}
    rows, sources = [], {}
    for group in json.loads(AUTHORING.read_bytes()):
        paper = group["paper_id"]
        doc_id = f'qasper:{paper}:paragraph:{group["paragraph_index"]}'
        if paper not in test or paper in blocked or doc_id not in qrel_docs:
            raise ValueError("Exposed or unavailable holdout source: " + doc_id)
        source = corpus[doc_id]
        sources[doc_id] = source
        for case in group["cases"]:
            quote = case["quote"]
            if source["text"].count(quote) != 1:
                raise ValueError("Quote must occur exactly once in cached source: " + doc_id)
            start = source["text"].index(quote)
            label = case["label"]
            rows.append({"id": f'holdout-v2:{len(rows)+1:03d}', "group_id": paper,
                "claim": case["claim"], "context": source["text"], "proposed_gold": label,
                "evidence": [{"quote": quote, "start": start, "end": start + len(quote)}],
                "evidence_role": "related_not_proof_of_absence" if label == "not_enough_info" else "label_evidence",
                "missing_information": case["missing"], "rationale": case["rationale"], "tags": case["tags"],
                "source": {**source["metadata"], "doc_id": doc_id,
                           "context_sha256": digest(source["text"].encode()), "paper_url": "https://arxiv.org/abs/" + paper}})
    if len(rows) != 30 or len(sources) != 10 or Counter(r["proposed_gold"] for r in rows) != Counter(support=10, contradict=10, not_enough_info=10):
        raise ValueError("Require 30 balanced cases from ten papers")
    overlap = screen(rows, paths, blocked, hashes, test)
    if overlap["flags"] or overlap["document_overlap"]:
        (ROOT / "research-runs/holdout-v2-overlap-inspection.json").write_bytes(json_bytes(overlap))
        raise ValueError("Unresolved overlap; inspect offline screen before freezing")
    registry = {"excluded_papers": {p: sorted(v) for p, v in sorted(blocked.items())},
                "selected_papers": sorted(r["group_id"] for r in rows[::3]),
                "scanned_files_sha256": hashes, "candidate_frozen_before_annotation": True}
    model_settings = {"model": "Qwen/Qwen2.5-3B-Instruct", "revision": "aa8e72537993ba99e69dfaafa59ed015b17504d1",
                      "seed": 42, "quantization": "NF4", "dtype": "float16", "do_sample": False,
                      "candidate_criteria_sha256": CRITERIA_SHA256,
                      "budget": {"calls_per_case": 8, "attempts_per_stage": 2, "new_tokens_per_call": 1536,
                                 "seconds_per_case": 180, "maximum_calls": 240, "maximum_generated_tokens": 368640}}
    protocol = {"version": "independent-verifier-pilot-v2", "scope": "supplied-context verifier; not pipeline E2E",
        **model_settings, "gate": {"cases": 30, "correct_labels": 30, "false_support": 0,
            "runtime_failed_rows": 0, "every_paper_complete_and_correct": True,
            "measured_token_budget_required": True, "decode_and_deadline_trace_required": True},
        "prerequisites": ["Direct human annotation admission", "Same-candidate smoke12, probe18 and human review",
                          "Same-candidate full39 and human review", "Record the preregistered dev30 result before holdout inference"],
        "report": ["confusion", "per_label_precision_recall", "support_recall", "false_support_and_denominator",
                   "runtime_failures", "per_paper_results", "latency", "backend_calls", "prompt_tokens", "generated_tokens"],
        "outcome_policy": "One preregistered quality run; preserve failures and declared technical reruns. Retire to development if used for tuning.",
        "label_origin": "AI-proposed; direct human adjudication pending",
        "limitations": overlap["limitations"] + ["Three contrast siblings per paper are correlated; not a representative random sample."]}
    provenance = {**{k: upstream[k] for k in ("source", "native_split", "source_revision", "source_card", "license_url", "attribution")},
        "upstream_manifest_sha256": digest((QASPER / "manifest.json").read_bytes()),
        "output_hashes": upstream["output_hashes"], "candidate_release_sha256": digest(release_path.read_bytes()),
        "annotation_origin": "AI-authored new claims and proposed labels; evidence copied exactly from cached QASPER paragraphs",
        "selection": "Paper-ID and lexical exposure exclusions, then manual semantic coverage selection before any candidate run; not selected by candidate scores.",
        "publication_recency_claimed": False, "model_outputs_on_holdout_used": False,
        "network_requests": 0, "new_model_inference": False}
    jsonl = lambda records: b"".join((json.dumps(r, ensure_ascii=False) + "\n").encode() for r in records)
    files = {"cases.jsonl": jsonl(rows), "inputs.jsonl": jsonl([{k: r[k] for k in ("id", "claim", "context")} for r in rows]),
             "sources.jsonl": jsonl(sources.values()), "criteria.json": json_bytes(protocol),
             "model-settings.json": json_bytes(model_settings), "overlap-report.json": json_bytes(overlap),
             "exposure-registry.json": json_bytes(registry), "source-provenance.json": json_bytes(provenance),
             "authoring.json": AUTHORING.read_bytes(), "review_gate.py": (ROOT / "scripts/atomic_holdout_review.py").read_bytes(),
             "annotation_gate_core.py": (ROOT / "scripts/atomic_validation_review.py").read_bytes()}
    manifest = {"version": "atomic-cellfix16-holdout30-v2", "status": "frozen_pending_human_annotation",
        "candidate": release["candidate"], "candidate_criteria_sha256": CRITERIA_SHA256,
        "evaluation_role": "independent_holdout_candidate", "cases": 30, "papers": 10,
        "proposed_label_counts": dict(Counter(r["proposed_gold"] for r in rows)),
        "files": {name: {"size": len(raw), "sha256": digest(raw)} for name, raw in sorted(files.items())},
        "human_adjudication_complete": False, "inference_completed": False, "independent_validation_completed": False}
    files["manifest.json"] = json_bytes(manifest)
    template = {"review_type": "human", "reviewer": "", "reviewed_on": "", "human_attestation": False,
        "provenance_limits_acknowledged": False, "no_candidate_outcomes_seen": False, "protocol_accepted": False,
        "manifest_sha256": digest(files["manifest.json"]), "candidate_criteria_sha256": CRITERIA_SHA256,
        "decisions": [{"id": r["id"], "accepted_label": None, "checks": dict.fromkeys(CHECKS), "note": ""} for r in rows]}
    files["annotation-review.template.json"] = json_bytes(template)
    files["REVIEW.html"] = review_html(rows, template).replace(b"cellfix6", b"cellfix16-holdout-v2")
    files["README.md"] = README.encode()
    files["blind-inputs.zip"] = archive({n: files[n] for n in ("inputs.jsonl", "model-settings.json")})
    lock = {"version": "holdout-v2-content-lock", "candidate_criteria_sha256": CRITERIA_SHA256,
            "files": {n: {"size": len(raw), "sha256": digest(raw)} for n, raw in sorted(files.items())}}
    files["packet-lock.json"] = json_bytes(lock)
    for name, raw in files.items():
        write_once(DEST / name, raw)
    verify(DEST)
    bundle = archive(files)
    write_once(DEST / "review-packet.zip", bundle)
    report = {"version": manifest["version"], "cases": 30, "papers": 10,
        "label_counts": manifest["proposed_label_counts"], "scanned_files": len(paths),
        "excluded_papers": len(blocked), "eligible_test_papers": len(test - set(blocked)),
        "overlap_flags": len(overlap["flags"]), "document_overlap": overlap["document_overlap"],
        "manifest_sha256": digest(files["manifest.json"]), "packet_lock_sha256": digest(files["packet-lock.json"]),
        "review_packet_zip_sha256": digest(bundle), "blind_inputs_zip_sha256": digest(files["blind-inputs.zip"]),
        "annotation_status": "AI proposed; human review pending", "model_inference_completed": False,
        "independent_validation_completed": False, "promoted_to_serving": False, "network_requests": 0}
    write_once(ROOT / "docs/atomic-verifier-cellfix16-holdout-v2-preparation.json", json_bytes(report))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    import sys
    inspect() if "--inspect" in sys.argv else build()
