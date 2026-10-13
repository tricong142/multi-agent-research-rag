"""Conservative screening and offline runner; no inference or network."""
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research_rag.evaluation import compare_blind_verifier as d
from research_rag.evaluation import screen_blind_verifier as offline
from research_rag.tests.test_blind_verifier import valid
from research_rag.tests.test_blind_verifier_regression import fixture, correct_outputs


s = importlib.import_module('04_factchecker.inference.evidence_screen')
v = d.verifier


def screen(claim, context, quotes=None, label='support'):
    return s.screen_support(claim, context, v.validate_verification(
        {**valid(label, context), 'evidence_quotes': quotes or [context]}, context))


class EvidenceScreenTests(unittest.TestCase):
    def test_missing_quantity_and_conjunct_are_flagged_without_assigning_new_label(self):
        context = 'Model Zeta uses 18% less memory than the baseline.'
        result = screen('Model Zeta uses 18% less memory and retains 96% accuracy.', context)
        self.assertEqual(result['status'], 'review_required')
        self.assertEqual({f['code'] for f in result['flags']}, {'claim_quantity_not_quoted', 'conjunct_lexical_gap'})
        self.assertFalse(result['claim_verified'])
        self.assertNotIn('assessed_label', result)
        complete = context + ' Model Zeta retains 96% accuracy.'
        self.assertEqual(screen('Model Zeta uses 18% less memory and retains 96% accuracy.', complete)['status'], 'screen_clear')

    def test_multisentence_quantity_coverage_and_unnumbered_conjunct(self):
        context = 'Six models were tested. Evaluation used three datasets.'
        claim = 'The evaluation tested six models on three datasets.'
        self.assertEqual(screen(claim, context, ['Six models were tested.'])['status'], 'review_required')
        self.assertEqual(screen(claim, context, ['Six models were tested.', 'Evaluation used three datasets.'])['status'], 'screen_clear')
        result = screen('Tuning decreased memory and increased recall.', 'Tuning reduced memory use.')
        self.assertIn('conjunct_lexical_gap', {r['code'] for r in result['flags']})

    def test_numeric_direction_uses_decimal_values_for_both_directions_and_equality(self):
        for before, after, verb, observed, conflict in (
                ('70', '52', 'reduced', 'decrease', False), ('70', '88', 'reduced', 'increase', True),
                ('-0.8', '-0.3', 'increased', 'increase', False), ('0.81', '0.74', 'increased', 'decrease', True),
                ('1,200', '900', 'reduced', 'decrease', False), ('15', '15', 'left unchanged', 'unchanged', False),
                ('15', '15', 'reduced', 'unchanged', True)):
            with self.subTest(before=before, after=after, verb=verb):
                context = f'Under matching conditions, median latency was {before} milliseconds before the update and {after} milliseconds after it.'
                result = screen(f'The update {verb} median latency.', context)
                self.assertEqual(result['numeric_checks'][0]['observed_direction'], observed)
                self.assertEqual(any(f['code'] == 'numeric_direction_conflict' for f in result['flags']), conflict)
                self.assertFalse(result['claim_verified'])

    def test_numeric_units_scope_negation_and_multiple_measurements_are_not_inferred(self):
        prefix = 'Median latency was 10 milliseconds before the update and 20'
        result = screen('The update reduced median latency.', prefix + ' seconds after it.')
        self.assertIn('numeric_units_require_review', {f['code'] for f in result['flags']})
        result = screen('The patch reduced median latency.', prefix + ' milliseconds after it.')
        self.assertIn('numeric_scope_requires_review', {f['code'] for f in result['flags']})
        context = prefix + ' milliseconds after it.'
        for claim in ('The update did not reduce median latency.', 'Some updates reduced median latency.'):
            self.assertEqual(screen(claim, context)['numeric_checks'], [])
        self.assertEqual(screen('The update reduced median latency.', context + ' ' + context)['numeric_checks'], [])

    def test_number_formats_existential_threshold_and_known_heuristic_limits(self):
        self.assertEqual(s.quantities('18% and 0.94 and 1,200.'),
                         {(s.Decimal('18'), 'percent'), (s.Decimal('0.94'), 'number'), (s.Decimal('1200'), 'number')})
        result = screen('At least one sampled server improved.', 'The sampled server Hazel improved.')
        self.assertEqual(result['status'], 'screen_clear')
        # Presence is not entailment; a semantic reviewer must inspect this clear screen.
        result = screen('Accuracy is 96%.', 'Accuracy is 80%, not 96%.')
        self.assertEqual(result['status'], 'screen_clear')
        self.assertFalse(result['claim_verified'])
        result = screen('Tuning reduced storage and increased sensitivity.', 'Tuning reduced storage and increased recall.')
        self.assertEqual(result['status'], 'review_required')  # Synonyms can produce a false positive flag.

    def test_validation_and_non_support_decisions_never_verify_a_claim(self):
        context = 'The sample contained 20 records.'
        for label in ('contradict', 'not_enough_info'):
            result = screen('The sample contained 40 records.', context, label=label)
            self.assertEqual(result['status'], 'not_support')
            self.assertFalse(result['claim_verified'])
        with self.assertRaises(ValueError):
            s.screen_support('', context, v.validate_verification(valid('support', context), context))
        with self.assertRaises(ValueError):
            s.screen_support('Claim', context, None)
        fabricated = v.Verification('support', ('Invented quotation',), (), 'Invalid fixture')
        with self.assertRaises(ValueError):
            s.screen_support('Claim', context, fabricated)


class OfflineScreenTests(unittest.TestCase):
    def make_run(self, root):
        criteria, _, cases = fixture()
        predictions = correct_outputs(cases)
        predictions[0]['verification'] = valid('support', cases[0]['context'])
        folder = root / 'original'
        source = folder / 'blind-verifier'
        source.mkdir(parents=True)
        for name, value in (('cases.json', cases), ('criteria.json', criteria),
                            ('metrics.json', {'base_instruct': d.score(predictions, cases, criteria)[0]})):
            (source / name).write_text(json.dumps(value), encoding='utf-8')
        (source / 'base_instruct.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in predictions), encoding='utf-8')
        files = [{'path': p.relative_to(folder).as_posix(), 'size': p.stat().st_size, 'sha256': d.sha256(p)}
                 for p in source.iterdir()]
        (folder / 'output-manifest.json').write_text(json.dumps({'files': files}), encoding='utf-8')
        return folder

    def test_offline_run_does_not_pass_release_or_leak_gold_into_screen(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); original = self.make_run(root); before = d.sha256(original / 'output-manifest.json')
            with patch.object(offline.screen, 'screen_support', wraps=s.screen_support) as observed:
                result = offline.run_screen(original, root / 'screen')
            self.assertEqual(len(observed.call_args_list), 39)
            for args, kwargs in observed.call_args_list:
                self.assertEqual(len(args), 3)
                self.assertIsInstance(args[0], str)
                self.assertIsInstance(args[1], str)
                self.assertIsInstance(args[2], v.Verification)
                self.assertEqual(kwargs, {})
            self.assertEqual(result['false_support_flagged'], 1)
            self.assertEqual(result['false_support_remaining_after_screen'], 0)
            self.assertEqual(result['model_calls'], 0)
            self.assertFalse(result['overall_pass'])
            self.assertFalse(result['promoted_to_serving'])
            self.assertFalse(result['original_automated_gate_pass'])
            self.assertEqual(d.sha256(original / 'output-manifest.json'), before)
            self.assertEqual(len((root / 'screen/screen-review.jsonl').read_text().splitlines()), 39)
            with self.assertRaises(FileExistsError):
                offline.run_screen(original, root / 'screen')
            with self.assertRaises(ValueError):
                offline.run_screen(original, original / 'screen')

    def test_tampered_artifact_or_mismatched_predictions_block_output(self):
        for mode in ('artifact', 'predictions', 'metrics', 'path'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); original = self.make_run(root); source = original / 'blind-verifier'
                manifest = json.loads((original / 'output-manifest.json').read_text())
                if mode == 'path':
                    manifest['files'][0]['path'] = '../outside'
                elif mode in ('artifact', 'metrics'):
                    p = source / 'metrics.json'
                    p.write_text('{}')
                else:
                    p = source / 'base_instruct.jsonl'
                    rows = p.read_text().splitlines();rows[1] = rows[0];p.write_text('\n'.join(rows))
                if mode in ('metrics', 'predictions'):
                    for r in manifest['files']:
                        p = original / r['path'];r.update(size=p.stat().st_size, sha256=d.sha256(p))
                (original / 'output-manifest.json').write_text(json.dumps(manifest))
                with self.assertRaises((ValueError, KeyError)):
                    offline.run_screen(original, root / 'screen')
                self.assertFalse((root / 'screen').exists())


if __name__ == '__main__':
    unittest.main()
