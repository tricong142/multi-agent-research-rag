"""Actual failed traces and novel controls; scripted checks are not inference."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import unittest

a=importlib.import_module('04_factchecker.inference.atomic_verifier')
d=importlib.import_module('04_factchecker.inference.atomic_decoding')
q=importlib.import_module('04_factchecker.inference.numeric_verifier')
rules=importlib.import_module('04_factchecker.inference.cellfix16_rules')
runtime=importlib.import_module('04_factchecker.inference.cellfix14_runtime')


def cases():
    return {v['example_id'][-3:]:v for v in json.loads((Path(__file__).parent/'fixtures/cellfix15_validation30.json').read_bytes())}


def received(cid):
    c=cases()[cid]
    plan=a.normalize_decomposition(c['traces'][0]['raw_output'],c['claim'])
    raw=deepcopy(next(t['raw_output'] for t in c['traces'] if t['stage']!='decompose'))
    return c,plan['parts'][0],raw


def accepts(schema, text):
    from lmformatenforcer import JsonSchemaParser, CharacterLevelParserConfig
    CheckedParser=importlib.import_module('04_factchecker.inference.decoder_parser').CheckedParser
    config=CharacterLevelParserConfig();config.force_json_field_order=True
    config.alphabet+=''.join(sorted(set(text)-set(config.alphabet)))
    parser=CheckedParser(JsonSchemaParser(schema,config=config))
    try:
        for char in text:parser=parser.add_character(char)
    except ValueError:return False
    return parser.can_end()


class Cellfix16Tests(unittest.TestCase):
    def test_four_received_false_supports_blocked_in_both_layers(self):
        for cid in ('005','008','026','029'):
            with self.subTest(cid=cid), runtime.decode_request(None):
                c,p,raw=received(cid)
                with self.assertRaises(ValueError):a.assess_part(raw,p,c['context'])
                self.assertFalse(accepts(d.assessment_schema(c['claim'],p,c['context']),json.dumps(raw)))
                witness=rules.explicit_witness(p,c['context'])
                self.assertEqual(witness['truth'],'false')
                passage=next(q for q in sorted(d.evidence_passages(c['context']),key=len) if witness['quotes'][0] in q)
                raw['observations'][0].update(member=witness['members'][0],truth='false',quotes=[passage])
                self.assertEqual(a.assess_part(raw,p,c['context'])['assessed_label'],'contradict')
                self.assertTrue(accepts(d.assessment_schema(c['claim'],p,c['context']),json.dumps(raw)))

    def test_decomposition_bad_entities_blocked_and_repairs_reachable(self):
        entities={'009':'sentence','015':'prediction','020':'80 events','023':'eight named-entity categories','025':'proposed model'}
        for cid,entity in entities.items():
            c=cases()[cid];raw=deepcopy(c['traces'][0]['raw_output'])
            with self.subTest(cid=cid),runtime.decode_request(None):
                schema=d.decomposition_schema(c['claim'])
                self.assertEqual(accepts(schema,json.dumps(raw)),cid=='015')
                raw['parts'][-1]['scope']['entity']=entity
                a.normalize_decomposition(raw,c['claim'])
                self.assertTrue(accepts(schema,json.dumps(raw)))

    def test_postposed_quantifier_and_compound_count(self):
        c=cases()['021'];raw=c['traces'][0]['raw_output']
        a.normalize_decomposition(raw,c['claim'])
        self.assertTrue(accepts(d.decomposition_schema(c['claim']),json.dumps(raw)))
        c=cases()['010'];raw={'parts':[dict(quote=c['claim'],quantifier='atomic',scope=dict(entity='dataset',metric=c['claim'].split('dataset ',1)[1].rstrip('.'),time='',condition=''))],'unresolved':[]}
        self.assertEqual(len(a.normalize_decomposition(raw,c['claim'])['parts'][0]['numeric_requirements']),3)
        self.assertTrue(accepts(d.decomposition_schema(c['claim']),json.dumps(raw)))
        raw['parts'][0]['scope']['metric']='contains'
        self.assertFalse(accepts(d.decomposition_schema(c['claim']),json.dumps(raw)))

    def test_bibref_operand_path_and_qualitative_not(self):
        c,p,raw=received('007');record=raw['observations'][0]['numeric']
        record['right']=deepcopy(record['left'])
        with runtime.decode_request(None):
            self.assertTrue(accepts(d.assessment_schema(c['claim'],p,c['context']),json.dumps(raw)))
            self.assertEqual(a.assess_part(raw,p,c['context'])['assessed_label'],'support')
        for cid,gold in [('013','support'),('014','contradict')]:
            c,p,raw=received(cid)
            self.assertEqual(a.assess_part(raw,p,c['context'])['assessed_label'],gold)
        self.assertEqual(q.numeric_requirements('A score of 37.5 BLEU BIBREF42.')[0]['unit'],'BLEU')

    def test_compound_counts_bind_total_and_subset_separately(self):
        c=cases()['010'];part=dict(quote=c['claim'],quantifier='atomic',scope=dict(entity='dataset',metric=c['claim'].split('dataset ',1)[1].rstrip('.'),time='',condition=''))
        decisions=importlib.import_module('04_factchecker.inference.assessment_decisions')
        with runtime.decode_request(None):
            groups=decisions.numeric_choices(part,c['context'])
            self.assertEqual([{truth for _,truth in group} for group in groups],[{'true'},{'true'},{'true'}])
            total=deepcopy(groups[1][0][0]);total['right']=deepcopy(groups[2][0][0]['right'])
            self.assertEqual(q.check_numeric(total,part['quote'],c['context'],metric=part['scope']['metric'])['truth'],'unknown')

    def test_multi_quantity_binding_preserves_modifiers(self):
        c,p,raw=received('022')
        from research_rag.tests.test_atomic_verifier import observation
        source=next(s for s in d.evidence_passages(c['context']) if 'However, in this study' in s and '980 annotations in 670 tweets in Turkish.' in s)
        left=q.numeric_requirements(p['quote']);right=q.numeric_requirements(source)
        records={}
        for i,l in enumerate(left):
            r=next(r for r in right if r['value']==l['value'])
            records['q'+str(i)]=dict(kind='value',source_quote=source,left={k:l[k] for k in ('value','unit','quote')},right={k:r[k] for k in ('value','unit','quote')})
        raw['observations'][0].update(truth='true',quotes=[source],numeric=records)
        with runtime.decode_request(None):
            self.assertEqual(a.assess_part(raw,p,c['context'])['assessed_label'],'support')
            self.assertTrue(accepts(d.assessment_schema(c['claim'],p,c['context']),json.dumps(raw)))
        self.assertIsNotNone(rules.quantity_modifier_issue({**records['q1'],'source_quote':source.replace('Turkish','French')},p['quote'],c['context']))

    def test_collective_quote_survives_repair(self):
        c,p,raw=received('019');w=rules.population_witness(p,c['context'])
        raw['coverage']=dict(complete=True,members=w['members'],quotes=w['quotes'])
        raw['observations'][0].update(member=w['members'][0],truth='true',quotes=w['quotes'])
        with runtime.decode_request(None):
            self.assertEqual(a.assess_part(raw,p,c['context'])['assessed_label'],'support')
            self.assertTrue(accepts(d.assessment_schema(c['claim'],p,c['context']),json.dumps(raw)))
            raw['coverage']['members']=['Dataset']
            self.assertFalse(accepts(d.assessment_schema(c['claim'],p,c['context']),json.dumps(raw)))
        # The actual unknown retry must no longer discard this collective result.
        retry=c['traces'][-1]['raw_output']
        with self.assertRaises(ValueError):a.assess_part(retry,p,c['context'])

    def test_received_unbound_numeric_quote_and_wrong_coverage_blocked(self):
        c,p,raw=received('011')
        with runtime.decode_request(None):
            schema=d.assessment_schema(c['claim'],p,c['context'])
            self.assertFalse(accepts(schema,json.dumps(raw)))
            self.assertFalse(accepts(schema,json.dumps(c['traces'][-1]['raw_output'])))
            raw['observations'][0]['member']='14,769 actions'
            raw['observations'][0]['truth']='false'
            self.assertTrue(accepts(schema,json.dumps(raw)))
            self.assertEqual(a.assess_part(raw,p,c['context'])['assessed_label'],'contradict')

    def test_novel_relation_and_ambiguous_source(self):
        p=dict(quote='Sections 8-9 were the training set.',quantifier='atomic',scope=dict(entity='Sections 8-9',metric='were the training set',time='',condition=''))
        context='Corpus (Corpus hereafter). Sections 8-9 were the development set.'
        self.assertEqual(rules.explicit_witness(p,context)['truth'],'false')
        self.assertIsNone(rules.explicit_witness(p,context+' Sections 8-9 were the training set.'))
        self.assertIsNone(rules.explicit_witness(p,'Sections 8-9 were not the development set.'))


if __name__=='__main__':unittest.main()
