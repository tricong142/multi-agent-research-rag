"""Member-local absence regressions. Scripted records are not model predictions."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import unittest

from research_rag.tests.test_atomic_decoding import token_backend, Sequence
from research_rag.tests import test_atomic_assessment_v8 as h
from research_rag.tests.test_atomic_assessment_cellfix10 import canonical
from research_rag.tests.test_atomic_smoke_cellfix3 import scoped
from research_rag.tests.test_atomic_verifier import assessment, observation

a = importlib.import_module('04_factchecker.inference.atomic_verifier')
f = importlib.import_module('04_factchecker.inference.assessment_focus')
m = importlib.import_module('04_factchecker.inference.assessment_members')


def received():
    data = json.loads((Path(__file__).parent/'fixtures/atomic_cellfix14_member_absence.json').read_bytes())
    return data['claim'], data['part'], data['context'], data['outputs']


def novel(quantifier='none'):
    prefix = {'none':'None of the', 'all':'All', 'some':'Some'}[quantifier]
    claim = prefix+' inspected vessels leaked during the trial.'
    context = ('Copper, Zinc and Quartz were inspected during the trial. '
               "Copper and Zinc had no leaks, but Quartz's leak status was not reported.")
    p = scoped(claim, 'inspected vessels', 'leaked', quantifier=quantifier, time='during the trial')
    raw = canonical(assessment([observation('Quartz','unknown',context.split('. ',1)[1])]), p, context)
    return claim, p, context, raw


def token_paths():
    claim, p, context, outputs = received()
    paths = [('received_attempt_'+str(i+1),claim,p,context,raw,False) for i,raw in enumerate(outputs)]
    good = deepcopy(outputs[0]);good['observations'][0].update(member='Silver', truth='unknown')
    paths.append(('silver_unknown',claim,p,context,good,True))
    for truth in ('true','false'):
        bad = deepcopy(good);bad['observations'][0]['truth'] = truth
        paths.append(('silver_'+truth+'_blocked',claim,p,context,bad,False))
    # Distinct members with actual negative observations must stay reachable.
    for member in ('Blue','Green'):
        known = deepcopy(good);known['observations'][0].update(member=member, truth='false')
        paths.append((member.lower()+'_known_false',claim,p,context,known,True))
    for quantifier in ('none','all','some'):
        claim,p,context,raw = novel(quantifier)
        paths.append(('novel_'+quantifier+'_unknown',claim,p,context,raw,True))
        for truth in ('true','false'):
            bad = deepcopy(raw);bad['observations'][0]['truth'] = truth
            paths.append(('novel_'+quantifier+'_'+truth+'_blocked',claim,p,context,bad,False))
    return paths


class MemberLocalAbsenceTests(unittest.TestCase):
    def test_received_invalid_records_are_rejected_by_validator(self):
        _,p,context,outputs = received()
        for raw in outputs:
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError,'missing_evidence_is_not_false'):
                a.assess_part(raw,p,context)

    def test_corrected_silver_is_nei(self):
        _,p,context,outputs = received()
        raw = deepcopy(outputs[0]);raw['observations'][0].update(member='Silver', truth='unknown')
        self.assertEqual(a.assess_part(raw,p,context)['assessed_label'], 'not_enough_info')

    def test_guard_is_member_local_not_population_wide(self):
        _,p,context,_ = received()
        self.assertTrue(m.member_absence_quotes(p,'Silver',context))
        for member in ('Blue','Green'):
            self.assertFalse(m.member_absence_quotes(p,member,context))
            self.assertIsNone(f.observation_focus_issue(p,member,[context.split('. ',1)[1]],'false',context))

    def test_other_predicate_absence_does_not_block_known_leak(self):
        _,p,_,_ = novel()
        context = "Quartz leaked during the trial. Quartz's temperature was not reported."
        self.assertFalse(m.member_absence_quotes(p,'Quartz',context))
        self.assertIsNone(f.observation_focus_issue(p,'Quartz',['Quartz leaked during the trial.'],'true',context))

    def test_competing_same_member_fact_is_not_hidden(self):
        _,p,context,_ = novel()
        context += ' Quartz leaked during the trial.'
        self.assertFalse(m.member_absence_quotes(p,'Quartz',context))
        self.assertIsNone(f.observation_focus_issue(p,'Quartz',['Quartz leaked during the trial.'],'true',context))

    def test_unknown_requires_its_own_absence_quote(self):
        _,p,context,_ = novel()
        self.assertEqual(f.observation_focus_issue(p,'Quartz',[],'unknown',context),'missing_evidence_quote_required')
        self.assertIsNotNone(f.observation_focus_issue(p,'Quartz',[context.split('. ')[0]+'.'],'unknown',context))

    def test_novel_quantifiers_stay_nei(self):
        for quantifier in ('none','all','some'):
            _,p,context,raw = novel(quantifier)
            with self.subTest(quantifier=quantifier):
                self.assertEqual(a.assess_part(raw,p,context)['assessed_label'],'not_enough_info')

    def test_actual_lmfe_paths_match_validator_contract(self):
        backend = token_backend()
        for name,claim,p,context,raw,expected in token_paths():
            with self.subTest(name=name):
                messages = [{'role':'system','content':a.ASSESS_PROMPT},
                            {'role':'user','content':json.dumps({'claim':claim,'part':p,'context':context})}]
                callback = backend.generation_options(messages)['prefix_allowed_tokens_fn']
                ids = Sequence([ord('P')]);accepted = True
                for char in h.AssessmentTokenFilterTests().ordered(raw):
                    if ord(char) not in callback(0,ids):
                        accepted = False;break
                    ids.append(ord(char))
                if accepted:accepted = 0 in callback(0,ids)
                self.assertEqual(accepted,expected)


if __name__ == '__main__':
    unittest.main()
