"""CPU-only regression tests for evidence boundaries and local repair behavior."""

import importlib
import json
from types import SimpleNamespace
import unittest


schemas = importlib.import_module("05_writer.schemas")
inference = importlib.import_module("05_writer.inference")
actions = importlib.import_module("05_writer.actions")
backend = importlib.import_module("05_writer.inference.backend")


class StubBackend:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def generate(self, messages):
        self.calls += 1
        return self.payload if isinstance(self.payload, str) else json.dumps(self.payload)


class InferenceActionsTests(unittest.TestCase):
    def setUp(self):
        self.claims = [
            schemas.VerifiedClaim(claim_id="c1", text="The study used 20 samples.",
                                 evidence="The study used 20 samples.", source_id="p1"),
            schemas.VerifiedClaim(claim_id="c2", text="Evaluation used five folds.",
                                 evidence="Evaluation used five folds.", source_id="p1"),
        ]
        self.intent = "How was the study evaluated?"
        self.report = inference.ReportGenerator().generate(self.claims, self.intent)

    def test_offline_copy_support_does_not_claim_intent_coverage(self):
        result = inference.Critic().review(self.claims, self.intent, self.report)
        self.assertTrue(result.needs_more_evidence)
        self.assertIn("coverage_not_assessed", result.summary)
        self.assertTrue(all(review.verdict == "supported" for review in result.sentence_reviews))

    def test_changed_number_remains_uncertain_until_repaired(self):
        self.report.sentences[0].text = "The study used 2000 samples."
        critique = inference.Critic().review(self.claims, self.intent, self.report)
        self.assertEqual(critique.sentence_reviews[0].verdict, "uncertain")
        action = inference.ActionSelector().select(self.claims, self.intent, self.report, critique)
        self.assertEqual(action.action, "rewrite_sentence")
        result = actions.rewrite_sentence(self.report, action, self.claims)
        self.assertEqual(result.sentences[0].text, self.claims[0].text)
        self.assertEqual(self.report.sentences[0].text, "The study used 2000 samples.")

    def test_reselect_ignores_proposed_invented_text(self):
        action = schemas.WriterAction(action="reselect_claims", sentence_id="s1",
                                      claim_ids=["c2"], replacement_text="Invented content.")
        result = actions.reselect_claims(self.report, action, self.claims)
        self.assertEqual(result.sentences[0].text, self.claims[1].text)
        self.assertEqual(result.sentences[0].claim_ids, ["c2"])
        self.assertEqual(self.report.sentences[0].claim_ids, ["c1"])

    def test_reselect_rejects_original_or_external_claims(self):
        for claim_id in ["c1", "external"]:
            with self.subTest(claim_id=claim_id), self.assertRaises(ValueError):
                actions.reselect_claims(self.report, schemas.WriterAction(
                    action="reselect_claims", sentence_id="s1", claim_ids=[claim_id]
                ), self.claims)

    def test_rewrite_cannot_switch_citations(self):
        with self.assertRaises(ValueError):
            actions.rewrite_sentence(self.report, schemas.WriterAction(
                action="rewrite_sentence", sentence_id="s1", claim_ids=["c2"]
            ), self.claims)

    def test_delete_preserves_other_sentences_and_original_report(self):
        result = actions.delete_sentence(self.report, schemas.WriterAction(
            action="delete_sentence", sentence_id="s1"
        ), self.claims)
        self.assertEqual([s.sentence_id for s in result.sentences], ["s2"])
        self.assertEqual(len(self.report.sentences), 2)

    def test_critic_rejects_missing_and_duplicate_sentence_reviews(self):
        single = {"sentence_id": "s1", "verdict": "supported", "reason": "Claim repeats evidence."}
        for reviews in [[single], [single, single]]:
            with self.subTest(reviews=reviews), self.assertRaises(ValueError):
                inference.Critic(StubBackend({"sentence_reviews": reviews})).review(
                    self.claims, self.intent, self.report
                )

    def test_critic_does_not_override_adverse_llm_review_for_exact_copy(self):
        stub = StubBackend({"sentence_reviews": [
            {"sentence_id": "s1", "verdict": "uncertain", "reason": "Question relevance is unclear."},
            {"sentence_id": "s2", "verdict": "supported", "reason": "Evidence supports it."},
        ], "needs_more_evidence": True})
        result = inference.Critic(stub).review(self.claims, self.intent, self.report)
        self.assertEqual(result.sentence_reviews[0].verdict, "uncertain")
        self.assertEqual(stub.calls, 1)

    def test_critic_cannot_accept_nonverbatim_number_or_negation(self):
        for altered in ("The study used 200 samples.", "The study did not use 20 samples."):
            with self.subTest(altered=altered):
                report = self.report.model_copy(deep=True)
                report.sentences[0].text = altered
                stub = StubBackend({"sentence_reviews": [
                    {"sentence_id": sentence.sentence_id, "verdict": "supported",
                     "reason": "The sentence exactly quotes its cited evidence claim."}
                    for sentence in report.sentences
                ], "needs_more_evidence": False})
                critique = inference.Critic(stub).review(self.claims, self.intent, report)
                self.assertEqual(critique.sentence_reviews[0].verdict, "uncertain")
                self.assertEqual(critique.sentence_reviews[1].verdict, "supported")

    def test_empty_report_cannot_pass_llm_coverage_claim(self):
        empty = schemas.ReportSchema(sentences=[])
        stub = StubBackend({"sentence_reviews": [], "needs_more_evidence": False})
        self.assertTrue(inference.Critic(stub).review(self.claims, self.intent, empty).needs_more_evidence)

    def test_missing_coverage_assessment_defaults_to_warning(self):
        stub = StubBackend({"sentence_reviews": [
            {"sentence_id": sentence.sentence_id, "verdict": "supported", "reason": "Exact copy."}
            for sentence in self.report.sentences
        ]})
        self.assertTrue(inference.Critic(stub).review(self.claims, self.intent, self.report).needs_more_evidence)

    def test_selector_refuses_edit_to_supported_sentence(self):
        critique = schemas.CritiqueResult(sentence_reviews=[
            schemas.SentenceCritique(sentence_id="s1", verdict="uncertain", reason="Unclear."),
            schemas.SentenceCritique(sentence_id="s2", verdict="supported", reason="Exact copy."),
        ])
        stub = StubBackend({"action": "delete_sentence", "sentence_id": "s2"})
        with self.assertRaises(ValueError):
            inference.ActionSelector(stub).select(self.claims, self.intent, self.report, critique)

    def test_all_supported_coverage_gap_has_no_blind_action(self):
        critique = inference.Critic().review(self.claims, self.intent, self.report)
        stub = StubBackend("must not be called")
        self.assertIsNone(inference.ActionSelector(stub).select(self.claims, self.intent, self.report, critique))
        self.assertEqual(stub.calls, 0)

    def test_generator_has_no_hidden_retry_for_malformed_json(self):
        stub = StubBackend("not json")
        with self.assertRaises(ValueError):
            inference.ReportGenerator(stub).generate(self.claims, self.intent)
        self.assertEqual(stub.calls, 1)

    def test_json_rejects_ambiguous_and_nonfinite_payloads(self):
        for payload in [
            '{"x":1,"x":2}', '{"nested":{"x":1,"x":2}}', '{"x":NaN}',
            '{"x":Infinity}', '{"x":1e999}', '[]', '```json\n{}\n```', '{} trailing',
        ]:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                backend.parse_json_object(payload)

    def test_hf_budget_validation_is_lazy_and_strict(self):
        for budget in [True, 0, -1, 1.5]:
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                backend.HFJsonBackend("unused-model", max_new_tokens=budget)

    def test_context_overflow_raises_without_silent_token_truncation(self):
        hf = backend.HFJsonBackend("unused-model", max_new_tokens=5)
        hf._model = SimpleNamespace(config=SimpleNamespace(max_position_embeddings=10))

        class FakeTokenizer:
            model_max_length = 10

            def apply_chat_template(self, messages, **kwargs):
                return "whole prompt"

            def __call__(self, text, **kwargs):
                if kwargs.get("truncation") is not False:
                    raise AssertionError("The backend attempted prompt truncation.")
                return {"input_ids": SimpleNamespace(shape=(1, 6))}

        hf._tokenizer = FakeTokenizer()
        with self.assertRaisesRegex(ValueError, "exceeds context window"):
            hf.generate([{"role": "user", "content": "whole prompt"}])


if __name__ == "__main__":
    unittest.main()
