"""Regression contracts only; scripted outputs are never model accuracy."""
from copy import deepcopy
import importlib
import json
import time
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

q=importlib.import_module('04_factchecker.inference.numeric_verifier')
a=importlib.import_module('04_factchecker.inference.atomic_verifier')
d=importlib.import_module('04_factchecker.inference.atomic_decoding')
b=importlib.import_module('04_factchecker.inference.cellfix14_binding_rules')
t=importlib.import_module('04_factchecker.inference.cellfix14_runtime')
from research_rag.tests.test_atomic_smoke_cellfix3 import scoped
from research_rag.tests.test_atomic_decoding import token_backend,Sequence
from research_rag.tests.test_atomic_verifier import assessment,observation,numeric
from research_rag.tests.test_atomic_assessment_cellfix10 import canonical


def duration_case(duration='half-hour'):
    claim='The corpus contains 90 '+duration+' conversations.'
    context='The corpus contains 90 half-hour conversations.'
    p=scoped(claim,'corpus','contains 90 '+duration+' conversations')
    left=q.numeric_requirements(claim);right=q.numeric_requirements(context)
    records={f'q{i}':numeric('value',context,{k:l[k] for k in ('value','unit','quote')},
                           {k:r[k] for k in ('value','unit','quote')}) for i,(l,r) in enumerate(zip(left,right))}
    raw=canonical(assessment([observation('corpus','true' if duration=='half-hour' else 'false',context,records)]),p,context)
    return claim,p,context,raw


class QuantityTests(unittest.TestCase):
    def test_model_and_section_ids_are_not_measurements(self):
        for claim in ('Model R-7 achieved 82.4% WER.',
                      'Dataset sections 3-5 were used for 12 epochs.'):
            rows=q.numeric_requirements(claim)
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['value'],'82.4' if 'WER' in claim else '12')

    def test_compound_count_objects_are_kept(self):
        rows=q.numeric_requirements('The study annotated 920 name annotations in 610 Spanish tweets.')
        self.assertEqual([(r['value'],r['unit']) for r in rows],[('920','name annotations'),('610','Spanish tweets')])

    def test_count_and_duration_have_separate_bound_operands(self):
        for duration,value in [('half-hour','0.5'),('two-hour','2')]:
            source='The corpus contains 90 '+duration+' conversations.'
            rows=q.numeric_requirements(source)
            self.assertEqual([(r['value'],r['unit']) for r in rows],[('90','conversations'),(value,'hour')])
            for row in rows:
                operand={k:row[k] for k in ('value','unit','quote')}
                self.assertEqual(str(q._operand(operand,source)[0]),row['value'])
                bad=dict(operand,value='999')
                with self.assertRaises(ValueError):q._operand(bad,source)

    def test_plain_units_percentages_and_repeats_survive(self):
        rows=q.numeric_requirements('The trial used 24 participants and 24 controls with 81% accuracy.')
        self.assertEqual([r['value'] for r in rows],['24','24','81'])
        self.assertEqual([r['unit'] for r in rows],['participants','controls','%'])

    def test_duration_is_checked_in_addition_to_the_count(self):
        for duration,label in [('half-hour','support'),('two-hour','contradict')]:
            claim,p,context,raw=duration_case(duration)
            self.assertEqual(a.assess_part(raw,p,context)['assessed_label'],label)
            if duration=='two-hour':
                wrong=deepcopy(raw);wrong['observations'][0]['truth']='true'
                self.assertEqual(a.assess_part(wrong,p,context)['assessed_label'],'contradict')

    def test_explicit_partitive_keeps_its_count_object_without_crossing_sentences(self):
        for source in ('The corpus contains 800 events, of which 230 are visible.',
                       'The corpus contains 800 events, 230 of which are visible.'):
            rows=q.numeric_requirements(source)
            self.assertEqual([(v['value'],v['unit']) for v in rows],[('800','events'),('230','events')])
            self.assertEqual(q._operand({k:rows[1][k] for k in ('value','unit','quote')},source)[1],'events')
        source='There are 800 events. A model reached 230.'
        self.assertEqual(q.numeric_requirements(source)[-1]['unit'],'')

    def test_compound_count_accepts_extra_source_modifier_but_not_another_object(self):
        claim='The corpus contains 680 video clips.'
        for obj,expected in [('short video clips','true'),('audio clips','unknown')]:
            proof='The corpus contains 680 '+obj+'.'
            left=q.numeric_requirements(claim)[0];right=q.numeric_requirements(proof)[0]
            record=numeric('value',proof,{k:left[k] for k in ('value','unit','quote')},{k:right[k] for k in ('value','unit','quote')})
            self.assertEqual(q.check_numeric(record,claim,proof,metric='contains 680 video clips')['truth'],expected)


class BindingTests(unittest.TestCase):
    def test_shared_head_list_is_explicit_not_fuzzy(self):
        p=scoped('The BENCH Fr-It system reported BLEU.','BENCH Fr-It','BLEU')
        context='For BENCH It-Fr, Fr-It and Es-It we measure detokenized BLEU.'
        self.assertEqual(a.target_members(p,context),['Fr-It'])
        decisions=importlib.import_module('04_factchecker.inference.assessment_decisions')
        self.assertTrue(decisions.scope_supported(p,context))
        self.assertFalse(a.other_named_target(p,context))
        self.assertEqual(a.target_members(p,'For OTHER Fr-It we measure BLEU.'),[])

    def test_acronym_sections_and_apposition_require_source_anchor(self):
        p=scoped('CORP sections 3-5 were the dev set.','CORP sections 3-5','dev set')
        context='We used the annotated corpus CORP (CORP hereafter). Sections 3-5 were the dev set.'
        self.assertEqual(a.target_members(p,context),['Sections 3-5'])
        self.assertEqual(a.target_members(p,'We used OTHER. Sections 3-5 were the dev set.'),[])
        p=scoped('DIALOG transcriptions contain calls.','DIALOG transcriptions','calls')
        self.assertEqual(a.target_members(p,'DIALOG BIBREF7, transcriptions from telephone calls.'),['DIALOG'])

    def test_author_model_is_not_the_comparator(self):
        p=scoped('The proposed model is better than Baseline Z.','proposed model','better')
        self.assertEqual(a.target_members(p,'Our model is better than Baseline Z.'),['Our model'])
        self.assertEqual(a.target_members(p,'Baseline Z is better than another model.'),[])
        decomp=importlib.import_module('04_factchecker.inference.cellfix14_decomposition')
        self.assertEqual(decomp.subject_issue(dict(p['scope'],entity='Baseline Z'),p['quote']),'subject_comparator_inverted')

    def test_population_fragments_block_known_outcomes_too(self):
        p=scoped('Every event has a report.','event','has a report',quantifier='all')
        for truth in ('true','false','unknown'):
            self.assertEqual(b.nominal_issue(p,'Dataset Q is a small data set consisting',truth,'',lambda *_:None),
                             'observation_member_is_not_entity')

    def test_unstated_property_cannot_be_refuted(self):
        p=scoped('The articles were written in Italian.','articles','written in Italian')
        self.assertEqual(b.property_issue(p,'articles',['The events have related articles.'],'false','',lambda *_:None),
                         'property_evidence_missing')
        self.assertIsNone(b.property_issue(p,'articles',['The articles were written in French.'],'false','',lambda *_:None))

    def test_object_quantifier_belongs_to_object_population(self):
        decomp=importlib.import_module('04_factchecker.inference.cellfix14_decomposition')
        quote='The corpus used all 60 events for training.'
        self.assertEqual(decomp.subject_issue({'entity':'corpus'},quote),'quantified_population_required')
        self.assertIsNone(decomp.subject_issue({'entity':'events'},quote))


class DecoderTests(unittest.TestCase):
    def test_mixed_clause_quantifiers_have_legal_paths(self):
        claim='The model achieved 0.612 accuracy and each prediction took 12 milliseconds.'
        schema=d.decomposition_schema(claim)
        parts=schema['properties']['parts']['items']['anyOf']
        self.assertEqual([p['properties']['quantifier']['enum'] for p in parts],[['atomic'],['all']])
        output={'parts':[
            {'quote':'The model achieved 0.612 accuracy','quantifier':'atomic',
             'scope':{'entity':'model','metric':'accuracy','time':'','condition':''}},
            {'quote':'and each prediction took 12 milliseconds.','quantifier':'all',
             'scope':{'entity':'prediction','metric':'took 12 milliseconds','time':'','condition':''}}], 'unresolved':[]}
        self.assertEqual(len(a.normalize_decomposition(output,claim)['parts']),2)
        backend=token_backend()
        messages=[{'role':'system','content':a.DECOMPOSE_PROMPT},{'role':'user','content':json.dumps({'claim':claim})}]
        callback=backend.generation_options(messages)['prefix_allowed_tokens_fn'];ids=Sequence([ord('P')])
        for char in json.dumps(output,separators=(',',':')):
            self.assertIn(ord(char),callback(0,ids),char);ids.append(ord(char))
        self.assertIn(0,callback(0,ids))

    def test_noun_phrase_conjunction_does_not_force_fragment(self):
        claim='The corpus was used for development and hyperparameter optimization.'
        self.assertEqual(len(a.scope_clauses(claim)),1)
        output={'parts':[{'quote':claim,'quantifier':'atomic','scope':{
            'entity':'corpus','metric':'development and hyperparameter optimization','time':'','condition':''}}],'unresolved':[]}
        self.assertEqual(len(a.normalize_decomposition(output,claim)['parts']),1)

    def test_unfamiliar_predicates_still_require_separate_parts(self):
        claim='The lamp glowed and the mirror shattered.'
        self.assertEqual(len(a.scope_clauses(claim)),2)
        output={'parts':[{'quote':claim,'quantifier':'atomic','scope':{
            'entity':'lamp','metric':'glowed','time':'','condition':''}}],'unresolved':[]}
        with self.assertRaisesRegex(ValueError,'unsplit_conjunction'):a.normalize_decomposition(output,claim)
        self.assertEqual(len(a.scope_clauses('The corpus was used for development and the model vanished.')),2)


class RuntimeTests(unittest.TestCase):
    def test_cache_is_request_local_and_never_skips_deadline(self):
        hits=[]
        @t.cached
        def f(part):hits.append(1);return part['value']
        with t.decode_request(None):
            self.assertEqual(f({'value':3}),3);self.assertEqual(f({'value':3}),3)
        with t.decode_request(None):f({'value':3})
        self.assertEqual(len(hits),2)
        with self.assertRaises(a.CaseDeadlineExceeded):
            with t.decode_request(time.monotonic()-1):f({'value':3})

    def test_actual_filter_callback_enforces_deadline(self):
        backend=token_backend();claim='The lamp brightness increased.'
        messages=[{'role':'system','content':a.DECOMPOSE_PROMPT},{'role':'user','content':json.dumps({'claim':claim})}]
        with backend.generation_deadline(time.monotonic()+5):
            callback=backend.generation_options(messages)['prefix_allowed_tokens_fn']
            backend._case_deadline=time.monotonic()-1
            with self.assertRaises(a.CaseDeadlineExceeded):callback(0,Sequence([ord('P')]))

    def test_schema_failure_still_emits_usage_unknown(self):
        backend=token_backend();events=[];backend.on_generation=events.append
        with patch.object(backend,'generation_options',side_effect=a.CaseDeadlineExceeded()):
            with self.assertRaises(a.CaseDeadlineExceeded):backend.generate_json([],max_new_tokens=16)
        self.assertEqual(len(events),1)
        self.assertIsNone(events[0]['generated_tokens'])
        self.assertFalse(events[0]['usage_complete'])
        self.assertEqual(events[0]['failure_phase'],'schema')
        self.assertIn('schema',events[0]['phase_timings_ms'])

    def test_supervisor_terminates_only_its_stalled_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            code="import json,time,sys; from pathlib import Path; p=Path(sys.argv[2]); (p/'calls.jsonl').write_text(json.dumps({'event':'call_started','example_id':'stalled','case_deadline_unix':time.time()+.2})+'\\n'); time.sleep(30)"
            started=time.monotonic()
            result=t.run_worker([sys.executable,'-c',code,'--output-dir',tmp],10)
            self.assertEqual(result,124)
            self.assertLess(time.monotonic()-started,12)
            record=json.loads((Path(tmp)/'watchdog.json').read_text())
            self.assertEqual(record['stop_reason'],'case_watchdog_timeout')
            self.assertFalse(record['usage_complete'])


if __name__=='__main__':unittest.main()
