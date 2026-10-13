import importlib
import unittest


prompts = importlib.import_module("04_factchecker.prompts")
inference = importlib.import_module("04_factchecker.inference")


class Backend:
    def __init__(self, output):
        self.output = output
        self.messages = []

    def generate_json(self, messages, **kwargs):
        self.messages = messages
        return self.output


class PromptProfileTests(unittest.TestCase):
    def test_experiment_does_not_change_training_or_default_judge(self):
        sample = {"claim": "A", "context": "B", "label": "not_enough_info", "reasoning": "Missing"}
        backend = Backend({"fact_check_label": "not_enough_info", "reasoning": "Missing"})
        inference.FactCheckJudge(backend).judge("A", "B")
        self.assertEqual(backend.messages[0]["content"], prompts.JUDGE_SYSTEM_PROMPT)
        self.assertEqual(prompts.build_training_messages(sample)[0], backend.messages[0])
        inference.FactCheckJudge(backend, system_prompt=prompts.COVERAGE_JUDGE_SYSTEM_PROMPT).judge("A", "B")
        self.assertEqual(backend.messages[0]["content"], prompts.COVERAGE_JUDGE_SYSTEM_PROMPT)

    def test_confidence_profile_keeps_actual_score_for_non_support_label(self):
        backend = Backend({"confidence_score": 0.92, "reasoning": "Explicit contradiction"})
        score = inference.ConfidenceEstimator(backend, system_prompt=prompts.LABEL_CONFIDENCE_SYSTEM_PROMPT).estimate(
            "A", "B", "contradict", "Explicit contradiction")
        self.assertEqual(score.confidence_score, 0.92)
        self.assertEqual(backend.messages[0]["content"], prompts.LABEL_CONFIDENCE_SYSTEM_PROMPT)
        self.assertIn("PROPOSED LABEL: contradict", backend.messages[1]["content"])


if __name__ == "__main__":
    unittest.main()
