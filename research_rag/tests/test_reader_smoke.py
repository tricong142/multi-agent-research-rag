"""Regression checks for the Reader smoke-test command's exit status."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from research_rag.evaluation.reader_smoke import main, score


class ReaderSmokeCommandTests(unittest.TestCase):
    def run_case(self, *, text="The total is 275 dollars.", expected="The total is 275 dollars.", missing=False, api_error=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            if not missing:
                (root / "sample.pdf").touch()  # Reader is injected; PDF parsing is tested separately.
            manifest = root / "manifest.jsonl"
            manifest.write_text(json.dumps({
                "pdf_path": "sample.pdf", "layout": "test",
                "expected_spans": [{"page_no": 0, "text": expected}],
            }) + "\n", encoding="utf-8")
            reader = Mock()
            if api_error:
                reader.read.side_effect = RuntimeError("private API detail")
            else:
                reader.read.return_value = [{"text": text, "metadata": {"page_no": 0}}]
            output = io.StringIO()
            exit_code = 0
            with patch("sys.argv", ["reader_smoke", "--manifest", str(manifest)]), \
                    patch("research_rag.evaluation.reader_smoke.PdfReader", return_value=reader), \
                    contextlib.redirect_stdout(output):
                try:
                    main()
                except SystemExit as exc:
                    exit_code = exc.code
            return exit_code, json.loads(output.getvalue())

    def test_complete_extraction_passes(self):
        code, result = self.run_case()
        self.assertEqual(code, 0)
        self.assertTrue(result["passed"])

    def test_missing_pdf_fails_even_without_a_reader_exception(self):
        code, result = self.run_case(missing=True)
        self.assertEqual(code, 1)
        self.assertEqual(result["evaluated_pdf_count"], 0)
        self.assertFalse(result["passed"])

    def test_missing_evidence_fails(self):
        code, result = self.run_case(text="The total is unknown.")
        self.assertEqual(code, 1)
        self.assertEqual(result["failures"], [])
        self.assertFalse(result["passed"])

    def test_api_failure_fails_without_exposing_error_message(self):
        code, result = self.run_case(api_error=True)
        self.assertEqual(code, 1)
        self.assertNotIn("private API detail", json.dumps(result))
        self.assertEqual(result["failures"][0]["error_type"], "RuntimeError")

    def test_partial_word_is_not_an_exact_span(self):
        code, result = self.run_case(text="The total is 275 dollarsmore.")
        self.assertEqual(code, 1)
        self.assertEqual(result["exact_span_rate"], 0.0)

    def test_pdf_ligature_matches_the_visually_identical_reference(self):
        code, result = self.run_case(text="The \ufb01nal result is supported.", expected="The final result is supported.")
        self.assertEqual(code, 0)
        self.assertEqual(result["exact_span_rate"], 1.0)

    def test_source_hash_mismatch_does_not_call_reader_or_score_changed_pdf(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "changed.pdf").write_bytes(b"modified fixture")
            manifest = root / "manifest.jsonl"
            manifest.write_text(json.dumps({"pdf_path": "changed.pdf", "source_sha256": "0" * 64,
                                             "expected_spans": [{"page_no": 0, "text": "A result"}]}))
            reader = Mock()
            result = score(manifest, reader)
            reader.read.assert_not_called()
            self.assertEqual(result["span_count"], 0)
            self.assertEqual(result["failures"][0]["error_type"], "SourceHashMismatch")


if __name__ == "__main__":
    unittest.main()
