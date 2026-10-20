"""Trace regressions and novel development sentences, never held-out outcomes."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import unittest

from research_rag.tests.test_atomic_smoke_cellfix3 import scoped, request
from research_rag.tests.test_atomic_verifier import assessment, observation, run
from research_rag.tests import test_atomic_assessment_v8 as h

a = importlib.import_module('04_factchecker.inference.atomic_verifier')
d = importlib.import_module('04_factchecker.inference.atomic_decoding')
e = importlib.import_module('04_factchecker.inference.assessment_evidence')
decisions = importlib.import_module('04_factchecker.inference.assessment_decisions')


def traces(case_id):
    path = Path(__file__).parent/'fixtures/atomic_cellfix8_full39_traces.json'
    row = next(v for v in json.loads(path.read_bytes()) if v['case']['example_id']==case_id)
    return [(t, json.loads(t['messages'][1]['content'])) for t in row['result']['trace'] if t['stage']!='decompose']


class BindingTests(unittest.TestCase):
    def test_received_north_label_has_only_south_quote_rejected(self):
        t, p = traces('scope:entity:support')[-1]
        with self.assertRaisesRegex(ValueError, 'observation_(?:target|evidence)'):
            a.assess_part(t['output'],p['part'],p['context'])

    def test_novel_prefix_and_suffix_named_targets(self):
        for entity, other in [('West relay','East relay'), ('Model Rowan','Model Larch')]:
            claim=f'The {entity} reduced latency.'
            context=f'The {entity} reduced latency. The {other} increased latency.'
            p=scoped(claim,entity,'latency')
            good=assessment([observation(entity,'true',context.split('.')[0]+'.')])
            self.assertEqual(a.assess_part(good,p,context)['assessed_label'],'support')
            self.assertTrue(a.other_named_target(p,context.split('. ')[1]))
            bad=deepcopy(good);bad['observations'][0]['quotes']=[context.split('. ')[1]]
            with self.assertRaises(ValueError):a.assess_part(bad,p,context)

    def test_roster_presence_cannot_borrow_other_subject_predicate(self):
        claim='The West relay reduced latency.'
        ctx='The West relay was listed. The East relay reduced latency.'
        p=scoped(claim,'West relay','latency')
        bad=assessment([observation('West relay','true',ctx)])
        with self.assertRaisesRegex(ValueError,'observation_predicate_not_grounded'):
            a.assess_part(bad,p,ctx)

    def test_roster_only_does_not_prove_leak(self):
        p=scoped('None of the inspected valves leaked.','inspected valves','leaked',quantifier='none')
        ctx='The inspected valves were Amber, Ivory and Slate.'
        bad=assessment([observation('Amber','true',ctx)])
        with self.assertRaisesRegex(ValueError,'observation_predicate_not_grounded'):
            a.assess_part(bad,p,ctx)

    def test_unknown_target_and_unknown_predicate_remain_unknown(self):
        claim='The West relay reduced latency.';ctx='The West relay latency was not measured.'
        p=scoped(claim,'West relay','latency')
        raw=assessment([observation('West relay','unknown',ctx)],missing=['The West relay latency result.'])
        self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'not_enough_info')

    def test_numeric_source_without_subject_is_not_a_bound_observation(self):
        from research_rag.tests.test_atomic_verifier import numeric, operand
        claim='The service reduced latency.'
        proof='Latency was 70 ms before tuning and 50 ms after tuning.'
        p=scoped(claim,'service','latency')
        raw=assessment([observation('service','true',proof,
            numeric('change',proof,operand('70','ms'),operand('50','ms')))])
        with self.assertRaisesRegex(ValueError,'observation_evidence_unbound'):
            a.assess_part(raw,p,'service. '+proof)


class PolarityTests(unittest.TestCase):
    def test_received_third_counterexample_does_not_borrow_two_improved(self):
        for t,p in traces('scope:universal:contradict'):
            raw=deepcopy(t['output']);raw['coverage']={'complete':False,'members':[],'quotes':[]}
            # The source and truth stay unchanged; only the unrelated coverage
            # assertion in the first model draft is removed for this unit test.
            self.assertEqual(a.assess_part(raw,p['part'],p['context'])['assessed_label'],'contradict')

    def test_new_counterexample_recalling_metric_and_named_clauses(self):
        claim='Every audit shard improved recall after the refresh.'
        ctx='The audit set consisted of exactly four shards. After the refresh, three improved recall, while the fourth became worse at recalling relevant records.'
        p=scoped(claim,'audit shard','recall',quantifier='all',time='after the refresh')
        raw=assessment([observation('the fourth','false',ctx)])
        self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'contradict')
        raw['observations'][0]['truth']='true'
        with self.assertRaises(ValueError):a.assess_part(raw,p,ctx)

    def test_none_truth_is_positive_predicate(self):
        claim='None of the inspected valves leaked.'
        ctx='The inspected valves were Amber, Ivory and Slate. Slate leaked; Amber and Ivory did not.'
        p=scoped(claim,'inspected valves','leaked',quantifier='none')
        good=assessment([observation('Slate','true',ctx)])
        self.assertEqual(a.assess_part(good,p,ctx)['assessed_label'],'contradict')
        bad=deepcopy(good);bad['observations'][0]['truth']='false'
        with self.assertRaises(ValueError):a.assess_part(bad,p,ctx)

    def test_out_of_scope_counterexample_is_not_decisive(self):
        claim='Every cycle conducted in June improved throughput.'
        p=scoped(claim,'cycle','throughput',quantifier='all',condition='in June')
        ctx='Exactly five cycles were conducted in June. Each of these five cycles improved throughput. A July cycle reduced throughput.'
        bad=assessment([observation('A July cycle','false',ctx)])
        with self.assertRaises(ValueError):a.assess_part(bad,p,ctx)

    def test_did_not_improve_is_not_misread_as_positive_improvement(self):
        p=scoped('Every probe improved.','probes','improved',quantifier='all')
        ctx='A probe did not improve.'
        raw=assessment([observation('A probe','false',ctx)])
        self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'contradict')


class PopulationTests(unittest.TestCase):
    def sample(self, quantifier='all', outcome='improved'):
        claim={'all':'Every inspected segment improved recall after the refresh.',
               'some':'At least one inspected segment reduced response time after the refresh.',
               'none':'None of the inspected valves leaked.'}[quantifier]
        if quantifier=='none':
            ctx='The inspected valves were Amber, Ivory and Slate. The report records no leaks for any of these three valves.'
            p=scoped(claim,'inspected valves','leaked',quantifier='none')
            member='Amber, Ivory and Slate';truth='false'
        else:
            ctx='The inspected set consisted of exactly four segments. Each of these four segments improved recall after the refresh.'
            p=scoped(claim,'inspected segment','recall',quantifier='all',time='after the refresh')
            member='four segments';truth='true'
        return claim,p,ctx,assessment([observation(member,truth,ctx)],complete=True)

    def test_uniform_closed_population_supports_all(self):
        _,p,ctx,raw=self.sample()
        self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'support')

    def test_explicit_no_leaks_supports_none(self):
        _,p,ctx,raw=self.sample('none')
        self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'support')

    def test_closed_all_false_refutes_some(self):
        claim='At least one inspected relay reduced response time after the refresh.'
        ctx='The inspected relays were Amber, Ivory and Slate. After the refresh, response time increased on Amber and Ivory and stayed unchanged on Slate.'
        p=scoped(claim,'inspected relay','response time',quantifier='some',time='after the refresh')
        raw=assessment([observation('Amber, Ivory and Slate','false',ctx)],complete=True)
        self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'contradict')

    def test_closed_collective_cannot_discard_coverage(self):
        _,p,ctx,raw=self.sample();raw['coverage']={'complete':False,'members':[],'quotes':[]}
        with self.assertRaisesRegex(ValueError,'population_closure_required'):a.assess_part(raw,p,ctx)

    def test_missing_member_result_never_invents_closure(self):
        claim='Every inspected segment improved recall.'
        ctx='The inspected segments were Amber, Ivory and Slate. Amber improved recall. The results for Ivory and Slate were not reported.'
        p=scoped(claim,'inspected segment','recall',quantifier='all')
        self.assertIsNone(e.population_witness(p,ctx))
        raw=assessment([observation('Amber','true',ctx)],missing=['Recall results for Ivory and Slate.'])
        self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'not_enough_info')

    def test_conflicting_member_results_do_not_create_uniform_witness(self):
        claim='Every inspected segment improved recall.'
        ctx='The inspected segments were Amber, Ivory and Slate. Each of these three segments improved recall. Slate worsened recall.'
        p=scoped(claim,'inspected segment','recall',quantifier='all')
        self.assertIsNone(e.population_witness(p,ctx))

    def test_no_explicit_closed_population_stays_unknown(self):
        claim='Every inspected segment improved recall.'
        ctx='Two inspected segments improved recall. No complete population list was reported.'
        p=scoped(claim,'inspected segment','recall',quantifier='all')
        self.assertIsNone(e.population_witness(p,ctx))

    def test_complete_individual_ledgers_still_work(self):
        claim='Every inspected valve improved recall.'
        ctx='The inspected valves were Amber, Ivory and Slate. Amber improved recall. Ivory improved recall. Slate improved recall.'
        p=scoped(claim,'inspected valve','recall',quantifier='all')
        raw=assessment([observation(name,'true',ctx) for name in ('Amber','Ivory','Slate')],complete=True)
        self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'support')

    def test_mismatched_count_and_names_do_not_close_population(self):
        claim='Every inspected valve improved recall.'
        ctx='The inspected set consisted of exactly four valves: Amber, Ivory and Slate. Each of these valves improved recall.'
        p=scoped(claim,'inspected valve','recall',quantifier='all')
        self.assertIsNone(e.population_witness(p,ctx))

    def test_qualified_population_negation_does_not_force_support(self):
        claim='Every certified probe improved recall.'
        ctx='The non-certified set consisted of exactly three probes. Each of these three probes improved recall.'
        p=scoped(claim,'certified probe','recall',quantifier='all')
        self.assertIsNone(e.population_witness(p,ctx))

    def test_missing_or_different_population_modifier_does_not_force(self):
        claim='Every copper probe improved recall.'
        p=scoped(claim,'copper probe','recall',quantifier='all')
        for label in ('silver','inspected'):
            ctx=f'The {label} set consisted of exactly three probes. Each of these three probes improved recall.'
            self.assertIsNone(e.population_witness(p,ctx))

    def test_explicitly_negated_predicate_is_outside_collective_shortcut(self):
        claim='Every inspected probe did not improve recall.'
        ctx='The inspected set consisted of exactly three probes. Each of these three probes improved recall.'
        p=scoped(claim,'inspected probe','recall',quantifier='all')
        self.assertIsNone(e.population_witness(p,ctx))

    def test_modality_and_missing_outcomes_do_not_create_collective_truth(self):
        claim='Every inspected probe improved recall.'
        p=scoped(claim,'inspected probe','recall',quantifier='all')
        for outcome in ('might improve recall','were expected to improve recall','had no recall results reported'):
            ctx='The inspected set consisted of exactly three probes. Each of these three probes '+outcome+'.'
            with self.subTest(outcome=outcome):self.assertIsNone(e.population_witness(p,ctx))

    def test_different_month_population_is_not_inherited(self):
        claim='Every cycle conducted in June improved recall.'
        ctx='Exactly four cycles were conducted in July. Each of these four cycles improved recall.'
        p=scoped(claim,'cycle','recall',quantifier='all',condition='in June')
        self.assertIsNone(e.population_witness(p,ctx))

    def test_incomplete_or_retracted_collective_statement_never_forces_truth(self):
        claim='Every inspected valve improved recall.'
        p=scoped(claim,'inspected valve','recall',quantifier='all')
        for ending in ('The recall result for the third valve was not reported.',
                       'This outcome was retracted as incorrect.'):
            ctx='The inspected set consisted of exactly three valves. Each of these valves improved recall. '+ending
            self.assertIsNone(e.population_witness(p,ctx))

    def test_collective_shortcut_never_bypasses_required_measurements(self):
        for claim,metric,outcome in [
            ('Every inspected valve reduced latency by 20%.','latency','reduced latency by 20%'),
            ('Every inspected valve reduced latency.','latency','reduced latency from 30 ms to 20 ms')]:
            ctx='The inspected set consisted of exactly three valves. Each of these valves '+outcome+'.'
            p=scoped(claim,'inspected valve',metric,quantifier='all')
            self.assertIsNone(e.population_witness(p,ctx))
            schema=d.assessment_schema(claim,p,ctx)
            self.assertTrue(any(v['properties']['truth']['enum']==['unknown']
                                for v in schema['properties']['observations']['items']['anyOf']))

    def test_different_event_cannot_borrow_time_from_roster(self):
        claim='Every inspected valve improved recall after the refresh.'
        p=scoped(claim,'inspected valve','recall',quantifier='all',time='after the refresh')
        ctx='After the refresh, the inspected set consisted of exactly three valves. Each of these valves improved recall after the overhaul.'
        self.assertIsNone(e.population_witness(p,ctx))

    def test_a_reported_subset_never_becomes_full_population_coverage(self):
        claim='Every inspected valve improved recall.'
        p=scoped(claim,'inspected valve','recall',quantifier='all')
        for outcome in ('Some of these three valves all improved recall.',
                        'Two valves were selected. Each of these valves improved recall.',
                        'Each of these two valves improved recall.'):
            ctx='The inspected set consisted of exactly three valves. '+outcome
            self.assertIsNone(e.population_witness(p,ctx))

    def test_unclosed_some_false_does_not_refute(self):
        claim='At least one inspected probe improved recall.'
        ctx='One inspected probe lost recall. The other results were not reported.'
        p=scoped(claim,'inspected probe','recall',quantifier='some')
        self.assertIsNone(e.population_witness(p,ctx))
        raw=assessment([observation('One inspected probe','false',ctx)],missing=['The other probe recall results.'])
        self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'not_enough_info')

    def test_real_scope_supports_have_collective_witnesses(self):
        for cid in ('scope:universal:support','scope:time:support','scope:condition:support','scope:none:support'):
            _,p=traces(cid)[-1]
            with self.subTest(cid=cid):self.assertIsNotNone(e.population_witness(p['part'],p['context']))


class MissingAndRepairTests(unittest.TestCase):
    def test_real_missing_wrong_metric_rejected(self):
        t,p=traces('contract:partial_memory')[0]
        with self.assertRaisesRegex(ValueError,'missing_information_wrong_metric'):
            a.assess_part(t['output'],p['part'],p['context'])

    def test_received_invented_author_year_rejected(self):
        t,p=traces('scope:direction:not_enough_info')[-1]
        with self.assertRaisesRegex(ValueError,'unattributed_prose_citation'):
            a.assess_part(t['output'],p['part'],p['context'])

    def test_novel_invented_citation_rejected_but_real_one_preserved(self):
        claim='The adapter reduced latency.';ctx='The adapter latency was not measured.'
        p=scoped(claim,'adapter','latency')
        raw=assessment([observation('adapter','unknown',ctx)],missing=['Rivera et al. (2022) did not report latency.'])
        with self.assertRaisesRegex(ValueError,'unattributed_prose_citation'):a.assess_part(raw,p,ctx)
        ctx+=' Rivera et al. (2022) reported that missing measurement.'
        self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'not_enough_info')

    def test_source_ordered_change_cannot_be_called_missing(self):
        claim='The configuration increased precision.'
        ctx='Precision fell from 0.91 to 0.84 after the configuration.'
        p=scoped(claim,'configuration','precision')
        self.assertEqual(decisions.decision_evidence(p,ctx)['truth'],'false')
        raw=assessment([observation('configuration','unknown',ctx)],missing=['Original precision.'])
        with self.assertRaisesRegex(ValueError,'decisive_witness'):a.assess_part(raw,p,ctx)

    def test_binding_enters_bounded_repair(self):
        claim='The West relay reduced latency.'
        ctx='The West relay reduced latency. The East relay increased latency.'
        p=scoped(claim,'West relay','latency')
        good=assessment([observation('West relay','true',ctx.split('.')[0]+'.')])
        bad=deepcopy(good);bad['observations'][0]['quotes']=[ctx.split('. ')[1]]
        dec={'parts':[{k:p[k] for k in ('quote','quantifier','scope')}],'unresolved':[]}
        result,_=run([dec,bad,good],claim,ctx,max_calls=8,max_attempts=2,max_new_tokens=1536,timeout_seconds=180)
        self.assertEqual(result['assessed_label'],'support');self.assertEqual(result['backend_calls'],3)
        result,_=run([dec,bad,bad],claim,ctx,max_calls=8,max_attempts=2,max_new_tokens=1536,timeout_seconds=180)
        self.assertIsNone(result['assessed_label']);self.assertEqual(result['stop_reason'],'invalid_output_exhausted')
        self.assertEqual(result['backend_calls'],3)


class TokenTests(unittest.TestCase):
    setUp=h.AssessmentTokenFilterTests.setUp
    accepts=h.AssessmentTokenFilterTests.accepts
    ordered=h.AssessmentTokenFilterTests.ordered

    def test_joint_binding_accepts_target_rejects_other_quote(self):
        claim='The West relay reduced latency.'
        ctx='The West relay reduced latency. The East relay increased latency.'
        p=scoped(claim,'West relay','latency')
        good=assessment([observation('West relay','true',ctx.split('.')[0]+'.')])
        self.assertTrue(self.accepts(self.ordered(good),request(claim,p,ctx)))
        good['observations'][0]['quotes']=[ctx.split('. ')[1]]
        self.assertFalse(self.accepts(self.ordered(good),request(claim,p,ctx)))

    def test_closed_collective_is_decodable_and_unknown_dodge_blocked(self):
        claim,p,ctx,raw=PopulationTests().sample()
        self.assertTrue(self.accepts(self.ordered(raw),request(claim,p,ctx)))
        bad=deepcopy(raw);bad['observations'][0]['truth']='unknown'
        self.assertFalse(self.accepts(self.ordered(bad),request(claim,p,ctx)))
        bad=deepcopy(raw);bad['coverage']={'complete':False,'members':[],'quotes':[]}
        self.assertFalse(self.accepts(self.ordered(bad),request(claim,p,ctx)))

    def test_none_closed_negative_truth_is_decodable(self):
        claim,p,ctx,raw=PopulationTests().sample('none')
        self.assertTrue(self.accepts(self.ordered(raw),request(claim,p,ctx)))
        raw['observations'][0]['truth']='true'
        self.assertFalse(self.accepts(self.ordered(raw),request(claim,p,ctx)))


if __name__=='__main__':unittest.main()
