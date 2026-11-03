"""Build the isolated Cellfix16 development candidate from verified Cellfix15."""
import importlib
import json
from pathlib import Path
import sys
from scripts.build_atomic_cellfix14_candidate import digest, replace

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'research-runs/atomic-cellfix16-candidate/workspace'


def build():
    if (ROOT/'docs/atomic-verifier-cellfix16-release.json').exists():
        raise ValueError('Released candidate is immutable')
    parent = json.loads((ROOT/'docs/atomic-verifier-cellfix15-candidate.json').read_bytes())
    release = json.loads((ROOT/'docs/atomic-verifier-cellfix15-release.json').read_bytes())
    for name, expected in release['files'].items():
        assert digest((ROOT/name).read_bytes()) == expected, name
    for name, expected in parent['input_manifest'].items():
        raw = (Path(parent['source_root'])/name).read_bytes()
        assert digest(raw) == expected['sha256'], name
        target = SOURCE/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    folder = SOURCE/'04_factchecker/inference'
    extra = ['04_factchecker/inference/cellfix16_rules.py', 'research_rag/tests/test_atomic_cellfix16.py',
             'research_rag/tests/fixtures/cellfix15_validation30.json']
    for name, src in zip(extra, ['atomic_cellfix16_rules.py', 'test_atomic_cellfix16.py', 'fixtures/cellfix15_validation30.json']):
        target = SOURCE/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT/'scripts'/src).read_bytes())
    def edit(name, before, after):
        p = folder/name
        p.write_text(replace(p.read_text(encoding='utf-8'), before, after), encoding='utf-8')
    def append(name, text):
        p = folder/name
        p.write_text(p.read_text(encoding='utf-8')+'\n'+text+'\n', encoding='utf-8')
    edit('assessment_decisions.py', 'or change_witness(part,context))',
         "or change_witness(part,context) or explicit_witness(part,context) or count_witness(part,context))")
    edit('assessment_decisions.py', 'def decision_evidence(part, context):',
         'from .cellfix16_rules import explicit_witness,count_witness\n\ndef decision_evidence(part, context):')
    edit('assessment_evidence.py', 'def population_witness(part, context):', 'def _previous_population_witness(part, context):')
    edit('assessment_evidence.py', 'population_witness=cached(population_witness)',
         'from .cellfix16_rules import population_witness as explicit_population\ndef population_witness(part,context):\n    return _previous_population_witness(part,context) or explicit_population(part,context)\npopulation_witness=cached(population_witness)')
    edit('assessment_focus.py', '    identity_issue = member_identity_issue(part,member,truth,context)',
         '    from .cellfix16_rules import relation_issue\n    relation_error=relation_issue(part,member,quotes,truth,context)\n    if relation_error:return relation_error\n    identity_issue = member_identity_issue(part,member,truth,context)')
    append('cellfix14_decomposition.py', 'from .cellfix16_rules import subject_issue')
    edit('cellfix14_decomposition.py', "if _VERB.search(right) or not (purpose or count_list):result.append(match)",
         "if not count_list and (_VERB.search(right) or not purpose):result.append(match)")
    append('atomic_decoding.py', "_cf15_decomposition_schema=decomposition_schema\nfrom .cellfix16_rules import decomposition_schema as joint_decomposition\ndef decomposition_schema(claim):\n    return joint_decomposition(claim,_cf15_decomposition_schema)\nDECODER.update(policy='atomic-schema-decoding-v5-cellfix16', explicit_relations='shared_finite_witness', population_subject='pre_or_postposed_quantifier')")
    append('atomic_decoding.py', '_cf15_assessment_schema=assessment_schema\nfrom .cellfix16_rules import coverage_schema,count_witness,count_schema\ndef assessment_schema(claim,part,context):\n    witness=count_witness(part,context)\n    if witness:return count_schema(witness)\n    return coverage_schema(_cf15_assessment_schema(claim,part,context),part,context)')
    append('atomic_verifier.py', "POLICY='atomic-verifier-constrained-v8-cellfix16'")
    edit('cellfix14_quantities.py', "if gap.strip() or word[0].casefold() in _STOP or word[0].casefold() in WORDS:",
         "if gap.strip() or word[0].upper() in {'BIBREF','TABREF','FIGREF'} or word[0].casefold() in _STOP or word[0].casefold() in WORDS:")
    edit('cellfix14_quantities.py', 'left=claimed.casefold().split();right=observed.casefold().split()',
         'from .cellfix16_rules import count_unit\n    left=count_unit(claimed).casefold().split();right=count_unit(observed).casefold().split()')
    # Qualitative dissatisfaction does not negate the explicitly reported measurement.
    edit('numeric_verifier.py', "    if re.search(r'\\b(?:not|never|hypothetical|would|could|may|might|should|if|expected|predicted|approximately|about)\\b', proof, re.I):",
         "    from .cellfix16_rules import measurement_qualification\n    qualification = measurement_qualification(proof,raw)\n    if re.search(r'\\b(?:not|never|hypothetical|would|could|may|might|should|if|expected|predicted|approximately|about)\\b', qualification, re.I):")
    edit('numeric_verifier.py', "    proof, bound = measurement_scope(raw, claim_part, metric)",
         "    from .cellfix16_rules import quantity_modifier_issue\n    modifier_issue=quantity_modifier_issue(raw,claim_part,context)\n    if modifier_issue:return {**result,'truth':'unknown','reason':modifier_issue}\n    proof, bound = measurement_scope(raw, claim_part, metric)")
    test_path=SOURCE/'research_rag/tests/test_atomic_cellfix14.py'
    test_path.write_text(replace(test_path.read_text(encoding='utf-8'),
        "self.assertEqual([p['properties']['quantifier']['enum'] for p in parts],[['atomic'],['all']])",
        "self.assertEqual({tuple(p['properties']['quantifier']['enum']) for p in parts},{('atomic',),('all',)})"),encoding='utf-8')
    sys.path.insert(0, str(SOURCE))
    a = importlib.import_module('04_factchecker.inference.atomic_verifier')
    d = importlib.import_module('04_factchecker.inference.atomic_decoding')
    path = SOURCE/'research_rag/evaluation/atomic_verifier_criteria_v8.json'
    original = json.loads(path.read_bytes())
    criteria = {**original, 'version': a.POLICY, 'policy': a.POLICY, 'structured_decoder': d.DECODER}
    criteria['source_sha256'] = {n:digest((SOURCE/n).read_bytes()) for n in list(original['source_sha256'])+extra}
    contract = json.loads((path.parent/criteria['contract_file']).read_bytes())
    contract.update(version='atomic-contract-constrained-v8-cellfix16', cellfix16='Shared explicit relations, population binding and quantity provenance; development only')
    contract_path = path.parent/'atomic_verifier_contract_v8_cellfix16.json'
    contract_path.write_text(json.dumps(contract, indent=2)+'\n', encoding='utf-8')
    criteria.update(contract_file=contract_path.name, contract_sha256=digest(contract_path.read_bytes()))
    path.write_text(json.dumps(criteria, indent=2)+'\n', encoding='utf-8')
    names = sorted(set(parent['input_manifest'])|set(extra)|{contract_path.relative_to(SOURCE).as_posix()})
    report = dict(candidate=a.POLICY, source_root=str(SOURCE), parent_criteria_sha256=parent['criteria_sha256'],
                  criteria_sha256=digest(path.read_bytes()), input_manifest={n:dict(size=(SOURCE/n).stat().st_size,sha256=digest((SOURCE/n).read_bytes())) for n in names},
                  validation30_used_for_tuning=True, evaluation_role='development', new_model_inference_completed=False,
                  independent_validation_completed=False, promoted_to_serving=False, parent_release_files=release['files'],
                  model_budget_gold_gate_unchanged=True, prompts_unchanged=True)
    (ROOT/'docs/atomic-verifier-cellfix16-candidate.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(report['criteria_sha256'], flush=True)


if __name__ == '__main__':build()
