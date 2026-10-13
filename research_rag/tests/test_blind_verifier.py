"""Contract and experiment tests with stubs; no claims about real-model quality."""
from contextlib import contextmanager, redirect_stdout
import importlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from research_rag.evaluation import compare_blind_verifier as diagnostic

v = importlib.import_module("04_factchecker.inference.verifier")


def valid(label="support", quote="The sample had 240 documents."):
    return {"assessed_label": label, "evidence_quotes": [quote],
            "missing_information": ["The claimed measurement is not supplied."] if label == "not_enough_info" else [],
            "explanation": "Test fixture only."}


class Backend:
    def __init__(self, outputs):
        self.outputs, self.calls = iter(outputs), []

    def generate_json(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        value = next(self.outputs)
        if isinstance(value, Exception):
            raise value
        return value


class BlindVerifierTests(unittest.TestCase):
    def test_scope_profile_reaches_initial_and_repair_calls_without_case_or_label_leakage(self):
        backend = Backend([valid(), valid(), valid()])
        v.BlindVerifier(backend).verify('The sample had 240 documents.', 'The sample had 240 documents.')
        candidate = v.BlindVerifier(backend, prompt_profile='scope_v2')
        for repair in (False, True):
            candidate.verify('The sample had 240 documents.', 'The sample had 240 documents.', repair=repair)
        self.assertEqual(backend.calls[0][0][0]['content'], v.SYSTEM_PROMPT)
        self.assertEqual(backend.calls[1][0][0]['content'], v.SCOPE_SYSTEM_PROMPT)
        self.assertTrue(backend.calls[2][0][0]['content'].startswith(v.SCOPE_SYSTEM_PROMPT))
        for messages, kwargs in backend.calls:
            self.assertEqual(set(json.loads(messages[1]['content'])), {'claim', 'context'})
            self.assertEqual(kwargs['max_new_tokens'], 384)
        cases = [json.loads(line) for line in diagnostic.CRITERIA.with_name(
            'factchecker_contract_cases.jsonl').read_text().splitlines()]
        for row in cases:
            self.assertNotIn(row['example_id'], v.SCOPE_SYSTEM_PROMPT)
            self.assertNotIn(row['claim'], v.SCOPE_SYSTEM_PROMPT)
            self.assertNotIn(row['context'], v.SCOPE_SYSTEM_PROMPT)

    def test_unknown_prompt_profile_fails_before_inference_or_output_creation(self):
        backend = Mock()
        with self.assertRaisesRegex(ValueError, 'Unknown verifier prompt'):
            v.BlindVerifier(backend, prompt_profile='typo')
        backend.generate_json.assert_not_called()
        with tempfile.TemporaryDirectory() as temp:
            criteria = json.loads(diagnostic.CRITERIA.read_text())
            criteria['verifier_prompt_profile'] = 'typo'
            path = Path(temp) / 'criteria.json'
            path.write_text(json.dumps(criteria))
            loader = Mock()
            out = Path(temp) / 'run'
            with self.assertRaisesRegex(ValueError, 'Unknown verifier prompt'):
                diagnostic.run_experiment(out, loader, criteria_path=path)
            loader.assert_not_called()
            self.assertFalse(out.exists())

    def test_scope_candidate_uses_only_base_and_records_selected_prompt_before_loading(self):
        path = diagnostic.CRITERIA.with_name('blind_verifier_scope_criteria.json')
        criteria = json.loads(path.read_text())
        self.assertEqual(criteria['backends'], ['base_instruct'])
        self.assertEqual(criteria['min_correct_labels_recognized'], 12)
        self.assertEqual(criteria['max_wrong_label_agreements'], 0)
        cases = [json.loads(line) for line in path.with_name('factchecker_contract_cases.jsonl').read_text().splitlines()]
        calls = []
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'run'
            @contextmanager
            def loader(kind, frozen):
                self.assertEqual(kind, 'base_instruct')
                self.assertEqual(frozen['verifier_prompt_profile'], 'scope_v2')
                provenance = json.loads((out / 'provenance.json').read_text())
                self.assertEqual(provenance['prompt'], v.SCOPE_SYSTEM_PROMPT)
                self.assertEqual(provenance['verifier_prompt_profile'], 'scope_v2')
                backend = Backend([valid(row['label'], row['context']) for row in cases])
                calls.append(backend.calls)
                yield backend, {'test_stub': True}
            with redirect_stdout(io.StringIO()):
                result = diagnostic.run_experiment(out, loader, criteria_path=path)
            self.assertEqual(result['prediction_count'], 12)
            self.assertEqual(result['backend_calls'], 12)
            self.assertFalse(result['promoted_to_serving'])
            self.assertFalse(result['overall_pass'])
            self.assertEqual(len(calls), 1)
            self.assertTrue(all(messages[0]['content'] == v.SCOPE_SYSTEM_PROMPT for messages, _ in calls[0]))

    def test_schema_rejects_fabricated_quotes_and_inconsistent_decisions(self):
        context = "The sample had 240 documents."
        good = valid()
        self.assertEqual(v.validate_verification(good, context).assessed_label, "support")
        bad = [None, {}, {**good, "extra": 1}, {**good, "assessed_label": "true"},
               {**good, "evidence_quotes": ["The sample had 250 documents."]},
               {**good, "evidence_quotes": []}, {**good, "evidence_quotes": [4]},
               {**good, "missing_information": ["Accuracy unknown"]},
               {**good, "missing_information": ""}, {**good, "explanation": ""},
               {**good, "assessed_label": "not_enough_info"}]
        for row in bad:
            with self.subTest(row=row), self.assertRaises(ValueError):
                v.validate_verification(row, context)

    def test_blinding_is_preserved_in_both_initial_and_repair_messages(self):
        backend = Backend([valid(), valid()])
        model = v.BlindVerifier(backend)
        for repair in (False, True):
            model.verify("The sample had 240 documents.", "The sample had 240 documents.", repair=repair)
        for messages, kwargs in backend.calls:
            payload = json.loads(messages[1]["content"])
            self.assertEqual(set(payload), {"claim", "context"})
            self.assertEqual(kwargs["max_new_tokens"], 384)
            self.assertNotIn("Judge reasoning", str(messages))

    def test_disagreement_and_missing_information_never_verify_a_claim(self):
        for decision in (None, v.validate_verification(valid("contradict"), "The sample had 240 documents."),
                         v.validate_verification(valid("not_enough_info"), "The sample had 240 documents.")):
            result = v.compare_with_judge(decision, "support")
            self.assertFalse(result["claim_verified"])
            self.assertEqual(result["status"], "needs_context")
        nei = v.validate_verification(valid("not_enough_info"), "The sample had 240 documents.")
        self.assertTrue(v.compare_with_judge(nei, "not_enough_info")["label_agreement"])
        self.assertFalse(v.compare_with_judge(nei, "not_enough_info")["claim_verified"])
        support = v.validate_verification(valid(), "The sample had 240 documents.")
        self.assertTrue(v.compare_with_judge(support, "support")["claim_verified"])

    def test_repair_budget_and_backend_failure_are_bounded(self):
        row = {"example_id": "private-id", "claim": "240 docs", "context": "The sample had 240 documents.",
               "label": "not_enough_info", "proposed_label": "contradict"}
        criteria = {"max_attempts": 2, "max_new_tokens": 384}
        backend = Backend([{}, {}, valid()])
        result = diagnostic.assess(backend, row, criteria)
        self.assertEqual(len(backend.calls), 2)
        self.assertEqual(result["status"], "verification_failed")
        for messages, _ in backend.calls:
            self.assertEqual(json.loads(messages[1]["content"]), {"claim": row["claim"], "context": row["context"]})
        backend = Backend([RuntimeError("transport unavailable"), valid()])
        self.assertEqual(diagnostic.assess(backend, row, criteria)["status"], "verification_failed")
        self.assertEqual(len(backend.calls), 1)
        backend = Backend([{}, valid()])
        self.assertEqual(diagnostic.assess(backend, row, criteria)["status"], "ok")
        self.assertEqual(len(backend.calls), 2)

    def test_matrix_is_frozen_before_calls_and_human_review_still_required(self):
        cases = [json.loads(line) for line in diagnostic.CRITERIA.with_name(
            "factchecker_contract_cases.jsonl").read_text().splitlines()]
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "run"
            loads, active, backends = [], [], []
            @contextmanager
            def loader(kind, criteria):
                self.assertFalse(active)
                self.assertTrue((out / "criteria.json").exists())
                self.assertTrue((out / "baseline.json").exists())
                loads.append(kind)
                active.append(kind)
                backend = Backend([valid(row["label"], row["context"]) for row in cases])
                backends.append(backend)
                try:
                    yield backend, {"test_stub": True}
                finally:
                    active.clear()
            with redirect_stdout(io.StringIO()):
                summary = diagnostic.run_experiment(out, loader)
            self.assertEqual(loads, ["finetuned", "base_instruct"])
            self.assertEqual(summary["prediction_count"], 24)
            self.assertEqual(summary["backend_calls"], 24)
            self.assertTrue(summary["automated_gate_pass"])
            self.assertFalse(summary["overall_pass"])
            self.assertFalse(summary["promoted_to_serving"])
            self.assertEqual(backends[0].calls, backends[1].calls)
            baseline = json.loads((out / "baseline-metrics.json").read_text())
            self.assertEqual((baseline["correct_labels_accepted"], baseline["wrong_labels_accepted"]), (4, 2))
            reviews = [json.loads(line) for line in (out / "evidence-review.jsonl").read_text().splitlines()]
            self.assertEqual(len(reviews), 24)
            self.assertTrue(all(row["review_status"] == "pending" for row in reviews))
            with self.assertRaises(FileExistsError):
                diagnostic.run_experiment(out, loader)

    def test_always_support_duplicate_and_incomplete_outputs_fail(self):
        criteria = json.loads(diagnostic.CRITERIA.read_text())
        cases = [json.loads(line) for line in diagnostic.CRITERIA.with_name(
            "factchecker_contract_cases.jsonl").read_text().splitlines()]
        rows = [{"example_id": row["example_id"], "status": "ok", "verification": valid("support", row["context"]),
                 "attempts": [{"attempt": 1, "ok": True}], "elapsed_ms": 0} for row in cases]
        metrics, _ = diagnostic.score(rows, cases, criteria)
        self.assertFalse(metrics["automated_gate_pass"])
        self.assertEqual(metrics["false_support"], 8)
        for output, case in zip(rows, cases):
            output["verification"] = valid(case["label"], case["context"])
        self.assertTrue(diagnostic.score(rows, cases, criteria)[0]["automated_gate_pass"])
        self.assertFalse(diagnostic.score(rows[:-1], cases, criteria)[0]["automated_gate_pass"])
        self.assertFalse(diagnostic.score(rows[:-1] + [rows[0]], cases, criteria)[0]["automated_gate_pass"])


if __name__ == "__main__":
    unittest.main()
