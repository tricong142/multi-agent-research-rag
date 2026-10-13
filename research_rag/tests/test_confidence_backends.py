"""Backend comparison wiring and gates use stubs; no model-quality claims."""
from contextlib import contextmanager, redirect_stdout
import importlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from research_rag.evaluation import compare_confidence_backends as diagnostic
from research_rag.tests.test_confidence_repair import Backend


class ConfidenceBackendTests(unittest.TestCase):
    def test_assessment_uses_proposed_label_and_repairs_within_budget_without_judge_calls(self):
        row = {"example_id": "test", "claim": "12 seconds", "context": "12 hours",
               "label": "contradict", "proposed_label": "support"}
        backend = Backend([{"confidence_score": 1, "reasoning": ""},
                           {"confidence_score": .1, "reasoning": "Hours conflict with seconds"}])
        estimator = importlib.import_module("04_factchecker.inference").ConfidenceEstimator(backend)
        result = diagnostic.assess(estimator, row, 3)
        self.assertEqual(result["predicted_label"], "support")
        self.assertEqual(result["gold_label"], "contradict")
        self.assertEqual(result["confidence_score"], .1)
        self.assertEqual(len(backend.calls), 2)
        self.assertIn("VALIDATION FEEDBACK", backend.calls[1][0][1]["content"])
        self.assertNotIn("contradict", backend.calls[0][0][1]["content"])
        bad = Backend([{"confidence_score": None}] * 3)
        failed = diagnostic.assess(importlib.import_module("04_factchecker.inference").ConfidenceEstimator(bad), row, 3)
        self.assertEqual(failed["status"], "confidence_failed")
        self.assertIsNone(failed["confidence_score"])
        self.assertEqual(len(bad.calls), 3)

    def test_complete_matrix_is_preregistered_and_never_promotes_always_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "new-run"
            loads, calls, live = [], [], []
            class AlwaysOne:
                def generate_json(self, messages, **kwargs):
                    calls.append((messages, kwargs))
                    return {"confidence_score": 1.0, "reasoning": "Stub only"}
            @contextmanager
            def loader(kind, criteria):
                self.assertFalse(live)
                self.assertTrue((out / "criteria.json").is_file())
                self.assertTrue((out / "cases.json").is_file())
                loads.append(kind); live.append(kind)
                try:
                    yield AlwaysOne(), {"fixture": kind}
                finally:
                    live.clear()
            with redirect_stdout(io.StringIO()):
                result = diagnostic.run_experiment(out, loader)
            self.assertEqual(loads, ["finetuned", "base_instruct"])
            self.assertEqual(result["prediction_count"], 96)
            self.assertEqual(result["backend_calls"], 96)
            self.assertTrue(result["experiment_completed"])
            self.assertFalse(result["automated_gate_pass"])
            self.assertFalse(result["promoted_to_serving"])
            self.assertEqual(result["qualifying_profiles"], [])
            # Same exact confidence prompts/inputs across the two backends.
            self.assertEqual(calls[:48], calls[48:])
            reviews = [json.loads(line) for line in (out / "explanation-review.jsonl").read_text().splitlines()]
            self.assertEqual(len(reviews), 96)
            self.assertTrue(all(r["review_status"] == "pending" and not r["reviewer"] for r in reviews))
            with self.assertRaises(FileExistsError):
                diagnostic.run_experiment(out, loader)

    def test_all_zero_and_missing_rows_fail_frozen_challenge_gate(self):
        criteria = json.loads(diagnostic.CRITERIA.read_text())
        cases = diagnostic.build_label_challenges([json.loads(line) for line in
            diagnostic.CRITERIA.with_name("factchecker_contract_cases.jsonl").read_text().splitlines()], criteria["label_challenges"])
        rows = [{"example_id": r["example_id"], "predicted_label": r["proposed_label"],
                 "gold_label": r["label"], "status": "ok", "confidence_score": 0} for r in cases]
        self.assertFalse(diagnostic.score_label_challenges(rows, criteria["label_challenges"], .7)["automated_gate_pass"])
        for row in rows:
            row["confidence_score"] = .9 if row["predicted_label"] == row["gold_label"] else .1
        self.assertTrue(diagnostic.score_label_challenges(rows, criteria["label_challenges"], .7)["automated_gate_pass"])
        self.assertFalse(diagnostic.score_label_challenges(rows[:-1], criteria["label_challenges"], .7)["automated_gate_pass"])

    def test_loader_pins_revision_shares_generation_and_releases_model_on_error(self):
        criteria = json.loads(diagnostic.CRITERIA.read_text())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            merged = root / "04_factchecker/checkpoints/factchecker_merged"
            merged.mkdir(parents=True)
            config = dict(model_type="qwen2", vocab_size=100, hidden_size=16, num_hidden_layers=2)
            (merged / "config.json").write_text(json.dumps(config))
            (merged / "tokenizer.json").write_text('{}')
            config_object = SimpleNamespace(**config)
            model = SimpleNamespace(config=config_object)
            model.eval = lambda: model
            generation = SimpleNamespace(to_dict=lambda: {"temperature": .7})
            torch = SimpleNamespace(__version__="test-stub", cuda=SimpleNamespace(is_available=lambda: True, get_device_name=lambda i: "stub",
                                                        empty_cache=Mock()), manual_seed=Mock(), float16="stub-f16")
            tokenizer = Mock(return_value="shared-tokenizer")
            loader = Mock(return_value=model)
            snapshot = Mock(return_value=str(merged))
            transformers = SimpleNamespace(AutoTokenizer=SimpleNamespace(from_pretrained=tokenizer),
                AutoModelForCausalLM=SimpleNamespace(from_pretrained=loader),
                BitsAndBytesConfig=lambda **kwargs: kwargs,
                GenerationConfig=SimpleNamespace(from_pretrained=lambda *a, **k: generation))
            with patch.object(diagnostic, "ROOT", root), patch.dict("sys.modules", {
                    "torch": torch, "transformers": transformers,
                    "huggingface_hub": SimpleNamespace(snapshot_download=snapshot)}):
                with self.assertRaisesRegex(RuntimeError, "interrupted"):
                    with diagnostic.model_loader(online=True)("base_instruct", criteria) as (backend, metadata):
                        self.assertEqual(metadata["revision"], criteria["base_revision"])
                        self.assertEqual(backend.tokenizer, "shared-tokenizer")
                        self.assertEqual(model.generation_config.to_dict(), generation.to_dict())
                        raise RuntimeError("interrupted")
            self.assertEqual(snapshot.call_args.kwargs["revision"], criteria["base_revision"])
            self.assertFalse(snapshot.call_args.kwargs["local_files_only"])
            tokenizer.assert_called_once_with(merged, local_files_only=True)
            self.assertIsNone(backend.model)
            torch.cuda.empty_cache.assert_called_once()


if __name__ == "__main__":
    unittest.main()
