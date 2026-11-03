"""Real rejected human-review ledgers and novel identities; never validation30."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import unittest

from research_rag.tests.test_atomic_smoke_cellfix3 import scoped,request
from research_rag.tests.test_atomic_verifier import assessment,observation,run
from research_rag.tests.test_atomic_assessment_cellfix10 import canonical
from research_rag.tests import test_atomic_assessment_v8 as h

a=importlib.import_module('04_factchecker.inference.atomic_verifier')
m=importlib.import_module('04_factchecker.inference.assessment_members')
f=importlib.import_module('04_factchecker.inference.assessment_focus')
r=importlib.import_module('04_factchecker.inference.assessment_reporting')
d=importlib.import_module('04_factchecker.inference.atomic_decoding')
FAILED=('contract:irrelevant','scope:none:not_enough_info','scope:conjunction:support',
    'scope:conjunction:contradict','scope:conjunction:not_enough_info','scope:condition:not_enough_info')


def real_ledgers():
    rows=json.loads((Path(__file__).parent/'fixtures/atomic_cellfix12_full39_traces.json').read_bytes())
    found=[]
    for row in rows:
        if row['case']['example_id'] not in FAILED:continue
        for t in row['result']['trace']:
            if t['stage']=='decompose':continue
            p=json.loads(t['messages'][1]['content'])
            found.append((row['case']['example_id'],p['claim'],p['part'],p['context'],deepcopy(t['output'])))
    return found


def empty_target(p,ctx):
    return canonical(assessment([],scope='unknown',missing=[r.missing_reason(p,ctx)]),p,ctx)


def repaired(cid,p,ctx,raw):
    if m.target_absent(p,ctx):return empty_target(p,ctx)
    raw=deepcopy(raw)
    obs=raw['observations'][0]
    obs['member']='Silver' if cid=='scope:none:not_enough_info' else 'low-temperature group'
    obs['truth']='unknown'
    obs['quotes']=m.member_absence_quotes(p,obs['member'],ctx) or f.absence_quotes(p,ctx)
    raw['missing_information']=[r.missing_reason(p,ctx)]
    return canonical(raw,p,ctx)


def novel_absent():
    claim='The Willow router reduced queue latency.'
    ctx='The workload used 6.2 megabytes. Queue latency declined from 46 to 29 milliseconds.'
    p=scoped(claim,'Willow router','queue latency')
    bad=canonical(assessment([observation('6.2 megabytes','unknown',ctx)],missing=['target_binding_unresolved']),p,ctx)
    return claim,p,ctx,bad,empty_target(p,ctx)


def novel_name():
    claim='None of the monitored valves leaked during the pressure test.'
    ctx="Copper, Jade and Onyx were monitored during the pressure test. Copper and Jade had no leaks, but Onyx's leak status was not reported."
    p=scoped(claim,'monitored valves','leaked',quantifier='none',time='during the pressure test')
    quote=ctx.split('. ')[1]
    raw=canonical(assessment([observation('Onyx','unknown',quote)],missing=['measurement_unreported']),p,ctx)
    return claim,p,ctx,raw


def novel_group():
    claim='Every cartridge in the dry-storage group gained capacity after flushing.'
    ctx='The dry-storage group included two cartridges, but no capacity changes were reported for that group. All wet-storage cartridges gained capacity after flushing.'
    p=scoped(claim,'cartridge','capacity',quantifier='all',time='after flushing',condition='in the dry-storage group')
    raw=canonical(assessment([observation('dry-storage group','unknown',ctx.split('. ')[0]+'.')]),p,ctx)
    return claim,p,ctx,raw


def novel_month():
    claim='Every weekly trial conducted in November improved throughput.'
    ctx='Every October trial improved throughput. The report contains no throughput results for the weekly trials conducted in November.'
    p=scoped(claim,'weekly trial','throughput',quantifier='all',condition='in November')
    quote=ctx.split('. ')[1]
    raw=canonical(assessment([observation('the weekly trials conducted in November','unknown',quote)]),p,ctx)
    return claim,p,ctx,raw


def token_paths():
    paths=[]
    for i,(cid,claim,p,ctx,bad) in enumerate(real_ledgers()):
        paths.extend([(cid+'_'+str(i)+'_bad',claim,p,ctx,bad,False),
            (cid+'_'+str(i)+'_fixed',claim,p,ctx,repaired(cid,p,ctx,bad),True)])
    claim,p,ctx,bad,good=novel_absent()
    paths.extend([('novel_unbound_quantity',claim,p,ctx,bad,False),('novel_empty_identity',claim,p,ctx,good,True)])
    for case in (novel_name,novel_group):
        claim,p,ctx,good=case()
        paths.append((case.__name__+'_valid',claim,p,ctx,good,True))
        bad=deepcopy(good)
        bad['observations'][0]['member']="Onyx's leak status was not" if case is novel_name else 'no capacity changes were'
        paths.append((case.__name__+'_fragment',claim,p,ctx,bad,False))
    claim,p,ctx,raw=novel_month()
    paths.append(('novel_month_absence_quote',claim,p,ctx,raw,True))
    bad=deepcopy(raw);bad['observations'][0]['quotes']=[]
    paths.append(('novel_month_absence_cannot_be_omitted',claim,p,ctx,bad,False))
    return paths


class IdentityTests(unittest.TestCase):
    def test_received_six_cases_nine_bad_records_rejected(self):
        samples=real_ledgers();self.assertEqual(len(samples),9)
        for cid,_,p,ctx,bad in samples:
            with self.subTest(cid=cid,part=p['quote']):
                with self.assertRaises(ValueError):a.assess_part(bad,p,ctx)
                good=repaired(cid,p,ctx,bad)
                checked=a.assess_part(good,p,ctx)
                self.assertEqual(checked['assessed_label'],'not_enough_info')
                self.assertEqual(bad['observations'][0]['truth'],'unknown')
                if m.target_absent(p,ctx):self.assertEqual(checked['observations'],[])

    def test_absent_target_does_not_invent_workload_or_quantity_member(self):
        _,p,ctx,bad,good=novel_absent()
        with self.assertRaisesRegex(ValueError,'unresolved_target_requires_empty_ledger'):a.assess_part(bad,p,ctx)
        result=a.assess_part(good,p,ctx)
        self.assertEqual(result['observations'],[])
        self.assertEqual(result['scope_match'],'unknown')
        self.assertEqual(result['missing_reason'],'target_binding_unresolved')
        self.assertIn('Willow router',result['missing_information'][0])

    def test_empty_unbound_scope_cannot_claim_matched(self):
        _,p,ctx,_,good=novel_absent();good['scope_match']='matched'
        with self.assertRaisesRegex(ValueError,'unresolved_target_scope_unknown'):a.assess_part(good,p,ctx)

    def test_unbound_target_requires_explicit_missing_reason(self):
        _,p,ctx,_,good=novel_absent();good['missing_information']=[]
        with self.assertRaisesRegex(ValueError,'unresolved_target_missing_information'):a.assess_part(good,p,ctx)

    def test_unbound_target_cannot_fabricate_coverage(self):
        _,p,ctx,_,good=novel_absent()
        good['coverage']={'complete':False,'members':['The workload'],'quotes':[ctx]}
        with self.assertRaises(ValueError):a.assess_part(good,p,ctx)

    def test_model_identifier_with_digits_is_still_an_entity(self):
        claim='Detector P4 improved precision.';ctx='Detector P4 precision was not measured.'
        p=scoped(claim,'Detector P4','precision')
        raw=canonical(assessment([observation('Detector P4','unknown',ctx)],missing=['measurement_unreported']),p,ctx)
        self.assertFalse(m.target_absent(p,ctx))
        self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'not_enough_info')

    def test_generic_absence_without_target_is_not_a_named_entity(self):
        _,p,_,_,_=novel_absent();ctx='No queue latency was reported.'
        raw=empty_target(p,ctx)
        self.assertEqual(a.assess_part(raw,p,ctx)['observations'],[])

    def test_proper_named_unknown_member_preserves_its_absence_quote(self):
        _,p,ctx,raw=novel_name()
        self.assertIsNone(m.member_identity_issue(p,'Onyx','unknown',ctx))
        self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'not_enough_info')
        self.assertTrue(m.member_absence_quotes(p,'Onyx',ctx))

    def test_named_unknown_cannot_drop_direct_status_absence(self):
        _,p,ctx,raw=novel_name();raw['observations'][0]['quotes']=[]
        with self.assertRaisesRegex(ValueError,'missing_evidence_quote_required'):a.assess_part(raw,p,ctx)

    def test_all_proper_name_clause_prefixes_are_not_member_aliases(self):
        _,p,ctx,raw=novel_name()
        for member in ("Onyx's","Onyx's leak","Onyx's leak status","Onyx's leak status was","Onyx's leak status was not",'leak status was not'):
            bad=deepcopy(raw);bad['observations'][0]['member']=member
            with self.assertRaises(ValueError,msg=member):a.assess_part(bad,p,ctx)

    def test_group_absence_prefixes_cannot_be_members(self):
        _,p,ctx,raw=novel_group()
        for member in ('no capacity','no capacity changes','no capacity changes were','capacity changes were reported'):
            bad=deepcopy(raw);bad['observations'][0]['member']=member
            with self.assertRaises(ValueError,msg=member):a.assess_part(bad,p,ctx)
        self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'not_enough_info')

    def test_unknown_population_nominals_and_scope_modifiers_remain_valid(self):
        p=scoped('Every weekly trial conducted in August improved recall.','weekly trial','recall',quantifier='all',condition='in August')
        ctx='The weekly trials conducted in August had no recall results.'
        for member in ('weekly trials','The weekly trials conducted in August'):
            self.assertIsNone(m.member_identity_issue(p,member,'unknown',ctx))

    def test_direct_month_absence_has_a_legal_quote_and_cannot_be_dropped(self):
        _,p,ctx,raw=novel_month()
        self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'not_enough_info')
        raw['observations'][0]['quotes']=[]
        with self.assertRaisesRegex(ValueError,'missing_evidence_quote_required'):a.assess_part(raw,p,ctx)

    def test_incomplete_population_and_numeric_prefix_are_not_fake_entities(self):
        p=scoped('Every validation shard improved recall.','validation shard','recall',quantifier='all')
        ctx='Two validation shards improved recall. The complete set of validation shards was not identified.'
        for member in ('Two validation shards','The complete set of validation shards'):
            self.assertIsNone(m.member_identity_issue(p,member,'unknown',ctx))

    def test_foreign_group_member_still_rejected(self):
        _,p,ctx,raw=novel_group();raw['observations'][0]['member']='wet-storage cartridges'
        with self.assertRaisesRegex(ValueError,'observation_scope_mismatch'):a.assess_part(raw,p,ctx)

    def test_qualified_non_population_cannot_be_unknown_member(self):
        p=scoped('Every certified sensor improved recall.','certified sensor','recall',quantifier='all')
        ctx='The non-certified sensors had no recall results.'
        self.assertEqual(m.member_identity_issue(p,'non-certified sensors','unknown',ctx),'observation_scope_mismatch')

    def test_conflicting_member_outcomes_not_hidden_by_absence_quote(self):
        _,p,ctx,_=novel_name()
        ctx+=' Onyx leaked during the pressure test.'
        self.assertEqual(m.member_absence_quotes(p,'Onyx',ctx),[])

    def test_known_closed_population_and_none_polarity_preserved(self):
        from research_rag.tests.test_atomic_assessment_cellfix9 import PopulationTests
        for q in ('all','some','none'):
            claim,p,ctx,raw=PopulationTests().sample(q)
            if q=='some':continue
            self.assertIn(a.assess_part(canonical(raw,p,ctx),p,ctx)['assessed_label'],('support','contradict'))


class RepairTests(unittest.TestCase):
    def test_real_bad_ledgers_repair_inside_existing_budget(self):
        samples=real_ledgers()
        for cid in FAILED:
            rows=[s for s in samples if s[0]==cid]
            _,claim,_,ctx,_=rows[0]
            dec={'parts':[{k:p[k] for k in ('quote','quantifier','scope')} for _,_,p,_,_ in rows],'unresolved':[]}
            outputs=[dec]
            for _,_,p,_,bad in rows:outputs.extend([bad,repaired(cid,p,ctx,bad)])
            result,_=run(outputs,claim,ctx,max_calls=8,max_attempts=2,max_new_tokens=1536,timeout_seconds=180)
            self.assertEqual(result['assessed_label'],'not_enough_info')
            self.assertEqual(result['backend_calls'],1+2*len(rows))
            self.assertEqual(len(result['parts']),len(rows))

    def test_absent_target_repairs_without_inventing_member(self):
        claim,p,ctx,bad,good=novel_absent();dec={'parts':[{k:p[k] for k in ('quote','quantifier','scope')}],'unresolved':[]}
        result,_=run([dec,bad,good],claim,ctx,max_calls=8,max_attempts=2,max_new_tokens=1536,timeout_seconds=180)
        self.assertEqual((result['assessed_label'],result['backend_calls']),('not_enough_info',3))
        self.assertEqual(result['parts'][0]['observations'],[])

    def test_repeated_invalid_identity_is_incomplete_not_accepted_nei(self):
        claim,p,ctx,bad,_=novel_absent();dec={'parts':[{k:p[k] for k in ('quote','quantifier','scope')}],'unresolved':[]}
        result,_=run([dec,bad,bad],claim,ctx,max_calls=8,max_attempts=2,max_new_tokens=1536,timeout_seconds=180)
        self.assertIsNone(result['assessed_label']);self.assertEqual(result['stop_reason'],'invalid_output_exhausted')


class TokenTests(unittest.TestCase):
    setUp=h.AssessmentTokenFilterTests.setUp
    accepts=h.AssessmentTokenFilterTests.accepts
    ordered=h.AssessmentTokenFilterTests.ordered

    def test_decoder_and_validator_agree_on_real_and_novel_members(self):
        for name,claim,p,ctx,raw,expected in token_paths():
            with self.subTest(name=name):
                self.assertEqual(self.accepts(self.ordered(raw),request(claim,p,ctx)),expected)
                if expected:a.assess_part(raw,p,ctx)
                else:
                    with self.assertRaises(ValueError):a.assess_part(raw,p,ctx)


if __name__=='__main__':unittest.main()
