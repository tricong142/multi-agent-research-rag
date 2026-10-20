"""Decomposition regressions with novel claims and a real token filter, no model."""
from copy import deepcopy
import importlib
import json
import unittest

from research_rag.tests.test_atomic_decoding import Sequence, TinyTokenizer, token_backend


a = importlib.import_module('04_factchecker.inference.atomic_verifier')
d = importlib.import_module('04_factchecker.inference.atomic_decoding')


def plan(claim, *, entity, metric, time='', condition='', quantifier='atomic'):
    return {'parts': [{'quote': claim, 'quantifier': quantifier,
                      'scope': {'entity': entity, 'metric': metric,
                                'time': time, 'condition': condition}}], 'unresolved': []}


class DecompositionV5RegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.backend = token_backend()

    def accepts(self, claim, value):
        request = [{'role': 'system', 'content': a.DECOMPOSE_PROMPT},
                   {'role': 'user', 'content': json.dumps({'claim': claim})}]
        callback = self.backend.generation_options(request)['prefix_allowed_tokens_fn']
        ids = Sequence([ord('P')])
        for char in json.dumps(value, separators=(',', ':')):
            if ord(char) not in callback(0, ids):
                return False
            ids.append(ord(char))
        return 0 in callback(0, ids)

    def test_single_predicate_cannot_drop_count_or_split_off_dataset_phrase(self):
        claim = 'The survey evaluated three encoders on five datasets.'
        good = plan(claim, entity='survey', metric='evaluated three encoders',
                    condition='on five datasets')
        self.assertTrue(self.accepts(claim, good))
        a.normalize_decomposition(good, claim)
        truncated = deepcopy(good)
        truncated['parts'][0]['quote'] = 'The survey evaluated three encoders'
        self.assertFalse(self.accepts(claim, truncated))
        fragmented = deepcopy(truncated)
        fragmented['parts'].append({'quote': 'on five datasets.', 'quantifier': 'atomic',
                                   'scope': {'entity': 'datasets', 'metric': 'evaluated',
                                             'time': '', 'condition': 'on five datasets'}})
        self.assertFalse(self.accepts(claim, fragmented))

    def test_single_predicate_cannot_end_before_temporal_suffix(self):
        claim = 'The West relay lowered jitter before maintenance.'
        good = plan(claim, entity='West relay', metric='jitter', time='before maintenance')
        self.assertTrue(self.accepts(claim, good))
        bad = deepcopy(good)
        bad['parts'][0]['quote'] = 'The West relay lowered jitter'
        self.assertFalse(self.accepts(claim, bad))
        with self.assertRaisesRegex(ValueError, 'uncovered_claim_content'):
            a.normalize_decomposition(bad, claim)

    def test_time_restriction_must_be_complete_and_cannot_be_a_condition_only(self):
        for claim, entity, metric, time in [
            ('The turbine reduced vibration after servicing.', 'turbine', 'vibration', 'after servicing'),
            ('The West relay lowered jitter before maintenance.', 'West relay', 'jitter', 'before maintenance'),
            ('During spring, the turbine reduced vibration.', 'turbine', 'vibration', 'During spring'),
        ]:
            with self.subTest(claim=claim):
                good = plan(claim, entity=entity, metric=metric, time=time)
                self.assertTrue(self.accepts(claim, good))
                for short_time in ('', time.split()[0]):
                    bad = deepcopy(good)
                    bad['parts'][0]['scope']['time'] = short_time
                    self.assertFalse(self.accepts(claim, bad))
                misplaced = deepcopy(good)
                misplaced['parts'][0]['scope'].update(time='', condition=time)
                self.assertFalse(self.accepts(claim, misplaced))
                with self.assertRaises(ValueError):
                    a.normalize_decomposition(misplaced, claim)

    def test_dataset_condition_cannot_be_only_a_preposition(self):
        claim = 'The survey evaluated three encoders on five datasets.'
        good = plan(claim, entity='survey', metric='evaluated three encoders',
                    condition='on five datasets')
        self.assertTrue(self.accepts(claim, good))
        for condition in ('', 'on', 'five datasets'):
            bad = deepcopy(good)
            bad['parts'][0]['scope']['condition'] = condition
            with self.subTest(condition=condition):
                self.assertFalse(self.accepts(claim, bad))

    def test_complete_quote_does_not_bypass_scope_validation(self):
        claim = 'The turbine reduced vibration after servicing.'
        bad = plan(claim, entity='turbine', metric='vibration')
        with self.assertRaisesRegex(ValueError, 'shared_time_required'):
            a.normalize_decomposition(bad, claim)
        bad['parts'][0]['scope']['time'] = 'after servicing'
        bad['parts'][0]['scope']['entity'] = 'a different turbine'
        with self.assertRaisesRegex(ValueError, 'scope_not_grounded'):
            a.normalize_decomposition(bad, claim)

    def test_repair_reports_scope_and_missing_source_together(self):
        claim = 'The West relay lowered jitter before maintenance.'
        bad = plan(claim, entity='West relay', metric='jitter', condition='before maintenance')
        bad['parts'][0]['quote'] = 'The West relay lowered jitter'
        detail = a.validation_detail(bad, claim, 'shared_time_required')
        codes = {issue['code'] for issue in detail['issues']}
        self.assertTrue({'shared_time_required', 'uncovered_claim_content'} <= codes)
        spans = detail['missing_source_spans']
        self.assertTrue(spans)
        self.assertIn('before maintenance', ' '.join(span['text'] for span in spans))
        for span in spans:
            self.assertEqual(claim[span['start']:span['end']], span['text'])
        previous = {'output': bad, 'validation_issue': 'shared_time_required',
                    'validation_detail': detail}
        repair = a.request_messages(a.DECOMPOSE_PROMPT, {'claim': claim}, previous)[-1]['content']
        self.assertIn('before maintenance', repair)
        self.assertIn('uncovered_claim_content', repair)

    def test_quantified_population_modifier_must_survive_in_entity_or_condition(self):
        claim = 'At least one inspected valve reduced leakage after servicing.'
        bad = plan(claim, entity='valve', metric='leakage', time='after servicing',
                   quantifier='some')
        with self.assertRaisesRegex(ValueError, 'population_modifier_missing'):
            a.normalize_decomposition(bad, claim)
        for entity, condition in [('inspected valve', ''), ('valve', 'inspected')]:
            good = deepcopy(bad)
            good['parts'][0]['scope'].update(entity=entity, condition=condition)
            with self.subTest(entity=entity, condition=condition):
                self.assertEqual(len(a.normalize_decomposition(good, claim)['parts']), 1)

    def test_two_and_predicates_keep_shared_scope_and_both_quotes(self):
        claim = 'After servicing, the turbine reduced vibration and increased output.'
        first = plan(claim, entity='turbine', metric='vibration', time='After servicing')['parts'][0]
        first['quote'] = 'After servicing, the turbine reduced vibration'
        second = deepcopy(first)
        second.update(quote='and increased output.')
        second['scope']['metric'] = 'output'
        good = {'parts': [first, second], 'unresolved': []}
        self.assertTrue(self.accepts(claim, good))
        normalized = a.normalize_decomposition(good, claim)
        self.assertEqual([part['quote'] for part in normalized['parts']], [first['quote'], second['quote']])
        unsplit = plan(claim, entity='turbine', metric='vibration', time='After servicing')
        with self.assertRaisesRegex(ValueError, 'unsplit_conjunction'):
            a.normalize_decomposition(unsplit, claim)

    def test_unsupported_or_cannot_gain_validity_from_complete_quote(self):
        claim = 'The turbine reduced vibration or increased output.'
        raw = plan(claim, entity='turbine', metric='vibration')
        with self.assertRaisesRegex(ValueError, 'unsupported_logical_structure'):
            a.normalize_decomposition(raw, claim)


if __name__ == '__main__':
    unittest.main()
