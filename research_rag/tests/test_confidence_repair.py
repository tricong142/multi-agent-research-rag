"""Contract regressions from Kaggle output, using stubs rather than model inference."""
import contextlib
import importlib
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch


inference = importlib.import_module("04_factchecker.inference")
judge_module = importlib.import_module("04_factchecker.inference.judge")
FactCheckerNode = importlib.import_module("04_factchecker.node").FactCheckerNode
runtime_prediction = importlib.import_module("04_factchecker.eval_factchecker").runtime_prediction
EMPTY = {"confidence_score": 1.0, "reasoning": ""}
VALID = {"confidence_score": .83, "reasoning": "The context explicitly gives the sample size."}


class Backend:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.calls = []

    def generate_json(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        result = next(self.outputs)
        if isinstance(result, Exception):
            raise result
        return result


def node_for(outputs, *, repair=True, attempts=3):
    backend = Backend(outputs)
    judge = inference.FactCheckJudge(Backend([{"fact_check_label": "support", "reasoning": "Explicit evidence"}] * 2))
    action = inference.ActionRecommender(Backend([{"recommended_action": "expand_context", "reasoning": "Uncertain"}] * 2))
    return FactCheckerNode(judge, inference.ConfidenceEstimator(backend, repair_invalid_output=repair),
                           action, max_internal_retry=attempts), backend


class ConfidenceRepairTests(unittest.TestCase):
    def test_observed_empty_reasoning_is_repaired_with_output_and_error(self):
        node, backend = node_for([EMPTY, VALID])
        result = node({"claim": "42 participants", "context": "42 participants"})
        self.assertEqual(result["fact_check_status"], "ok")
        self.assertEqual(result["confidence_score"], .83)
        self.assertEqual(len(backend.calls), 2)
        first, second = [call[0][1]["content"] for call in backend.calls]
        self.assertNotIn("VALIDATION FEEDBACK", first)
        self.assertIn("Confidence reasoning must be a nonempty string", second)
        self.assertIn(json.dumps(json.dumps(EMPTY)), second)
        self.assertEqual([r["ok"] for r in result["fact_check_attempts"] if r["stage"] == "confidence"], [False, True])

    def test_exhaustion_uses_exact_budget_and_keeps_failure_score_out_of_metrics(self):
        for attempts in (1, 3):
            with self.subTest(attempts=attempts):
                node, backend = node_for([EMPTY] * attempts, attempts=attempts)
                result = runtime_prediction(node, {"claim": "A", "context": "B", "label": "support", "example_id": "bad"})
                self.assertEqual(len(backend.calls), attempts)
                self.assertEqual(result["status"], "confidence_failed")
                self.assertIsNone(result["confidence_score"])

    def test_invalid_json_preserves_raw_output_without_putting_it_in_error_message(self):
        raw = '{"confidence_score":'
        class Tokenizer:
            eos_token_id = 0
            def apply_chat_template(self, *args, **kwargs): return "prompt"
            def __call__(self, *args, **kwargs): return {"input_ids": SimpleNamespace(shape=(1, 2))}
            def decode(self, *args, **kwargs): return raw
        model = SimpleNamespace(generate=lambda **kwargs: [[1, 2, 3]])
        with patch.dict("sys.modules", {"torch": SimpleNamespace(inference_mode=contextlib.nullcontext)}):
            with self.assertRaises(judge_module.ModelOutputError) as caught:
                inference.TransformersJSONBackend(model, Tokenizer()).generate_json([], max_new_tokens=192)
        self.assertEqual(caught.exception.raw_output, raw)
        self.assertNotIn(raw, str(caught.exception))
        node, backend = node_for([caught.exception, VALID])
        self.assertEqual(node({"claim": "A", "context": "B"})["fact_check_status"], "ok")
        self.assertIn(json.dumps(raw), backend.calls[1][0][1]["content"])
        self.assertIn("Model output is not valid JSON", backend.calls[1][0][1]["content"])

    def test_contract_rejects_invalid_scores_and_reasoning_without_coercion(self):
        invalid = [None, [], {}, *[{"confidence_score": score, "reasoning": "Explanation"}
                   for score in (True, False, "0.9", None, -0.1, 1.1, float("nan"), float("inf"), 10**400)],
                   *[{"confidence_score": .9, "reasoning": reason} for reason in (None, [], 1, "", " \n ")]]
        for output in invalid:
            with self.subTest(output=output):
                estimator = inference.ConfidenceEstimator(Backend([output]))
                with self.assertRaises(judge_module.ModelOutputError):
                    estimator.estimate("A", "B", "support", "C")

    def test_valid_boundary_scores_and_non_support_label_are_retained(self):
        for label in ("support", "contradict", "not_enough_info"):
            for score in (0, .91, 1):
                with self.subTest(label=label, score=score):
                    estimate = inference.ConfidenceEstimator(Backend([{"confidence_score": score, "reasoning": " Evidence "}]))
                    result = estimate.estimate("A", "B", label, "C")
                    self.assertEqual(result.confidence_score, score)
                    self.assertEqual(result.reasoning, "Evidence")

    def test_feedback_is_local_to_one_call_and_never_includes_transport_errors(self):
        node, backend = node_for([EMPTY, VALID, VALID])
        node({"claim": "A", "context": "B"})
        node({"claim": "D", "context": "E"})
        self.assertNotIn("VALIDATION FEEDBACK", backend.calls[2][0][1]["content"])
        node, backend = node_for([RuntimeError("private transport error"), VALID])
        node({"claim": "A", "context": "B"})
        self.assertEqual(backend.calls[0], backend.calls[1])
        self.assertNotIn("private transport error", str(backend.calls))

    def test_diagnostic_can_replay_identical_prompts_without_nested_retries(self):
        node, backend = node_for([EMPTY] * 3, repair=False)
        result = node({"claim": "A", "context": "B"})
        self.assertEqual(result["fact_check_status"], "confidence_failed")
        self.assertEqual(len(backend.calls), 3)
        self.assertEqual(backend.calls[0], backend.calls[1])
        self.assertEqual(backend.calls[1], backend.calls[2])
        self.assertEqual(node.confidence_threshold, .7)

    def test_only_last_failed_output_is_kept_with_bounded_feedback(self):
        first = judge_module.ModelOutputError("bad first", "first failed output")
        last = judge_module.ModelOutputError("bad last", "x" * 5000)
        node, backend = node_for([first, last, VALID])
        node({"claim": "A", "context": "B"})
        content = backend.calls[2][0][1]["content"]
        self.assertNotIn("first failed output", content)
        self.assertIn("bad last", content)
        self.assertNotIn("x" * 4001, content)


if __name__ == "__main__":
    unittest.main()
