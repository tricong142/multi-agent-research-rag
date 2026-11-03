"""Offline integrity and human annotation admission for Cellfix16 holdout v2."""
import argparse
from collections import Counter
import json
from pathlib import Path, PurePosixPath

if __package__:
    from .atomic_validation_review import admit, digest, json_bytes, packet, write_once, CHECKS
else:
    from annotation_gate_core import admit, digest, json_bytes, packet, write_once, CHECKS

CRITERIA_SHA256 = "c025247428698d892e549fb12ad22e19561020b034a2a2276c9dfcaf0cbdc966"


def verify(folder):
    folder = Path(folder).resolve()
    lock = json.loads((folder / "packet-lock.json").read_bytes())
    if lock["candidate_criteria_sha256"] != CRITERIA_SHA256:
        raise ValueError("Wrong holdout candidate")
    for name, item in lock["files"].items():
        rel = PurePosixPath(name)
        target = (folder / name).resolve()
        if rel.is_absolute() or ".." in rel.parts or "\\" in name or ":" in name or not target.is_relative_to(folder):
            raise ValueError("Unsafe holdout path")
        raw = target.read_bytes()
        if len(raw) != item["size"] or digest(raw) != item["sha256"]:
            raise ValueError("Holdout hash mismatch: " + name)
    manifest, rows = packet(folder)
    if manifest["candidate_criteria_sha256"] != CRITERIA_SHA256 or manifest["evaluation_role"] != "independent_holdout_candidate":
        raise ValueError("Wrong holdout identity")
    if len(rows) != 30 or len({r["group_id"] for r in rows}) != 10:
        raise ValueError("Holdout must contain 30 cases from 10 papers")
    expected_labels = {"support": 10, "contradict": 10, "not_enough_info": 10}
    if dict(Counter(r["proposed_gold"] for r in rows)) != expected_labels:
        raise ValueError("Unbalanced holdout labels")
    blind = [json.loads(s) for s in (folder / "inputs.jsonl").read_text(encoding="utf-8").splitlines()]
    if blind != [{k: r[k] for k in ("id", "claim", "context")} for r in rows]:
        raise ValueError("Blind inputs differ from locked cases")
    sources = {s["doc_id"]: s for s in (json.loads(line) for line in (folder / "sources.jsonl").read_text(encoding="utf-8").splitlines())}
    registry = json.loads((folder / "exposure-registry.json").read_bytes())
    overlap = json.loads((folder / "overlap-report.json").read_bytes())
    if overlap["flags"] or overlap["document_overlap"]:
        raise ValueError("Unresolved exposure overlap")
    for row in rows:
        if row["group_id"] in registry["excluded_papers"]:
            raise ValueError("Holdout paper previously exposed")
        if row["group_id"] != row["source"]["paper_id"]:
            raise ValueError("Paper grouping mismatch")
        source = sources[row["source"]["doc_id"]]
        if source["text"] != row["context"] or digest(row["context"].encode()) != row["source"]["context_sha256"]:
            raise ValueError("Context differs from cached source")
        if len(row["claim"].split()) > 80 or len(row["context"].split()) > 600:
            raise ValueError("Input exceeds frozen candidate limits")
        if not row["evidence"]:
            raise ValueError("Evidence span required")
        for span in row["evidence"]:
            if (type(span["start"]) is not int or type(span["end"]) is not int or
                    not 0 <= span["start"] < span["end"] <= len(row["context"]) or not span["quote"]):
                raise ValueError("Invalid evidence offsets")
        if row["proposed_gold"] == "not_enough_info" and row["evidence_role"] != "related_not_proof_of_absence":
            raise ValueError("NEI span must not be represented as proof of absence")
    return manifest, rows


def admit_holdout(folder, review):
    verify(folder)
    for decision in review.get("decisions", []):
        if any(decision.get("checks", {}).get(key) is not True for key in CHECKS):
            raise ValueError("Every human annotation criterion must be explicitly true")
    result = admit(folder, review)
    return {**result, "evaluation_role": "independent_holdout_candidate",
            "annotation_review_sha256": digest(json_bytes(review)),
            "packet_lock_sha256": digest((Path(folder) / "packet-lock.json").read_bytes()),
            "independent_validation_completed": False, "promoted_to_serving": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--lock", type=Path)
    args = parser.parse_args()
    if bool(args.review) != bool(args.lock):
        parser.error("Use --review and --lock together")
    manifest, rows = verify(args.packet)
    if args.review:
        result = admit_holdout(args.packet, json.loads(args.review.read_bytes()))
        write_once(args.lock, json_bytes(result))
    else:
        result = {"status": "frozen_pending_human_annotation", "cases": len(rows), "papers": manifest["papers"],
                  "inference_completed": False, "independent_validation_completed": False}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
