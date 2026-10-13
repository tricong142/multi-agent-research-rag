"""Frozen expanded-regression wiring/gates, tested without inference or network."""
from contextlib import contextmanager, redirect_stdout
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from research_rag.evaluation import compare_blind_verifier as d
from research_rag.tests.test_blind_verifier import Backend, valid


CRITERIA = d.CRITERIA.with_name('blind_verifier_scope_regression_criteria.json')


def fixture():
    criteria = json.loads(CRITERIA.read_text())
    original, cases, _ = d.load_cases(CRITERIA, criteria)
    return criteria, original, cases


def correct_outputs(cases):
    return [{'example_id': r['example_id'], 'status': 'ok', 'verification': valid(r['label'], r['context']),
             'attempts': [{'attempt': 1, 'ok': True}], 'elapsed_ms': 0} for r in cases]


class ScopeRegressionTests(unittest.TestCase):
    def test_frozen_cases_are_balanced_contrasts_and_not_embedded_in_prompt(self):
        criteria, original, cases = fixture()
        self.assertEqual((len(original), len(cases)), (12, 39))
        extra = cases[12:]
        self.assertEqual(len({r['family'] for r in extra}), 9)
        labels = {'support', 'contradict', 'not_enough_info'}
        for family in {r['family'] for r in extra}:
            self.assertEqual({r['label'] for r in extra if r['family'] == family}, labels)
        for label in labels:
            self.assertEqual(sum(r['label'] == label for r in cases), 13)
        for row in cases:
            self.assertNotIn(row['claim'], d.verifier.SCOPE_SYSTEM_PROMPT)
            self.assertNotIn(row['context'], d.verifier.SCOPE_SYSTEM_PROMPT)
        self.assertEqual(criteria['prompt_sha256'], hashlib.sha256(d.verifier.SCOPE_SYSTEM_PROMPT.encode()).hexdigest())

    def test_all_wrong_alternatives_catch_third_label_error(self):
        criteria, _, cases = fixture()
        outputs = correct_outputs(cases)
        index = next(i for i, r in enumerate(cases) if r['example_id'] == 'contract:scope')
        outputs[index]['verification'] = valid('not_enough_info', cases[index]['context'])
        metrics, comparisons = d.score(outputs, cases, criteria)
        self.assertEqual(metrics['correct_labels_recognized'], 38)
        self.assertEqual(metrics['wrong_label_agreements'], 1)
        self.assertEqual(metrics['wrong_alternatives_tested'], 78)
        self.assertEqual(len(comparisons), 117)
        self.assertEqual(metrics['dataset_groups']['original_contracts']['correct_labels'], 11)
        self.assertEqual(metrics['dataset_groups']['scope_regression']['correct_labels'], 27)
        self.assertFalse(metrics['automated_gate_pass'])
        old_policy = {**criteria, 'comparison_policy': 'selected_wrong_label'}
        self.assertEqual(d.score(outputs, cases, old_policy)[0]['wrong_label_agreements'], 0)

    def test_always_abstaining_or_always_supporting_fails_even_without_runtime_errors(self):
        criteria, _, cases = fixture()
        for label in ('not_enough_info', 'support'):
            outputs = correct_outputs(cases)
            for output, row in zip(outputs, cases):
                output['verification'] = valid(label, row['context'])
            metrics, _ = d.score(outputs, cases, criteria)
            self.assertEqual(metrics['correct_labels_recognized'], 13)
            self.assertFalse(metrics['automated_gate_pass'])
            self.assertEqual(metrics['false_support'], 26 if label == 'support' else 0)

    def test_missing_failed_duplicate_and_overbudget_rows_cannot_pass(self):
        criteria, _, cases = fixture()
        outputs = correct_outputs(cases)
        self.assertTrue(d.score(outputs, cases, criteria)[0]['automated_gate_pass'])
        self.assertFalse(d.score(outputs[:-1], cases, criteria)[0]['automated_gate_pass'])
        self.assertFalse(d.score(outputs[:-1] + [outputs[0]], cases, criteria)[0]['automated_gate_pass'])
        failed = copy.deepcopy(outputs)
        failed[-1].update(status='verification_failed', verification=None)
        metrics, _ = d.score(failed, cases, criteria)
        self.assertEqual(metrics['classification']['n'], 39)
        self.assertLess(metrics['classification']['accuracy'], 1)
        self.assertEqual(metrics['runtime_failed_rows'], 1)
        self.assertFalse(metrics['automated_gate_pass'])
        outputs[-1]['attempts'] *= 3
        self.assertFalse(d.score(outputs, cases, criteria)[0]['checks']['attempt_budget'])

    def test_tampered_inputs_prompt_or_budget_are_rejected_before_model_loading(self):
        for mode in ('prompt', 'extra', 'historical', 'duplicate', 'group', 'budget', 'path'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temp:
                folder = Path(temp)
                criteria = json.loads(CRITERIA.read_text())
                for name in ('factchecker_contract_cases.jsonl', 'blind_verifier_repair_baseline.json',
                             criteria['supplemental_cases_file'], criteria['historical_verifier_file']):
                    (folder / name).write_bytes(CRITERIA.with_name(name).read_bytes())
                if mode == 'prompt':
                    criteria['prompt_sha256'] = 'incorrect'
                elif mode in ('extra', 'historical'):
                    name = criteria['supplemental_cases_file'] if mode == 'extra' else criteria['historical_verifier_file']
                    with (folder / name).open('ab') as handle:
                        handle.write(b'\n')
                elif mode in ('duplicate', 'group'):
                    path = folder / criteria['supplemental_cases_file']
                    rows = [json.loads(line) for line in path.read_text().splitlines()]
                    if mode == 'duplicate':
                        rows[1]['example_id'] = rows[0]['example_id']
                    else:
                        rows[0]['dataset_group'] = 'incorrect_group'
                    path.write_bytes(''.join(json.dumps(r) + '\n' for r in rows).encode())
                    criteria['supplemental_cases_sha256'] = d.sha256(path)
                elif mode == 'budget':
                    criteria['maximum_total_backend_calls'] = 77
                else:
                    criteria['supplemental_cases_file'] = '../outside.jsonl'
                path = folder / 'criteria.json'
                path.write_text(json.dumps(criteria))
                loader = Mock()
                with self.assertRaises(ValueError):
                    d.run_experiment(folder / 'run', loader, criteria_path=path)
                loader.assert_not_called()
                self.assertFalse((folder / 'run').exists())

    def test_full_experiment_preserves_baselines_and_groups_without_label_leakage(self):
        criteria, _, cases = fixture()
        historical = json.loads(CRITERIA.with_name(criteria['historical_verifier_file']).read_text())
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'run'
            backend = Backend([valid(r['label'], r['context']) for r in cases])
            loads = []
            @contextmanager
            def loader(kind, frozen):
                loads.append(kind)
                self.assertEqual(frozen['cases_per_backend'], 39)
                self.assertTrue((out / 'criteria.json').exists())
                self.assertTrue((out / 'scope_regression.jsonl').exists())
                self.assertTrue((out / 'historical-verifier-metrics.json').exists())
                yield backend, copy.deepcopy(historical['model_metadata'])
            with redirect_stdout(io.StringIO()):
                summary = d.run_experiment(out, loader, criteria_path=CRITERIA)
            self.assertEqual(loads, ['base_instruct'])
            self.assertEqual((summary['prediction_count'], summary['backend_calls']), (39, 39))
            self.assertTrue(summary['automated_gate_pass'])
            self.assertFalse(summary['overall_pass'])
            self.assertFalse(summary['promoted_to_serving'])
            self.assertEqual(json.loads((out / 'historical-verifier-metrics.json').read_text())['correct_labels_recognized'], 11)
            self.assertEqual(json.loads((out / 'historical-verifier-metrics.json').read_text())['wrong_label_agreements'], 1)
            metrics = json.loads((out / 'metrics.json').read_text())['base_instruct']
            self.assertEqual(metrics['dataset_groups']['original_contracts']['correct_labels'], 12)
            self.assertEqual(metrics['dataset_groups']['scope_regression']['correct_labels'], 27)
            self.assertEqual(metrics['classification']['macro_f1'], 1)
            self.assertEqual(len(json.loads((out / 'base_instruct-comparisons.json').read_text())), 117)
            for (messages, _), row in zip(backend.calls, cases):
                self.assertEqual(json.loads(messages[1]['content']), {'claim': row['claim'], 'context': row['context']})
            reviews = [json.loads(line) for line in (out / 'evidence-review.jsonl').read_text().splitlines()]
            self.assertEqual(len(reviews), 39)
            self.assertTrue(all(r['review_status'] == 'pending' for r in reviews))
            with self.assertRaises(FileExistsError):
                d.run_experiment(out, loader, criteria_path=CRITERIA)

    def test_changed_historical_pairing_blocks_new_calls_and_preserves_provenance(self):
        criteria, _, cases = fixture()
        historical = json.loads(CRITERIA.with_name(criteria['historical_verifier_file']).read_text())
        metadata = copy.deepcopy(historical['model_metadata'])
        metadata['revision'] = 'different-revision'
        backend = Backend([valid(r['label'], r['context']) for r in cases])
        @contextmanager
        def loader(kind, frozen):
            yield backend, metadata
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'run'
            with self.assertRaisesRegex(ValueError, 'Historical verifier artifacts'):
                d.run_experiment(out, loader, criteria_path=CRITERIA)
            self.assertEqual(backend.calls, [])
            provenance = json.loads((out / 'provenance.json').read_text())
            self.assertFalse(provenance['historical_verifier_pairing']['revision'])


if __name__ == '__main__':
    unittest.main()
