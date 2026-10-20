"""Patch only a new copy of the audited cf8 source; never mutate its release."""
from pathlib import Path
from scripts.atomic_cellfix7_patch import replace_once


def apply_patch(root):
    root = Path(root)
    (root/'04_factchecker/inference/assessment_evidence.py').write_bytes(
        Path(__file__).with_name('atomic_cellfix9_evidence.py').read_bytes())
    path = root/'04_factchecker/inference/assessment_rules.py'
    text = path.read_text(encoding='utf-8')
    text = replace_once(text, "    relevant = [p for p in own if contains(part['scope']['metric'], p) or _MISSING.search(p)] or pieces",
                        "    relevant = [p for p in own if contains(part['scope']['metric'], p) or _MISSING.search(p)] or own")
    text = replace_once(text, "    if truth == 'unknown':\n        return None\n    pieces =", "    if truth == 'unknown':\n        return None\n    from .assessment_evidence import citation_issue, population_witness\n    witness = population_witness(part, ' '.join(quotes))\n    if witness and member in witness['members'] and truth == witness['truth']:\n        return None\n    pieces =")
    text = replace_once(text, "    if relevant and all(_MISSING.search(p) for p in relevant):", "    scoped = relevant or pieces\n    if scoped and all(_MISSING.search(p) for p in scoped):")
    text = replace_once(text, "    if relevant and all(scope_conflict(part, p) for p in relevant):", "    if scoped and all(scope_conflict(part, p) for p in scoped):")
    text = replace_once(text, "    return None\n\n\ndef passage_issue", "    return citation_issue(part, member, quotes, truth)\n\n\ndef passage_issue")
    path.write_text(text, encoding='utf-8')
    # Three old fixtures tested arithmetic/coverage/conflict with evidence that
    # did not identify the claimed subject or predicate. Preserve their test
    # purpose with bound evidence; the new tests separately reject old inputs.
    path = root/'research_rag/tests/test_atomic_verifier.py'
    text = path.read_text(encoding='utf-8')
    text = replace_once(text,
        "            proof = f'Latency was 42 ms before tuning and {end} ms after tuning.'",
        "            proof = f'The service latency was 42 ms before tuning and {end} ms after tuning.'")
    text = replace_once(text,
        "        p = part('Some service improved latency.', quantifier='some')\n        raw = assessment([observation('A', 'false', context)], complete=True)",
        "        p = part('Some service improved.', quantifier='some', metric='improved')\n        raw = assessment([observation('A', 'true', context)], complete=True)")
    text = replace_once(text,
        "        raw = assessment([observation('A', 'true', 'A improved.'), observation('B', 'false', 'B worsened.')])\n        self.assertEqual(a.assess_part(raw, p, 'A improved. B worsened.')['assessed_label'], 'not_enough_info')",
        "        context = 'The service increased precision. The service did not increase precision.'\n        raw = assessment([observation('service', 'unknown', context)])\n        self.assertEqual(a.assess_part(raw, p, context)['assessed_label'], 'not_enough_info')")
    path.write_text(text, encoding='utf-8')
    path = root/'04_factchecker/inference/assessment_decisions.py'
    text = path.read_text(encoding='utf-8')
    text = replace_once(text, 'def decision_evidence(part, context):', 'def _legacy_decision_evidence(part, context):')
    marker = '\n\ndef assessment_issue(raw, part, context):'
    replacement = '''

def decision_evidence(part, context):
    from .assessment_evidence import population_witness, change_witness
    return (_legacy_decision_evidence(part,context) or population_witness(part,context)
            or change_witness(part,context))


def assessment_issue(raw, part, context):
    from .assessment_evidence import population_issue, missing_issue
    issue = population_issue(raw,part,context) or missing_issue(raw,part,context)
    if issue:
        return issue
'''
    text = replace_once(text, marker, replacement)
    path.write_text(text, encoding='utf-8')
    path = root/'04_factchecker/inference/atomic_verifier.py'
    text = path.read_text(encoding='utf-8')
    old = "    return bool(mentions) and name not in {m.casefold() for m in mentions}"
    new = '''    if mentions and name not in {m.casefold() for m in mentions}:
        return True
    # A leading identifier (West gateway) is not a suffix identifier (Model West).
    suffix = ' '.join(words[1:])
    prefixes = re.findall(r'(?<!\\w)([A-Z][\\w-]*)\\s+'+re.escape(suffix)+r'(?!\\w)',proof)
    return bool(words[0][:1].isupper() and prefixes and words[0].casefold() not in {p.casefold() for p in prefixes})'''
    text = replace_once(text, old, new)
    text += '''

POLICY = 'atomic-verifier-constrained-v8-cellfix9'
REPAIR_HINTS.update(
    observation_evidence_unbound='Cite the observation member and its predicate in the SAME local evidence. A different subject cannot supply its truth.',
    observation_predicate_not_grounded='A roster identifies members but does not establish the predicate. Cite actual member outcomes, not just the population list.',
    population_witness_missing='Use the explicit closed-population witness and its full outcome quote. Truth is the positive predicate before ALL/SOME/NONE.',
    population_closure_required='For a closed, completely reported population, coverage members must match observation members. A collective member requires the entire-population outcome quote.',
    missing_information_wrong_metric='Name missing evidence for this PART and metric only. Do not borrow another conjunct or an already reported metric.',
    unattributed_prose_citation='Remove invented author/year references. Use only facts and sources present in the input.',
    observation_polarity_mismatch='Inspect only the cited member outcome. Different members may have different outcomes; never borrow another member polarity.')
ASSESS_PROMPT += (
    '\\nCitations must bind member and predicate in their own local clauses. A roster '
    'alone is not an outcome. Do not select a date, update, bare number or other subject '
    'as a population member. For a closed population with an explicit collective '
    'result, use the exact collective source span provided by the schema, cite '
    'the whole population/result passage, and use that same span in coverage. '
    'For NONE, no leak means leaked=false; an actual leak means leaked=true. '
    'Never add an author/year reference absent from the input. Missing facts must '
    'refer to the current part, not another metric or a known source measurement.\\n')
'''
    path.write_text(text, encoding='utf-8')
    path = root/'04_factchecker/inference/atomic_decoding.py'
    text = path.read_text(encoding='utf-8')
    text += '''

from .assessment_evidence import citation_issue, population_witness
DECODER.update(policy='atomic-schema-decoding-v5-cellfix9',
    member_predicate_binding='local_clause_no_unrelated_fallback',
    population_coverage='explicit_closed_collective_witness',
    missing_information_scope='part_metric_and_source_reference')
_cellfix8_final_schema = assessment_schema

def assessment_schema(claim, part, context):
    schema = _cellfix8_final_schema(claim,part,context)
    props = schema['properties']
    population = population_witness(part,context)
    if population:
        truth = population['truth']
        complete = (part['quantifier']=='all' and truth=='true'
                    or part['quantifier'] in ('some','none') and truth=='false')
        member = {'type':'string','enum':population['members']}
        proof = {'type':'string','enum':population['quotes']}
        props['coverage'] = obj({'complete':{'const':bool(complete)},
            'members':array(member,minimum=1 if complete else 0,maximum=1 if complete else 0),
            'quotes':array(proof,minimum=1 if complete else 0,maximum=1 if complete else 0)})
        obs = obj({'member':member,'truth':{'type':'string','enum':[truth]},
            'quotes':array(proof,minimum=1,maximum=1),
            'explanation':bounded_text(ASSESSMENT_LIMITS['explanation_chars']),
            'numeric':{'type':'null'}})
        props['observations'] = array(obs,minimum=1,maximum=1)
        props['missing_information']['maxItems'] = 0
        return schema
    kept = []
    for branch in props['observations']['items']['anyOf']:
        obs = branch['properties']
        if obs['truth']['enum']==['unknown']:
            kept.append(branch)
            continue
        # Bind choices jointly, not independent member/quote enums. Otherwise
        # a legal member could still select another member's legal passage.
        def numeric_passages(value):
            if not isinstance(value,dict):
                return set()
            found = set(value.get('properties',{}).get('source_quote',{}).get('enum',[]))
            for item in value.values():
                if isinstance(item,dict):
                    found.update(numeric_passages(item))
                elif isinstance(item,list):
                    for sub in item:
                        found.update(numeric_passages(sub))
            return found
        ledger_quotes = numeric_passages(obs['numeric'])
        for member in obs['member'].get('enum',[]):
            quotes = [q for q in obs['quotes']['items'].get('enum',[])
                      if q in ledger_quotes or not citation_issue(part,member,[q],obs['truth']['enum'][0])]
            if not quotes:
                continue
            fixed = deepcopy(branch)
            fixed['properties']['member'] = {'type':'string','enum':[member]}
            fixed['properties']['quotes']['items'] = {'type':'string','enum':quotes}
            kept.append(fixed)
    if not kept:
        raise ValueError('unrepresentable_assessment_evidence')
    props['observations']['items']['anyOf'] = kept
    return schema
'''
    path.write_text(text, encoding='utf-8')
