"""Received cf11 failures plus new target/absence sentences; no held-out cases."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import unittest

from research_rag.tests.test_atomic_smoke_cellfix3 import scoped, request
from research_rag.tests.test_atomic_verifier import assessment, observation, run
from research_rag.tests.test_atomic_assessment_cellfix10 import canonical
from research_rag.tests import test_atomic_assessment_v8 as h

a = importlib.import_module('04_factchecker.inference.atomic_verifier')
f = importlib.import_module('04_factchecker.inference.assessment_focus')
e = importlib.import_module('04_factchecker.inference.assessment_decisions')


def received(cid):
    rows = json.loads((Path(__file__).parent/'fixtures/atomic_cellfix11_full39_traces.json').read_bytes())
    row = next(v for v in rows if v['case']['example_id'] == cid)
    t = next(v for v in reversed(row['result']['trace']) if v['stage'] != 'decompose')
    payload = json.loads(t['messages'][1]['content'])
    return payload['claim'], payload['part'], payload['context'], deepcopy(t['output'])


def repaired(cid):
    claim, p, ctx, raw = received(cid)
    obs = raw['observations'][0]
    if cid.startswith('scope:entity:'):
        obs.update(member=p['scope']['entity'], truth='true' if cid.endswith(':support') else 'false',
            quotes=[ctx.split('. ')[0]+'.'])
        raw['missing_information'] = []
    elif cid.startswith('scope:condition:'):
        obs.update(member='low-temperature group', truth='unknown', quotes=f.absence_quotes(p,ctx))
        raw['missing_information'] = ['population_results_unresolved']
    else:
        obs.update(member='Silver',truth='unknown')
    return claim, p, ctx, canonical(raw,p,ctx)


def entity_sample(truth='true', possessive=True, time=True):
    restriction = 'after alignment' if time else ''
    claim = 'The Amber repeater reduced its error rate'+(' after alignment.' if time else '.')
    result = 'decreased' if truth == 'true' else 'increased'
    own = ("The Amber repeater's error rate "+result if possessive else
           'The Amber repeater '+('reduced' if truth == 'true' else 'increased')+' its error rate')
    own += (' after alignment.' if time else '.')
    ctx = own+' The Violet repeater\'s error rate increased.'
    p = scoped(claim,'Amber repeater','error rate',time=restriction)
    raw = canonical(assessment([observation('Amber repeater',truth,own)]),p,ctx)
    return claim,p,ctx,raw


def absence_sample(verb='measured'):
    claim = 'Every specimen in the dry-season group gained conductivity after annealing.'
    ctx = ('The dry-season group contained three specimens, but no conductivity changes were '+verb+
           ' for that group. All wet-season specimens gained conductivity after annealing.')
    p = scoped(claim,'specimen','conductivity',quantifier='all',time='after annealing',condition='in the dry-season group')
    raw = canonical(assessment([observation('dry-season group','unknown',ctx.split('. ')[0]+'.')]),p,ctx)
    return claim,p,ctx,raw


def token_paths():
    paths = []
    for cid in ('scope:entity:support','scope:entity:contradict','scope:condition:not_enough_info','scope:none:not_enough_info'):
        claim,p,ctx,bad = received(cid)
        paths.append((cid+'_bad',claim,p,ctx,bad,False))
        claim,p,ctx,good = repaired(cid)
        paths.append((cid+'_repaired',claim,p,ctx,good,True))
    for truth in ('true','false'):
        claim,p,ctx,good = entity_sample(truth)
        paths.append(('novel_root_'+truth,claim,p,ctx,good,True))
        for kind in ('empty','other'):
            bad = deepcopy(good)
            bad['observations'][0].update(truth='unknown',quotes=[] if kind=='empty' else [ctx.split('. ')[1]])
            bad['missing_information'] = [importlib.import_module('04_factchecker.inference.assessment_reporting').missing_reason(p,ctx)]
            paths.append(('novel_unknown_'+truth+'_'+kind,claim,p,ctx,bad,False))
    for verb in ('measured','reported','recorded'):
        claim,p,ctx,good = absence_sample(verb)
        paths.append(('novel_absence_'+verb,claim,p,ctx,good,True))
        for truth in ('true','false'):
            bad = deepcopy(good)
            bad['observations'][0]['truth'] = truth
            paths.append(('novel_absence_'+verb+'_'+truth,claim,p,ctx,bad,False))
        bad = deepcopy(good)
        bad['observations'][0]['member'] = 'no conductivity changes were '+verb+' for that group'
        paths.append(('novel_clause_member_'+verb,claim,p,ctx,bad,False))
    claim,p,_,raw = entity_sample()
    ctx = 'The Amber repeater was documented after alignment. Maintenance records were archived after alignment.'
    raw['observations'][0].update(truth='unknown',quotes=[ctx.split('. ')[0]+'.',ctx.split('. ')[1]])
    paths.append(('novel_unknown_mixed_bound_unbound_quotes',claim,p,ctx,canonical(raw,p,ctx),False))
    return paths


class BindingTests(unittest.TestCase):
    def test_received_bad_ledgers_rejected_and_repairs_accepted(self):
        for cid, expected in [('scope:entity:support','support'),('scope:entity:contradict','contradict'),('scope:condition:not_enough_info','not_enough_info'),('scope:none:not_enough_info','not_enough_info')]:
            with self.subTest(cid=cid):
                _,p,ctx,raw = received(cid)
                with self.assertRaises(ValueError): a.assess_part(raw,p,ctx)
                _,p,ctx,raw = repaired(cid)
                self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],expected)

    def test_new_atomic_subjects_have_decisive_property_witnesses(self):
        for truth in ('true','false'):
            for possessive in (True,False):
                for time in (True,False):
                    _,p,ctx,raw = entity_sample(truth,possessive,time)
                    self.assertEqual(e.decision_evidence(p,ctx)['truth'],truth)
                    self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'support' if truth=='true' else 'contradict')

    def test_unknown_cannot_discard_known_outcome(self):
        _,p,ctx,raw = entity_sample()
        raw['observations'][0].update(truth='unknown',quotes=[])
        with self.assertRaisesRegex(ValueError,'decisive_witness_missing_or_unknown'): a.assess_part(raw,p,ctx)

    def test_unknown_quote_binds_even_without_decisive_witness(self):
        claim,p,_,raw = entity_sample()
        ctx = 'The Amber repeater was documented after alignment. The Violet repeater was documented after alignment.'
        raw['observations'][0].update(truth='unknown',quotes=[ctx.split('. ')[1]])
        with self.assertRaisesRegex(ValueError,'observation_target_mismatch|observation_evidence_unbound'): a.assess_part(raw,p,ctx)

    def test_unknown_quote_cannot_borrow_other_local_clause(self):
        _,p,_,raw = entity_sample()
        ctx = 'The Amber repeater was documented after alignment. Maintenance records were archived after alignment.'
        raw['observations'][0].update(truth='unknown',quotes=['Maintenance records were archived after alignment.'])
        with self.assertRaisesRegex(ValueError,'observation_evidence_unbound'): a.assess_part(raw,p,ctx)
        raw['observations'][0]['quotes'].insert(0,'The Amber repeater was documented after alignment.')
        with self.assertRaisesRegex(ValueError,'observation_evidence_unbound'): a.assess_part(raw,p,ctx)

    def test_unknown_with_genuine_uncertainty_remains_valid(self):
        claim,p,_,raw = entity_sample()
        ctx = 'The Amber repeater was documented after alignment.'
        raw['observations'][0].update(truth='unknown',quotes=[ctx])
        self.assertIsNone(e.decision_evidence(p,ctx))
        self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'not_enough_info')

    def test_conflicting_same_target_directions_not_forced(self):
        _,p,ctx,_ = entity_sample()
        ctx += " The Amber repeater's error rate increased after alignment."
        self.assertIsNone(e.decision_evidence(p,ctx))

    def test_other_metric_does_not_establish_requested_direction(self):
        _,p,_,_ = entity_sample()
        ctx = "The Amber repeater's latency decreased after alignment."
        self.assertIsNone(e.decision_evidence(p,ctx))

    def test_modal_embedded_and_conditional_not_forced(self):
        _,p,_,_ = entity_sample()
        for ctx in ["The Amber repeater's error rate may decrease after alignment.",
                    "The Amber repeater's error rate improved after alignment.",
                    "An analyst said the Amber repeater's error rate decreased after alignment.",
                    "If the Amber repeater's error rate decreased after alignment, service would resume."]:
            self.assertIsNone(e.decision_evidence(p,ctx),ctx)

    def test_opposed_time_not_a_decisive_witness(self):
        _,p,ctx,_ = entity_sample()
        self.assertIsNone(e.decision_evidence(p,ctx.replace('after alignment','before alignment')))

    def test_new_suffix_named_target_remains_supported(self):
        claim = 'Unit Citrine reduced latency.'
        ctx = 'Unit Citrine reduced latency. Unit Opal increased latency.'
        p = scoped(claim,'Unit Citrine','latency')
        raw = canonical(assessment([observation('Unit Citrine','true','Unit Citrine reduced latency.')]),p,ctx)
        self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'support')

    def test_nonqualified_does_not_establish_qualified_population(self):
        p = scoped('Every certified repeater improved.','certified repeater','improved',quantifier='all')
        self.assertIsNone(e.decision_evidence(p,'A non-certified repeater improved.'))
        p = scoped('The certified repeater used three channels.','certified repeater','used three channels')
        self.assertIsNone(e.decision_evidence(p,'The non-certified repeater used three channels.'))


class AbsenceTests(unittest.TestCase):
    def test_no_measurement_variants_remain_unknown(self):
        for verb in ('measured','reported','evaluated','recorded'):
            _,p,ctx,raw = absence_sample(verb)
            self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'not_enough_info')
            for truth in ('true','false'):
                bad = deepcopy(raw);bad['observations'][0]['truth'] = truth
                with self.assertRaises(ValueError): a.assess_part(bad,p,ctx)

    def test_absence_clause_cannot_be_entity_even_if_unknown(self):
        _,p,ctx,raw = absence_sample()
        raw['observations'][0]['member'] = 'no conductivity changes were measured for that group'
        with self.assertRaisesRegex(ValueError,'observation_member_is_not_entity'): a.assess_part(raw,p,ctx)

    def test_measured_unchanged_is_actual_counterevidence(self):
        claim = 'The Amber repeater reduced its error rate after alignment.'
        ctx = "The Amber repeater's error rate remained unchanged after alignment."
        p = scoped(claim,'Amber repeater','error rate',time='after alignment')
        raw = canonical(assessment([observation('Amber repeater','false',ctx)]),p,ctx)
        self.assertEqual(f.absence_quotes(p,ctx),[])
        self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'contradict')

    def test_report_of_no_changes_is_not_missing_measurement(self):
        claim = 'Every sample gained conductivity.'
        ctx = 'The sample showed no conductivity changes.'
        p = scoped(claim,'sample','conductivity',quantifier='all')
        self.assertEqual(f.absence_quotes(p,ctx),[])
        self.assertIsNone(f.observation_focus_issue(p,'sample',[ctx],'false',ctx))

    def test_metric_absence_can_omit_event_subject(self):
        from research_rag.tests.test_atomic_assessment_cellfix11 import novel_metric
        _,p,ctx,raw = novel_metric()
        self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'not_enough_info')

    def test_direct_denial_stays_counterevidence(self):
        claim = 'The survey used paper forms.'
        ctx = 'The survey did not use any paper forms.'
        p = scoped(claim,'survey','used paper forms')
        raw = canonical(assessment([observation('survey','false',ctx)]),p,ctx)
        self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'contradict')


class RepairTests(unittest.TestCase):
    def test_received_bad_outputs_enter_bounded_repair(self):
        for cid in ('scope:entity:support','scope:entity:contradict','scope:condition:not_enough_info','scope:none:not_enough_info'):
            claim,p,ctx,bad = received(cid)
            _,_,_,good = repaired(cid)
            dec = {'parts':[{k:p[k] for k in ('quote','quantifier','scope')}], 'unresolved':[]}
            result,_ = run([dec,bad,good],claim,ctx,max_calls=8,max_attempts=2,max_new_tokens=1536,timeout_seconds=180)
            self.assertEqual(result['backend_calls'],3)
            self.assertEqual(result['stop_reason'],'completed')
            self.assertIsNotNone(result['trace'][1]['validation_issue'])

    def test_repeated_wrong_output_stays_incomplete(self):
        claim,p,ctx,bad = received('scope:entity:contradict')
        dec = {'parts':[{k:p[k] for k in ('quote','quantifier','scope')}], 'unresolved':[]}
        result,_ = run([dec,bad,bad],claim,ctx,max_calls=8,max_attempts=2,max_new_tokens=1536,timeout_seconds=180)
        self.assertIsNone(result['assessed_label'])
        self.assertEqual(result['stop_reason'],'invalid_output_exhausted')


class TokenTests(unittest.TestCase):
    setUp = h.AssessmentTokenFilterTests.setUp
    accepts = h.AssessmentTokenFilterTests.accepts
    ordered = h.AssessmentTokenFilterTests.ordered

    def test_real_traces_and_novel_paths_share_validator_constraints(self):
        for name,claim,p,ctx,raw,expected in token_paths():
            with self.subTest(name=name):
                self.assertEqual(self.accepts(self.ordered(raw),request(claim,p,ctx)),expected)
                if expected: a.assess_part(raw,p,ctx)
                else:
                    with self.assertRaises(ValueError): a.assess_part(raw,p,ctx)


if __name__ == '__main__':
    unittest.main()
