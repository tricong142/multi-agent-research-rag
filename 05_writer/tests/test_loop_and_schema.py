"""Contract/regression tests using labelled synthetic fixtures, no network/GPU."""
import importlib
import json
import unittest

S = importlib.import_module("05_writer.schemas")
V = importlib.import_module("05_writer.report_schema_validator")
L = importlib.import_module("05_writer.loop_controller")
N = importlib.import_module("05_writer.node")
E = importlib.import_module("05_writer.eval_writer")
P = importlib.import_module("05_writer.prompts")
R = importlib.import_module("05_writer.inference.report_generator")


def claims():
    return [S.VerifiedClaim(claim_id="c1", text="The synthetic sample contains 10 items.",
                            evidence="The synthetic sample contains 10 items.", source_id="synthetic:p1"),
            S.VerifiedClaim(claim_id="c2", text="The synthetic control contains 20 items.",
                            evidence="The synthetic control contains 20 items.", source_id="synthetic:p1")]


def draft(text=None):
    return S.ReportSchema(sentences=[S.ReportSentence(sentence_id="s1", text=text or claims()[0].text,
                                                     claim_ids=["c1"])])


class Generator:
    def __init__(self, result):
        self.result, self.calls = result, 0

    def generate(self, pool, intent):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result.model_copy(deep=True)


class Reviewer:
    def __init__(self, verdict="supported", needs=False):
        self.verdict, self.needs, self.calls = verdict, needs, 0

    def review(self, pool, intent, report):
        self.calls += 1
        return S.CritiqueResult(sentence_reviews=[S.SentenceCritique(sentence_id=s.sentence_id,
            verdict=self.verdict, reason="Synthetic test verdict.") for s in report.sentences],
            needs_more_evidence=self.needs)


class Selector:
    def __init__(self, action):
        self.action, self.calls = action, 0

    def select(self, *args):
        self.calls += 1
        return self.action


class SchemaTests(unittest.TestCase):
    def test_claims_reject_duplicate_and_unverified(self):
        with self.assertRaises(ValueError):
            V.parse_claims(claims() + claims()[:1])
        item = claims()[0].model_dump()
        item["verification_status"] = "pending"
        with self.assertRaises(ValueError):
            V.parse_claims([item])

    def test_unknown_citation_rejected(self):
        data = draft().model_dump()
        data["sentences"][0]["claim_ids"] = ["new_claim"]
        with self.assertRaises(ValueError):
            V.validate_report(data, claims())

    def test_duplicate_sentence_rejected(self):
        data = draft().model_dump()
        data["sentences"] *= 2
        with self.assertRaises(ValueError):
            V.validate_report(data, claims())

    def test_uncited_metadata_assertions_rejected(self):
        for field, value in [("title", "Treatment doubles survival"), ("limitations", ["Accuracy is 99%."])]:
            data = draft().model_dump()
            data[field] = value
            with self.assertRaises(ValueError):
                V.validate_report(data, claims())

    def test_critique_must_cover_all_sentences(self):
        with self.assertRaises(ValueError):
            V.parse_critique({"sentence_reviews": []}, draft())

    def test_no_external_or_same_claim_reselection(self):
        for ids in [["new"], ["c1"]]:
            with self.assertRaises(ValueError):
                V.validate_action({"action": "reselect_claims", "sentence_id": "s1", "claim_ids": ids}, draft(), claims())
        with self.assertRaises(ValueError):
            V.validate_action({"action": "request_new_claim", "sentence_id": "s1"}, draft(), claims())

    def test_string_false_not_boolean(self):
        with self.assertRaises(ValueError):
            S.FactCheckerNodeOutput.model_validate({"verified_claims": [], "low_confidence_warning": "false"})

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(ValueError):
            V.validate_report('{"sentences": [], "sentences": []}', claims())


class LoopTests(unittest.TestCase):
    def test_pass_without_repair(self):
        gen, critic, selector = Generator(draft()), Reviewer(), Selector(None)
        out = L.WriterLoopController(gen, critic, selector).run(claims(), "Summarize fixture")
        self.assertFalse(out.low_confidence_warning)
        self.assertEqual(out.internal_retries, 0)
        self.assertEqual(selector.calls, 0)

    def test_empty_claims_never_calls_model(self):
        gen = Generator(RuntimeError("must never run"))
        out = L.WriterLoopController(gen).run([], "Fixture")
        self.assertTrue(out.low_confidence_warning)
        self.assertEqual(out.final_report.sentences, [])
        self.assertEqual(gen.calls, 0)

    def test_repeated_generation_failure_is_bounded(self):
        gen = Generator(ValueError("bad JSON"))
        out = L.WriterLoopController(gen, max_internal_retry=2).run(claims(), "Fixture")
        self.assertEqual(gen.calls, 3)
        self.assertEqual(out.internal_retries, 2)
        self.assertTrue(out.low_confidence_warning)
        self.assertEqual(len(out.final_report.sentences), 2)
        self.assertIn("deterministic_claim_copy_fallback", out.warning_reasons)
        self.assertTrue(any(item.get("stage") == "deterministic_fallback" for item in out.trace))

    def test_zero_budget_returns_original_with_warning(self):
        out = L.WriterLoopController(Generator(draft("Wrong 99 items.")), Reviewer("unsupported"),
                                    max_internal_retry=0).run(claims(), "Fixture")
        self.assertTrue(out.low_confidence_warning)
        self.assertEqual(out.internal_retries, 0)
        self.assertEqual(out.final_report.sentences[0].text, "Wrong 99 items.")

    def test_internal_rewrite_is_rechecked(self):
        class TextReviewer(Reviewer):
            def review(self, pool, intent, report):
                self.verdict = "supported" if report.sentences[0].text == pool[0].text else "unsupported"
                return super().review(pool, intent, report)
        reviewer = TextReviewer()
        out = L.WriterLoopController(Generator(draft("Wrong 99 items.")), reviewer).run(claims(), "Fixture")
        self.assertFalse(out.low_confidence_warning)
        self.assertEqual(out.internal_retries, 1)
        self.assertEqual(reviewer.calls, 2)

    def test_stale_failed_review_is_replaced(self):
        class FlakyReviewer(Reviewer):
            def review(self, *args):
                if self.calls == 0:
                    self.calls += 1
                    raise RuntimeError("temporary backend failure")
                return super().review(*args)
        out = L.WriterLoopController(Generator(draft()), FlakyReviewer("unsupported"),
                                    max_internal_retry=1).run(claims(), "Fixture")
        self.assertEqual(out.critique.sentence_reviews[0].verdict, "unsupported")

    def test_repair_cannot_add_claim(self):
        selector = Selector({"action": "reselect_claims", "sentence_id": "s1", "claim_ids": ["external"]})
        out = L.WriterLoopController(Generator(draft()), Reviewer("uncertain"), selector,
                                    max_internal_retry=1).run(claims(), "Fixture")
        self.assertTrue(out.low_confidence_warning)
        self.assertEqual(out.final_report.sentences[0].claim_ids, ["c1"])

    def test_invalid_model_action_uses_exact_copy_rewrite_with_warning(self):
        class ExactReviewer(Reviewer):
            def review(self, pool, intent, report):
                self.verdict = "supported" if report.sentences[0].text == pool[0].text else "uncertain"
                return super().review(pool, intent, report)

        class MalformedSelector:
            def select(self, *args):
                raise ValueError("Model output is not a complete JSON object: Extra data")

        selectors = (
            MalformedSelector(),
            Selector({"action": "reselect_claims", "sentence_id": "s1", "claim_ids": ["c1"]}),
        )
        for selector in selectors:
            with self.subTest(selector=type(selector).__name__):
                out = L.WriterLoopController(Generator(draft("Wrong 99 items.")),
                                             ExactReviewer(), selector).run(claims(), "Fixture")
                self.assertEqual(out.final_report.sentences[0].text, claims()[0].text)
                self.assertTrue(out.low_confidence_warning)
                self.assertIn("action_selection_failed", out.warning_reasons)
                self.assertEqual(out.internal_retries, 1)
                self.assertTrue(any(item.get("stage") == "repair" and item.get("ok") for item in out.trace))

    def test_empty_generated_report_not_success(self):
        out = L.WriterLoopController(Generator(S.ReportSchema(sentences=[])), Reviewer()).run(claims(), "Fixture")
        self.assertTrue(out.low_confidence_warning)

    def test_upstream_warning_preserved(self):
        out = L.WriterLoopController(Generator(draft()), Reviewer()).run(claims(), "Fixture", upstream_warning=True)
        self.assertTrue(out.low_confidence_warning)

    def test_invalid_inputs_fail_soft(self):
        for pool, intent in [("wrong", "Fixture"), (claims(), None)]:
            out = L.WriterLoopController().run(pool, intent)
            self.assertTrue(out.low_confidence_warning)

    def test_node_returns_partial_state_no_routing(self):
        state = {"verified_claims": [c.model_dump() for c in claims()], "intent": "Fixture", "retry_count": 12}
        out = N.WriterNode()(state)
        self.assertEqual(set(out), {"final_report", "low_confidence_warning", "writer_diagnostics"})
        self.assertEqual(state["retry_count"], 12)

    def test_report_generator_removes_duplicate_claim_text(self):
        duplicate = claims()[0].model_copy(update={"claim_id": "c3"})
        report = R.ReportGenerator().generate(claims() + [duplicate], "Fixture")
        self.assertEqual(len(report.sentences), 2)
        self.assertEqual([s.claim_ids for s in report.sentences], [["c1"], ["c2"]])


class EvaluationTests(unittest.TestCase):
    def data(self):
        case = {"example_id": "synthetic:eval", "verified_claims": [c.model_dump() for c in claims()]}
        prediction = {"example_id": case["example_id"], "final_report": draft().model_dump(), "low_confidence_warning": True}
        return case, prediction

    def test_missing_human_labels_not_claimed_gold(self):
        case, pred = self.data()
        result = E.evaluate([case], [pred])
        self.assertIsNone(result["faithfulness_score"])
        self.assertEqual(result["exact_copy_support_proxy"], 1.0)
        self.assertEqual(result["low_confidence_warning_percent"], 100.0)

    def test_independent_labels_bound_to_report(self):
        case, pred = self.data()
        case.update(human_reviewed=True, human_sentence_labels={"s1": False},
                    reviewed_report_sha256=E.report_hash(pred["final_report"]))
        self.assertEqual(E.evaluate([case], [pred])["faithfulness_score"], 0.0)
        pred["final_report"]["sentences"][0]["text"] = "Changed content."
        with self.assertRaises(ValueError):
            E.evaluate([case], [pred])

    def test_missing_prediction_counts_invalid(self):
        case, _ = self.data()
        result = E.evaluate([case], [])
        self.assertEqual(result["schema_validity_rate"], 0)
        self.assertEqual(result["warning_field_coverage"], 0)

    def test_prompt_does_not_contain_target_report(self):
        data = {"task": "report", "verified_claims": [], "intent": "Fixture", "report": draft().model_dump()}
        messages = P.training_messages(data)
        self.assertNotIn("The synthetic sample", messages[1]["content"])
        self.assertIn("The synthetic sample", messages[-1]["content"])

    def test_prompt_uses_compact_output_contracts(self):
        report = draft().model_dump()
        critique = {
            "sentence_reviews": [], "needs_more_evidence": True, "summary": "Fixture",
        }
        cases = (
            (P.report_messages([], "Fixture"), ("title", "sentences", "claim_ids", "limitations")),
            (P.critic_messages([], "Fixture", report),
             ("sentence_reviews", "verdict", "needs_more_evidence", "summary")),
            (P.action_messages([], "Fixture", report, critique),
             ("action", "sentence_id", "claim_ids", "replacement_text", "reason")),
        )
        for messages, fields in cases:
            system_prompt = messages[0]["content"]
            self.assertIn("Output contract:", system_prompt)
            self.assertNotIn('"$defs"', system_prompt)
            self.assertNotIn('"properties"', system_prompt)
            for field in fields:
                self.assertIn(f'"{field}"', system_prompt)

    def test_prompts_require_full_pool_coverage(self):
        report_prompt = P.report_messages(claims(), "Fixture")[0]["content"]
        critic_prompt = P.critic_messages(claims(), "Fixture", draft())[0]["content"]
        self.assertIn("entire claim pool", report_prompt)
        self.assertIn("do not stop after the first two claims", report_prompt)
        self.assertIn("every requested part", critic_prompt)

    def test_prompt_exposes_only_writer_relevant_claim_fields(self):
        claim = {
            "claim_id": "c1", "text": "Supported statement.",
            "evidence": "Long source paragraph that the upstream verifier already checked.",
            "source_id": "paper:paragraph:1", "confidence": 0.99,
            "verification_status": "verified",
        }
        payload = json.loads(P.report_messages([claim], "Fixture")[1]["content"])
        self.assertEqual(
            payload["verified_claims"],
            [{"claim_id": "c1", "text": "Supported statement."}],
        )


if __name__ == "__main__":
    unittest.main()
