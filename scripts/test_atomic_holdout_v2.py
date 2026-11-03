"""Holdout integrity tests only; never call verifier or use outcomes to tune rules."""
from collections import Counter
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

from scripts.atomic_holdout_review import admit_holdout, verify
from scripts.atomic_validation_review import CHECKS, digest, write_once

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs/validation/atomic-cellfix16-holdout30-v2"


def simulated_review():
    """In-memory protocol fixture, not an actual human approval or output file."""
    review = json.loads((DATA / "annotation-review.template.json").read_bytes())
    review.update(reviewer="SIMULATED_TEST_NOT_HUMAN_APPROVAL", reviewed_on="2026-11-03",
                  human_attestation=True, provenance_limits_acknowledged=True,
                  no_candidate_outcomes_seen=True, protocol_accepted=True)
    rows = [json.loads(line) for line in (DATA / "cases.jsonl").read_text(encoding="utf-8").splitlines()]
    for decision, row in zip(review["decisions"], rows):
        decision.update(accepted_label=row["proposed_gold"], checks=dict.fromkeys(CHECKS, True),
                        note="Disposable protocol test fixture; no real person approved this annotation.")
    return review


class HoldoutPacketTests(unittest.TestCase):
    def test_balanced_cases_per_paper_and_limits(self):
        manifest, rows = verify(DATA)
        self.assertEqual(manifest["proposed_label_counts"], {"support": 10, "contradict": 10, "not_enough_info": 10})
        groups = {}
        for row in rows:
            groups.setdefault(row["group_id"], []).append(row)
            self.assertLessEqual(len(row["claim"].split()), 80)
            self.assertLessEqual(len(row["context"].split()), 600)
            for span in row["evidence"]:
                self.assertEqual(row["context"][span["start"]:span["end"]], span["quote"])
                self.assertLessEqual(len(span["quote"]), 384)
        self.assertEqual(len(groups), 10)
        for siblings in groups.values():
            self.assertEqual(Counter(r["proposed_gold"] for r in siblings), Counter(support=1, contradict=1, not_enough_info=1))

    def test_papers_disjoint_from_dev30_and_known_exposure(self):
        _, rows = verify(DATA)
        dev = ROOT / "docs/validation/atomic-cellfix16-dev30-v1/original/cases.jsonl"
        papers = {r["group_id"] for r in rows}
        old = {json.loads(line)["group_id"] for line in dev.read_text(encoding="utf-8").splitlines()}
        registry = json.loads((DATA / "exposure-registry.json").read_bytes())
        overlap = json.loads((DATA / "overlap-report.json").read_bytes())
        self.assertFalse(papers & old)
        self.assertFalse(papers & set(registry["excluded_papers"]))
        self.assertEqual(overlap["flags"], [])
        self.assertGreater(len(registry["scanned_files_sha256"]), 400)
        self.assertFalse(overlap["model_outputs_on_holdout_used"])

    def test_source_snapshots_are_exact_cached_paragraphs(self):
        selected = {r["doc_id"]: r for r in (json.loads(line) for line in (DATA / "sources.jsonl").read_text(encoding="utf-8").splitlines())}
        found = {}
        with (ROOT / "kb_indexing/data/qasper_eval_20260926/corpus.jsonl").open(encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                if row["doc_id"] in selected:
                    found[row["doc_id"]] = row
        self.assertEqual(selected, found)

    def test_blind_archive_excludes_gold_rationales_and_source_metadata(self):
        with zipfile.ZipFile(DATA / "blind-inputs.zip") as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(set(archive.namelist()), {"inputs.jsonl", "model-settings.json"})
            self.assertEqual(archive.read("inputs.jsonl"), (DATA / "inputs.jsonl").read_bytes())
            for line in archive.read("inputs.jsonl").splitlines():
                self.assertEqual(set(json.loads(line)), {"id", "claim", "context"})

    def test_complete_review_archive_contains_all_locked_bytes(self):
        with zipfile.ZipFile(DATA / "review-packet.zip") as archive:
            self.assertIsNone(archive.testzip())
            lock = json.loads(archive.read("packet-lock.json"))
            self.assertEqual(set(archive.namelist()), set(lock["files"]) | {"packet-lock.json"})
            for name, item in lock["files"].items():
                self.assertEqual(digest(archive.read(name)), item["sha256"])

    def test_draft_cannot_be_admitted_and_form_does_not_preapprove(self):
        template = json.loads((DATA / "annotation-review.template.json").read_bytes())
        with self.assertRaises(ValueError):
            admit_holdout(DATA, template)
        form = (DATA / "REVIEW.html").read_text(encoding="utf-8")
        self.assertEqual(form.count("<article data-id="), 30)
        self.assertNotIn('checked="', form)
        self.assertNotIn("checked>", form)
        self.assertFalse(template["human_attestation"])
        self.assertFalse((DATA / "annotation-admission.json").exists())

    def test_admission_protocol_with_disposable_simulated_review(self):
        result = admit_holdout(DATA, simulated_review())
        self.assertFalse(result["inference_completed"])
        self.assertFalse(result["independent_validation_completed"])
        self.assertFalse(result["promoted_to_serving"])

    def test_wrong_hash_gold_and_non_boolean_reviews_rejected(self):
        for kind in ("hash", "gold", "boolean"):
            review = simulated_review()
            if kind == "hash":
                review["manifest_sha256"] = "0" * 64
            elif kind == "gold":
                review["decisions"][0]["accepted_label"] = "contradict"
            else:
                review["decisions"][0]["checks"][CHECKS[0]] = 1
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                admit_holdout(DATA, review)

    def test_tampering_and_overwrite_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "packet"
            shutil.copytree(DATA, target)
            (target / "inputs.jsonl").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                verify(target)
            with self.assertRaisesRegex(ValueError, "Immutable artifact"):
                write_once(target / "inputs.jsonl", b"replacement")

    def test_standalone_gate_needs_no_repository_imports(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, "-E", str(DATA / "review_gate.py"), "--packet", str(DATA)],
                                    cwd=directory, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["cases"], 30)


if __name__ == "__main__":
    unittest.main(verbosity=2)
