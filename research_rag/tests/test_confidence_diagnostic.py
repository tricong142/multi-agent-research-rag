"""Check diagnostic accounting and gates without loading model weights."""
import copy
import io
import json
from pathlib import Path
import unittest

from research_rag.evaluation.compare_factchecker import TracedBackend, compare_gates, diagnostic_metrics, profiles_for
from research_rag.tests.test_confidence_repair import Backend, EMPTY, VALID, inference


ROOT = Path(__file__).resolve().parents[2]


def prediction(example_id, *, gold="support", predicted="support", score=.9, status="ok"):
    return {"example_id": example_id, "gold_label": gold, "predicted_label": predicted,
            "confidence_score": score if status == "ok" else None, "status": status,
            "attempts": [{"stage": "confidence", "attempt": 1, "ok": status == "ok"}],
            "backend_calls": 2, "elapsed_ms": 10}


class ConfidenceDiagnosticTests(unittest.TestCase):
    def test_profiles_change_only_confidence_prompt_and_repair(self):
        profiles = profiles_for("confidence")
        self.assertEqual(len({value[0] for value in profiles.values()}), 1)
        self.assertEqual(profiles["legacy_retry"][:2], profiles["repair"][:2])
        self.assertFalse(profiles["legacy_retry"][2])
        self.assertTrue(profiles["repair"][2])
        self.assertNotEqual(profiles["repair"][1], profiles["label_confidence_repair"][1])

    def test_metrics_include_failed_rows_and_exclude_fallback_scores(self):
        rows = [prediction("ok"), prediction("bad", status="confidence_failed"),
                prediction("unsafe", gold="contradict")]
        rows[1]["attempts"][0].update(error_type="ModelOutputError")
        result = diagnostic_metrics(rows, threshold=.7)
        self.assertEqual(result["runtime_failed_rows"], 1)
        self.assertEqual(result["confidence_invalid_attempts"], 1)
        self.assertEqual(result["backend_calls"], 6)
        self.assertIsNone(result["calibration"])
        self.assertEqual(result["support_at_threshold"]["precision"], .5)
        self.assertEqual(result["support_at_threshold"]["coverage"], 2 / 3)
        self.assertEqual(result["support_at_threshold"]["false_support"], 1)

    def test_trace_retains_rejected_output_and_actual_repair_prompt(self):
        handle, calls = io.StringIO(), []
        traced = TracedBackend(Backend([EMPTY, VALID]), "confidence", {"example_id": "test"}, handle, calls)
        estimator = inference.ConfidenceEstimator(traced)
        try:
            estimator.estimate("A", "B", "support", "C")
        except ValueError as error:
            estimator.estimate("A", "B", "support", "C", previous_error=error)
        events = [json.loads(line) for line in handle.getvalue().splitlines()]
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["parsed_output"], EMPTY)
        self.assertIn("VALIDATION FEEDBACK", events[1]["messages"][1]["content"])
        self.assertTrue(all(event["elapsed_ms"] >= 0 for event in events))

    def test_frozen_regressions_are_observed_cases_not_independent_gold(self):
        rows = [json.loads(line) for line in (ROOT / "research_rag/evaluation/confidence_failures_20261009.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 5)
        self.assertEqual(len({(r["claim"], r["context"]) for r in rows}), 4)
        self.assertTrue(all(r["observed_output"] == EMPTY and r["label_rationale"] for r in rows))
        self.assertTrue(all("not independent human annotation" in r["source"] for r in rows))

    def test_gates_reject_failures_abstention_unsafe_support_and_missing_rows(self):
        criteria = json.loads((ROOT / "research_rag/evaluation/confidence_criteria.json").read_text(encoding="utf-8"))
        predictions = {profile: {dataset: [prediction(str(i)) for i in range(n)]
                                for dataset, n in criteria["datasets"].items()}
                       for profile in (criteria["baseline"], *criteria["candidates"])}
        def evaluate(rows):
            results = {p: {d: diagnostic_metrics(v, threshold=criteria["threshold"]) for d, v in sets.items()}
                       for p, sets in rows.items()}
            return compare_gates(results, rows, criteria)
        good = evaluate(predictions)
        self.assertTrue(good["candidates"]["repair"]["automated_gate_pass"])
        self.assertFalse(good["overall_pass"])
        self.assertFalse(good["promoted_to_serving"])
        for problem in ("failed", "abstain", "unsafe", "missing", "budget", "changed_label"):
            with self.subTest(problem=problem):
                changed = copy.deepcopy(predictions)
                row = changed["repair"]["dev30"][0]
                if problem == "failed": row.update(status="confidence_failed", confidence_score=None)
                if problem == "unsafe": row.update(gold_label="contradict")
                if problem == "missing": changed["repair"]["dev30"].pop()
                if problem == "budget": row["attempts"][0]["attempt"] = 4
                if problem == "changed_label": row["predicted_label"] = "not_enough_info"
                if problem == "abstain":
                    for values in changed["repair"].values():
                        for item in values: item["confidence_score"] = 0
                self.assertFalse(evaluate(changed)["candidates"]["repair"]["automated_gate_pass"])


if __name__ == "__main__":
    unittest.main()
