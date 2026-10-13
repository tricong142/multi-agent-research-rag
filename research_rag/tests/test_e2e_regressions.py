"""Regressions from the first real E2E run; all model responses here are stubs."""
import contextlib
import importlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from research_rag.adapters import PdfReader
from research_rag.evaluation.autonomy import score_case, summarize_results
from research_rag.planning import answer_coverage_gap
from research_rag.tests.test_autonomy import make_graph
from research_rag.tests.test_integration import FakeRetriever, FakeSummarizer, chunk
from train_agent2_reader.reader_agent import ReaderAgent
from train_agent3_summarizer.node import SummarizerNode


FACT = "The Delta study enrolled 17 participants."
OPPOSING = "The Delta study enrolled 29 participants."


class E2ERegressions(unittest.TestCase):
    def test_numeric_answer_is_rewritten_before_factchecking(self):
        node = SummarizerNode(None, None, None, None)
        calls = []
        def generator(context, question, instruction):
            calls.append(instruction)
            return {"answer": "17" if len(calls) == 1 else FACT, "evidence_spans": [FACT]}
        node._call_generator = generator
        node._call_critic = lambda *args: {"is_supported": True, "reason": "Supported", "action": ""}
        result = node.run(FACT, "How many participants?")
        self.assertEqual(result.answer, FACT)
        self.assertEqual(len(calls), 2)
        self.assertFalse(result.reasoning_trace[0].is_supported)

    def test_section_pointer_cannot_complete_a_value_question(self):
        pointer = "The sample size is reported in the appendix."
        result = make_graph(retriever=FakeRetriever([chunk(pointer)]),
                            summarizer=FakeSummarizer(pointer, pointer)).invoke({"question": "What is the sample size?"})
        self.assertNotEqual(result["status"], "completed")
        self.assertFalse(result["verified_claims"])
        self.assertNotIn("write", [h["action"] for h in result["action_history"]])
        self.assertTrue(result["research_plan"]["tasks"][0]["missing_questions"])
        self.assertIsNone(answer_coverage_gap("Where is the sample size reported?", pointer))

    def test_supported_full_chunk_can_replace_a_wrong_selected_span(self):
        wrong = "The protocol describes recruitment."
        def checker(state):
            return {"fact_check_label": "support" if state["context"] == FACT else "not_enough_info",
                    "confidence_score": .9, "fact_check_status": "ok"}
        result = make_graph(retriever=FakeRetriever([chunk(wrong, "wrong"), chunk(FACT, "right")]),
                            summarizer=FakeSummarizer(FACT, wrong), factchecker=checker).invoke({"question": "Sample size?"})
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["verified_claims"][0]["source_id"], "right")
        self.assertEqual(result["verified_claims"][0]["evidence"], FACT)

    def test_unaccepted_summary_can_audit_conflicting_sources_but_never_verify(self):
        for conflict in (True, False):
            with self.subTest(conflict=conflict):
                calls = []
                def checker(state):
                    calls.append(state)
                    return {"fact_check_label": "contradict" if conflict and state["claim"] != state["context"] else "support",
                            "confidence_score": .9, "fact_check_status": "ok"}
                summary = SimpleNamespace(run=lambda **kwargs: SimpleNamespace(
                    answer="Sources disagree.", evidence_spans=[FACT, OPPOSING], is_supported=False, confidence="low"))
                state = make_graph(retriever=FakeRetriever([chunk(FACT, "a"), chunk(OPPOSING, "b")]),
                                   summarizer=summary, factchecker=checker, max_graph_retries=0).invoke({"question": "How many?"})
                self.assertEqual(len(calls), 4)
                self.assertFalse(state["verified_claims"])
                self.assertFalse(state["final_report"]["sentences"])
                self.assertEqual(any(r["label"] == "contradict" for r in state["fact_check_results"]), conflict)

    def test_prior_evidence_survives_a_full_new_context_window(self):
        contexts = []
        class Retriever(FakeRetriever):
            def search(self, *args, **kwargs):
                result = super().search(*args, **kwargs)
                result["chunks"] = [chunk(FACT, "answer")] if len(self.calls) == 1 else [chunk("noise " * 18, "noise")]
                return result
        class Summarizer:
            def run(self, context, question):
                contexts.append(context)
                return SimpleNamespace(answer=FACT, evidence_spans=[FACT], is_supported=True, confidence="high")
        def checker(state):
            return {"fact_check_label": "not_enough_info", "confidence_score": .2, "fact_check_status": "ok"}
        make_graph(retriever=Retriever([]), summarizer=Summarizer(), factchecker=checker,
                   max_context_chars=110).invoke({"question": "How many participants?"})
        self.assertEqual(len(contexts), 2)
        self.assertTrue(all(FACT in text for text in contexts))

    def test_failed_confidence_keeps_attempts_and_blocks_publication(self):
        def checker(state):
            return {"fact_check_label": "support", "confidence_score": 0.0,
                    "fact_check_status": "confidence_failed", "confidence_reasoning": "Invalid score",
                    "fact_check_attempts": [{"stage": "confidence", "attempt": 1, "ok": False,
                                             "error_type": "ValueError", "error": "private diagnostic"}]}
        state = make_graph(factchecker=checker).invoke({"question": "Sample?"})
        review = state["fact_check_results"][0]
        self.assertEqual(review["attempts"][0]["stage"], "confidence")
        self.assertNotIn("error", review["attempts"][0])
        self.assertEqual(state["stop_reason"], "factchecker_failed")
        self.assertFalse(state["verified_claims"])

    def test_reader_preserves_rejection_details_at_graph_boundary(self):
        import fitz
        agent = SimpleNamespace(process_page=lambda *args: {
            "success": False, "blocks": [], "final_tool": "alt_segmentation",
            "attempts": [{"tool": "alt_segmentation", "reason": "Rejected fixture", "accepted": False}]})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.pdf"
            with fitz.open() as doc:
                doc.new_page().insert_text((50, 90), FACT)
                doc.save(path)
            state = make_graph(reader=PdfReader(agent)).invoke({"question": "Sample size?", "pdf_path": str(path)})
        self.assertEqual(state["stop_reason"], "reader_failed")
        trial = state["reader_diagnostics"]["page_trials"][0]
        self.assertEqual(trial["attempts"][0]["reason"], "Rejected fixture")
        self.assertEqual(state["agent_cycles"][0]["local_execution"], state["reader_diagnostics"])
        self.assertFalse(state["pdf_chunks"])

    def test_reader_error_records_stage_and_code_without_exception_secrets(self):
        class ApiFailure(RuntimeError):
            code = 503
        reader = ReaderAgent()
        with patch.object(reader, "_extract_heuristic_features", return_value={}), \
                patch.object(reader, "_decide_tool", return_value="alt_segmentation"), \
                patch.object(reader, "_run_tool", return_value=[]), \
                patch.object(reader, "_critique", side_effect=ApiFailure("private credential")):
            result = reader.process_page("unused.pdf")
        self.assertFalse(result["success"])
        self.assertEqual(result["attempts"][0]["stage"], "critique")
        self.assertEqual(result["attempts"][0]["http_status"], 503)
        self.assertNotIn("private credential", json.dumps(result))

    def test_factchecker_raw_json_diagnostics_are_opt_in(self):
        Backend = importlib.import_module("04_factchecker.inference.judge").TransformersJSONBackend
        for raw in ('{"fact_check_label":"support"}', '{"confidence_score":'):
            events = []
            class Tokenizer:
                eos_token_id = 0
                def apply_chat_template(self, *args, **kwargs): return "prompt"
                def __call__(self, *args, **kwargs): return {"input_ids": SimpleNamespace(shape=(1, 2))}
                def decode(self, *args, **kwargs): return raw
            model = SimpleNamespace(generate=lambda **kwargs: [[1, 2, 3, 4]])
            with patch.dict("sys.modules", {"torch": SimpleNamespace(inference_mode=contextlib.nullcontext)}):
                for callback in (None, events.append):
                    backend = Backend(model, Tokenizer(), on_generation=callback)
                    if raw.endswith(":"):
                        with self.assertRaises(ValueError): backend.generate_json([], max_new_tokens=192)
                    else:
                        backend.generate_json([], max_new_tokens=192)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["raw_output"], raw)
            self.assertEqual(events[0]["generated_tokens"], 2)
            self.assertEqual(events[0]["json_valid"], not raw.endswith(":"))

    def test_automated_failures_are_distinct_from_pending_human_review(self):
        names = ("sufficient", "missing", "conflict", "pdf_pages", "budget", "heldout_1", "heldout_2", "heldout_3")
        results = {name: {"automated_gate_pass": True} for name in names}
        policies = [{"case": f"heldout_{i}", "policy": mode, "union_recall": 1., "fallback_count": 0}
                    for i in range(1, 4) for mode in ("adaptive", "bm25", "dense")]
        complete = summarize_results(results, policies, independent_test_proven=False)
        self.assertEqual(complete["status"], "awaiting_human_review")
        self.assertFalse(complete["overall_pass"])
        results["missing"]["automated_gate_pass"] = False
        self.assertEqual(summarize_results(results, policies, independent_test_proven=False)["status"], "automated_gates_failed")
        self.assertFalse(summarize_results(results, [], independent_test_proven=False)["retrieval_policy_gate_pass"])

    def test_safety_gate_checks_time_search_and_call_budgets(self):
        state = make_graph().invoke({"question": "Sample?"})
        self.assertFalse(score_case({"id": "sufficient"}, state, elapsed_ms=10**9)["safety_gate_pass"])
        for key, budget_key in (("search_count", "max_searches"), ("factcheck_calls_used", "max_factcheck_calls")):
            changed = dict(state)
            limit = state["budget"].get(budget_key, state["budget"]["policy"].get(budget_key))
            changed[key] = limit + 1
            self.assertFalse(score_case({"id": "sufficient"}, changed)["safety_gate_pass"])


if __name__ == "__main__":
    unittest.main()
