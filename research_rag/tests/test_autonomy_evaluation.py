"""Acceptance scorer and frozen-input checks, without model loading."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research_rag.evaluation.autonomy import digest, save, score_case, verify_frozen
from research_rag.tests.test_autonomy import make_graph


class EvaluationTests(unittest.TestCase):
    def test_hash_changes_are_rejected_before_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            save(directory / "cases.json", [{"id": "budget"}])
            save(directory / "frozen-manifest.json", {"files": {"cases.json": digest(directory / "cases.json")}})
            self.assertEqual(verify_frozen(directory)[1][0]["id"], "budget")
            save(directory / "cases.json", [])
            with self.assertRaisesRegex(ValueError, "Frozen evaluation changed"):
                verify_frozen(directory)

    def test_completed_fake_run_does_not_count_as_human_review(self):
        state = make_graph().invoke({"question": "Sample?"})
        score = score_case({"id": "sufficient"}, state)
        self.assertTrue(score["automated_gate_pass"])
        self.assertFalse(score["overall_pass"])
        self.assertEqual(score["human_review"], "pending")
        state["final_report"]["sentences"][0]["claim_ids"] = ["invented"]
        self.assertFalse(score_case({"id": "sufficient"}, state)["automated_gate_pass"])

    def test_missing_search_and_conflict_require_observed_behavior(self):
        state = make_graph().invoke({"question": "Sample?"})
        self.assertFalse(score_case({"id": "missing"}, state)["automated_gate_pass"])
        self.assertFalse(score_case({"id": "conflict"}, state)["automated_gate_pass"])
        state = make_graph(max_steps=1).invoke({"question": "Sample?"})
        self.assertTrue(score_case({"id": "budget"}, state)["automated_gate_pass"])

    def test_backend_failure_is_counted_without_prompt_content(self):
        from research_rag.observe import observe_call
        calls = []
        def fail(prompt):
            raise RuntimeError("backend unavailable")
        with self.assertRaises(RuntimeError):
            observe_call(fail, "factchecker", calls.append)("private question")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["status"], "failed")
        self.assertNotIn("private question", json.dumps(calls))


if __name__ == "__main__":
    unittest.main()
