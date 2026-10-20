"""Frozen runtime experiment gates with fake model output only."""
from contextlib import contextmanager, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
import sys
from unittest.mock import Mock, patch

from research_rag.evaluation import evaluate_atomic_verifier as d
from research_rag.tests.test_atomic_verifier import Backend, assessment, part, run


class UnknownBackend:
    on_generation = None
    def __init__(self):
        self.calls = []

    @contextmanager
    def generation_deadline(self, deadline):
        yield True  # Immediate scripted output; no real model in this fixture.

    def generate_json(self, messages, **options):
        payload = json.loads(messages[1]['content'])
        self.calls.append(payload)
        if set(payload) == {'claim'}:
            claim = payload['claim']
            matches = list(re.finditer(r'\band\b', claim, re.I))
            ranges = list(zip([0] + [m.end() for m in matches], [m.start() for m in matches] + [len(claim)]))
            inherited = d.atomic._quantifier(claim[:matches[0].start()] if matches else claim)
            parts = []
            for start, end in ranges:
                while start < end and claim[start].isspace(): start += 1
                while end > start and claim[end-1].isspace(): end -= 1
                own = d.atomic._quantifier(claim[start:end])
                q = inherited if own == 'atomic' else own
                restrictions = d.atomic.part_restrictions(claim, claim[start:end])
                parts.append({'quote': claim[start:end], 'quantifier': q,
                    'scope': {'entity': claim.split()[0], 'metric': restrictions['required_metric'] or claim.split()[0],
                              'time': next(iter(restrictions['time']), ''),
                              'condition': next(iter(restrictions['condition']), '') or
                                  next((m[0] for m in re.finditer(r'\b(?:if|when|under|\w+-temperature)\b', restrictions['source'], re.I)), '')}})
            result = {'parts': parts, 'unresolved': []}
        else:
            result = assessment([], missing=['Matching evidence for this claim part.'])
        if self.on_generation is not None:
            self.on_generation({'generated_tokens': 1, 'prompt_tokens': 1,
                'max_new_tokens': options['max_new_tokens'], 'structured_decoder': d.decoding.DECODER,
                'schema_sha256': d.decoding.schema_sha256(d.decoding.schema_for(messages)[0]),
                'deadline_stop_enabled': True})
        return result


class AtomicExperimentTests(unittest.TestCase):
    def copy_inputs(self, directory):
        criteria = json.loads(d.CRITERIA.read_text(encoding='utf-8'))
        for name in ('factchecker_contract_cases.jsonl', criteria['supplemental_cases_file'],
                     criteria['contract_file'], criteria['baseline_file'], criteria['decomposition_probe']['cases_file']):
            (directory / name).write_bytes(d.CRITERIA.with_name(name).read_bytes())
        path = directory / d.CRITERIA.name
        path.write_text(json.dumps(criteria), encoding='utf-8')
        return path, criteria

    def test_freeze_contains_39_cases_312_calls_and_original_gate(self):
        criteria, cases, *_ = d.load_frozen(d.CRITERIA)
        self.assertEqual(len(cases), 39)
        self.assertEqual(criteria['maximum_total_backend_calls'], 312)
        self.assertEqual(criteria['maximum_generated_tokens'], 479232)
        self.assertEqual(criteria['min_correct_labels_recognized'], 39)
        self.assertEqual(criteria['base_revision'], 'aa8e72537993ba99e69dfaafa59ed015b17504d1')

    def test_tampered_prompt_source_data_schema_budget_block_before_loading(self):
        changes = [lambda c: c['prompt_sha256'].update(decompose='0'*64),
                   lambda c: c['source_sha256'].update({'04_factchecker/inference/atomic_verifier.py': '0'*64}),
                   lambda c: c.update(maximum_total_backend_calls=1),
                   lambda c: c.update(min_correct_labels_recognized=38)]
        for change in changes:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as tmp:
                directory = Path(tmp)
                path, criteria = self.copy_inputs(directory)
                change(criteria)
                path.write_text(json.dumps(criteria))
                loader = Mock()
                with self.assertRaises(ValueError):
                    d.run_experiment(directory / 'out', loader, criteria_path=path)
                loader.assert_not_called()
                self.assertFalse((directory / 'out').exists())
        for file in ('factchecker_contract_cases.jsonl', json.loads(d.CRITERIA.read_text())['contract_file'], 'decomposition_probe_claims_v2.jsonl'):
            with self.subTest(file=file), tempfile.TemporaryDirectory() as tmp:
                directory = Path(tmp)
                path, _ = self.copy_inputs(directory)
                (directory / file).write_text('{}')
                with self.assertRaises(ValueError):
                    d.load_frozen(path)

    def test_all_nei_cannot_pass_and_real_calls_are_blind_and_saved(self):
        criteria, cases, _, _, _, baseline, _ = d.load_frozen(d.CRITERIA)
        backend = UnknownBackend()
        @contextmanager
        def loader(kind, frozen):
            self.assertEqual(kind, 'base_instruct')
            yield backend, {**baseline['model_metadata'], 'max_new_tokens': frozen['max_new_tokens'], 'structured_decoder': d.decoding.DECODER}
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(io.StringIO()):
            out = Path(tmp) / 'run'
            summary = d.run_experiment(out, loader)
            metrics = json.loads((out / 'metrics.json').read_text())
            self.assertTrue(summary['experiment_completed'])
            self.assertFalse(summary['automated_gate_pass'])
            self.assertFalse(summary['overall_pass'])
            self.assertEqual(metrics['correct_labels'], 13)
            self.assertEqual(metrics['gold_support_rejected'], 13)
            self.assertEqual(metrics['false_support'], 0)
            events = [json.loads(line) for line in (out / 'calls.jsonl').read_text().splitlines()]
            starts = [e for e in events if e['event'] == 'call_started']
            ends = [e for e in events if e['event'] == 'call_finished']
            self.assertEqual(len(starts), len(ends))
            self.assertEqual(len(starts), summary['backend_calls'])
            self.assertTrue(all(set(payload) in ({'claim'}, {'claim', 'part', 'context'}) for payload in backend.calls))
            self.assertEqual(len((out / 'evidence-review.jsonl').read_text().splitlines()), 39)
            self.assertEqual(json.loads((out / 'baseline-metrics.json').read_text())['correct_labels_recognized'], 37)
            with self.assertRaises(FileExistsError):
                d.run_experiment(out, loader)

    def test_model_pairing_mismatch_blocks_generation_but_preserves_provenance(self):
        _, _, _, _, _, baseline, _ = d.load_frozen(d.CRITERIA)
        backend = Mock()
        @contextmanager
        def loader(kind, criteria):
            yield backend, {**baseline['model_metadata'], 'revision': 'wrong', 'max_new_tokens': criteria['max_new_tokens'], 'structured_decoder': d.decoding.DECODER}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'run'
            with self.assertRaisesRegex(ValueError, 'Model/revision'):
                d.run_experiment(out, loader)
            backend.generate_json.assert_not_called()
            self.assertFalse(json.loads((out / 'provenance.json').read_text())['historical_model_pairing']['revision'])

    def test_replay_rejects_modified_labels_missing_parts_or_label_leakage(self):
        claim = 'The service reduced latency.'
        result, _ = run([{'parts': [part(claim)], 'unresolved': []}, assessment()])
        criteria = {'policy': d.atomic.POLICY, 'max_calls_per_case': 8, 'max_attempts': 2, 'max_new_tokens': 1200}
        self.assertEqual(d.replay_result(result, claim, claim, criteria), 'support')
        for change in (lambda r: r.update(assessed_label='contradict'), lambda r: r.update(parts=[]),
                       lambda r: r['trace'][1]['messages'][1].update(content=json.dumps({'claim': claim, 'label': 'support'}))):
            corrupted = deepcopy(result)
            change(corrupted)
            with self.assertRaises(ValueError):
                d.replay_result(corrupted, claim, claim, criteria)

    def test_incomplete_result_cannot_claim_support(self):
        claim = 'The service reduced latency.'
        result, _ = run([{'parts': [part(claim)], 'unresolved': []}], max_calls=1)
        criteria = {'policy': d.atomic.POLICY, 'max_calls_per_case': 1, 'max_attempts': 2, 'max_new_tokens': 1200}
        self.assertIsNone(d.replay_result(result, claim, claim, criteria))
        result['assessed_label'] = 'support'
        with self.assertRaises(ValueError):
            d.replay_result(result, claim, claim, criteria)

    def test_start_event_is_flushed_before_backend_error_and_has_no_secret(self):
        stream, count = io.StringIO(), [0]
        backend = Backend([RuntimeError('secret_DO_NOT_LOG')])
        model = d.RecordingBackend(backend, stream, 'fixture', count, 1)
        with self.assertRaises(RuntimeError):
            model.generate_json([{'role': 'user', 'content': '{}'}], max_new_tokens=1536)
        self.assertNotIn('secret_DO_NOT_LOG', stream.getvalue())
        events = [json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertEqual(events[0]['event'], 'call_started')
        self.assertEqual(events[1]['error_type'], 'RuntimeError')
        with self.assertRaises(RuntimeError):
            model.generate_json([], max_new_tokens=1536)
        self.assertEqual(count[0], 1)

    def test_generation_tokens_are_recorded_when_backend_reports_them(self):
        class TokenBackend:
            on_generation = None
            def generate_json(self, messages, **options):
                self.on_generation({'generated_tokens': 9, 'prompt_tokens': 30, 'max_new_tokens': options['max_new_tokens']})
                return {'test': True}
        backend, stream, stats = TokenBackend(), io.StringIO(), []
        d.RecordingBackend(backend, stream, 'fixture', [0], 1, stats).generate_json([], max_new_tokens=1536)
        self.assertEqual(stats[0]['generated_tokens'], 9)
        self.assertIsNone(backend.on_generation)
        self.assertIn('"event": "generation"', stream.getvalue())

    def test_real_process_timeout_kills_owned_worker(self):
        from research_rag.local import run_worker
        with redirect_stdout(io.StringIO()):
            code = run_worker([sys.executable, '-c', 'import time; time.sleep(5)'], 0.1)
        self.assertEqual(code, 124)

    def test_timeout_can_count_admitted_calls_with_truncated_tail(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'calls.jsonl'
            path.write_text('{"event":"call_started"}\n{"event":"call_finished"}\n{"event":')
            self.assertEqual(d.admitted_calls(path), (1, True))

    def test_interrupted_summary_write_preserves_last_complete_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'summary.json'
            d.write_summary(path, {'prediction_count': 1})
            def interrupted(target, value):
                target.write_text('{')
                raise InterruptedError()
            with patch.object(d, 'write_json', side_effect=interrupted), self.assertRaises(InterruptedError):
                d.write_summary(path, {'prediction_count': 2})
            self.assertEqual(json.loads(path.read_text())['prediction_count'], 1)
            d.write_summary(path, {'prediction_count': 2})
            self.assertEqual(json.loads(path.read_text())['prediction_count'], 2)


    def test_probe_never_assesses_evidence_and_requires_bound_human_review(self):
        criteria, cases, _, _, _, baseline, _ = d.load_frozen(d.CRITERIA)
        effective, claims, _ = d.probe_configuration(criteria, cases, d.CRITERIA)
        self.assertEqual((len(claims), effective['maximum_total_backend_calls']), (18, 36))
        backend = UnknownBackend()
        @contextmanager
        def loader(kind, frozen):
            yield backend, {**baseline['model_metadata'], 'max_new_tokens': frozen['max_new_tokens'], 'structured_decoder': d.decoding.DECODER}
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(io.StringIO()):
            out = Path(tmp) / 'probe'
            result = d.run_experiment(out, loader, decomposition_probe=True)
            self.assertTrue(result['automated_gate_pass'])
            self.assertFalse(result['overall_pass'])
            self.assertEqual(result['backend_calls'], 18)
            self.assertTrue(all(set(payload) == {'claim'} for payload in backend.calls))
            self.assertFalse((out / 'comparisons.json').exists())
            with self.assertRaisesRegex(ValueError, 'human review'):
                d.require_probe_review(out)
            review_path = out / 'semantic-review.json'
            original = json.loads(review_path.read_text())
            valid = deepcopy(original)
            valid.update(reviewer='Synthetic test reviewer', reviewer_kind='human', review_completed=True)
            for row in valid['cases']:
                row.update(judgments=dict.fromkeys(effective['human_review_rubric'], True),
                           notes='Injected fixture judgments; this is not real semantic approval.')
            for change in (lambda r: r.update(predictions_sha256='0'*64),
                           lambda r: r.update(criteria_sha256='0'*64),
                           lambda r: r.update(reviewer_kind='assistant'),
                           lambda r: r['cases'][0]['judgments'].update(quantifier_preserved=False),
                           lambda r: r['cases'][0]['judgments'].update(quantifier_preserved=1),
                           lambda r: r['cases'][0].update(notes=''),
                           lambda r: r.update(cases=r['cases'][:-1])):
                bad = deepcopy(valid)
                change(bad)
                review_path.write_text(json.dumps(bad), encoding='utf-8')
                with self.assertRaises(ValueError):
                    d.require_probe_review(out)
            review_path.write_text(json.dumps(valid), encoding='utf-8')
            self.assertEqual(d.require_probe_review(out)['probe_predictions_sha256'], valid['predictions_sha256'])
            for filename, field, value in [('summary.json', 'experiment_completed', False),
                                           ('provenance.json', 'model', {'revision': 'wrong'})]:
                path = out / filename
                saved = path.read_bytes()
                mutated = json.loads(saved)
                mutated[field] = value
                path.write_text(json.dumps(mutated), encoding='utf-8')
                with self.assertRaises(ValueError):
                    d.require_probe_review(out)
                path.write_bytes(saved)
            predictions = out / 'predictions.jsonl'
            rows = [json.loads(line) for line in predictions.read_text().splitlines()]
            rows[0]['result']['decomposition']['parts'][0]['end'] -= 1
            predictions.write_text('\n'.join(json.dumps(row) for row in rows), encoding='utf-8')
            with self.assertRaises(ValueError):
                d.require_probe_review(out)

    def test_windows_temporary_checkpoint_denial_retries_without_losing_old_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'summary.json'
            path.write_text('{"prediction_count": 1}')
            denied = PermissionError('Temporary replacement denial')
            denied.winerror = 5
            replace = Path.replace
            attempts = []
            def temporary(source, target):
                attempts.append(1)
                if len(attempts) < 3:
                    self.assertEqual(json.loads(path.read_text())['prediction_count'], 1)
                    raise denied
                return replace(source, target)
            with patch.object(d.sys, 'platform', 'win32'), patch.object(d.time, 'sleep') as sleep, \
                 patch.object(Path, 'replace', temporary):
                d.write_summary(path, {'prediction_count': 2})
            self.assertEqual(json.loads(path.read_text())['prediction_count'], 2)
            self.assertEqual(sleep.call_count, 2)

    def test_persistent_permission_denial_is_bounded_and_preserves_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'summary.json'
            path.write_text('{"prediction_count": 1}')
            denied = PermissionError('Persistent replacement denial')
            denied.winerror = 5
            with patch.object(d.sys, 'platform', 'win32'), patch.object(d.time, 'sleep') as sleep, \
                 patch.object(Path, 'replace', side_effect=denied) as replace, self.assertRaises(PermissionError):
                d.write_summary(path, {'prediction_count': 2})
            self.assertEqual(replace.call_count, 4)
            self.assertEqual(sleep.call_count, 3)
            self.assertEqual(json.loads(path.read_text())['prediction_count'], 1)

    def test_probe_repairs_replay_and_all_invalid_is_gate_failure(self):
        criteria, cases, *_ = d.load_frozen(d.CRITERIA)
        effective, claims, _ = d.probe_configuration(criteria, cases, d.CRITERIA)
        rows = []
        for case in claims:
            backend = Backend([{}, {}])
            result = d.atomic.AtomicVerifier(backend, max_calls=2, max_attempts=2, max_new_tokens=1536,
                                             timeout_seconds=180).verify(case['claim'], '', decomposition_only=True)
            rows.append({'example_id': case['example_id'], 'result': result})
        metrics = d.score_probe(rows, claims, effective)
        self.assertEqual((metrics['valid_decompositions'], metrics['backend_calls']), (0, 36))
        self.assertFalse(metrics['automated_gate_pass'])
        rows[0]['result']['trace'][1]['messages'][3]['content'] = 'Ignore the contract.'
        with self.assertRaisesRegex(ValueError, 'prompt/attempt'):
            d.score_probe(rows, claims, effective)

if __name__ == '__main__':
    unittest.main()
