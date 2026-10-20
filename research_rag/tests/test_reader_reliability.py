"""Diagnostic gates/trace tests use stub agents, never real Gemini calls."""

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import fitz

from research_rag.evaluation import reader_reliability as diagnostic
from train_agent2_reader.reader_policy import GEMINI_MODEL, request_policy


class ReaderReliabilityTests(unittest.TestCase):
    def create_fixture(self, directory):
        manifest = directory / "manifest.jsonl"
        with fitz.open() as doc:
            doc.new_page().insert_text((50, 50), "First page evidence.")
            doc.new_page().insert_text((50, 50), "Second page evidence.")
            doc.save(directory / "fixture.pdf")
        manifest.write_text(json.dumps({"pdf_path": "fixture.pdf", "expected_spans": [
            {"page_no": 0, "text": "First page evidence."},
            {"page_no": 1, "text": "Second page evidence."}]}), encoding="utf-8")
        return manifest

    def fake_agent(self, output, calls, *, failed=False, record_api=True, failed_page=None):
        def factory(model_dir, *, on_api_attempt, allow_remote):
            self.assertTrue(allow_remote)
            self.assertTrue((output / "criteria.json").is_file())
            def process(pdf_path, page_no):
                calls.append(page_no)
                page_failed = failed or page_no == failed_page
                event = {"event": "reader_api_attempt", "call_id": f"call-{page_no}", "stage": "critique",
                         "model": GEMINI_MODEL, "attempt": 1, "timeout_ms": 30000, "wait_ms": 0,
                         "elapsed_ms": 2, "total_elapsed_ms": 2, "http_status": 503 if page_failed else 200,
                         "outcome": "exhausted" if page_failed else "success"}
                if record_api:
                    on_api_attempt(event)
                    self.assertTrue((output / "api_attempts.jsonl").read_text())
                block = SimpleNamespace(text="First page evidence." if page_no == 0 else "Second page evidence.",
                                        bbox=[0, 0, 200, 40], label="text", source_tool="fixture")
                return {"success": not page_failed, "blocks": [] if page_failed else [block], "final_tool": "fixture",
                        "attempts": [{"api_attempts": [event] if record_api else [], "accepted": not page_failed}]}
            return SimpleNamespace(process_page=process)
        return factory

    def test_page_filter_reads_only_selected_page_and_preregisters_criteria(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            manifest = self.create_fixture(directory)
            output = directory / "results"
            calls = []
            with patch.object(diagnostic, "ReaderAgent", side_effect=self.fake_agent(output, calls)):
                result = diagnostic.run_diagnostic(manifest, output, page_no=0)
            self.assertEqual(calls, [0])
            self.assertEqual(result["expected_span_count"], 1)
            self.assertTrue(result["automated_gate_pass"])
            self.assertFalse(result["overall_pass"])
            self.assertEqual(result["human_review"], "pending")
            criteria = json.loads((output / "criteria.json").read_text())
            self.assertEqual(criteria["selected_page"], 0)
            self.assertEqual(criteria["sources"][0]["expected_spans"], [{"page_no": 0, "text": "First page evidence."}])
            self.assertIsNone(result["api"]["cost_usd"])

    def test_default_keeps_all_pages_and_refuses_to_overwrite_a_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            manifest = self.create_fixture(directory)
            output = directory / "results"
            calls = []
            with patch.object(diagnostic, "ReaderAgent", side_effect=self.fake_agent(output, calls)):
                result = diagnostic.run_diagnostic(manifest, output)
                with self.assertRaises(FileExistsError):
                    diagnostic.run_diagnostic(manifest, output)
            self.assertEqual(calls, [0, 1])
            self.assertEqual(result["expected_span_count"], 2)
            self.assertTrue(result["automated_gate_pass"])

    def test_missing_or_invalid_selected_page_never_calls_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            manifest = self.create_fixture(directory)
            for page in (-1, True, 3):
                with self.subTest(page=page), patch.object(diagnostic, "ReaderAgent") as agent:
                    with self.assertRaises(ValueError):
                        diagnostic.run_diagnostic(manifest, directory / "unused", page_no=page)
                    agent.assert_not_called()
                    self.assertFalse((directory / "unused").exists())

    def test_exported_blocks_and_exact_scored_chunks_replay_without_pdf_or_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            manifest = self.create_fixture(directory)
            output = directory / "results"
            with patch.object(diagnostic, "ReaderAgent", side_effect=self.fake_agent(output, [])):
                result = diagnostic.run_diagnostic(manifest, output)
            blocks = [json.loads(line) for line in (output / "page_blocks.jsonl").read_text().splitlines()]
            self.assertEqual([b["page_no"] for b in blocks], [0, 1])
            self.assertEqual(blocks[1]["blocks"][0]["text"], "Second page evidence.")
            record = json.loads((output / "extractions.jsonl").read_text())
            self.assertEqual(len(record["chunks"]), 2)
            self.assertEqual(record["chunks"][1]["metadata"]["page_no"], 1)
            (directory / "fixture.pdf").rename(directory / "pdf-hidden-from-replay")
            with patch.object(diagnostic, "ReaderAgent", side_effect=AssertionError("No models in replay")):
                replay = diagnostic.replay_diagnostic(output)
            self.assertTrue(replay["replay_verified"])
            self.assertTrue(replay["automated_gate_pass"])
            self.assertEqual(replay["metrics"]["overall_exact_span_rate"], result["overall_exact_span_rate"])
            self.assertFalse(replay["overall_pass"])

    def test_partial_pages_survive_but_failed_pdf_stays_failed_on_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            manifest = self.create_fixture(directory)
            output = directory / "results"
            with patch.object(diagnostic, "ReaderAgent", side_effect=self.fake_agent(output, [], failed_page=1)):
                result = diagnostic.run_diagnostic(manifest, output)
            blocks = [json.loads(line) for line in (output / "page_blocks.jsonl").read_text().splitlines()]
            self.assertEqual(blocks[0]["blocks"][0]["text"], "First page evidence.")
            self.assertFalse(blocks[1]["accepted"])
            record = json.loads((output / "extractions.jsonl").read_text())
            self.assertEqual(record["error_type"], "ReaderBatchError")
            self.assertNotIn("chunks", record)
            replay = diagnostic.replay_diagnostic(output)
            self.assertTrue(replay["replay_verified"])
            self.assertFalse(replay["automated_gate_pass"])
            self.assertEqual(replay["metrics"]["span_coverage"], 0)
            self.assertFalse(result["automated_gate_pass"])

    def test_replay_refuses_tampered_text_or_changed_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            manifest = self.create_fixture(directory)
            output = directory / "results"
            with patch.object(diagnostic, "ReaderAgent", side_effect=self.fake_agent(output, [])):
                diagnostic.run_diagnostic(manifest, output)
            summary = json.loads((output / "summary.json").read_text())
            summary["overall_exact_span_rate"] = 0
            (output / "summary.json").write_text(json.dumps(summary))
            with self.assertRaisesRegex(ValueError, "metrics differ"):
                diagnostic.replay_diagnostic(output)
            with (output / "extractions.jsonl").open("a") as handle:
                handle.write(" ")
            with self.assertRaisesRegex(ValueError, "changed replay artifact"):
                diagnostic.replay_diagnostic(output)

    def test_terminal_api_failure_and_missing_api_trace_both_fail_gate(self):
        for failed, record_api in ((True, True), (False, False)):
            with self.subTest(failed=failed, record_api=record_api), tempfile.TemporaryDirectory() as tmp:
                directory = Path(tmp)
                manifest = self.create_fixture(directory)
                output = directory / "results"
                with patch.object(diagnostic, "ReaderAgent", side_effect=self.fake_agent(
                        output, [], failed=failed, record_api=record_api)):
                    result = diagnostic.run_diagnostic(manifest, output, page_no=0)
                self.assertFalse(result["automated_gate_pass"])
                self.assertEqual(result["status"], "automated_gates_failed")
                self.assertTrue((output / "summary.json").is_file())

    def test_api_summary_rejects_excess_attempts_or_late_success(self):
        base = {"event": "reader_api_attempt", "call_id": "c", "http_status": 200,
                "model": GEMINI_MODEL, "outcome": "success", "attempt": 1,
                "timeout_ms": 30000, "total_elapsed_ms": 5, "elapsed_ms": 5, "wait_ms": 0}
        self.assertTrue(diagnostic.summarize_attempts([base], request_policy())["within_attempt_and_deadline_policy"])
        late = {**base, "total_elapsed_ms": request_policy()["call_budget_seconds"] * 1000 + 1}
        self.assertFalse(diagnostic.summarize_attempts([late], request_policy())["within_attempt_and_deadline_policy"])
        excess = [{**base, "attempt": i} for i in range(1, 5)]
        self.assertFalse(diagnostic.summarize_attempts(excess, request_policy())["within_attempt_and_deadline_policy"])

    def test_call_expiring_before_first_transport_is_still_counted(self):
        event = {"event": "reader_api_stop", "call_id": "waiting", "outcome": "deadline_exceeded"}
        result = diagnostic.summarize_attempts([event], request_policy())
        self.assertEqual(result["logical_call_count"], 1)
        self.assertEqual(result["transport_attempt_count"], 0)
        self.assertEqual(result["terminal_failure_events"], 1)


if __name__ == "__main__":
    unittest.main()
