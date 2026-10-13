"""Bad labels and failed PDFs must not appear as successful evaluation."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from research_rag.evaluate import confidence_metrics
from research_rag.evaluation.reader_smoke import score


class EvaluationContractTests(unittest.TestCase):
    def test_calibration_rejects_unknown_labels_and_failed_runtime(self):
        valid = {"gold_label": "support", "predicted_label": "support", "confidence_score": 0.9}
        for update in ({"gold_label": "made_up"}, {"predicted_label": "made_up"},
                       {"status": "confidence_failed"}, {"gold_label": None}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                confidence_metrics([valid | update])

    def test_label_confidence_is_distinct_from_supported_claim_precision(self):
        rows = [
            {"gold_label": "contradict", "predicted_label": "contradict", "confidence_score": 0.9},
            {"gold_label": "support", "predicted_label": "support", "confidence_score": 0.9},
            {"gold_label": "not_enough_info", "predicted_label": "support", "confidence_score": 0.8},
            {"gold_label": "support", "predicted_label": "support", "confidence_score": 0.4},
        ]
        result = confidence_metrics(rows, bins=2)
        self.assertEqual(result["support_at_threshold"]["accepted"], 2)
        self.assertEqual(result["support_at_threshold"]["false_support"], 1)
        self.assertEqual(result["support_at_threshold"]["precision"], 0.5)
        self.assertEqual(result["per_predicted_label"]["contradict"]["accuracy"], 1.0)
        self.assertEqual(sum(bucket["n"] for bucket in result["reliability_bins"]), 4)
        self.assertIsNone(confidence_metrics(rows[:1])["support_at_threshold"]["precision"])

    def test_partial_reader_failure_keeps_total_coverage_visible(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "exists.pdf").touch()
            rows = [{"pdf_path": filename, "expected_spans": [{"page_no": 0, "text": "Known span"}]}
                    for filename in ("exists.pdf", "missing.pdf")]
            manifest = root / "manifest.jsonl"
            manifest.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
            reader = Mock()
            reader.read.return_value = [{"text": "Known span", "metadata": {"page_no": 0}}]
            result = score(manifest, reader)
            self.assertEqual(result["expected_span_count"], 2)
            self.assertEqual(result["span_count"], 1)
            self.assertEqual(result["span_coverage"], 0.5)
            self.assertEqual(result["overall_exact_span_rate"], 0.5)
            self.assertEqual(result["exact_span_rate"], 1.0)  # conditional on PDFs that could be read


if __name__ == "__main__":
    unittest.main()
