"""Safety gate and verdict contracts for the 3B/7B pilot."""
from importlib import import_module
import json
import unittest

from research_rag.evaluation.factcheck_sla import score


verdict = import_module('04_factchecker.inference.semantic_verdict')
decoder = import_module('04_factchecker.inference.atomic_decoding')
pilot = import_module('scripts.run_factcheck_verdict')


def rows(*values):
    return [dict(gold=gold, prediction=prediction, n=n) for gold, prediction, n in values]


class FactcheckSLATests(unittest.TestCase):
    def test_valid_nei_does_not_count_as_missed_answerable_case(self):
        report = score(rows(('support', 'support', 10), ('contradict', 'contradict', 10),
                            ('not_enough_info', 'not_enough_info', 10)))
        self.assertTrue(report['sla_pass'])
        self.assertEqual(report['answerable_abstention_rate'], 0)
        self.assertAlmostEqual(report['overall_abstention_rate'], 1 / 3)

    def test_false_support_blocks_high_scoring_run(self):
        report = score(rows(('support', 'support', 100), ('contradict', 'contradict', 99),
                            ('contradict', 'support', 1), ('not_enough_info', 'not_enough_info', 100)))
        self.assertFalse(report['sla_pass'])
        self.assertAlmostEqual(report['false_support_rate'], 1 / 200)
        self.assertGreaterEqual(report['macro_f1'], .85)

    def test_incomplete_and_nei_on_answerable_cases_are_abstentions(self):
        report = score(rows(('support', 'support', 8), ('support', '__incomplete__', 2),
                            ('contradict', 'contradict', 8), ('contradict', 'not_enough_info', 2),
                            ('not_enough_info', 'not_enough_info', 10)))
        self.assertEqual(report['answerable_abstention_rate'], .2)
        self.assertEqual(report['incomplete'], 2)
        self.assertFalse(report['checks']['answerable_abstention_at_most_15'])

    def test_syntax_and_verbatim_proof_are_separate(self):
        from lmformatenforcer import CharacterLevelParserConfig, JsonSchemaParser

        context = 'The evaluation used CPUs only.'
        claim = 'The evaluation used GPUs.'
        raw = dict(label='contradict', evidence=[context], confidence=None, reasoning='The evaluation was CPU only.')
        schema, _ = decoder.schema_for(verdict.messages(claim, context))
        state = JsonSchemaParser(schema, CharacterLevelParserConfig(force_json_field_order=True))
        for c in json.dumps(raw, separators=(',', ':')):
            self.assertIn(c, state.get_allowed_characters())
            state = state.add_character(c)
        self.assertTrue(state.can_end())
        self.assertEqual(verdict.validate(raw, context), raw)
        with self.assertRaisesRegex(ValueError, 'non-verbatim'):
            verdict.validate({**raw, 'evidence': ['We used GPUs.']}, context)
        self.assertEqual(verdict.veto(raw, claim, lambda *_: None, .85)[0]['label'], 'not_enough_info')
        scores = dict(contradiction=.90, entailment=.05, neutral=.05)
        self.assertEqual(verdict.veto(raw, claim, lambda *_: scores, .85), (raw, scores))

    def test_source_ids_resolve_exact_offsets_and_reject_bad_references(self):
        source = '  Score was 66.20.\n\nGPU only. '
        segments = verdict.source_segments(source)
        self.assertEqual(list(segments), ['S1', 'S2'])
        schema, _ = decoder.schema_for(verdict.segment_messages(verdict.SOURCE_ID_PROMPT, 'A claim', segments))
        self.assertEqual(schema['properties']['evidence_ids']['items']['enum'], ['S1', 'S2'])
        raw = dict(label='support', evidence_ids=['S2'], confidence=None, reasoning='GPU only.')
        result = verdict.resolve_segments(raw, segments)
        span = result['evidence_spans'][0]
        self.assertEqual(source[span['start']:span['end']], 'GPU only.')
        for ids in ([], ['S3'], ['S1', 'S1'], ['GPU only.']):
            with self.assertRaisesRegex(ValueError, 'invalid_evidence_ids'):
                verdict.resolve_segments({**raw, 'evidence_ids': ids}, segments)
        nei = verdict.resolve_segments({**raw, 'label': 'not_enough_info', 'evidence_ids': []}, segments)
        self.assertEqual(nei['evidence'], [])

    def test_source_id_runner_blocks_missing_quantities_and_scope(self):
        rival = 'The competing model used 25,000 candidates.'
        target = 'The KDG model used 24,000 candidates.'
        claim = 'The KDG model used exactly 25,000 candidates.'
        case = dict(claim=claim, context=rival + ' ' + target)

        def fact(sentence, subject, value):
            return dict(evidence=[sentence], subjects=[dict(text=subject, key='KDG model')],
                        property=dict(text='used', key='candidate count'), scope=[], relation='eq',
                        cue='exactly' if sentence == claim else '',
                        values=[dict(kind='number', text=value, key=value, unit='candidates')])

        def generate(messages):
            prompt = messages[0]['content']
            if prompt == verdict.SOURCE_ID_PROMPT:
                return dict(label='support', evidence_ids=['S1'], confidence=.9, reasoning='The count is 25,000.')
            if prompt == verdict.NUMERIC_CLAIM_PROMPT:
                requirement = fact(claim, 'KDG model', '25,000')
                requirement.pop('evidence')
                return dict(requirements=[requirement], unresolved=[])
            self.assertEqual(prompt, verdict.NUMERIC_SOURCE_PROMPT)
            evidence = json.loads(messages[1]['content'])['segments']
            misbound = fact(rival, 'competing model', '25,000')
            misbound.pop('evidence')
            misbound['evidence_ids'] = ['S1']
            misbound['assertion'] = ''
            if 'S2' not in evidence:
                return dict(facts=[misbound])
            misbound['evidence_ids'].append('S2')
            actual = fact(target, 'KDG model', '24,000')
            actual.pop('evidence')
            actual['evidence_ids'] = ['S2']
            actual['assertion'] = ''
            return dict(facts=[misbound, actual])

        _, final, check = pilot.assess_case(case, generate, evidence_format='ids')
        self.assertEqual((final['label'], final['evidence_ids']), ('contradict', ['S2']))
        self.assertEqual([attempt['label'] for attempt in check['attempts']], ['not_enough_info', 'contradict'])
        span = check['parts'][0]['source_spans'][0]
        self.assertEqual(case['context'][span['start']:span['end']], target)

    def test_source_id_includes_local_antecedent(self):
        case = dict(claim='Coverbs and localizers are separate targets.',
                    context='Coverbs and localizers co-occur. We treat them as separate targets.')

        def generate(messages):
            if messages[0]['content'] == verdict.SOURCE_ID_PROMPT:
                return dict(label='support', evidence_ids=['S2'], confidence=None, reasoning='Separate targets.')
            selected = json.loads(messages[1]['content'])['segments']
            self.assertEqual(list(selected), ['S1', 'S2'])
            return dict(label='support', reasoning='Both groups are named in the preceding sentence.')

        proposal, final, _ = pilot.assess_case(case, generate, evidence_format='ids')
        self.assertEqual(proposal['evidence_ids'], ['S2'])
        self.assertEqual(final['evidence_ids'], ['S1', 'S2'])

    def test_count_contradiction_requires_the_same_category(self):
        claim = 'The parser tagged exactly 150 targets as nouns.'

        def fact(sentence, category, value, cue):
            return dict(evidence=[sentence], subjects=[dict(text='The parser', key='parser')],
                        property=dict(text='tagged', key='tag count'),
                        scope=[dict(text='targets', key='targets'), dict(text=category, key=category)],
                        relation='eq', cue=cue,
                        values=[dict(kind='number', text=value, key=value, unit='')])

        for category, expected in [('adpositions', 'not_enough_info'), ('nouns', 'contradict')]:
            with self.subTest(category=category):
                source = f'The parser tagged 385 targets as {category}.'

                def generate(messages):
                    prompt = messages[0]['content']
                    if prompt == verdict.SOURCE_ID_PROMPT:
                        return dict(label='contradict', evidence_ids=['S1'], confidence=None, reasoning='385 differs.')
                    if prompt == verdict.NUMERIC_CLAIM_PROMPT:
                        requirement = fact(claim, 'nouns', '150', 'exactly')
                        requirement.pop('evidence')
                        return dict(requirements=[requirement], unresolved=[])
                    self.assertEqual(prompt, verdict.NUMERIC_SOURCE_PROMPT)
                    observed = fact(source, category, '385', '')
                    observed.pop('evidence')
                    return dict(facts=[dict(evidence_ids=['S1'], assertion='', **observed)])

                _, final, check = pilot.assess_case(dict(claim=claim, context=source), generate, evidence_format='ids')
                self.assertEqual(final['label'], expected)
                self.assertIn('parts', check)

    def test_numeric_decoding_requires_literal_spans_and_source_ids(self):
        claim = 'The corpus contained 6,105 documents.'
        messages = [{'role': 'system', 'content': verdict.NUMERIC_CLAIM_PROMPT},
                    {'role': 'user', 'content': json.dumps(dict(claim=claim))}]
        schema, _ = decoder.schema_for(messages)
        fields = schema['properties']['requirements']['items']['properties']
        self.assertNotIn('evidence', fields)
        self.assertIn('contained', fields['property']['properties']['text']['enum'])
        self.assertNotIn('contains', fields['property']['properties']['text']['enum'])
        numeric = fields['values']['items']['anyOf'][0]['properties']['text']['enum']
        self.assertEqual(numeric, ['6,105'])

        segments = {'S3': 'The other corpus is a set of 881 sports news.'}
        targets = [dict(subjects=['sports news corpus'], property='document count', scope=[])]
        messages = [{'role': 'system', 'content': verdict.NUMERIC_SOURCE_PROMPT},
                    {'role': 'user', 'content': json.dumps(dict(segments=segments, targets=targets))}]
        schema, _ = decoder.schema_for(messages)
        fields = schema['properties']['facts']['items']['properties']
        self.assertEqual(fields['evidence_ids']['items']['enum'], ['S3'])
        self.assertEqual(fields['property']['properties']['key']['enum'], ['document count'])
        self.assertNotIn('contains', fields['property']['properties']['text']['enum'])

        targets = [dict(subjects=['tweets'], property='coverage', scope=[])]
        messages[1]['content'] = json.dumps(dict(
            segments={'S1': 'Coverage was 64% and 70% for Tweets and News, respectively.'}, targets=targets))
        schema, _ = decoder.schema_for(messages)
        subjects = schema['properties']['facts']['items']['properties']['subjects']
        keys = subjects['items']['properties']['key']['enum']
        self.assertTrue({'tweets', 'news'} <= set(keys))

    def test_numeric_claim_normalizes_duplicate_count_but_keeps_missing_transition_invalid(self):
        parser = import_module('04_factchecker.inference.decoder_parser')
        claim = 'The corpus contained 6,105 documents after preprocessing.'
        scalar = dict(subjects=[dict(text='corpus', key='corpus')], property=dict(text='contained', key='count'),
                      scope=[], relation='eq', cue='',
                      values=[dict(kind='number', text='6,105', key='count', unit='')])
        duplicate = {**scalar, 'relation': 'transition', 'cue': 'after preprocessing'}
        raw = verdict._numeric_claim_records(dict(requirements=[scalar, duplicate], unresolved=[]), claim)
        requirements = parser.parse_requirements(raw, claim, numeric_binding=True)
        self.assertEqual(len(requirements), 1)
        self.assertEqual(requirements[0].scope[0].span.text, 'after preprocessing')
        raw = verdict._numeric_claim_records(dict(requirements=[duplicate], unresolved=[]), claim)
        with self.assertRaisesRegex(ValueError, 'invalid_transition_operands'):
            parser.parse_requirements(raw, claim, numeric_binding=True)

    def test_sampling_proof_binds_method_split_selection_and_purpose(self):
        proof = import_module('04_factchecker.inference.explicit_numeric_proof')
        claim = 'The stratified ranking method used 500 samples randomly selected from the evaluation data for warm-up.'
        source = ('We experimented with both the uniform baseline and the proposed stratified ranking methods. '
                  'For the stratified approach, we randomly picked 500 samples from the evaluation data set as warm up samples.')

        def assess(text):
            return proof.compare_explicit(claim, ['S2'], verdict.source_segments(text), text)

        self.assertEqual(assess(source)[:2], ('support', ('S1', 'S2')))
        self.assertEqual(assess(source.replace('500 samples', '450 samples'))[0], 'contradict')
        for original, changed in (
            ('evaluation data set', 'training data set'),
            ('randomly picked', 'manually picked'),
            ('warm up samples', 'test samples'),
            ('warm up samples', 'warm up utterances'),
            ('uniform baseline', 'stratified baseline'),
            ('stratified ranking methods.', 'stratified reranking methods.'),
            ('methods. For', 'methods.\n\nFor'),
        ):
            with self.subTest(changed=changed):
                self.assertIsNone(assess(source.replace(original, changed)))

    def test_explicit_numeric_comparison_checks_the_binding_and_value(self):
        proof = import_module('04_factchecker.inference.explicit_numeric_proof')

        def assess(claim, context, selected=('S1',)):
            return proof.compare_explicit(claim, selected, verdict.source_segments(context), context)

        claim = 'The Orion corpus contained 50 articles.'
        source = "The corpus (named here 'News') contains 50 articles. The other corpus (called 'Orion') contains 72 articles."
        self.assertEqual(assess(claim, source)[:2], ('contradict', ('S2',)))
        self.assertEqual(assess(claim.replace('50', '72'), source)[0], 'support')
        self.assertIsNone(assess(claim, source.replace("'Orion'", "'Other'")))
        self.assertIsNone(assess(claim, source.replace("72 articles", "72 tokens")))
        self.assertIsNone(assess(claim, source.replace('. The other', '.\n\nThe other')))
        self.assertIsNone(assess(claim, source.replace('contains 72', 'does not contain 72')))
        conflict = source.replace("'News'", "'Orion'")
        self.assertIsNone(assess(claim, conflict))

        claim = 'Patterns covered 80% of nouns in the Bronze dataset.'
        source = 'Patterns cover 62% and 80% nouns in Bronze and Silver, respectively.'
        self.assertEqual(assess(claim, source)[0], 'contradict')
        self.assertEqual(assess(claim.replace('Bronze', 'Silver'), source)[0], 'support')
        self.assertIsNone(assess(claim, source.replace('nouns', 'verbs')))
        self.assertIsNone(assess(claim, source.replace('respectively', 'on average')))

        claim = 'The standard Alpha negative-sampling distribution uses a smoothing exponent of 0.5.'
        source = ('This is the choice of noise distribution for negative sampling. '
                  'Alpha employs a smoothed unigram distribution with a power rate of 1/2 as the noise distribution.')
        self.assertEqual(assess(claim, source, ('S2',))[0], 'support')
        self.assertEqual(assess(claim, source.replace('1/2', '3/4'), ('S2',))[0], 'contradict')
        self.assertIsNone(assess(claim, source.replace('negative sampling', 'evaluation'), ('S2',)))
