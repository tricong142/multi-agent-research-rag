"""Small source edits for the isolated cellfix6 candidate, based on audited cf5."""
from pathlib import Path


def replace_once(text, old, new):
    assert text.count(old) == 1, old[:120]
    return text.replace(old, new)


NUMERIC_HELPERS = r'''

# Cellfix6: one lexical rule for requirement extraction and operand validation.
_NON_UNITS = {'before', 'after', 'afterward', 'afterwards', 'previously',
    'subsequently', 'then', 'to', 'and', 'on', 'in', 'at', 'for', 'with', 'than', 'or'}

def metric_in_measurement(metric, proof):
    if re.search(r'(?<!\w)' + re.escape(metric) + r'(?!\w)', proof, re.I):
        return True
    # shortcut: a single intervening object modifier can be discharged by an
    # explicit "for the same <object plural>" clause, never by the claim itself.
    words = metric.split()
    if len(words) == 3:
        statistic, obj, head = words
        if (statistic.casefold() in {'median', 'mean', 'average', 'peak', 'maximum', 'minimum'}
                and re.search(r'\bfor the same\s+' + re.escape(obj) + r's\b', proof, re.I)
                and re.search(r'\b' + re.escape(statistic + ' ' + head) + r'\b', proof, re.I)
                and not re.search(r'\b(?:other|different)\s+' + re.escape(obj) + r's\b', proof, re.I)):
            return True
    return False

def change_scope(raw, metric):
    proof = raw['source_quote']
    if not metric:
        return proof, True
    # Preserve the before-and-after pair. Split only between measurements.
    pieces = [p.strip(' ,') for p in re.split(
        r';|[.!?](?=\s|$)|\b(?:while|whereas|but)\b|\band\b(?=\s+[A-Za-z][^.;]*?\bfrom\b)', proof, flags=re.I) if p.strip(' ,')]
    candidates = [p for p in pieces if _occurrences(raw['left']['quote'], p)
        and _occurrences(raw['right']['quote'], p) and (not metric or metric_in_measurement(metric, p))]
    if len(candidates) != 1:
        return proof, False
    selected = candidates[0]
    if selected != proof:
        # No stripping shared modality, negation or a later retraction.
        if re.search(_NUMERIC_MODAL + r'|\b(?:not|never|without|neither|retracted|incorrect|false|hypothetically)\b', proof, re.I):
            return proof, False
    return selected, True
'''


DECODER = r'''

# Cellfix6: use the same conservative passage and ordered-measurement checks.
from .assessment_rules import passage_issue
from .numeric_verifier import check_numeric
DECODER.update(policy='atomic-schema-decoding-v5-cellfix6',
    assessment_evidence_guards='explicit_absence_and_scope',
    ordered_metric_measurement_binding=True)
_cellfix5_schema = assessment_schema

def assessment_schema(claim, part, context):
    schema = _cellfix5_schema(claim, part, context)
    props = schema['properties']
    changes = []
    if not numeric_requirements(part['quote']) and direction(part['quote']):
        for passage in evidence_passages(context):
            operands = operand_schema(passage)
            for left in operands:
                for right in operands:
                    record = dict(kind='change', source_quote=passage,
                        left={k:v['enum'][0] for k,v in left['properties'].items()},
                        right={k:v['enum'][0] for k,v in right['properties'].items()})
                    result = check_numeric(record, part['quote'], context, metric=part['scope']['metric'])
                    if result['truth'] != 'unknown' and numeric_metric_matches(part,record,[]):
                        changes.append(obj({'kind':{'type':'string','enum':['change']},
                            'source_quote':{'type':'string','enum':[passage]},'left':left,'right':right}))
    kept = []
    for branch in props['observations']['items']['anyOf']:
        obs = branch['properties']
        if obs['truth']['enum'] == ['unknown']:
            kept.append(branch)
            continue
        quotes = [p for p in obs['quotes']['items'].get('enum',[]) if not passage_issue(part,p)]
        if not quotes:
            continue
        obs['quotes']['items'] = {'type':'string','enum':quotes}
        if not numeric_requirements(part['quote']) and direction(part['quote']):
            # Qualitative passages must stay representable even if unrelated
            # numerical evidence elsewhere in context cannot bind this metric.
            choices = ([{'type':'null'}] if any(not numeric_proof_required(part,[p]) for p in quotes) else [])
            if changes:
                record = changes[0] if len(changes)==1 else {'anyOf':changes}
                choices += [record,array(record,minimum=1,maximum=1)]
            if not choices:
                continue
            obs['numeric'] = {'anyOf':choices}
        kept.append(branch)
    props['observations']['items']['anyOf'] = kept
    return schema
'''


def apply_patch(root):
    root = Path(root)
    path = root/'04_factchecker/inference/numeric_verifier.py'
    text = path.read_text(encoding='utf-8')
    for literal in ("{'before', 'after', 'to', 'and', 'on', 'in', 'at', 'for', 'with', 'than', 'or'}",
                    "{'before', 'after', 'to', 'and', 'on', 'in', 'at', 'for', 'with', 'than'}"):
        text = replace_once(text, literal, '_NON_UNITS')
    text = replace_once(text, "    if unit and not (unit == '%'", "    if unit.casefold() in _NON_UNITS:\n        raise ValueError('numeric_unit_not_grounded')\n    if unit and not (unit == '%'")
    text = replace_once(text, "        return proof, bool(metric and metric.casefold() in proof.casefold())", "        return change_scope(raw, metric)")
    text = replace_once(text, "    if raw['kind'] != 'value':\n        return result\n    proof, bound = measurement_scope(raw, claim_part, metric)",
        "    proof, bound = measurement_scope(raw, claim_part, metric)\n    if raw['kind'] == 'change':\n        if not bound:\n            return {**result, 'truth':'unknown', 'reason':'numeric_metric_binding_unresolved'}\n        if proof != raw['source_quote']:\n            result = {**_cellfix2_numeric({**raw, 'source_quote':proof}, claim_part, context), 'input':raw}\n        return result")
    path.write_text(text + NUMERIC_HELPERS, encoding='utf-8')

    (root/'04_factchecker/inference/assessment_rules.py').write_bytes(
        Path(__file__).with_name('atomic_cellfix6_assessment_rules.py').read_bytes())
    path = root/'04_factchecker/inference/atomic_verifier.py'
    text = path.read_text(encoding='utf-8')
    old = "        checked.append({**obs, 'quotes': quotes, 'citation_additions': citation_additions,"
    new = "        issue = evidence_issue(part, member, quotes, truth)\n        if issue:\n            raise ValueError(issue)\n" + old
    text = replace_once(text, old, new)
    text += '''\n\nfrom .assessment_rules import evidence_issue, PROMPT
POLICY = 'atomic-verifier-constrained-v8-cellfix6'
ASSESS_PROMPT = PROMPT
REPAIR_HINTS.update(
    missing_evidence_is_not_false='Missing/unreported results are unknown, not false. Inspect the cited member and metric; use unknown/null with specific missing information.',
    observation_scope_mismatch='Use evidence for the SAME population, time and condition. An out-of-scope counterexample cannot decide this part.',
    observation_scope_binding_unresolved='Bind the witness to its own population clause. Cite the decisive local sentence and separate population evidence. Do not combine opposed groups.',
    observation_polarity_mismatch='The cited member has positive directional evidence, not a counterexample. Record predicate truth independently of whether population coverage is complete.',
    positive_predicate_before_quantifier='truth describes the positive predicate BEFORE NONE: a member that satisfies it is true and refutes NONE. An unreported member is unknown.')
'''
    path.write_text(text, encoding='utf-8')
    path = root/'04_factchecker/inference/atomic_decoding.py'
    path.write_text(path.read_text(encoding='utf-8') + DECODER, encoding='utf-8')
