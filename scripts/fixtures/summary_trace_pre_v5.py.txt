from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from research_rag import local
from train_agent3_summarizer.node import SummarizerNode


class SummaryTraceTests(unittest.TestCase):
    def generate(self, raw, callback=None, role="generator"):
        class Inputs(dict):
            def to(self, device):
                return self

        tokenizer = SimpleNamespace(
            apply_chat_template=lambda *args, **kwargs: "private prompt",
            decode=lambda *args, **kwargs: raw,
        )
        class Tokenizer:
            apply_chat_template = tokenizer.apply_chat_template
            decode = tokenizer.decode

            def __call__(self, *args, **kwargs):
                return Inputs(input_ids=SimpleNamespace(shape=(1, 2)))

        model = SimpleNamespace(device="cpu", generate=lambda **kwargs: [[1, 2, 3, 4]])
        node = SummarizerNode(model, Tokenizer(), model, Tokenizer(), on_generation=callback)
        with patch.dict("sys.modules", {"torch": SimpleNamespace(no_grad=contextlib.nullcontext)}):
            return node._generate_json(model, node.generator_tokenizer, "system", "question", role=role)

    def test_malformed_generation_is_preserved_with_parse_error(self):
        events = []
        raw = '{"answer": "unfinished'
        self.assertIsNone(self.generate(raw, events.append))
        self.assertEqual(events[0]["raw_output"], raw)
        self.assertFalse(events[0]["json_valid"])
        self.assertIsNotNone(events[0]["parse_error"])
        self.assertEqual(events[0]["generated_tokens"], 2)

    def test_critic_rejection_is_distinct_from_invalid_json(self):
        events = []
        raw = '{"is_supported": false, "reason": "Missing source", "action": "rewrite"}'
        parsed = self.generate(raw, events.append, role="critic")
        self.assertFalse(parsed["is_supported"])
        self.assertTrue(events[0]["json_valid"])
        self.assertEqual(events[0]["role"], "critic")
        self.assertEqual(json.loads(events[0]["raw_output"])["reason"], "Missing source")

    def test_default_generation_does_not_print_raw_text(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(self.generate('{"answer": "private answer"}'), {"answer": "private answer"})
        self.assertEqual(stdout.getvalue(), "")

    def test_cli_trace_is_opt_in_and_preserves_existing_files(self):
        def builder(**kwargs):
            if kwargs["on_generation"]:
                kwargs["on_generation"]({"event": "summarizer_generation", "raw_output": "private evidence"})
            return SimpleNamespace(invoke=lambda state: {"status": "insufficient_evidence", "draft_answer": "private answer"})

        with tempfile.TemporaryDirectory() as directory, patch.object(local, "build_local_graph", side_effect=builder) as build:
            trace = Path(directory) / "trace.jsonl"
            selected_corpus, selected_index = Path(directory) / "new.jsonl", Path(directory) / "new_index"
            argv = ["local", "--question", "fixture", "--corpus", str(selected_corpus),
                    "--index-dir", str(selected_index)]
            with patch("sys.argv", argv), contextlib.redirect_stdout(io.StringIO()):
                local.main()
            self.assertIsNone(build.call_args.kwargs["on_generation"])
            self.assertEqual(build.call_args.kwargs["corpus_path"], selected_corpus)
            self.assertEqual(build.call_args.kwargs["index_dir"], selected_index)
            with patch("sys.argv", argv + ["--trace-output", str(trace)]), contextlib.redirect_stdout(io.StringIO()):
                local.main()
            rows = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(rows[0]["raw_output"], "private evidence")
            self.assertEqual(rows[1]["state"]["draft_answer"], "private answer")
            original = trace.read_bytes()
            with patch("sys.argv", argv + ["--trace-output", str(trace)]), self.assertRaises(FileExistsError):
                local.main()
            self.assertEqual(trace.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
