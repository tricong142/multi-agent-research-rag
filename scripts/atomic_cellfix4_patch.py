"""Small source delta on the audited cellfix3 copy; released candidates stay intact."""


def apply_patch(root):
    path = root / '04_factchecker/inference/atomic_verifier.py'
    text = path.read_text(encoding='utf-8')
    changes = [
        ("                value = check_numeric(record, part['quote'], context, metric=part['scope']['metric'])",
         """                value = check_numeric(record, part['quote'], context, metric=part['scope']['metric'])
                member_scope = {**part, 'scope': {**part['scope'], 'entity': member}}
                if explicit_other_target(target_entity(member_scope), record['source_quote']):
                    raise ValueError('observation_target_mismatch')"""),
        ("quotes = _quotes(obs['quotes'], context, required=truth != 'unknown')",
         "quotes = list(_quotes(obs['quotes'], context, required=truth != 'unknown'))\n        citation_additions = []"),
        ("                if not any(record['source_quote'] in quote for quote in quotes):\n                    raise ValueError('numeric_evidence_not_cited')",
         """                if not any(record['source_quote'] in quote for quote in quotes):
                    # Numeric source_quote is already an explicit model citation.
                    # Verify exact membership before adding its redundant ledger entry.
                    _quotes([record['source_quote']], context, required=True)
                    quotes.append(record['source_quote'])
                    citation_additions.append(record['source_quote'])"""),
        ("        checked.append({**obs, 'model_truth': obs['truth'], 'truth': truth, 'numeric_result': numeric})",
         """        if (len(quotes) > limits['quotes_per_record']
                or any(len(q) > limits['quote_chars'] for q in quotes)):
            raise ValueError('assessment_length')
        checked.append({**obs, 'quotes': quotes, 'citation_additions': citation_additions,
                        'model_truth': obs['truth'], 'truth': truth, 'numeric_result': numeric})"""),
        ("def other_named_target(part, proof):",
         r"""def explicit_other_target(entity, proof):
    return bool(entity and re.search(r'\b(?:another|other|different|second|third)\s+'
        +re.escape(entity)+r'(?!\w)', proof, re.I))


def other_named_target(part, proof):"""),
        ("    if len(words)<2:\n        return False",
         """    if explicit_other_target(target_entity(part), proof):
        return True
    if len(words)<2:
        return False"""),
        ('Every source_quote must be included in this observation\'s quotes.',
         'Every source_quote must be an exact source passage. Code includes verified numeric citations in this observation\'s evidence ledger.'),
    ]
    for old, new in changes:
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    text += '''

POLICY = 'atomic-verifier-constrained-v8-cellfix4'
ASSESS_PROMPT += """

A numeric source_quote is itself an explicit evidence citation. The validator
checks its exact source membership, operands, target and measurement binding,
then includes it in the observation evidence ledger if missing from quotes.
This does not create checks or infer any missing quantity. Keep all conflicting
and qualitative evidence in quotes. Do not borrow another report's measurements.
All original evidence-length, quantity-coverage and repair budgets still apply.
"""
'''
    path.write_bytes(text.encode('utf-8'))
    path = root / '04_factchecker/inference/atomic_decoding.py'
    text = path.read_text(encoding='utf-8')
    text += "\nDECODER.update(policy='atomic-schema-decoding-v5-cellfix4', numeric_citation_ledger='verified_source_quote_union')\n"
    path.write_bytes(text.encode('utf-8'))
    # Keep this negative case negative: explicit second-report identity is now
    # rejected by the target guard, even if a model cites that report twice.
    path = root / 'research_rag/tests/test_atomic_contract_v5.py'
    text = path.read_text(encoding='utf-8')
    old = "with self.assertRaisesRegex(ValueError, 'numeric_evidence_not_cited'):"
    assert text.count(old) == 1
    path.write_bytes(text.replace(old, "with self.assertRaisesRegex(ValueError, 'observation_target_mismatch'):").encode('utf-8'))


TESTS = r'''
"""Citation ledger regression; synthetic tests are development, not held-out quality."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from research_rag.tests.test_atomic_verifier import a, n, part, observation, assessment, operand, numeric, run
from research_rag.tests import test_atomic_assessment_v8 as h


class CitationLedgerTests(unittest.TestCase):
    setUp = h.AssessmentTokenFilterTests.setUp
    accepts = h.AssessmentTokenFilterTests.accepts
    ordered = h.AssessmentTokenFilterTests.ordered

    def example(self):
        claim = 'The audit evaluated six systems on three corpora.'
        first = 'Six systems were evaluated in the audit.'
        second = 'Evaluation used three corpora.'
        p = part(claim, metric='evaluated six systems', condition='on three corpora')
        p['scope']['entity'] = 'audit'
        records = [numeric('value', first, operand('6','systems','six systems'), operand('6','systems','Six systems')),
                   numeric('value', second, operand('3','corpora','three corpora'), operand('3','corpora','three corpora'))]
        return claim, p, first + ' ' + second, assessment([observation('audit','true',first,records)])

    def request(self, claim, p, context):
        return [{'role':'system','content':a.ASSESS_PROMPT},
                {'role':'user','content':json.dumps({'claim':claim,'part':p,'context':context})}]

    def test_exact_failed_trace_uses_its_existing_numeric_citation_without_mutation(self):
        rows = json.loads((Path(__file__).parent/'fixtures/atomic_cellfix3_citation_traces.json').read_text())
        self.assertEqual(len(rows), 2)
        first, repaired = rows
        with self.assertRaisesRegex(ValueError, 'numeric_requirement_missing'):
            a.assess_part(first['output'], first['part'], first['context'])
        before = deepcopy(repaired['output'])
        result = a.assess_part(repaired['output'], repaired['part'], repaired['context'])
        self.assertEqual(result['assessed_label'], 'support')
        self.assertEqual(repaired['output'], before)
        obs = result['observations'][0]
        self.assertEqual(obs['citation_additions'], ['Evaluation used two datasets.'])
        self.assertEqual(len(obs['numeric_result']), 2)

    def test_novel_two_quantity_proofs_form_an_exact_replayable_ledger(self):
        claim, p, context, raw = self.example()
        self.assertTrue(self.accepts(self.ordered(raw), self.request(claim,p,context)))
        original = deepcopy(raw)
        result = a.assess_part(raw,p,context)
        self.assertEqual(result['assessed_label'],'support')
        self.assertEqual(raw,original)
        obs = result['observations'][0]
        self.assertEqual(obs['quotes'], [r['source_quote'] for r in raw['observations'][0]['numeric']])
        self.assertEqual(obs['citation_additions'], [raw['observations'][0]['numeric'][1]['source_quote']])
        repeated = a.assess_part(raw,p,context)
        self.assertEqual(repeated,result)

    def test_fully_cited_output_is_unchanged_and_never_duplicates_a_quote(self):
        claim,p,context,raw = self.example()
        raw['observations'][0]['quotes'] = [context]
        result = a.assess_part(raw,p,context)
        self.assertEqual(result['assessed_label'],'support')
        self.assertEqual(result['observations'][0]['quotes'],[context])
        self.assertEqual(result['observations'][0]['citation_additions'],[])

    def test_missing_or_duplicate_quantity_still_enters_repair(self):
        claim,p,context,raw = self.example()
        raw['observations'][0]['numeric'].pop()
        with self.assertRaisesRegex(ValueError,'numeric_requirement_missing'):
            a.assess_part(raw,p,context)
        raw['observations'][0]['numeric'] *= 2
        with self.assertRaisesRegex(ValueError,'duplicate_numeric_requirement'):
            a.assess_part(raw,p,context)

    def test_fabricated_numeric_source_cannot_become_a_citation(self):
        claim,p,context,raw = self.example()
        raw['observations'][0]['numeric'][1]['source_quote'] = 'Evaluation used thirty corpora.'
        with self.assertRaisesRegex(ValueError,'numeric_source_membership'):
            a.assess_part(raw,p,context)
        self.assertFalse(self.accepts(self.ordered(raw),self.request(claim,p,context)))

    def test_right_operand_must_be_in_the_supplied_numeric_source(self):
        claim,p,context,raw = self.example()
        raw['observations'][0]['numeric'][1]['source_quote'] = raw['observations'][0]['quotes'][0]
        with self.assertRaises(ValueError):
            a.assess_part(raw,p,context)
        self.assertFalse(self.accepts(self.ordered(raw),self.request(claim,p,context)))

    def test_explicit_other_target_cannot_supply_even_a_fully_cited_number(self):
        for modifier in ('another','other','different','second','third'):
            with self.subTest(modifier=modifier):
                claim,p,context,raw = self.example()
                proof = 'A '+modifier+' audit evaluated six systems on three corpora.'
                context += ' '+proof
                raw['observations'][0]['quotes'].append(proof)
                with self.assertRaisesRegex(ValueError,'observation_target_mismatch'):
                    a.assess_part(raw,p,context)
                # Even a legacy generic entity cannot borrow measurements for
                # an explicitly different observation member's event.
                raw['observations'][0]['quotes'] = [raw['observations'][0]['quotes'][0]]
                raw['observations'][0]['numeric'][0]['source_quote'] = proof
                raw['observations'][0]['numeric'][0]['right']['quote'] = 'six systems'
                p['scope']['entity'] = 'The'
                with self.assertRaisesRegex(ValueError,'observation_target_mismatch'):
                    a.assess_part(raw,p,context)

    def test_wrong_binding_is_not_repaired_by_citation_union(self):
        claim,p,context,raw = self.example()
        raw['observations'][0]['numeric'][1].update(
            source_quote=raw['observations'][0]['numeric'][0]['source_quote'],
            right=operand('6','systems','Six systems'))
        with self.assertRaisesRegex(ValueError,'numeric_metric_binding_unresolved'):
            a.assess_part(raw,p,context)

    def test_unknown_association_and_local_negation_keep_their_decisions(self):
        claim,p,context,raw = self.example()
        raw['observations'][0]['truth'] = 'unknown'
        self.assertEqual(a.assess_part(raw,p,context)['assessed_label'],'not_enough_info')
        claim = 'Model Larch retained 71% accuracy.'
        proof = 'Model Larch retained 63% accuracy, not 71%.'
        p = part(claim,metric='accuracy'); p['scope']['entity']='Model Larch'
        raw=assessment([observation('Model Larch','true',proof,
            numeric('value',proof,operand('71','%','71%'),operand('63','%','63%')))])
        self.assertEqual(a.assess_part(raw,p,proof)['assessed_label'],'contradict')

    def test_extra_qualitative_counterevidence_is_never_removed(self):
        claim,p,context,raw = self.example()
        extra = 'The audit did not establish comparable performance.'
        context += ' '+extra
        raw['observations'][0]['quotes'].append(extra)
        before=deepcopy(raw)
        result=a.assess_part(raw,p,context)
        self.assertEqual(raw,before)
        self.assertIn(extra,result['observations'][0]['quotes'])

    def test_union_keeps_existing_quote_count_and_length_limits(self):
        claim,p,context,raw = self.example()
        extras = ['The audit was reviewed.', 'The audit was published.', 'The audit was archived.']
        context += ' '+' '.join(extras)
        raw['observations'][0]['quotes'] += extras
        with self.assertRaisesRegex(ValueError,'assessment_length'):
            a.assess_part(raw,p,context)
        claim,p,context,raw = self.example()
        proof = 'Evaluation used three corpora '+('during review ' * 35)+'.'
        context += ' '+proof
        raw['observations'][0]['numeric'][1]['source_quote'] = proof
        with self.assertRaisesRegex(ValueError,'assessment_length'):
            a.assess_part(raw,p,context)

    def test_malformed_json_schema_is_rejected_before_citation_projection(self):
        claim,p,context,raw = self.example()
        for bad in ([], {}, {**raw, 'observations':[{}]}):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                a.assess_part(bad,p,context)

    def test_bounded_repair_replay_preserves_raw_output_and_all_budgets(self):
        claim,p,context,good = self.example(); bad=deepcopy(good)
        bad['observations'][0]['numeric'].pop()
        settings=dict(max_calls=8,max_attempts=2,max_new_tokens=1536,timeout_seconds=180)
        result,backend=run([{'parts':[p],'unresolved':[]},bad,good],claim,context,**settings)
        self.assertEqual(result['assessed_label'],'support')
        self.assertEqual(result['backend_calls'],3)
        self.assertEqual(result['trace'][-1]['output'],good)
        self.assertEqual(result['parts'][0]['observations'][0]['citation_additions'],
            [good['observations'][0]['numeric'][1]['source_quote']])
        from research_rag.evaluation import evaluate_atomic_verifier as e
        criteria={'policy':a.POLICY,'max_calls_per_case':8,'max_attempts':2,'max_new_tokens':1536,'case_deadline_seconds':180}
        self.assertEqual(e.replay_result(result,claim,context,criteria),'support')
        failed,_=run([{'parts':[p],'unresolved':[]},bad,bad],claim,context,**settings)
        self.assertEqual(failed['stop_reason'],'invalid_output_exhausted')
        self.assertIsNone(failed['assessed_label'])
        self.assertEqual(failed['backend_calls'],3)


if __name__ == '__main__':
    unittest.main()
'''
