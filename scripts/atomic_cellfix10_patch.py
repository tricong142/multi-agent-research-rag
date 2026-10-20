"""Apply the next candidate change to a new copy, retaining historical bytes."""
from pathlib import Path
from scripts.atomic_cellfix7_patch import replace_once


def apply_patch(root):
    root = Path(root)
    (root/'04_factchecker/inference/assessment_reporting.py').write_bytes(
        Path(__file__).with_name('atomic_cellfix10_reporting.py').read_bytes())
    path = root/'04_factchecker/inference/assessment_evidence.py'
    text = path.read_text(encoding='utf-8')
    old = """        if any(not contains(w,sentence) for w in part['scope']['entity'].split()[:-1]):
            continue"""
    new = """        # Reviewed convention: a unique 'complete <selection> set' roster
        # refers to the queried selected population. This is scoped discourse
        # binding, not a general set/entity alias. Keep it visible for review.
        selection = re.fullmatch(r'The complete (audited|inspected|monitored|tested|evaluated|surveyed) set (?:was|were) '
            r'[A-Z][\\w-]*(?:,\\s*[A-Z][\\w-]*)*(?:,?\\s+and\\s+[A-Z][\\w-]*)[.!]?', sentence)
        elliptical = bool(selection and part['scope']['entity'].casefold().startswith(selection[1]+' ')
            and len(re.findall(r'\\b(?:set|population|group)\\b',context,re.I))==1
            and not re.search(r'\\b(?:other|another|different|non-|not|except|subset|selected|remaining)\\b',context,re.I)
            and not re.search(r'\\b(?:these|those|they)\\s+(?:are|were)\\b',context,re.I))
        if not elliptical and any(not contains(w,sentence) for w in part['scope']['entity'].split()[:-1]):
            continue"""
    text = replace_once(text, old, new)
    text = replace_once(text, "'count': n, 'text': text}", "'count': n, 'text': text, 'binding_basis': 'unique_complete_selection_set' if elliptical else 'explicit_population'}")
    text = replace_once(text, "if head.endswith('y') else head+'es'", "if head.endswith('y') and len(head)>1 and head[-2] not in 'aeiou' else head+'es'")
    # Do not ignore a later in-scope correction. The existing 384-character
    # passage bound still refuses oversized collective shortcuts.
    text = replace_once(text, "sentences[i+1:i+3]", "sentences[i+1:]")
    path.write_text(text, encoding='utf-8')
    path = root/'04_factchecker/inference/atomic_verifier.py'
    text = path.read_text(encoding='utf-8')
    text += '''


POLICY = 'atomic-verifier-constrained-v8-cellfix10'
from .assessment_reporting import reporting_issue, render as render_assessment
_cellfix9_assess = assess_part
def assess_part(raw, part, context):
    result = _cellfix9_assess(raw,part,context)
    issue = reporting_issue(raw,part,context)
    if issue:
        raise ValueError(issue)
    return render_assessment(result,raw,part,context)
REPAIR_HINTS.update(
    duplicate_coverage_member='List each member once. For a closed population use the exact roster and its full outcomes; one false member alone cannot refute SOME.',
    population_closure_required='Retain the exact closed-population roster and all its results. Do not drop coverage on retry to evade a duplicate-member error.',
    missing_reason_binding='Choose the current part missing-reason code from the schema. Binding absence is not a missing measurement; another conjunct cannot supply this reason.',
    missing_information_wrong_metric='Use the current part missing-reason code. Do not describe another conjunct. If the target is absent use target_binding_unresolved.',
    unattributed_prose_citation='Use the schema evidence-note constants and missing-reason code. Do not generate author names or narrative.')
ASSESS_PROMPT += (
    '\\nREPORTING CONTRACT: Do not generate narrative prose. Observation explanation '
    'is exactly "Predicate evidence recorded."; assessment explanation is exactly '
    '"Assess the recorded evidence ledger.". missing_information is [] when the '
    'part is decided, otherwise choose the current part reason code allowed by '
    'the schema. Code renders the user explanation only after checking scope, '
    'truth, coverage and quantities. Do not change an unknown truth to obtain '
    'an answer. A complete false population refutes SOME, but one false member '
    'without closure does not. Keep evidence and closure during repair.\\n')
'''
    path.write_text(text, encoding='utf-8')
    path = root/'04_factchecker/inference/atomic_decoding.py'
    text = path.read_text(encoding='utf-8')
    text += '''


from .assessment_reporting import constrain_schema
DECODER.update(policy='atomic-schema-decoding-v5-cellfix10',
    prose='validated_ledger_renderer_v1',missing_information_scope='part_bound_reason_code')
_cellfix9_final_schema = assessment_schema
def assessment_schema(claim, part, context):
    return constrain_schema(_cellfix9_final_schema(claim,part,context),part,context)
'''
    path.write_text(text, encoding='utf-8')
    # Synthetic token-filter fixtures now speak the revised prose contract.
    # Ledger/polarity/quantity assertions are retained; no frozen case is edited.
    path = root/'research_rag/tests/test_atomic_verifier.py'
    text = path.read_text(encoding='utf-8')
    text = replace_once(text, "'explanation': 'Synthetic fixture evidence.'", "'explanation': 'Predicate evidence recorded.'")
    text = replace_once(text, "'explanation': 'Synthetic fixture, not a model prediction.'", "'explanation': 'Assess the recorded evidence ledger.'")
    path.write_text(text, encoding='utf-8')
    path = root/'research_rag/tests/test_atomic_assessment_v8.py'
    text = path.read_text(encoding='utf-8')
    text = replace_once(text, "missing=['Source evidence is absent.']", "missing=['source_evidence_absent']")
    path.write_text(text, encoding='utf-8')
    replacements = {
        'test_atomic_decoding.py': [
            ("'explanation': 'Missing measurement.'", "'explanation': 'Predicate evidence recorded.'"),
            ("'missing_information': ['Measurement.'], 'explanation': 'Missing evidence.'",
             "'missing_information': ['scoped_evidence_unresolved'], 'explanation': 'Assess the recorded evidence ledger.'"),
        ],
        'test_atomic_smoke_cellfix2.py': [("missing=['Capacity measurement.']", "missing=['measurement_unreported']")],
        'test_atomic_assessment_cellfix8.py': [
            ("missing=['In-scope latency result.'])\n        self.assertTrue(tester.accepts",
             "missing=['measurement_unreported'])\n        self.assertTrue(tester.accepts")],
    }
    for name, edits in replacements.items():
        path = root/'research_rag/tests'/name
        text = path.read_text(encoding='utf-8')
        for old, new in edits:
            text = replace_once(text, old, new)
        path.write_text(text, encoding='utf-8')
