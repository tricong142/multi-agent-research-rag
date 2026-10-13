import importlib
import unittest


runtime_prediction = importlib.import_module("04_factchecker.eval_factchecker").runtime_prediction


class CalibrationCollectionTests(unittest.TestCase):
    def test_real_score_and_label_are_retained(self):
        row = {"example_id": "fixture:1", "claim": "A", "context": "B", "label": "contradict"}
        calls = []

        def node(state):
            calls.append(state)
            return {"fact_check_status": "ok", "fact_check_label": "contradict", "confidence_score": 0.82}

        result = runtime_prediction(node, row)
        self.assertEqual(calls, [{"claim": "A", "context": "B"}])
        self.assertEqual(result["confidence_score"], 0.82)
        self.assertEqual(result["gold_label"], result["predicted_label"])

    def test_failed_runtime_score_is_not_treated_as_model_confidence(self):
        row = {"example_id": "fixture:2", "claim": "A", "context": "B", "label": "support"}
        for status in ("judge_failed", "confidence_failed", "action_failed"):
            with self.subTest(status=status):
                result = runtime_prediction(lambda state: {
                    "fact_check_status": status, "fact_check_label": "not_enough_info", "confidence_score": 0.0}, row)
                self.assertIsNone(result["confidence_score"])
                self.assertEqual(result["error"], status)


if __name__ == "__main__":
    unittest.main()
