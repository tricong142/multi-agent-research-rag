from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import fitz

from research_rag.adapters import PdfReader, ReaderBatchError
from train_agent2_reader.reader_agent import ReaderAgent
from train_agent2_reader.tools.common_schema import ExtractedBlock


class LocalReaderTests(unittest.TestCase):
    def fixture(self, root, *, scan=False):
        path = root / "sample.pdf"
        with fitz.open() as document:
            page = document.new_page()
            page.insert_text((50, 60), "The reference sample contains 275 documents.")
            if scan:
                raster = page.get_pixmap().tobytes("png")
                with fitz.open() as scanned:
                    scanned.new_page().insert_image(page.rect, stream=raster)
                    scanned.save(path)
            else:
                document.save(path)
        return path

    def block(self):
        return ExtractedBlock(0, "The reference sample contains 275 documents.",
                              [50, 45, 300, 65], confidence=.95, source_tool="ocr_fallback")

    def test_real_text_pdf_uses_local_reader_without_api(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
                "train_agent2_reader.reader_policy.get_client", side_effect=AssertionError("No Gemini")) as api:
            path = self.fixture(Path(tmp))
            chunks = PdfReader().read(str(path))
            api.assert_not_called()
            self.assertIn("275 documents", chunks[0]["text"])
            self.assertEqual(chunks[0]["metadata"]["source_tool"], "alt_segmentation")

    def test_ambiguous_text_layout_still_uses_local_parser(self):
        features = {"has_text_layer": True, "avg_block_count": 50, "image_area_ratio": .3}
        with patch("train_agent2_reader.reader_policy.get_client") as api:
            self.assertEqual(ReaderAgent()._decide_tool(features), "alt_segmentation")
            api.assert_not_called()

    def test_scan_goes_directly_to_ocr_no_cloud(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
                "train_agent2_reader.reader_agent.extract_with_ocr", return_value=[self.block()]) as ocr, patch(
                "train_agent2_reader.reader_policy.get_client", side_effect=AssertionError("No Gemini")) as api:
            path = self.fixture(Path(tmp), scan=True)
            result = ReaderAgent().process_page(str(path))
            self.assertTrue(result["success"])
            self.assertEqual(result["final_tool"], "ocr_fallback")
            self.assertEqual(result["attempts"][0]["api_attempts"], [])
            self.assertEqual(result["attempts"][0]["validation_mode"], "local_extraction_guards")
            ocr.assert_called_once()
            api.assert_not_called()

    def test_empty_or_failed_parser_falls_back_once_to_ocr(self):
        for failed in (False, True):
            with self.subTest(failed=failed), tempfile.TemporaryDirectory() as tmp, patch(
                    "train_agent2_reader.reader_agent.extract_with_pymupdf",
                    **({"side_effect": RuntimeError("private url")} if failed else {"return_value": []})), patch(
                    "train_agent2_reader.reader_agent.extract_with_ocr", return_value=[self.block()]) as ocr:
                result = ReaderAgent().process_page(str(self.fixture(Path(tmp))))
                self.assertTrue(result["success"])
                self.assertEqual(len(result["attempts"]), 2)
                self.assertNotIn("private url", str(result))
                ocr.assert_called_once()

    def test_bad_ocr_never_publishes_blocks_or_calls_cloud(self):
        for blocks in ([], [replace(self.block(), confidence=.01)],
                       [replace(self.block(), confidence=float("nan"))],
                       [replace(self.block(), bbox=[0, 0, float("inf"), 30])],
                       [replace(self.block(), bbox=[0, 0, 90000, 30])]):
            with self.subTest(blocks=blocks), tempfile.TemporaryDirectory() as tmp, patch(
                    "train_agent2_reader.reader_agent.extract_with_ocr", return_value=blocks), patch(
                    "train_agent2_reader.reader_policy.get_client") as api:
                result = ReaderAgent().process_page(str(self.fixture(Path(tmp), scan=True)))
                self.assertFalse(result["success"])
                self.assertEqual(result["blocks"], [])
                self.assertEqual(len(result["attempts"]), 1)
                api.assert_not_called()

    def test_missing_ocr_binary_is_an_explicit_batch_failure(self):
        import pytesseract
        with tempfile.TemporaryDirectory() as tmp, patch(
                "train_agent2_reader.tools.tool_ocr_fallback.pytesseract.image_to_data",
                side_effect=pytesseract.TesseractNotFoundError()), patch(
                "train_agent2_reader.reader_policy.get_client") as api:
            path = self.fixture(Path(tmp), scan=True)
            with self.assertRaises(ReaderBatchError) as caught:
                PdfReader().read(str(path))
            diagnostics = caught.exception.diagnostics
            trial = diagnostics["page_trials"][0]
            self.assertFalse(trial["accepted"])
            self.assertEqual(trial["attempts"][0]["error_type"], "TesseractNotFoundError")
            api.assert_not_called()

    def test_ocr_groups_words_into_citable_paragraph_and_preserves_coordinates(self):
        from train_agent2_reader.tools.tool_ocr_fallback import extract_with_ocr
        data = {"text": ["", "Sample", "contains", "275", "documents."],
                "conf": [-1, 96, 96, 96, 96], "left": [0, 10, 50, 110, 140],
                "top": [0, 20, 20, 20, 20], "width": [0, 35, 55, 25, 65],
                "height": [0, 15, 15, 15, 15], "block_num": [0, 1, 1, 1, 1],
                "par_num": [0, 1, 1, 1, 1]}
        with tempfile.TemporaryDirectory() as tmp, patch(
                "train_agent2_reader.tools.tool_ocr_fallback.pytesseract.image_to_data", return_value=data) as ocr:
            blocks = extract_with_ocr(str(self.fixture(Path(tmp), scan=True)), dpi=72)
            self.assertEqual(len(blocks), 1)
            self.assertEqual(blocks[0].text, "Sample contains 275 documents.")
            self.assertEqual(blocks[0].bbox, [10, 20, 205, 35])
            self.assertAlmostEqual(blocks[0].confidence, .96)
            self.assertEqual(ocr.call_args.kwargs["timeout"], 60)


if __name__ == "__main__":
    unittest.main()
