"""Real cf10 traces and new scope/absence/causality cases, never validation30."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import unittest

from research_rag.tests.test_atomic_smoke_cellfix3 import scoped,request
from research_rag.tests.test_atomic_verifier import assessment,observation,run
from research_rag.tests import test_atomic_assessment_v8 as h

a=importlib.import_module('04_factchecker.inference.atomic_verifier')
d=importlib.import_module('04_factchecker.inference.atomic_decoding')
f=importlib.import_module('04_factchecker.inference.assessment_focus')
r=importlib.import_module('04_factchecker.inference.assessment_reporting')


def trace(cid):
    rows=json.loads((Path(__file__).parent/'fixtures/atomic_cellfix10_full39_traces.json').read_bytes())
    row=next(v for v in rows if v['case']['example_id']==cid)
    t=next(v for v in reversed(row['result']['trace']) if v['stage']!='decompose')
    return deepcopy(t['output']),json.loads(t['messages'][1]['content'])


def repaired(raw,p,ctx,member=None):
    raw=deepcopy(raw)
    raw['missing_information']=[r.missing_reason(p,ctx)]
    for obs in raw['observations']:
        if member:obs['member']=member
        quotes=f.absence_quotes(p,ctx)
        if quotes:obs['quotes']=[quotes[0]]
    return raw


def novel_metric():
    claim='The revision increased specificity.'
    ctx='Sensitivity rose from 0.62 to 0.78 after the revision. Specificity was not measured.'
    p=scoped(claim,'revision','specificity')
    raw=assessment([observation('revision','unknown','Specificity was not measured.')],missing=['measurement_unreported'])
    return claim,p,ctx,raw


def novel_group():
    claim='Every chamber in the cold-storage group gained yield after the revision.'
    ctx='The cold-storage group contained three chambers, but no yield changes were measured for that group. All measured hot-storage chambers gained yield after the revision.'
    p=scoped(claim,'chamber','yield',quantifier='all',time='after the revision',condition='in the cold-storage group')
    raw=assessment([observation('cold-storage group','unknown',ctx.split('. ')[0]+'.')])
    return claim,p,ctx,raw


class CausalTests(unittest.TestCase):
    def test_received_causal_missing_names_the_missing_relation(self):
        raw,payload=trace('contract:causality_missing');p,ctx=payload['part'],payload['context']
        with self.assertRaisesRegex(ValueError,'missing_evidence_quote_required|missing_reason_binding'):
            a.assess_part(raw,p,ctx)
        result=a.assess_part(repaired(raw,p,ctx),p,ctx)
        self.assertEqual(result['assessed_label'],'not_enough_info')
        self.assertEqual(result['missing_reason'],'causal_relationship')
        self.assertIn('causal relationship',result['missing_information'][0])
        self.assertIn(p['quote'],result['missing_information'][0])
        self.assertEqual(raw['observations'][0]['quotes'],[])

    def test_new_cooccurrence_does_not_establish_causality(self):
        claim='The polymer caused the conductivity increase.'
        ctx='The polymer and increased conductivity were observed together. The experiment did not establish a causal link.'
        p=scoped(claim,'polymer','conductivity')
        raw=assessment([observation('polymer','unknown','The experiment did not establish a causal link.')],missing=['causal_relationship'])
        result=a.assess_part(raw,p,ctx)
        self.assertEqual(result['assessed_label'],'not_enough_info')
        self.assertEqual(result['missing_reason'],'causal_relationship')

    def test_new_led_to_predicate_preserves_causal_requirement(self):
        claim='The catalyst led to the efficiency increase.'
        ctx='The catalyst was tested alongside the efficiency increase.'
        p=scoped(claim,'catalyst','efficiency')
        raw=assessment([observation('catalyst','unknown',ctx)],missing=['causal_relationship'])
        self.assertEqual(a.assess_part(raw,p,ctx)['missing_reason'],'causal_relationship')

    def test_noncausal_claim_does_not_request_causal_evidence(self):
        claim='The polymer increased conductivity.'
        ctx='The polymer conductivity was not measured.'
        p=scoped(claim,'polymer','conductivity')
        self.assertEqual(r.missing_reason(p,ctx),'measurement_unreported')

    def test_missing_identity_precedes_the_causal_reason(self):
        p=scoped('The membrane caused the pressure increase.','membrane','pressure')
        self.assertEqual(r.missing_reason(p,'Pressure increased in the vessel.'),'target_binding_unresolved')


class QuoteTests(unittest.TestCase):
    def test_received_wrong_metric_quote_enters_repair(self):
        raw,payload=trace('scope:metric:not_enough_info');p,ctx=payload['part'],payload['context']
        with self.assertRaisesRegex(ValueError,'missing_evidence_quote_required'):
            a.assess_part(raw,p,ctx)
        result=a.assess_part(repaired(raw,p,ctx),p,ctx)
        self.assertEqual(result['assessed_label'],'not_enough_info')
        self.assertEqual(result['observations'][0]['quotes'],['Precision was not measured.'])

    def test_new_metric_selects_direct_absence_not_other_measurement(self):
        _,p,ctx,raw=novel_metric()
        self.assertEqual(f.absence_quotes(p,ctx),['Specificity was not measured.'])
        self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'not_enough_info')
        raw['observations'][0]['quotes']=[ctx.split('. ')[0]+'.']
        with self.assertRaisesRegex(ValueError,'missing_evidence_quote_required'):
            a.assess_part(raw,p,ctx)

    def test_no_quote_dodge_rejected_when_local_absence_is_explicit(self):
        _,p,ctx,raw=novel_metric();raw['observations'][0]['quotes']=[]
        with self.assertRaisesRegex(ValueError,'missing_evidence_quote_required'):
            a.assess_part(raw,p,ctx)

    def test_unknown_not_promoted_to_false_or_support(self):
        _,p,ctx,raw=novel_metric()
        for truth in ('true','false'):
            bad=deepcopy(raw);bad['observations'][0]['truth']=truth
            with self.assertRaises(ValueError):a.assess_part(bad,p,ctx)

    def test_known_and_absent_facts_keep_conflict_available(self):
        _,p,ctx,raw=novel_metric()
        # Opposed reported outcomes create conflict; absence alone is not denial.
        ctx+=' Specificity rose after the revision. Specificity fell after the revision.'
        self.assertEqual(f.absence_quotes(p,ctx),[])
        raw['observations'][0]['quotes']=[ctx]
        self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'not_enough_info')

    def test_known_metric_does_not_inherit_other_metrics_absence(self):
        claim='The revision increased specificity.'
        ctx='Specificity rose after the revision, but sensitivity was not measured.'
        p=scoped(claim,'revision','specificity')
        self.assertEqual(f.absence_quotes(p,ctx),[])

    def test_foreign_group_absence_cannot_supply_current_quote(self):
        claim,p,ctx,raw=novel_group()
        ctx='The cold-storage group was listed. Yield in the hot-storage group was not measured.'
        self.assertEqual(f.absence_quotes(p,ctx),[])

    def test_source_quote_punctuation_and_bytes_are_retained(self):
        _,p,ctx,raw=novel_metric()
        for quote in f.absence_quotes(p,ctx):self.assertIn(quote,ctx)
        bad=deepcopy(raw);bad['observations'][0]['quotes']=['Specificity was measured.']
        with self.assertRaisesRegex(ValueError,'quote_membership'):
            a.assess_part(bad,p,ctx)


class ScopeTests(unittest.TestCase):
    def test_received_foreign_unknown_member_is_rejected(self):
        raw,payload=trace('scope:condition:not_enough_info');p,ctx=payload['part'],payload['context']
        with self.assertRaisesRegex(ValueError,'observation_scope_mismatch'):
            a.assess_part(raw,p,ctx)
        result=a.assess_part(repaired(raw,p,ctx,'low-temperature group'),p,ctx)
        self.assertEqual(result['assessed_label'],'not_enough_info')
        self.assertIn('low-temperature',result['observations'][0]['member'])
        self.assertTrue(all('high-temperature' not in q for q in result['observations'][0]['quotes']))

    def test_new_cold_hot_scopes_filter_unknown_members(self):
        _,p,ctx,raw=novel_group()
        self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'not_enough_info')
        raw['observations'][0]['member']='All measured hot-storage chambers'
        with self.assertRaisesRegex(ValueError,'observation_scope_mismatch'):
            a.assess_part(raw,p,ctx)

    def test_new_wet_dry_conditions_are_also_scoped(self):
        claim='Every sample in the wet-season group improved recall.'
        ctx='The wet-season group recall was not measured. All dry-season samples improved recall.'
        p=scoped(claim,'sample','recall',quantifier='all',condition='in the wet-season group')
        raw=assessment([observation('dry-season samples','unknown',ctx)])
        with self.assertRaisesRegex(ValueError,'observation_scope_mismatch'):
            a.assess_part(raw,p,ctx)

    def test_generic_member_cannot_borrow_foreign_only_outcomes(self):
        p=scoped('Every chamber in the cold-storage group gained yield.','chamber','yield',quantifier='all',condition='in the cold-storage group')
        ctx='All hot-storage chambers gained yield.'
        raw=assessment([observation('chambers','unknown',ctx)])
        with self.assertRaisesRegex(ValueError,'observation_scope_mismatch'):
            a.assess_part(raw,p,ctx)

    def test_explicit_foreign_month_is_rejected_even_when_unknown(self):
        p=scoped('Every trial conducted in August improved recall.','trial','recall',quantifier='all',condition='in August')
        ctx='The trials conducted in September improved recall.'
        raw=assessment([observation('trials conducted in September','unknown',ctx)])
        with self.assertRaisesRegex(ValueError,'observation_scope_mismatch'):
            a.assess_part(raw,p,ctx)

    def test_before_result_cannot_be_unknown_witness_for_after_claim(self):
        p=scoped('Every chamber improved recall after the revision.','chamber','recall',quantifier='all',time='after the revision')
        ctx='The chamber improved recall before the revision.'
        raw=assessment([observation('chamber','unknown',ctx)])
        with self.assertRaisesRegex(ValueError,'observation_scope_mismatch'):
            a.assess_part(raw,p,ctx)

    def test_generic_member_resolves_with_its_local_in_scope_quote(self):
        p=scoped('Every chamber in the cold-storage group gained yield.','chamber','yield',quantifier='all',condition='in the cold-storage group')
        ctx='The cold-storage chambers yield was not measured. The hot-storage chambers gained yield.'
        raw=assessment([observation('chambers','unknown','The cold-storage chambers yield was not measured.')])
        self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'not_enough_info')

    def test_cross_sentence_member_cannot_merge_opposed_scopes(self):
        _,p,ctx,raw=novel_group()
        member='that group. All measured hot-storage'
        self.assertIn(member,ctx)
        raw['observations'][0]['member']=member
        with self.assertRaises(ValueError):a.assess_part(raw,p,ctx)


class RepairTests(unittest.TestCase):
    def test_bad_quote_repairs_in_existing_budget(self):
        claim,p,ctx,good=novel_metric()
        bad=deepcopy(good);bad['observations'][0]['quotes']=[ctx.split('. ')[0]+'.']
        dec={'parts':[{k:p[k] for k in ('quote','quantifier','scope')}],'unresolved':[]}
        result,_=run([dec,bad,good],claim,ctx,max_calls=8,max_attempts=2,max_new_tokens=1536,timeout_seconds=180)
        self.assertEqual((result['assessed_label'],result['backend_calls']),('not_enough_info',3))
        self.assertEqual(result['trace'][1]['validation_issue'],'missing_evidence_quote_required')
        self.assertEqual(result['trace'][1]['output'],bad)

    def test_bad_group_repairs_in_existing_budget(self):
        claim,p,ctx,good=novel_group()
        bad=deepcopy(good);bad['observations'][0]['member']='All measured hot-storage chambers'
        dec={'parts':[{k:p[k] for k in ('quote','quantifier','scope')}],'unresolved':[]}
        result,_=run([dec,bad,good],claim,ctx,max_calls=8,max_attempts=2,max_new_tokens=1536,timeout_seconds=180)
        self.assertEqual((result['assessed_label'],result['backend_calls']),('not_enough_info',3))

    def test_repair_exhaustion_stays_incomplete_not_accepted_nei(self):
        claim,p,ctx,good=novel_metric()
        bad=deepcopy(good);bad['observations'][0]['quotes']=[]
        dec={'parts':[{k:p[k] for k in ('quote','quantifier','scope')}],'unresolved':[]}
        result,_=run([dec,bad,bad],claim,ctx,max_calls=8,max_attempts=2,max_new_tokens=1536,timeout_seconds=180)
        self.assertIsNone(result['assessed_label'])
        self.assertEqual(result['stop_reason'],'invalid_output_exhausted')
        self.assertEqual(result['backend_calls'],3)


class TokenTests(unittest.TestCase):
    setUp=h.AssessmentTokenFilterTests.setUp
    accepts=h.AssessmentTokenFilterTests.accepts
    ordered=h.AssessmentTokenFilterTests.ordered

    def test_new_direct_metric_absence_is_decodable_wrong_quote_is_filtered(self):
        claim,p,ctx,raw=novel_metric();msg=request(claim,p,ctx)
        self.assertTrue(self.accepts(self.ordered(raw),msg))
        raw['observations'][0]['quotes']=[ctx.split('. ')[0]+'.']
        self.assertFalse(self.accepts(self.ordered(raw),msg))

    def test_received_three_failures_have_legal_repaired_paths(self):
        for cid in ('contract:causality_missing','scope:metric:not_enough_info','scope:condition:not_enough_info'):
            raw,payload=trace(cid);p,ctx=payload['part'],payload['context']
            good=repaired(raw,p,ctx,'low-temperature group' if cid.startswith('scope:condition') else None)
            self.assertTrue(self.accepts(self.ordered(good),request(payload['claim'],p,ctx)),cid)
            self.assertFalse(self.accepts(self.ordered(raw),request(payload['claim'],p,ctx)),cid)

    def test_foreign_only_context_has_an_honest_empty_unknown_path(self):
        claim='Every chamber in the cold-storage group gained yield.'
        ctx='All hot-storage chambers gained yield.'
        p=scoped(claim,'chamber','yield',quantifier='all',condition='in the cold-storage group')
        raw=assessment([],missing=['population_results_unresolved'],scope='unknown')
        self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'not_enough_info')
        self.assertTrue(self.accepts(self.ordered(raw),request(claim,p,ctx)))

    def test_local_unknown_path_keeps_scope_and_shared_decoder_rule(self):
        claim,p,ctx,good=novel_group();msg=request(claim,p,ctx)
        self.assertTrue(self.accepts(self.ordered(good),msg))
        bad=deepcopy(good);bad['observations'][0]['member']='All measured hot-storage chambers'
        self.assertFalse(self.accepts(self.ordered(bad),msg))


if __name__=='__main__':unittest.main()
