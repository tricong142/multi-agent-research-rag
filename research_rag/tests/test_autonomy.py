"""Behavior checks for autonomous control; synthetic models, not a quality evaluation."""
from __future__ import annotations

import contextlib
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from research_rag.adapters import PdfReader
from research_rag.controller import Decision, EXECUTABLE_ACTIONS, enforce_limits
from research_rag.graph import build_graph
from research_rag.local import run_worker
from research_rag.observe import run_with_metrics
from research_rag.tests.test_integration import FakeRetriever, FakeSummarizer, FakeFactchecker, WriterNode, chunk
from train_agent3_summarizer.node import SummarizerNode

EVIDENCE = "The sample contained 42 cases."


class CompleteWriter:
    """Accept exact claim copies for synthetic tasks whose requested fact is covered."""
    def __call__(self, state):
        result = WriterNode()(state)
        result["low_confidence_warning"] = False
        result["writer_diagnostics"]["critique"]["needs_more_evidence"] = False
        return result


def make_graph(**kwargs):
    defaults = dict(retriever=FakeRetriever([chunk(EVIDENCE)]), summarizer=FakeSummarizer(EVIDENCE, EVIDENCE),
                    factchecker=FakeFactchecker(["support"]), writer=CompleteWriter())
    return build_graph(**(defaults | kwargs))


class AutonomyTests(unittest.TestCase):
    def test_complete_goal_has_citations_and_content_free_events(self):
        events = []
        result, metrics = run_with_metrics(make_graph(on_event=events.append), {"question": "Private sample size?"})
        self.assertEqual(result["goal"], "Private sample size?")
        self.assertEqual(result["stop_reason"], "task_completed")
        self.assertEqual(result["status"], "completed")
        self.assertEqual([h["action"] for h in result["action_history"]], ["search", "summarize", "factcheck", "write"])
        self.assertEqual(result["final_report"]["sentences"][0]["claim_ids"], ["claim:1"])
        self.assertEqual(result["agent_result"]["agent"], "write")
        self.assertNotIn(EVIDENCE, json.dumps(events) + json.dumps(metrics))
        self.assertNotIn("Private sample", json.dumps(events) + json.dumps(metrics))

    def test_missing_context_yields_immediately_and_changes_query(self):
        node = SummarizerNode(None, None, None, None)
        generation_calls = []
        def generate(*args):
            generation_calls.append(args)
            return {"answer": "Unknown.", "evidence_spans": []}
        node._call_generator = generate
        node._call_critic = lambda *args: {"is_supported": False, "reason": "Missing sample count",
                                          "action": "request_more_context", "suggested_query": "study sample count"}
        result = node.run(context="Unrelated text", question="How many?")
        self.assertEqual(len(generation_calls), 1)
        self.assertEqual(result.suggested_query, "study sample count")
        self.assertEqual(result.missing_information, ["Missing sample count"])
        retriever = FakeRetriever([chunk("Unrelated text")])
        final = make_graph(retriever=retriever, summarizer=node).invoke({"question": "How many?"})
        self.assertEqual(retriever.calls[1]["query"], "study sample count")
        self.assertEqual(retriever.calls[1]["method"], "dense")
        self.assertEqual(final["stop_reason"], "search_budget_exhausted")

    def test_more_context_can_recover_and_clear_resolved_warning(self):
        class Retriever(FakeRetriever):
            def search(self, query, **kwargs):
                result = super().search(query, **kwargs)
                result["chunks"] = [chunk("Study methods.", "methods")] if len(self.calls) == 1 else [chunk(EVIDENCE, "sample")]
                return result
        class Summarizer:
            def run(self, context, question):
                if EVIDENCE in context:
                    self.context = context
                    return SimpleNamespace(answer=EVIDENCE, evidence_spans=[EVIDENCE], is_supported=True, confidence="high")
                return SimpleNamespace(answer="", evidence_spans=[], is_supported=False, confidence="low",
                                       missing_information=["Sample count"], suggested_query="sample count")
        summarizer = Summarizer()
        result = make_graph(retriever=Retriever([]), summarizer=summarizer).invoke({"question": "How many?"})
        self.assertEqual(result["status"], "completed")
        self.assertFalse(result["low_confidence_warning"])
        self.assertIn("Study methods.", summarizer.context)
        self.assertEqual(len(result["seen_chunks"]), 2)

    def test_step_and_time_limits_stop_before_next_model(self):
        for kwargs, reason in (({"max_steps": 1}, "step_budget_exhausted"),
                               ({"max_seconds": 1}, "time_budget_exhausted")):
            with self.subTest(reason=reason):
                now = [100.0]
                class Retriever(FakeRetriever):
                    def search(self, *args, **options):
                        now[0] += 2
                        return super().search(*args, **options)
                checker = FakeFactchecker(["support"])
                result = make_graph(retriever=Retriever([chunk(EVIDENCE)]), factchecker=checker,
                                    clock=lambda: now[0], **kwargs).invoke({"question": "Sample?"})
                self.assertEqual(result["stop_reason"], reason)
                self.assertEqual(checker.calls, [])
                self.assertEqual(result["steps_used"], 1)

    def test_cost_reservation_blocks_unaffordable_action(self):
        bounds = {action: 0.3 for action in EXECUTABLE_ACTIONS}
        result = make_graph(max_cost_usd=0.5, action_cost_bounds=bounds).invoke({"question": "Sample?"})
        self.assertEqual(result["stop_reason"], "cost_budget_exhausted")
        self.assertAlmostEqual(result["reserved_cost_usd"], 0.3)
        self.assertEqual(result["steps_used"], 1)
        with self.assertRaisesRegex(ValueError, "upper bound"):
            make_graph(max_cost_usd=1)

    def test_factcheck_budget_is_global_across_search_rounds(self):
        class Retriever(FakeRetriever):
            def search(self, *args, **kwargs):
                result = super().search(*args, **kwargs)
                result["chunks"] = [chunk(EVIDENCE, f"paper:{len(self.calls)}")]
                return result
        checker = FakeFactchecker(["not_enough_info"])
        result = make_graph(retriever=Retriever([]), factchecker=checker, max_factcheck_calls=1).invoke({"question": "Sample?"})
        self.assertEqual(len(checker.calls), 1)
        self.assertEqual(result["stop_reason"], "factcheck_budget_exhausted")
        self.assertEqual(result["verified_claims"], [])
        checks = [c for c in result["agent_cycles"] if c["agent"] == "factcheck"]
        self.assertTrue(checks)
        self.assertTrue(all(c["evaluation"]["authority"] == "advise" for c in checks))

    def test_factchecker_can_request_clarification(self):
        def checker(state):
            return {"fact_check_label": "not_enough_info", "confidence_score": 0.2,
                    "fact_check_status": "ok", "recommended_action": "ask_clarify"}
        result = make_graph(factchecker=checker).invoke({"question": "Which sample?"})
        self.assertEqual(result["status"], "needs_input")
        self.assertEqual(result["stop_reason"], "needs_clarification")
        self.assertEqual(result["search_count"], 1)
        self.assertEqual(result["agent_result"]["missing_information"], [EVIDENCE])

    def test_budget_exit_copies_only_verified_claims_without_writer_call(self):
        def writer(state):
            self.fail("Writer must not be called after step budget is used")
        result = make_graph(max_steps=3, writer=writer).invoke({"question": "Sample?"})
        self.assertEqual(result["stop_reason"], "step_budget_exhausted")
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["final_report"]["sentences"][0]["text"], EVIDENCE)

    def test_writer_unsupported_sentences_are_not_published(self):
        def writer(state):
            output = CompleteWriter()(state)
            output["final_report"]["sentences"][0]["text"] = "Invented number 999."
            output["writer_diagnostics"]["critique"]["sentence_reviews"][0]["verdict"] = "unsupported"
            return output
        result = make_graph(writer=writer, max_graph_retries=0).invoke({"question": "Sample?"})
        self.assertEqual(result["final_report"]["sentences"], [])
        self.assertNotEqual(result["status"], "completed")

    def test_repeated_search_is_blocked_even_with_available_budget(self):
        result = make_graph(max_steps=1).invoke({"question": "Sample?"})
        result["steps_used"] = 0
        action = Decision(action="search", reason="retry", query="Sample?", method="bm25", top_k=5)
        result["budget"]["max_steps"] = 30
        checked = enforce_limits(action, result, now=result["started_at"])
        self.assertEqual(checked.reason, "repeated_search_without_progress")

    def test_unknown_tool_and_extra_arguments_are_rejected(self):
        for value in ({"action": "shell", "reason": "try"},
                      {"action": "search", "reason": "try", "method": "hyde", "query": "x", "top_k": 5},
                      {"action": "write", "reason": "try", "query": "x"}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Decision.model_validate(value)

    def test_reader_expansion_keeps_the_missing_information_query(self):
        class Reader:
            def read_for_question(self, path, *, question, excluded_pages):
                page = len(excluded_pages)
                return {"chunks": [chunk("Methods." if page == 0 else EVIDENCE, f"pdf:{page}")],
                        "read_pages": [page], "remaining_pages": [1] if page == 0 else [], "diagnostics": {}}
        class Summarizer:
            def run(self, context, question):
                if EVIDENCE in context:
                    return SimpleNamespace(answer=EVIDENCE, evidence_spans=[EVIDENCE], is_supported=True, confidence="high")
                return SimpleNamespace(answer="", evidence_spans=[], is_supported=False, confidence="low",
                                       missing_information=["Sample count"], suggested_query="sample count")
        retriever = FakeRetriever([])
        result = make_graph(reader=Reader(), retriever=retriever, summarizer=Summarizer()).invoke(
            {"question": "Describe study", "pdf_path": "synthetic.pdf"})
        self.assertEqual([h["action"] for h in result["action_history"]][:5],
                         ["read", "search", "summarize", "read", "search"])
        self.assertEqual(retriever.calls[1]["query"], "sample count")
        self.assertEqual(result["read_pages"], [0, 1])

    def test_empty_search_after_writer_request_preserves_verified_partial_report(self):
        result = make_graph(writer=WriterNode()).invoke({"question": "Describe the study completely"})
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["search_count"], 2)
        self.assertEqual(result["verified_claims"][0]["text"], EVIDENCE)
        self.assertTrue(result["final_report"]["sentences"])

    def test_writer_cannot_claim_completion_when_coverage_is_missing(self):
        def writer(state):
            result = CompleteWriter()(state)
            result["writer_diagnostics"]["critique"]["needs_more_evidence"] = True
            return result
        result = make_graph(writer=writer, max_graph_retries=0).invoke({"question": "Describe study"})
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["stop_reason"], "search_budget_exhausted")


class PersistenceAndReaderTests(unittest.TestCase):
    def test_sqlite_resume_preserves_evidence_history_and_budget_after_reopen(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "task.sqlite"
            config = {"configurable": {"thread_id": "research-1"}}
            retriever = FakeRetriever([chunk(EVIDENCE)])
            with contextlib.closing(sqlite3.connect(path, check_same_thread=False)) as conn:
                saver = SqliteSaver(conn, serde=JsonPlusSerializer(allowed_msgpack_modules=[]))
                first = make_graph(retriever=retriever, checkpointer=saver)
                state = first.invoke({"question": "Sample?"}, config, interrupt_after=["retrieval"])
                self.assertEqual(state["steps_used"], 1)
                deadline = state["deadline_at"]
            with contextlib.closing(sqlite3.connect(path, check_same_thread=False)) as conn:
                resumed = make_graph(retriever=retriever, checkpointer=SqliteSaver(conn))
                result, metrics = run_with_metrics(resumed, None, config)
            self.assertEqual(len(retriever.calls), 1)
            self.assertEqual(result["deadline_at"], deadline)
            self.assertEqual(result["steps_used"], 4)
            self.assertEqual(result["stop_reason"], "task_completed")
            self.assertEqual(metrics["final_status"], "completed")

    def test_expired_pending_action_does_not_run_on_resume(self):
        from langgraph.checkpoint.memory import InMemorySaver
        now = [100.0]
        retriever = FakeRetriever([chunk(EVIDENCE)])
        graph = make_graph(retriever=retriever, checkpointer=InMemorySaver(), clock=lambda: now[0], max_seconds=10)
        config = {"configurable": {"thread_id": "expired"}}
        graph.invoke({"question": "Sample?"}, config, interrupt_before=["retrieval"])
        now[0] += 20
        result = graph.invoke(None, config)
        self.assertEqual(result["stop_reason"], "time_budget_exhausted")
        self.assertEqual(retriever.calls, [])

    def test_question_selects_relevant_pages_and_can_expand_to_unread_pages(self):
        import fitz
        from train_agent2_reader.tools.common_schema import ExtractedBlock
        class Reader:
            def process_page(self, path, page_no):
                with fitz.open(path) as doc:
                    text = doc[page_no].get_text()
                return {"success": True, "blocks": [ExtractedBlock(page_no=page_no, text=text,
                                      bbox=[1, 2, 3, 4], source_tool="alt_segmentation")]}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "pages.pdf"
            doc = fitz.open()
            for text in ("Introduction", "Methods", "Limitations", "sample contained 42 cases"):
                doc.new_page().insert_text((72, 72), text)
            doc.save(path)
            doc.close()
            reader = PdfReader(Reader())
            first = reader.read_for_question(str(path), question="sample cases", excluded_pages=[], page_batch=1)
            self.assertEqual(first["read_pages"], [3])
            second = reader.read_for_question(str(path), question="sample cases", excluded_pages=[3])
            self.assertEqual(set(second["read_pages"]), {0, 1, 2})
            self.assertEqual(second["remaining_pages"], [])

    def test_hard_timeout_terminates_worker(self):
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            code = run_worker([sys.executable, "-c", "import time; time.sleep(60)"], 0.1)
        self.assertEqual(code, 124)
        self.assertIn("process_timeout", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
