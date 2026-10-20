"""Real cf7 failures and new development sentences; no validation outcomes."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import unittest

from lmformatenforcer import JsonSchemaParser, CharacterLevelParserConfig, TokenEnforcer, TokenEnforcerTokenizerData
from research_rag.tests.test_atomic_smoke_cellfix3 import scoped, request
from research_rag.tests.test_atomic_verifier import assessment, observation, run
from research_rag.tests import test_atomic_assessment_v8 as h

a = importlib.import_module('04_factchecker.inference.atomic_verifier')
d = importlib.import_module('04_factchecker.inference.atomic_decoding')
rules = importlib.import_module('04_factchecker.inference.assessment_decisions')
CheckedParser = importlib.import_module('04_factchecker.inference.decoder_parser').CheckedParser
alphabet_tree = importlib.import_module('04_factchecker.inference.decoder_parser').alphabet_tree


class ParserTests(unittest.TestCase):
    def setup_enforcer(self, strict=True, extra=''):
        alphabet = ''.join(chr(i) for i in range(32,127)) + extra
        self.mapping = {v:i for i,v in enumerate(alphabet)}
        vocabulary = [(i,v,False) for v,i in self.mapping.items()]
        vocabulary.append((len(vocabulary),'内存',False))
        self.bad = len(vocabulary)-1
        self.eos = len(vocabulary)
        config = CharacterLevelParserConfig(alphabet=alphabet, max_consecutive_whitespaces=4)
        parser = JsonSchemaParser(d.obj({'explanation':d.bounded_text(64)}),config=config)
        if strict: parser = CheckedParser(parser, filtered_cache=True)
        data = TokenEnforcerTokenizerData(vocabulary,lambda ids:''.join(vocabulary[i][1] for i in ids if i<self.eos),self.eos,False,self.eos+1)
        enforcer = TokenEnforcer(data,parser)
        if strict: enforcer.tokenizer_tree = alphabet_tree(enforcer.tokenizer_tree,config)
        enforcer.root_parser.config = config
        return enforcer

    def feed(self,enforcer,text):
        ids=[self.eos]
        for char in text:
            token=self.mapping[char]
            self.assertIn(token,enforcer.get_allowed_tokens(ids).allowed_tokens)
            ids.append(token)
        return ids

    def test_old_freetext_cache_accepts_out_of_alphabet_and_early_eos(self):
        old=self.setup_enforcer(False)
        ids=self.feed(old,'{"explanation":"Context confirms the claim about Model Juniper using 25% less')
        self.assertIn(self.bad,old.get_allowed_tokens(ids).allowed_tokens)
        ids.append(self.bad)
        self.assertIn(self.eos,old.get_allowed_tokens(ids).allowed_tokens)

    def test_checked_parser_rejects_the_same_token_and_early_eos(self):
        enforcer=self.setup_enforcer()
        ids=self.feed(enforcer,'{"explanation":"Context confirms the claim about Model Juniper using 25% less')
        allowed=enforcer.get_allowed_tokens(ids).allowed_tokens
        self.assertNotIn(self.bad,allowed)
        self.assertNotIn(self.eos,allowed)

    def test_64_character_boundary_closes_json_instead_of_stopping(self):
        enforcer=self.setup_enforcer()
        text='{"explanation":"'+'x'*64
        ids=self.feed(enforcer,text)
        allowed=enforcer.get_allowed_tokens(ids).allowed_tokens
        self.assertNotIn(self.mapping['x'],allowed)
        self.assertNotIn(self.eos,allowed)
        for char in '"}':
            self.assertIn(self.mapping[char],enforcer.get_allowed_tokens(ids).allowed_tokens)
            ids.append(self.mapping[char])
        self.assertIn(self.eos,enforcer.get_allowed_tokens(ids).allowed_tokens)

    def test_unicode_in_config_is_preserved_and_no_premature_eos(self):
        enforcer=self.setup_enforcer(extra='é')
        ids=self.feed(enforcer,'{"explanation":"Résumé confirmed."}')
        self.assertIn(self.eos,enforcer.get_allowed_tokens(ids).allowed_tokens)

    def test_whitespace_boundary_cannot_escape_the_current_string(self):
        enforcer=self.setup_enforcer()
        ids=self.feed(enforcer,'{"explanation":"Word    ')
        allowed=enforcer.get_allowed_tokens(ids).allowed_tokens
        self.assertNotIn(self.mapping[' '],allowed)
        self.assertNotIn(self.eos,allowed)
        self.assertIn(self.mapping['"'],allowed)

    def test_json_escapes_remain_available_without_backslash_in_alphabet(self):
        enforcer=self.setup_enforcer()
        config=enforcer.root_parser.config
        config.alphabet=config.alphabet.replace('\\','')
        enforcer.tokenizer_tree=alphabet_tree(enforcer.tokenizer_tree,config)
        ids=self.feed(enforcer,json.dumps({'explanation':'A "quoted" result.'},separators=(',',':')))
        self.assertIn(self.eos,enforcer.get_allowed_tokens(ids).allowed_tokens)


class ScopedMissingTests(unittest.TestCase):
    def sample(self):
        claim='On the Falcon corpus, the parser reduced latency.'
        context='The parser reduced latency on the Falcon corpus. Results on other corpora are unknown.'
        part=scoped(claim,'parser','latency',condition='On the Falcon corpus')
        good=assessment([observation('parser','true','The parser reduced latency on the Falcon corpus.')])
        return claim,part,context,good

    def test_real_bounded_scope_trace_is_rejected_not_silently_promoted(self):
        rows=json.loads((Path(__file__).parent/'fixtures/atomic_cellfix7_smoke_traces.json').read_text())
        row=next(r for r in rows if r['case']['example_id']=='contract:bounded_scope')
        t=row['result']['trace'][-1];p=json.loads(t['messages'][1]['content'])
        with self.assertRaisesRegex(ValueError,'irrelevant_missing_information'):
            a.assess_part(t['output'],p['part'],p['context'])
        self.assertEqual(t['output']['missing_information'],['structural information about other datasets'])

    def test_new_scoped_claim_does_not_require_other_corpora(self):
        _,p,ctx,good=self.sample()
        self.assertEqual(a.assess_part(good,p,ctx)['assessed_label'],'support')
        bad=deepcopy(good);bad['missing_information']=['Results on other corpora.']
        with self.assertRaisesRegex(ValueError,'irrelevant_missing_information'):a.assess_part(bad,p,ctx)

    def test_missing_and_wrong_conditions_remain_unknown(self):
        _,p,_,_=self.sample()
        for ctx in ('The parser reduced latency on the Heron corpus.',
                    'The parser latency on the Falcon corpus was not reported.',
                    'The parser might reduce latency on the Falcon corpus.'):
            self.assertIsNone(rules.decision_evidence(p,ctx))
            raw=assessment([observation('parser','unknown',ctx)],missing=['In-scope latency result.'])
            self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'not_enough_info')

    def test_conditional_extra_arguments_and_quantities_are_not_forced(self):
        p=scoped('The parser reduced latency.','parser','latency')
        for ctx in ('The parser reduced latency on a tiny corpus.',
                    'The parser reduced latency only if caching was enabled.',
                    'The parser reduced latency by 12%.',
                    'Another parser reduced latency.',
                    'The parser planned to reduce latency.'):
            self.assertIsNone(rules.decision_evidence(p,ctx),ctx)

    def test_conflicting_in_scope_reports_keep_unknown(self):
        _,p,ctx,_=self.sample()
        ctx += ' The parser did not reduce latency on the Falcon corpus.'
        self.assertIsNone(rules.decision_evidence(p,ctx))

    def test_explicit_scoped_denial_is_counterevidence_not_missing(self):
        _,p,_,_=self.sample()
        ctx='The parser did not reduce latency on the Falcon corpus.'
        raw=assessment([observation('parser','false',ctx)])
        self.assertEqual(a.assess_part(raw,p,ctx)['assessed_label'],'contradict')

    def test_truncated_json_repairs_without_increasing_budget(self):
        from research_rag.tests.test_atomic_verifier import ModelOutputError
        claim,p,ctx,good=self.sample()
        decomposition={'parts':[{k:p[k] for k in ('quote','quantifier','scope')}],'unresolved':[]}
        broken='{"scope_match":"matched","coverage":'
        result,_=run([decomposition,ModelOutputError('Invalid JSON',broken),good],claim,ctx,
            max_calls=8,max_attempts=2,max_new_tokens=1536,timeout_seconds=180)
        self.assertEqual(result['assessed_label'],'support')
        self.assertEqual(result['backend_calls'],3)
        self.assertEqual(result['trace'][1]['raw_output'],broken)

    def test_new_trace_repair_succeeds_and_exhaustion_is_bounded(self):
        claim,p,ctx,good=self.sample()
        decomposition={'parts':[{k:p[k] for k in ('quote','quantifier','scope')}],'unresolved':[]}
        bad=deepcopy(good);bad['missing_information']=['Unrelated corpus results.']
        result,_=run([decomposition,bad,good],claim,ctx)
        self.assertEqual(result['assessed_label'],'support')
        self.assertEqual(result['backend_calls'],3)
        self.assertEqual(result['trace'][1]['validation_issue'],'irrelevant_missing_information')
        result,_=run([decomposition,bad,bad],claim,ctx)
        self.assertIsNone(result['assessed_label'])
        self.assertEqual(result['stop_reason'],'invalid_output_exhausted')
        self.assertEqual(result['backend_calls'],3)

    def test_decoder_rejects_out_of_scope_missing_and_keeps_genuine_missing(self):
        claim,p,ctx,good=self.sample()
        tester=h.AssessmentTokenFilterTests();tester.setUp()
        self.assertTrue(tester.accepts(tester.ordered(good),request(claim,p,ctx)))
        bad=deepcopy(good);bad['missing_information']=['Other corpora.']
        self.assertFalse(tester.accepts(tester.ordered(bad),request(claim,p,ctx)))
        ctx='The parser latency on the Falcon corpus was not measured.'
        raw=assessment([observation('parser','unknown',ctx)],missing=['In-scope latency result.'])
        self.assertTrue(tester.accepts(tester.ordered(raw),request(claim,p,ctx)))


if __name__=='__main__':unittest.main()
