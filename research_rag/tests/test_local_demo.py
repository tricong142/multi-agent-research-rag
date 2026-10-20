"""Diagnostic reporting must not turn a replay or a failed worker into model proof."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from research_rag.evaluation import local_demo as d


class LocalDemoTests(unittest.TestCase):
    def test_outputs_cannot_overwrite_an_earlier_run(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'metrics.json'
            d.save_json(path, {'accuracy': .5})
            before = path.read_bytes()
            with self.assertRaises(FileExistsError):
                d.save_json(path, {'accuracy': 1})
            self.assertEqual(path.read_bytes(), before)

    def test_successful_exit_without_metrics_is_a_failed_stage(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(d.subprocess, 'run') as run:
            run.return_value.returncode = 0
            result = d.run_stage('metrics', 'summarizer', Path(folder), 10)
            self.assertEqual(result['state'], 'failed')
            self.assertIsNone(result['result'])

    def test_timeout_is_not_reported_as_completed(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(d.subprocess, 'run') as run:
            run.side_effect = subprocess.TimeoutExpired('test command', 10)
            result = d.run_stage('tests', 'reader', Path(folder), 10)
            self.assertEqual(result['state'], 'timed_out')
            self.assertEqual(result['exit_code'], 124)

    def test_html_exposes_replay_source_and_escapes_content(self):
        stage = {'state': 'completed', 'result': {'execution_mode': 'stored_prediction_scoring <script>',
                                                'accuracy': .5}}
        summary = {'run_id': '<script>alert(1)</script>', 'agents': {'factchecker': {
            'tests': {'state': 'completed', 'result': {'passed': 2, 'tests_run': 2}},
            'metrics': stage, 'model_status': 'Chua chay model'}}}
        report = d.render_report(summary)
        self.assertNotIn('<script>', report)
        self.assertIn('stored_prediction_scoring', report)
        self.assertIn('Chưa xác nhận cả năm model', report)
        self.assertIn('Chua chay model', report)


if __name__ == '__main__':
    unittest.main()
