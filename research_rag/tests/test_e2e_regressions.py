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
from research_rag.graph import pdf_evidence_units
from research_rag.planning import answer_coverage_gap
from research_rag.pdf_table_cells import table_percentage_cells
from research_rag.tests.test_autonomy import make_graph
from research_rag.tests.test_integration import FakeRetriever, FakeSummarizer, chunk
from train_agent2_reader.reader_agent import ReaderAgent
from train_agent3_summarizer.node import SummarizerNode, evidence_numbers


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

    def test_numeric_summary_retries_when_the_quote_omits_the_value(self):
        adjacent = "The Delta study recruited participants online."
        node = SummarizerNode(None, None, None, None)
        node._call_generator = unittest.mock.Mock(side_effect=[
            {"answer": FACT, "evidence_spans": [adjacent]},
            {"answer": FACT, "evidence_spans": [FACT]},
        ])
        node._call_critic = unittest.mock.Mock(return_value={"is_supported": True, "reason": "Supported", "action": ""})
        result = node.run(adjacent + "\n" + FACT, "How many participants?")
        self.assertEqual(result.evidence_spans, [FACT])
        self.assertFalse(result.reasoning_trace[0].is_supported)
        self.assertIn("absent from the selected evidence", node._call_generator.call_args.args[2])
        self.assertEqual(node._call_critic.call_count, 1)

    def test_table_references_do_not_hide_values_in_row_labels(self):
        self.assertEqual(evidence_numbers("Table 3 lists 12.4%."), {"12.4%"})
        self.assertEqual(evidence_numbers("Graph/Figure 12.4%"), {"12.4%"})

    def test_pdf_table_cell_provenance_reaches_the_factchecker(self):
        import fitz

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "table.pdf"
            with fitz.open() as doc:
                page = doc.new_page()
                for y, label, rate, note in ((70, "Type", "%", "ID"), (100, "Optical", "12.4%", "100"),
                                              (125, "Thermal", "", "19.1%")):
                    for x, text in ((70, label), (150, rate), (210, note)):
                        if text:
                            page.insert_text((x, y), text)
                page.insert_text((70, 170), "Table 3: Results by group.")
                doc.save(path)
            def pdf_chunk(text, block, top, bottom):
                item = chunk(text, f"pdf:fixture:p0:b{block}:c0")
                item["metadata"] = {"page_no": 0, "bbox": [65, top, 250, bottom]}
                return item

            header = pdf_chunk("Type\n%\nID", 0, 55, 75)
            row = pdf_chunk("Optical\n12.4%\n100", 1, 85, 105)
            wrong_column = pdf_chunk("Thermal\n19.1%", 2, 110, 130)
            caption = pdf_chunk("Table 3: Results by group.", 3, 155, 175)
            blocks = [caption, header, row, wrong_column]
            self.assertEqual(set(table_percentage_cells(str(path), blocks)), {row["source_id"]})
            self.assertFalse(table_percentage_cells(str(path), [caption, row]))
            edited_row = {**row, "text": "Optical\n19.1%\n100"}
            self.assertFalse(table_percentage_cells(str(path), [caption, header, edited_row]))
            reader = SimpleNamespace(read_for_question=lambda *args, **kwargs: {
                "chunks": blocks, "read_pages": [0], "remaining_pages": [], "diagnostics": {},
            })
            retriever = SimpleNamespace(search=lambda *args, **kwargs: {"chunks": [caption], "decision": "dense"})
            claim = "Optical accounts for 12.4%."
            def summarize(units, question, *, table_scope, table_cells):
                id_ = next(key for key, text in units.items() if text == row["text"])
                self.assertEqual(table_scope[id_], [caption["text"], header["text"]])
                self.assertEqual(table_cells[id_]["cell_text"], "12.4%")
                return SimpleNamespace(answer=claim, evidence_spans=[row["text"]], is_supported=True,
                                       confidence="high", claim_sources={claim: [id_]})
            checker = unittest.mock.Mock(return_value={
                "fact_check_label": "not_enough_info", "confidence_score": 0, "fact_check_status": "ok"})
            result = make_graph(reader=reader, retriever=retriever, factchecker=checker,
                                summarizer=SimpleNamespace(run_with_source_ids=summarize), max_graph_retries=0).invoke(
                                    {"question": "What percentage is listed for Optical in Table 3?", "pdf_path": str(path)})
            req = checker.call_args_list[0].args[0]
            self.assertEqual(req["context"], row["text"])
            self.assertEqual(req["table_cell"]["cell_text"], "12.4%")
            self.assertEqual(req["table_cell"]["header_source_id"], header["source_id"])
            self.assertEqual(req["table_cell"]["row_source_id"], row["source_id"])
            self.assertEqual(req["table_cell"]["caption_source_id"], caption["source_id"])
            self.assertFalse(result["verified_claims"])

            from research_rag.atomic_adapter import AtomicFactCheckerNode
            runtime = SimpleNamespace(criteria={"case_deadline_seconds": 30})
            backend = unittest.mock.Mock()
            events = []
            adapter = AtomicFactCheckerNode(backend, runtime, on_trace=events.append)
            structured = {**req, "claim": "In Table 3, the percentage for Optical is 12.4%."}
            self.assertEqual(adapter(structured)["fact_check_label"], "support")
            for variant, verdict in (
                ({"claim": "In Table 4, the percentage for Optical is 12.4%."}, "not_enough_info"),
                ({"claim": "In Table 3, the percentage for Thermal is 12.4%."}, "not_enough_info"),
                ({"claim": "In Table 3, the percentage for Optical is 19.1%."}, "contradict"),
                ({"context": "Optical\n100"}, "not_enough_info"),
                ({"source_id": wrong_column["source_id"]}, "not_enough_info"),
                ({"table_cell": {**req["table_cell"], "column_header": "ID"}}, "not_enough_info"),
                ({"table_cell": {**req["table_cell"], "cell_bbox": [210, 85, 240, 104]}}, "not_enough_info"),
            ):
                with self.subTest(variant=variant):
                    self.assertEqual(adapter({**structured, **variant})["fact_check_label"], verdict)
            self.assertTrue(all(event["event"] == "table_cell_verification" for event in events))
            backend.generate_json.assert_not_called()

            request = {"question": "What percentage is listed for Optical in Table 3?", "pdf_path": str(path)}
            claim = structured["claim"]
            def verify(req):
                if "table_cell" in req:
                    return adapter(req)
                return {"fact_check_label": "not_enough_info", "confidence_score": 0, "fact_check_status": "ok"}

            written = make_graph(reader=reader, retriever=retriever, factchecker=verify,
                                 summarizer=SimpleNamespace(run_with_source_ids=summarize)).invoke(request)
            self.assertEqual(written["final_report"]["sentences"][0]["text"], claim)
            self.assertEqual(written["verified_claims"][0]["source_id"], row["source_id"])

    def test_table_critic_gets_only_related_scope_and_keeps_the_row_citation(self):
        node = SummarizerNode(None, None, None, None)
        caption = "Table 3: Results by group."
        header = "Type\n%"
        row = "Optical\n12.4%"
        claim = "In Table 3, the percentage for Optical is 12.4%."
        node._call_generator = unittest.mock.Mock(return_value={"claims": [{"text": claim, "source_ids": ["S1"]}]})
        node._call_critic = unittest.mock.Mock(return_value={
            "is_supported": True, "reason": "fixture", "action": ""})
        result = node.run_with_source_ids({"S1": row, "S2": "Thermal\n19.1%"}, "Which percentage?",
                                          table_scope={"S1": [caption, header]})
        node._call_critic.assert_called_once_with("\n\n".join([caption, header, row]), "Which percentage?",
                                                 claim, [caption, header, row])
        self.assertEqual(result.evidence_spans, [row])

    def test_pdf_source_ids_preserve_sentence_and_row_text(self):
        raw = chunk("The protocol describes recruitment. " + FACT, "pdf:fixture:p0:b0:c0")
        row = chunk("Text\n81.6%\n1802.08969", "pdf:fixture:p0:b1:c0")
        units = pdf_evidence_units([raw, row], {row["source_id"]})
        self.assertEqual([ref["text"] for ref in units.values()],
                         ["The protocol describes recruitment.", FACT, row["text"]])

    def test_source_id_rejects_unknown_ids_and_values_in_other_sources(self):
        for id_ in ("S99", "S1"):
            with self.subTest(id_=id_):
                node = SummarizerNode(None, None, None, None)
                node._call_generator = unittest.mock.Mock(return_value={
                    "claims": [{"text": FACT, "source_ids": [id_]}]})
                node._call_critic = unittest.mock.Mock()
                result = node.run_with_source_ids({"S1": OPPOSING, "S2": FACT}, "How many participants?")
                self.assertFalse(result.is_supported)
                self.assertFalse(result.claim_sources)
                node._call_critic.assert_not_called()

    def test_source_id_scope_check_receives_only_the_bound_evidence(self):
        node = SummarizerNode(None, None, None, None)
        wrong = "The Echo study enrolled 17 participants."
        node._call_generator = unittest.mock.Mock(side_effect=[
            {"claims": [{"text": FACT, "source_ids": ["S1"]}]},
            {"claims": []},
        ])
        node._call_critic = unittest.mock.Mock(return_value={
            "is_supported": False, "reason": "The selected study is different", "action": "rewrite"})
        result = node.run_with_source_ids({"S1": wrong, "S2": FACT}, "How many participants?")
        self.assertFalse(result.is_supported)
        self.assertFalse(result.evidence_spans)
        node._call_critic.assert_called_once_with(wrong, "How many participants?", FACT, [wrong])

    def test_source_id_table_retry_names_candidates_without_changing_bindings(self):
        node = SummarizerNode(None, None, None, None)
        claim = "The optical group accounts for 12.4% of results."
        units = {"S1": "Optical\n12.4%", "S2": "Thermal\n19.1%"}
        wrong = {"claims": [{"text": claim, "source_ids": ["S2"]}]}
        right = {"claims": [{"text": claim, "source_ids": ["S1"]},
                            {"text": "The thermal group accounts for 19.1% of results.", "source_ids": ["S2"]}]}
        node._call_generator = unittest.mock.Mock(side_effect=[wrong, right])
        node._call_critic = unittest.mock.Mock(return_value={"is_supported": True, "reason": "fixture", "action": ""})
        result = node.run_with_source_ids(units, "What are the shares in each group?")
        self.assertTrue(result.is_supported)
        self.assertIn("12.4%. Check S1", node._call_generator.call_args.args[2])
        self.assertEqual([args.args[3] for args in node._call_critic.call_args_list],
                         [[units["S1"]], [units["S2"]]])

    def test_unbound_pdf_passage_cannot_supply_the_final_citation(self):
        bound = chunk("The Delta trial enrolled 17 participants.", "pdf:fixture:p0:b0:c0")
        other = chunk(FACT, "pdf:fixture:p0:b1:c0")
        reader = SimpleNamespace(read_for_question=lambda *args, **kwargs: {
            "chunks": [bound, other], "read_pages": [0], "remaining_pages": [], "diagnostics": {},
        })
        node = SummarizerNode(None, None, None, None)
        node._call_generator = unittest.mock.Mock(return_value={
            "claims": [{"text": FACT, "source_ids": ["S1"]}]})
        node._call_critic = unittest.mock.Mock(return_value={
            "is_supported": True, "reason": "fixture", "action": ""})
        checker = unittest.mock.Mock(side_effect=lambda req: {
            "fact_check_label": "support" if req["context"] == FACT else "not_enough_info",
            "confidence_score": .9, "fact_check_status": "ok"})
        result = make_graph(reader=reader, retriever=FakeRetriever([]), summarizer=node,
                            factchecker=checker, max_graph_retries=0).invoke({
                                "question": "How many participants?", "pdf_path": "fixture.pdf"})
        self.assertEqual(result["evidence_refs"][0]["evidence_id"], "S1")
        self.assertEqual(checker.call_args_list[0].args[0]["context"], bound["text"])
        self.assertFalse(result["verified_claims"])

    def test_explicit_pdf_table_keeps_caption_and_rows_in_summary_context(self):
        def pdf_chunk(text, page, block, y):
            result = chunk(text, f"pdf:fixture:p{page}:b{block}:c0")
            result["metadata"] = {"page_no": page, "bbox": [20, y, 210, y + 10]}
            return result

        caption = pdf_chunk("Table 3: Enrollment by study.", 0, 3, 200)
        row = pdf_chunk(FACT, 0, 2, 170)
        wrong_page = pdf_chunk(OPPOSING, 1, 2, 170)
        reader = SimpleNamespace(read_for_question=lambda *args, **kwargs: {
            "chunks": [caption, row, wrong_page], "read_pages": [0, 1], "remaining_pages": [], "diagnostics": {},
        })
        retriever = SimpleNamespace(search=lambda *args, **kwargs: {"chunks": [caption], "decision": "dense"})
        summary = unittest.mock.Mock(return_value=SimpleNamespace(
            answer=FACT, evidence_spans=[FACT], is_supported=True, confidence="high"))
        def check(state):
            return {"fact_check_label": "support" if state["context"] == FACT else "not_enough_info",
                    "confidence_score": .9, "fact_check_status": "ok"}

        result = make_graph(reader=reader, retriever=retriever, summarizer=SimpleNamespace(run=summary),
                            factchecker=check).invoke({"question": "How many participants according to Table 3?",
                                                       "pdf_path": "fixture.pdf"})
        context = summary.call_args.kwargs["context"]
        self.assertIn(caption["text"], context)
        self.assertIn(FACT, context)
        self.assertNotIn(OPPOSING, context)
        self.assertEqual(result["verified_claims"][0]["source_id"], row["source_id"])

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
