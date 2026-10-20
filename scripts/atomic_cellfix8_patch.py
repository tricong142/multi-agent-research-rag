"""Small cf8 patch on a copied, frozen cf7 workspace."""
from pathlib import Path
from scripts.atomic_cellfix7_patch import replace_once


PROPERTY_TRUTH = '''
    # Only the same explicit, root subject + verb + named property is decidable.
    # Require the source clause itself to carry every nonnumeric restriction.
    if (not numeric_requirements(part['quote']) and not numeric_requirements(text)
            and scope_supported(part,text)
            and re.fullmatch(r'[A-Za-z][A-Za-z -]*',metric)):
        verbs = r'(?:improved|increased|decreased|reduced|retained|maintained)'
        predicate = re.search(r'(?<!\\w)'+re.escape(member)+r'\\s+('
            +verbs+r')\\s+'+re.escape(metric)+r'(?!\\w)',part['quote'],re.I)
        if predicate:
            tail = part['quote'][predicate.end():].strip(' .,;:')
            for restriction in (part['scope']['time'],part['scope']['condition']):
                if restriction:
                    tail = re.sub(re.escape(restriction),'',tail,flags=re.I).strip(' .,;:')
            stem = {'improved':'improve','increased':'increase','decreased':'decrease',
                    'reduced':'reduce','retained':'retain','maintained':'maintain'}[predicate[1].lower()]
            for truth,verb in [('true',re.escape(predicate[1])),
                               ('false',r'did not '+stem)]:
                found = re.search(subject+verb+r'\\s+'+re.escape(metric)+r'(?!\\w)',text,re.I)
                if found:
                    source_tail = text[found.end():].strip(' .,;:')
                    for restriction in (part['scope']['time'],part['scope']['condition']):
                        if restriction:
                            source_tail = re.sub(re.escape(restriction),'',source_tail,flags=re.I).strip(' .,;:')
                    if not tail and not source_tail:
                        return truth
'''


def apply_patch(root):
    root = Path(root)
    path = root/'04_factchecker/inference/decoder_parser.py'
    path.write_bytes(Path(__file__).with_name('atomic_cellfix8_parser.py').read_bytes())
    path = root/'04_factchecker/inference/atomic_decoding.py'
    text = path.read_text(encoding='utf-8')
    text = replace_once(text,
        'enforcer = TokenEnforcer(self.tokenizer_data, JsonSchemaParser(schema, config=config))',
        'from .decoder_parser import CheckedParser, alphabet_tree\n        enforcer = TokenEnforcer(self.tokenizer_data, CheckedParser(JsonSchemaParser(schema, config=config), filtered_cache=True))\n        enforcer.tokenizer_tree = alphabet_tree(enforcer.tokenizer_tree, config)')
    text += '''

DECODER.update(policy='atomic-schema-decoding-v5-cellfix8',
    json_freetext_policy='character_checked_request_alphabet_cache',
    scoped_missing_information='reject_when_finite_witness_is_decisive')
_cellfix7_final_schema = assessment_schema

def assessment_schema(claim, part, context):
    schema = _cellfix7_final_schema(claim, part, context)
    if decision_evidence(part,context):
        schema['properties']['missing_information']['maxItems'] = 0
    return schema
'''
    path.write_text(text, encoding='utf-8')
    path = root/'04_factchecker/inference/assessment_decisions.py'
    text = path.read_text(encoding='utf-8')
    text = replace_once(text, "    return None\n\n\ndef decision_evidence", PROPERTY_TRUTH+"    return None\n\n\ndef decision_evidence")
    anchor = "        return 'decisive_witness_missing_or_unknown'\n    return None"
    text = replace_once(text, anchor,
        "        return 'decisive_witness_missing_or_unknown'\n    if raw['missing_information']:\n        return 'irrelevant_missing_information'\n    return None")
    path.write_text(text, encoding='utf-8')
    path = root/'04_factchecker/inference/atomic_verifier.py'
    text = path.read_text(encoding='utf-8')
    text += '''

POLICY = 'atomic-verifier-constrained-v8-cellfix8'
REPAIR_HINTS['irrelevant_missing_information'] = (
    'Reassess only the current subject, predicate, time and condition. '
    'Do not require measurements from other datasets, times or conjuncts '
    'when the in-scope witness already decides this part. Return [] if nothing '
    'required by this part is missing; do not remove genuinely absent facts.')
ASSESS_PROMPT += (
    '\\nMissing information must concern the current part only. Evidence for a '
    'tested condition does not require results for other conditions. If all '
    'requirements in this part are established, missing_information is []. '
    'Do not generalize a scoped result. Keep explanations short enough to '
    'finish a sentence before the 64-character limit.\\n')
'''
    path.write_text(text, encoding='utf-8')
