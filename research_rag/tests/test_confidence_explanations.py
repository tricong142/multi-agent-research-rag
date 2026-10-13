"""Prospective explanation gates; no claim about the quality of a real model."""
import contextlib
import hashlib
import importlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from research_rag.evaluation.compare_factchecker import (
    ProposedLabelJudge, build_label_challenges, explanation_review_row, profiles_for, score_label_challenges,
)
from research_rag.tests.test_confidence_repair import Backend
from research_rag.evaluation import compare_factchecker


ROOT = Path(__file__).resolve().parents[2]


class ConfidenceExplanationTests(unittest.TestCase):
    def setUp(self):
        self.criteria = json.loads((ROOT / "research_rag/evaluation/confidence_explanation_criteria.json").read_text())
        self.contracts = [json.loads(line) for line in (ROOT / "research_rag/evaluation/factchecker_contract_cases.jsonl").read_text().splitlines()]

    def test_default_still_uses_audited_repair_and_candidate_is_explicit(self):
        inference = importlib.import_module("04_factchecker.inference")
        prompts = importlib.import_module("04_factchecker.prompts")
        default = inference.ConfidenceEstimator(Backend([]))
        profiles = profiles_for("explanation")
        self.assertEqual(default.system_prompt, profiles["repair"][1])
        self.assertTrue(default.repair_invalid_output)
        self.assertEqual(profiles["repair"], profiles_for("confidence")["repair"])
        self.assertEqual(profiles["repair"][0], profiles["explanation_repair"][0])
        self.assertNotEqual(profiles["explanation_repair"][1], prompts.LABEL_CONFIDENCE_SYSTEM_PROMPT)
        self.assertNotEqual(default.system_prompt, profiles["explanation_repair"][1])
        # Prompt hashes recorded in the audited Kaggle 20261009T120708Z provenance.
        self.assertEqual(hashlib.sha256(default.system_prompt.encode()).hexdigest(),
                         "cc80fad9db9942a05bae03872c024495edb2952ffe755bf4e1ba7d4606929d1d")
        self.assertEqual(hashlib.sha256(profiles["repair"][0].encode()).hexdigest(),
                         "89559612b52febe67ead7630b4d38f5fb8142e802ef0c32e9a7329a8a3e030e5")

    def test_challenges_pair_same_evidence_with_correct_and_wrong_labels(self):
        rows = build_label_challenges(self.contracts, self.criteria["label_challenges"])
        self.assertEqual(len(rows), 24)
        for correct, wrong in zip(rows[::2], rows[1::2]):
            self.assertEqual((correct["claim"], correct["context"]), (wrong["claim"], wrong["context"]))
            self.assertEqual(correct["proposed_label"], correct["label"])
            self.assertNotEqual(wrong["proposed_label"], wrong["label"])
            decision = ProposedLabelJudge(wrong["proposed_label"]).judge(wrong["claim"], wrong["context"])
            self.assertEqual(decision.fact_check_label, wrong["proposed_label"])
            self.assertNotIn("gold", str(decision.raw))
            self.assertNotIn("deliberately wrong", decision.reasoning)

    def predictions(self, correct_score=.9, wrong_score=.1):
        rows = build_label_challenges(self.contracts, self.criteria["label_challenges"])
        return [{"example_id": r["example_id"], "gold_label": r["label"], "predicted_label": r["proposed_label"],
                 "confidence_score": correct_score if r["label"] == r["proposed_label"] else wrong_score,
                 "status": "ok"} for r in rows]

    def test_always_one_and_always_zero_cannot_pass_new_gate(self):
        criteria = self.criteria["label_challenges"]
        score = lambda rows: score_label_challenges(rows, criteria, .7)
        self.assertTrue(score(self.predictions())["automated_gate_pass"])
        for outputs in (self.predictions(1, 1), self.predictions(0, 0), self.predictions()[:-1]):
            self.assertFalse(score(outputs)["automated_gate_pass"])
        failed = self.predictions()
        failed[1].update(status="confidence_failed", confidence_score=None)
        self.assertFalse(score(failed)["automated_gate_pass"])

    def test_review_template_preserves_evidence_but_never_fakes_human_judgment(self):
        source = self.contracts[9]
        output = {"predicted_label": "contradict", "confidence_score": .2, "confidence_reasoning": "Test only", "status": "ok"}
        row = explanation_review_row("explanation_repair", "contracts", source, output, self.criteria["human_review_rubric"])
        self.assertEqual(row["context"], source["context"])
        self.assertEqual(row["reasoning"], output["confidence_reasoning"])
        self.assertEqual(row["review_status"], "pending")
        self.assertEqual(row["reviewer"], "")
        self.assertTrue(all(value is None for value in row["judgments"].values()))

    def test_cli_writes_complete_diagnostics_but_rejects_always_one_stub(self):
        inference = importlib.import_module("04_factchecker.inference")
        class AlwaysOne:
            def __init__(self, *args, **kwargs): pass
            def generate_json(self, messages, **kwargs):
                if messages[0]["content"].startswith("You are a strict scientific fact checker"):
                    return {"fact_check_label": "support", "reasoning": "Stub judge, not model evidence"}
                return {"confidence_score": 1.0, "reasoning": "Stub confidence, not model evidence"}
        torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True, get_device_name=lambda n: "stub",
                                                     max_memory_allocated=lambda n: 0), float16="stub", __version__="stub")
        transformers = SimpleNamespace(
            AutoTokenizer=SimpleNamespace(from_pretrained=lambda *a, **k: object()),
            AutoModelForCausalLM=SimpleNamespace(from_pretrained=lambda *a, **k: SimpleNamespace(eval=lambda: object())),
            BitsAndBytesConfig=lambda **kwargs: kwargs)
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "new-run"
            with patch.dict("sys.modules", {"torch": torch, "transformers": transformers}), \
                    patch.object(inference, "TransformersJSONBackend", AlwaysOne), \
                    patch("sys.argv", ["diagnostic", "--comparison", "explanation", "--output-dir", str(out)]), \
                    contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as stopped:
                    compare_factchecker.main()
            self.assertEqual(stopped.exception.code, 1)
            gate = json.loads((out / "gate-results.json").read_text())
            self.assertFalse(gate["candidates"]["explanation_repair"]["checks"]["controlled_labels_discriminated"])
            self.assertFalse(gate["promoted_to_serving"])
            reviews = [json.loads(line) for line in (out / "explanation-review.jsonl").read_text().splitlines()]
            self.assertEqual(len(reviews), 71)
            self.assertTrue(all(r["review_status"] == "pending" for r in reviews))
            self.assertEqual(json.loads((out / "criteria.json").read_text()), self.criteria)
            controlled = [json.loads(line) for line in (out / "repair-label_challenges-calls.jsonl").read_text().splitlines()]
            self.assertFalse(any(c["stage"] == "judge" for c in controlled))


if __name__ == "__main__":
    unittest.main()
