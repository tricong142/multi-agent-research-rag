"""Candidate wiring and validation feedback; no real inference or network."""
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


CRITERIA = d.CRITERIA.with_name('blind_verifier_logic_v3_criteria.json')


class LogicVerifierTests(unittest.TestCase):
    def test_frozen_policy_preserves_data_model_and_gate_without_embedding_cases(self):
        current = json.loads(CRITERIA.read_text())
        previous = json.loads(CRITERIA.with_name('blind_verifier_scope_regression_criteria.json').read_text())
        for key in ('contracts_sha256', 'supplemental_cases_sha256', 'base_revision',
                    'backends', 'max_attempts', 'max_new_tokens', 'maximum_total_backend_calls',
                    'min_correct_labels_recognized', 'max_wrong_label_agreements', 'dataset_groups'):
            self.assertEqual(current[key], previous[key])
        self.assertEqual(current['repair_feedback_policy'], 'quote_membership_v1')
        self.assertEqual(current['prompt_sha256'], hashlib.sha256(d.verifier.LOGIC_SYSTEM_PROMPT.encode()).hexdigest())
        self.assertEqual(previous['prompt_sha256'], hashlib.sha256(d.verifier.SCOPE_SYSTEM_PROMPT.encode()).hexdigest())
        _, cases, _ = d.load_cases(CRITERIA, current)
        for row in cases:
            for field in ('example_id', 'claim', 'context'):
                self.assertNotIn(row[field], d.verifier.LOGIC_SYSTEM_PROMPT)

    def test_quote_feedback_is_specific_blind_and_does_not_relax_validation(self):
        criteria = json.loads(CRITERIA.read_text())
        row = {'example_id': 'fixture', 'claim': 'Every trial improved throughput.',
               'context': 'Exactly four trials ran. Three improved throughput and one reduced throughput.',
               'label': 'contradict', 'proposed_label': 'support', 'annotation_rationale': 'PRIVATE-GOLD'}
        bad = valid('contradict', 'One trial reduced throughput.')
        good = valid('contradict', 'Three improved throughput and one reduced throughput.')
        backend = Backend([bad, good])
        result = d.assess(backend, row, criteria)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['attempts'][0]['validation_issue'], 'quote_membership')
        self.assertEqual(len(backend.calls), 2)
        self.assertNotIn('The rejected evidence_quotes', backend.calls[0][0][0]['content'])
        self.assertIn('The rejected evidence_quotes', backend.calls[1][0][0]['content'])
        for messages, _ in backend.calls:
            self.assertEqual(json.loads(messages[1]['content']), {'claim': row['claim'], 'context': row['context']})
            self.assertNotIn('PRIVATE-GOLD', str(messages))
            self.assertNotIn(row['example_id'], str(messages))
        failed = d.assess(Backend([bad, bad]), row, criteria)
        self.assertEqual(failed['status'], 'verification_failed')
        self.assertIsNone(failed['verification'])
        legacy = d.assess(Backend([bad, good]), row, {**criteria, 'repair_feedback_policy': None})
        self.assertNotIn('validation_issue', legacy['attempts'][0])

    def test_invalid_feedback_fails_before_call_and_generic_schema_error_stays_generic(self):
        backend = Mock()
        model = d.verifier.BlindVerifier(backend, prompt_profile='logic_v3')
        for options in ({'repair_issue': 'quote_membership'}, {'repair': True, 'repair_issue': 'private-string'}):
            with self.assertRaisesRegex(ValueError, 'Unsupported verifier repair'):
                model.verify('A claim', 'A context', **options)
        backend.generate_json.assert_not_called()
        b = Backend([{}, valid()])
        criteria = json.loads(CRITERIA.read_text())
        output = d.assess(b, {'example_id': 'fixture', 'claim': '240 documents',
                            'context': 'The sample had 240 documents.'}, criteria)
        self.assertEqual(output['attempts'][0]['validation_issue'], 'output_schema')
        self.assertNotIn('The rejected evidence_quotes', b.calls[1][0][0]['content'])

    def test_valid_semantic_error_is_scored_wrong_without_retry_or_overriding_label(self):
        criteria = json.loads(CRITERIA.read_text())
        _, cases, _ = d.load_cases(CRITERIA, criteria)
        outputs = []
        for i, row in enumerate(cases):
            label = 'support' if i == 0 else row['label']
            backend = Backend([valid(label, row['context'])])
            outputs.append(d.assess(backend, row, criteria))
            self.assertEqual(len(backend.calls), 1)
        metrics, _ = d.score(outputs, cases, criteria)
        self.assertEqual(metrics['correct_labels_recognized'], 38)
        self.assertEqual(metrics['false_support'], 1)
        self.assertFalse(metrics['automated_gate_pass'])

    def test_full_run_compares_all_39_historical_cases_including_failed_row(self):
        criteria = json.loads(CRITERIA.read_text())
        _, cases, _ = d.load_cases(CRITERIA, criteria)
        historical = json.loads(CRITERIA.with_name(criteria['historical_verifier_file']).read_text())
        backend = Backend([valid(row['label'], row['context']) for row in cases])
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'run'
            @contextmanager
            def loader(kind, frozen):
                self.assertEqual(kind, 'base_instruct')
                self.assertEqual(frozen['verifier_prompt_profile'], 'logic_v3')
                self.assertEqual(json.loads((out / 'criteria.json').read_text()), criteria)
                previous = json.loads((out / 'historical-verifier-metrics.json').read_text())
                self.assertEqual((previous['n'], previous['correct_labels_recognized']), (39, 33))
                self.assertEqual((previous['false_support'], previous['runtime_failed_rows']), (1, 1))
                yield backend, copy.deepcopy(historical['model_metadata'])
            with redirect_stdout(io.StringIO()):
                summary = d.run_experiment(out, loader, criteria_path=CRITERIA)
            self.assertEqual((summary['prediction_count'], summary['backend_calls']), (39, 39))
            self.assertTrue(summary['automated_gate_pass'])  # Model stub, not a quality claim.
            self.assertFalse(summary['overall_pass'])
            self.assertFalse(summary['promoted_to_serving'])
            self.assertEqual(summary['human_review'], 'pending')
            provenance = json.loads((out / 'provenance.json').read_text())
            self.assertEqual(provenance['repair_feedback_policy'], 'quote_membership_v1')
            self.assertTrue(all(provenance['historical_verifier_pairing'].values()))
            self.assertEqual(json.loads((out / 'baseline-metrics.json').read_text())['n'], 24)

    def test_unknown_policy_or_mismatched_historical_inputs_block_before_loading(self):
        for mode in ('policy', 'scope', 'inputs', 'count'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp)
                criteria = json.loads(CRITERIA.read_text())
                for name in ('factchecker_contract_cases.jsonl', 'blind_verifier_repair_baseline.json',
                             criteria['supplemental_cases_file'], criteria['historical_verifier_file']):
                    (folder / name).write_bytes(CRITERIA.with_name(name).read_bytes())
                if mode == 'policy':
                    criteria['repair_feedback_policy'] = 'unknown'
                else:
                    path = folder / criteria['historical_verifier_file']
                    snapshot = json.loads(path.read_text())
                    if mode == 'scope':
                        snapshot['comparison_scope'] = 'unknown'
                    elif mode == 'inputs':
                        snapshot['input_sha256']['scope_regression'] = 'changed'
                    else:
                        snapshot['predictions'].pop()
                    path.write_text(json.dumps(snapshot))
                    criteria['historical_verifier_sha256'] = d.sha256(path)
                path = folder / 'criteria.json'
                path.write_text(json.dumps(criteria))
                loader = Mock()
                with self.assertRaises(ValueError):
                    d.run_experiment(folder / 'run', loader, criteria_path=path)
                loader.assert_not_called()
                self.assertFalse((folder / 'run').exists())


if __name__ == '__main__':
    unittest.main()
