"""Named-property metric constraints shared by the candidate validator and decoder."""

# shortcut: finite active property grammar; use a parser if unseen syntax needs enforcement.
METRIC_HELPERS = r'''
_PROPERTY_CHANGE_VERBS = (
    r'improves?|improved|increases?|increased|decreases?|decreased|reduces?|reduced|'
    r'gains?|gained|retains?|retained|maintains?|maintained|raises?|raised|'
    r'lowers?|lowered|boosts?|boosted'
)
# Finite engineering measurement vocabulary, not a semantic noun classifier.
# Unknown heads and ambiguous syntax keep the existing human-review path.
_PROPERTY_HEADS = frozenset({
    'accuracy','precision','recall','latency','throughput','yield','delay','jitter',
    'memory','use','duration','rate','score','capacity','pressure','temperature',
    'humidity','voltage','vibration','leakage','output','stability','robustness',
    'reliability','availability','efficiency','utilization','consumption','quality',
    'fidelity','variance','loss','cost','speed','power','energy','coverage','skill',
    'performance','noise','resolution','brightness',
})


def metric_clause_body(source):
    """Apply the existing clause/prefix boundaries before looking for a metric."""
    prefix = re.match(r'\s*(?:(?:after|before|during|on|using|under)\s+[^,.;]+,\s*)+', source, re.I)
    body = source[prefix.end():] if prefix else source
    body = re.sub(r'^\s*and\s+', '', body, flags=re.I).strip()
    restrictions = scope_restrictions(body)
    end = min([body.index(value) for values in restrictions.values() for value in values] or [len(body)])
    return body[:end].rstrip(' ,.;:')


def named_property_requirement(source):
    """Exact property span in a supported active change-verb + noun-phrase form."""
    body = metric_clause_body(source)
    verbs = list(re.finditer(r'\b(?:'+_PROPERTY_CHANGE_VERBS+r')\b', body, re.I))
    if len(verbs) != 1:
        return None
    verb = verbs[0]
    # Do not reinterpret negation, auxiliaries, relative clauses or attribution
    # as a simple active predicate. Their meaning still requires semantic review.
    # May in a prepositional population restriction is a month, not modal may.
    subject = re.sub(r'\b(?:in|during)\s+May\b', '', body[:verb.start()], flags=re.I)
    if re.search(r'\b(?:not|never|who|which|that|named|called|if|when|can|could|may|might|'
            r'must|should|would|will|was|were|is|are|be|been|has|have|had|reported|observed|'
            r'described|stated|claimed|predicted|expected|suggested|noted|showed|found)\b',
            subject, re.I):
        return None
    argument = body[verb.end():].strip()
    argument = re.split(r'\s+(?:after|before|during|on|using|under|in|at|for|with|without|'
                        r'when|if|by|from|to|because|while|than)\b', argument, maxsplit=1, flags=re.I)[0]
    argument = re.sub(r'^(?:the|its|their)\s+', '', argument, flags=re.I)
    if not re.fullmatch(r'[A-Za-z][A-Za-z-]*(?:\s+[A-Za-z][A-Za-z-]*){0,7}', argument):
        return None
    words = argument.casefold().split()
    if words[-1] not in _PROPERTY_HEADS or any(w in {
            'only','also','significantly','substantially','slightly','dramatically',
            'approximately','about','roughly','not','never','or','and'} for w in words):
        return None
    return argument


'''


def apply_patch(root):
    path = root/'04_factchecker/inference/atomic_verifier.py'
    text = path.read_text(encoding='utf-8')
    old = '''def source_metric_requirement(source):
    """Bind a simple numeric predicate from source, independent of model scope."""
    prefix = re.match(r'\s*(?:(?:after|before|during|on|using|under)\s+[^,.;]+,\s*)+', source, re.I)
    body = source[prefix.end():] if prefix else source
    body = re.sub(r'^\s*and\s+', '', body, flags=re.I).strip()
    restrictions = scope_restrictions(body)
    end = min([body.index(value) for values in restrictions.values() for value in values] or [len(body)])
    body = body[:end].rstrip(' ,.;:')
'''
    new = METRIC_HELPERS + '''def source_metric_requirement(source):
    """One source-bound requirement for validator and decoder; no output rewriting."""
    property_span = named_property_requirement(source)
    if property_span is not None:
        return property_span
    body = metric_clause_body(source)
'''
    assert text.count(old) == 1
    text = text.replace(old,new)
    old = "    if required_metric:\n        add('metric_predicate_incomplete', 'metric', [required_metric])"
    new = """    if required_metric:
        code = ('metric_property_not_canonical' if named_property_requirement(restrictions['source'])
                else 'metric_predicate_incomplete')
        add(code, 'metric', [required_metric])"""
    assert text.count(old) == 1
    text = text.replace(old,new)
    text += '''

POLICY = 'atomic-verifier-constrained-v8-cellfix5'
REPAIR_HINTS['metric_property_not_canonical'] = (
    'Copy the exact named-property required_source span from validation details, '
    'without its change verb, article or possessive. Preserve every property modifier '
    '(for example median request latency). Keep direction, quantities and restrictions '
    'in the original quote; do not rewrite the claim or other scope fields.'
)
'''
    path.write_bytes(text.encode('utf-8'))
    path = root/'04_factchecker/inference/atomic_decoding.py'
    text = path.read_text(encoding='utf-8')
    text += "\nDECODER.update(policy='atomic-schema-decoding-v5-cellfix5', named_property_source_binding='active_change_verb_and_known_measurement_head')\n"
    path.write_bytes(text.encode('utf-8'))


TESTS = r'''
"""Development regressions: fixed real traces, novel claims and actual LMFE filters."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import unittest
from research_rag.tests.test_atomic_decomposition_v5 import plan
from research_rag.tests.test_atomic_decoding import Sequence, messages, token_backend
from research_rag.tests.test_atomic_verifier import Backend
from research_rag.evaluation import evaluate_atomic_verifier as runner

a = importlib.import_module('04_factchecker.inference.atomic_verifier')
d = importlib.import_module('04_factchecker.inference.atomic_decoding')

NOVEL = (
    ('Every calibrated gauge improved signal fidelity after inspection.', 'calibrated gauge', 'signal fidelity', 'after inspection', '', 'all'),
    ('Some coastal stations gained predictive skill during winter.', 'coastal stations', 'predictive skill', 'during winter', '', 'some'),
    ('None of the tuned encoders increased noise variance.', 'tuned encoders', 'noise variance', '', '', 'none'),
    ('The scheduler reduced median batch latency.', 'scheduler', 'median batch latency', '', '', 'atomic'),
    ('The actuator lowered operating pressure before shutdown.', 'actuator', 'operating pressure', 'before shutdown', '', 'atomic'),
    ('The filter retains reconstruction quality.', 'filter', 'reconstruction quality', '', '', 'atomic'),
    ('The channel boosts spectral resolution.', 'channel', 'spectral resolution', '', '', 'atomic'),
    ('On the Iris dataset, the parser improved token precision.', 'parser', 'token precision', '', 'On the Iris dataset', 'atomic'),
)


class NamedMetricTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.backend = token_backend()

    def accepts(self, claim, raw):
        callback = self.backend.generation_options(messages(claim))['prefix_allowed_tokens_fn']
        ids = Sequence([ord('P')])
        for char in json.dumps(raw,separators=(',',':')):
            if ord(char) not in callback(0,ids):
                return False
            ids.append(ord(char))
        return 0 in callback(0,ids)

    def verify(self, claim, outputs):
        backend=Backend(outputs)
        result=a.AtomicVerifier(backend,max_calls=2,max_attempts=2,max_new_tokens=1536,
            timeout_seconds=180).verify(claim,'',decomposition_only=True)
        criteria={'policy':a.POLICY,'max_calls_per_case':2,'max_attempts':2,
            'max_new_tokens':1536,'case_deadline_seconds':180}
        runner.replay_result(result,claim,'',criteria)
        return result,backend

    def test_failed_real_traces_are_rejected_without_rewriting_and_canonical_paths_exist(self):
        rows=json.loads((Path(__file__).parent/'fixtures/atomic_cellfix4_metric_traces.json').read_text())
        self.assertEqual(len(rows),3)
        for row in rows:
            with self.subTest(case=row['example_id']):
                bad=row['output'];before=deepcopy(bad)
                with self.assertRaisesRegex(ValueError,'metric_property_not_canonical'):
                    a.normalize_decomposition(bad,row['claim'])
                self.assertEqual(bad,before)
                self.assertFalse(self.accepts(row['claim'],bad))
                good=deepcopy(bad)
                good['parts'][0]['scope']['metric']=row['expected_metric']
                self.assertTrue(self.accepts(row['claim'],good))
                self.assertEqual(a.normalize_decomposition(good,row['claim'])['parts'][0]['scope']['metric'],row['expected_metric'])

    def test_novel_properties_share_exact_validator_and_decoder_requirement(self):
        for claim,entity,metric,time,condition,quantifier in NOVEL:
            with self.subTest(claim=claim):
                raw=plan(claim,entity=entity,metric=metric,time=time,condition=condition,quantifier=quantifier)
                self.assertEqual(a.source_metric_requirement(claim),metric)
                schema=d.decomposition_schema(claim)
                self.assertEqual(schema['properties']['parts']['items']['properties']['scope']['properties']['metric']['enum'],[metric])
                self.assertTrue(self.accepts(claim,raw))
                self.assertEqual(a.normalize_decomposition(raw,claim)['parts'][0]['scope']['metric'],metric)

    def test_novel_verb_property_and_modifier_dropping_are_blocked(self):
        for claim,entity,metric,time,condition,quantifier in NOVEL:
            words=metric.split()
            verb=next(m.group() for m in a.re.finditer(r'\b(?:'+a._PROPERTY_CHANGE_VERBS+r')\b',claim,a.re.I))
            for wrong in (verb,verb+' '+metric,words[-1]):
                if wrong not in claim or wrong==metric: continue
                with self.subTest(claim=claim,metric=wrong):
                    raw=plan(claim,entity=entity,metric=wrong,time=time,condition=condition,quantifier=quantifier)
                    self.assertFalse(self.accepts(claim,raw))
                    with self.assertRaisesRegex(ValueError,'metric_property_not_canonical'):
                        a.normalize_decomposition(raw,claim)

    def test_article_and_possessive_are_not_property_modifiers(self):
        for phrase,metric in (('the signal quality','signal quality'),('its error rate','error rate'),('their predictive skill','predictive skill')):
            claim='The controller improved '+phrase+'.'
            good=plan(claim,entity='controller',metric=metric)
            self.assertTrue(self.accepts(claim,good))
            bad=deepcopy(good);bad['parts'][0]['scope']['metric']=phrase
            with self.assertRaisesRegex(ValueError,'metric_property_not_canonical'):
                a.normalize_decomposition(bad,claim)

    def test_case_and_all_property_modifiers_remain_exact(self):
        claim='The relay reduced Median Request Latency.'
        good=plan(claim,entity='relay',metric='Median Request Latency')
        self.assertTrue(self.accepts(claim,good))
        self.assertEqual(a.source_metric_requirement(claim),'Median Request Latency')
        for wrong in ('Request Latency','Latency'):
            bad=deepcopy(good);bad['parts'][0]['scope']['metric']=wrong
            self.assertFalse(self.accepts(claim,bad))
            with self.assertRaisesRegex(ValueError,'metric_property_not_canonical'):
                a.normalize_decomposition(bad,claim)

    def test_bounded_repair_reports_exact_property_and_replays(self):
        claim='The estimator improved signal fidelity after inspection.'
        bad=plan(claim,entity='estimator',metric='improved signal fidelity',time='after inspection')
        good=deepcopy(bad);good['parts'][0]['scope']['metric']='signal fidelity'
        result,backend=self.verify(claim,[bad,good])
        self.assertEqual((result['status'],result['backend_calls']),('completed',2))
        self.assertEqual(result['trace'][0]['validation_issue'],'metric_property_not_canonical')
        repair=backend.calls[1][0][-1]['content']
        self.assertIn('signal fidelity',repair)
        self.assertIn('without its change verb',repair)
        self.assertIn('parts[0].scope.metric',repair)
        self.assertEqual(result['decomposition']['parts'][0]['scope']['time'],'after inspection')

    def test_repair_exhaustion_stops_without_assessment_or_budget_growth(self):
        claim='The estimator improved signal fidelity.'
        bad=plan(claim,entity='estimator',metric='improved signal fidelity')
        result,backend=self.verify(claim,[bad,bad])
        self.assertEqual(result['stop_reason'],'invalid_output_exhausted')
        self.assertEqual(result['backend_calls'],2)
        self.assertIsNone(result['assessed_label'])
        self.assertTrue(all(set(json.loads(m[1]['content']))=={'claim'} for m,_ in backend.calls))

    def test_each_part_keeps_its_property_and_local_restriction(self):
        claim='The pump reduced vibration after servicing and increased output before inspection.'
        first=plan(claim,entity='pump',metric='vibration',time='after servicing')['parts'][0]
        first['quote']='The pump reduced vibration after servicing'
        second=plan(claim,entity='pump',metric='output',time='before inspection')['parts'][0]
        second['quote']='and increased output before inspection.'
        raw={'parts':[first,second],'unresolved':[]}
        self.assertTrue(self.accepts(claim,raw))
        normalized=a.normalize_decomposition(raw,claim)
        self.assertEqual([p['scope']['time'] for p in normalized['parts']],['after servicing','before inspection'])
        bad=deepcopy(raw);bad['parts'][1]['scope']['metric']='vibration'
        self.assertFalse(self.accepts(claim,bad))
        with self.assertRaisesRegex(ValueError,'metric_property_not_canonical'):
            a.normalize_decomposition(bad,claim)

    def test_leading_shared_time_population_and_quantifiers_are_preserved(self):
        claim='After calibration, every inspected relay reduced vibration and increased output.'
        first=plan(claim,entity='inspected relay',metric='vibration',time='After calibration',quantifier='all')['parts'][0]
        first['quote']='After calibration, every inspected relay reduced vibration'
        second=deepcopy(first);second['quote']='and increased output.';second['scope']['metric']='output'
        raw={'parts':[first,second],'unresolved':[]}
        self.assertTrue(self.accepts(claim,raw))
        checked=a.normalize_decomposition(raw,claim)
        self.assertEqual([p['scope']['time'] for p in checked['parts']],['After calibration']*2)
        bad=deepcopy(raw);bad['parts'][0]['scope']['entity']='relay'
        with self.assertRaisesRegex(ValueError,'population_modifier_missing'):
            a.normalize_decomposition(bad,claim)

    def test_missing_time_and_wrong_named_metric_are_reported_together(self):
        claim='The relay reduced operating pressure before maintenance.'
        bad=plan(claim,entity='relay',metric='reduced operating pressure')
        details=a.validation_detail(bad,claim,'metric_property_not_canonical')
        codes={i['code'] for i in details['issues']}
        self.assertTrue({'metric_property_not_canonical','shared_time_required'} <= codes)

    def test_numeric_predicates_and_multiple_quantity_requirements_remain_intact(self):
        for claim,entity,metric,condition,n in (
            ('Compilation took seven minutes.','Compilation','took seven minutes','',1),
            ('The bin contained five sensors.','bin','contained five sensors','',1),
            ('The audit evaluated six systems on three datasets.','audit','evaluated six systems','on three datasets',2)):
            raw=plan(claim,entity=entity,metric=metric,condition=condition)
            self.assertTrue(self.accepts(claim,raw))
            self.assertEqual(len(a.normalize_decomposition(raw,claim)['parts'][0]['numeric_requirements']),n)
            bad=deepcopy(raw);bad['parts'][0]['scope']['metric']=metric.split(' ',1)[1]
            with self.assertRaisesRegex(ValueError,'metric_predicate_incomplete'):
                a.normalize_decomposition(bad,claim)

    def test_no_property_is_invented_for_bare_change_or_event_object(self):
        for claim,entity,metric in (
            ('All tasks improved after compression.','tasks','improved'),
            ('The user gained access.','user','gained access'),
            ('The application gained new users.','application','gained new users'),
            ('The output signal improved.','output signal','improved')):
            self.assertIsNone(a.named_property_requirement(claim))
            raw=plan(claim,entity=entity,metric=metric,
                time='after compression' if 'after compression' in claim else '',
                quantifier='all' if claim.startswith('All') else 'atomic')
            a.normalize_decomposition(raw,claim)

    def test_ambiguous_attributed_passive_or_negated_forms_are_not_reinterpreted(self):
        for claim in (
            'The reported model was improved under inspection.',
            'The study reported increased accuracy.',
            'The improved cache reduced latency.',
            'The estimator did not improve signal fidelity.',
            'The estimator might improve signal fidelity.',
            'The estimator improved significantly signal fidelity.',
            'The operator who improved precision remained active.'):
            with self.subTest(claim=claim):
                self.assertIsNone(a.named_property_requirement(claim))

    def test_verb_inside_a_temporal_restriction_is_not_the_main_metric(self):
        claim='The lamp failed after the operator improved precision.'
        self.assertIsNone(a.named_property_requirement(claim))
        raw=plan(claim,entity='lamp',metric='failed',time='after the operator improved precision')
        self.assertTrue(self.accepts(claim,raw))

    def test_may_restriction_stays_a_population_filter(self):
        for month in ('June','May'):
            claim='Every seasonal trial conducted in '+month+' improved spectral resolution.'
            raw=plan(claim,entity='seasonal trial',metric='spectral resolution',condition='in '+month,quantifier='all')
            self.assertTrue(self.accepts(claim,raw))
            result=a.normalize_decomposition(raw,claim)['parts'][0]
            self.assertEqual(result['scope']['time'],'')
            self.assertEqual(result['scope']['condition'],'in '+month)
            self.assertEqual(result['quote'],claim)


if __name__=='__main__':
    unittest.main()
'''
