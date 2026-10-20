"""Build a separate candidate, preserving audited cf5 and its original labels."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import sys

from atomic_cellfix6_patch import apply_patch, replace_once

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT/'research-runs/audit-cellfix5-full39-20261018T153854Z-2c3e0bd6'
SOURCE = ROOT/'research-runs/atomic-cellfix6-candidate/workspace'
CRITERIA = 'research_rag/evaluation/atomic_verifier_criteria_v8.json'
OVERLAY = 'atomic_binding_adjudication_cellfix6.json'
sha = lambda b: hashlib.sha256(b).hexdigest()
dump = lambda p, v: p.write_text(json.dumps(v, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

OVERLAY_CODE = '''

def apply_adjudication(cases, path):
    """Apply a hash-bound annotation revision, never modify historical fixtures."""
    spec = json.loads(path.read_text(encoding='utf-8'))
    lookup = {c['example_id']: c for c in cases}
    changes = {r['example_id']: r for r in spec['cases']}
    if (spec['version'] != 'strict-identity-v1' or len(changes) != len(spec['cases'])
            or not set(changes) <= set(lookup)):
        raise ValueError('Invalid binding adjudication')
    result = []
    for case in cases:
        entry = changes.get(case['example_id'])
        if entry is None:
            result.append(case)
            continue
        if (entry['original_label'] != case['label'] or entry['label'] not in LABELS
                or entry['claim_sha256'] != hashlib.sha256(case['claim'].encode()).hexdigest()
                or entry['context_sha256'] != hashlib.sha256(case['context'].encode()).hexdigest()
                or not entry['rationale']):
            raise ValueError('Adjudication input mismatch')
        result.append({**case, 'original_label':case['label'], 'label':entry['label'],
            'original_annotation_rationale':case.get('annotation_rationale',''),
            'annotation_rationale':entry['rationale'], 'annotation_version':spec['version']})
    return result
'''


def build():
    assert not (ROOT/'docs/atomic-verifier-cellfix6-release.json').exists(), 'Released candidate is immutable.'
    release = json.loads((ROOT/'docs/atomic-verifier-cellfix5-fresh-colab-release.json').read_text())
    manifest = json.loads((PARENT/'artifact/input-manifest.json').read_text())
    assert manifest == release['payload_files']
    for name, item in manifest.items():
        data = (PARENT/'workspace'/name).read_bytes()
        assert sha(data) == item['sha256'] and len(data) == item['size'], name
        dest = SOURCE/name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    for catalog in ('atomic-verifier-cellfix5-fresh-colab-release.json','atomic-verifier-cellfix5-full39-colab-release.json'):
        for name, digest in json.loads((ROOT/'docs'/catalog).read_text())['files'].items():
            assert sha((ROOT/name).read_bytes()) == digest, name
    assert sha((PARENT/'original-output.zip').read_bytes()) == '8425775efc1703b317f2d15d87a54e3fdbf4f0a9ccbe2a0c1490554c61c06e3a'
    preservation = {'parent_run':'20261018T153854Z-2c3e0bd6',
        'zip_sha256':sha((PARENT/'original-output.zip').read_bytes()),
        'original_predictions_sha256':sha((PARENT/'artifact/verifier39/predictions.jsonl').read_bytes()),
        'parent_criteria_sha256':sha((PARENT/'workspace'/CRITERIA).read_bytes()),
        'parent_inputs':manifest, 'original_release_files_verified':True}
    dump(ROOT/'docs/atomic-verifier-cellfix5-preserved-before-cellfix6.json', preservation)

    apply_patch(SOURCE)
    cases = json.loads((PARENT/'artifact/verifier39/cases.json').read_text())
    annotation = {'version':'strict-identity-v1', 'decision_date':'2026-10-18',
        'authorization':'User selected: Giữ context, đánh nhãn lại theo evidence nghiêm ngặt.',
        'scope':'Development annotation correction; not independent held-out adjudication.',
        'rule':'Claim/workload similarity is not evidence of target identity. Missing target identity is NEI for both support and contradiction.',
        'historical_dataset_unchanged':True, 'cases':[]}
    for case in cases:
        if case.get('family') == 'conjunction':
            annotation['cases'].append({'example_id':case['example_id'],
                'claim_sha256':sha(case['claim'].encode()), 'context_sha256':sha(case['context'].encode()),
                'original_label':case['label'], 'label':'not_enough_info',
                'rationale':'The context does not identify the claimed extractor. Workload-level measurements cannot establish either predicate for that target. Identity evidence is missing; no supported conjunct is assumed.'})
    assert len(annotation['cases']) == 3
    overlay = SOURCE/'research_rag/evaluation'/OVERLAY
    dump(overlay,annotation)
    dump(ROOT/'docs/atomic-verifier-cellfix6-binding-adjudication.json',annotation)

    runner = SOURCE/'research_rag/evaluation/evaluate_atomic_verifier.py'
    text = runner.read_text(encoding='utf-8')
    text = replace_once(text, '\ndef load_frozen(criteria_path):', OVERLAY_CODE+'\n\ndef load_frozen(criteria_path):')
    text = replace_once(text, '    probe_configuration(criteria, cases, criteria_path)', '''    annotation_path = frozen_file(criteria_path, criteria['annotation_file'], criteria['annotation_sha256'])
    cases = apply_adjudication(cases, annotation_path)
    inputs = {**inputs, 'annotation-revision':annotation_path}
    revised_metrics, _ = score_legacy(baseline['predictions'], cases, {**criteria,
        'comparison_policy':'all_labels', 'max_attempts':2, 'max_wrong_label_agreements':0})
    metrics = {**metrics, 'label_version':'historical_original',
        'rescored_stored_predictions_under_current_annotation':revised_metrics,
        'new_baseline_inference':False}
    probe_configuration(criteria, cases, criteria_path)''')
    text = replace_once(text, "'gold': case['label'],\n                        'baseline_label'", "'gold': case['label'],\n                        'original_gold':case.get('original_label',case['label']),\n                        'annotation_version':criteria['annotation_version'],\n                        'baseline_label'")
    runner.write_text(text,encoding='utf-8')
    # These assertions describe fixture label counts, not candidate quality.
    path = SOURCE/'research_rag/tests/test_atomic_experiment.py'
    text = path.read_text(encoding='utf-8')
    text = replace_once(text, "criteria['contract_file'], criteria['baseline_file'], criteria['decomposition_probe']['cases_file']", "criteria['contract_file'], criteria['baseline_file'], criteria['decomposition_probe']['cases_file'], criteria['annotation_file']")
    text = replace_once(text,"self.assertEqual(metrics['correct_labels'], 13)","self.assertEqual(metrics['correct_labels'], 15)")
    text = replace_once(text,"self.assertEqual(metrics['gold_support_rejected'], 13)","self.assertEqual(metrics['gold_support_rejected'], 12)")
    path.write_text(text,encoding='utf-8')
    path = SOURCE/'research_rag/tests/test_atomic_verifier.py'
    text = path.read_text(encoding='utf-8')
    text = replace_once(text,"            second = assessment([observation(truth=truth, quote='Accuracy was not measured.')],", "            evidence = {'unknown':'Accuracy was not measured.', 'false':'The service did not retain accuracy.', 'true':'The service retained accuracy.'}[truth]\n            context = 'The service reduced memory. ' + evidence\n            second = assessment([observation(truth=truth, quote=evidence)],")
    text = replace_once(text,'            # true/false are injected output to test aggregation, not entailment.',
        '            # Keep aggregation fixtures consistent with the evidence guard.')
    text = replace_once(text,"            observations = [observation(member=m, truth=t, quote=context) for m, t in zip(('A', 'B'), values)]",
        "            context = ' '.join(m + {'true':' improved.', 'false':' did not improve.', 'unknown':' status was unreported.'}[t] for m,t in zip(('A','B'),values)) + ' The complete set is A and B.'\n            observations = [observation(member=m, truth=t, quote=context) for m, t in zip(('A', 'B'), values)]")
    path.write_text(text,encoding='utf-8')
    test = 'research_rag/tests/test_atomic_assessment_cellfix6.py'
    (SOURCE/test).write_bytes((ROOT/'scripts/test_atomic_cellfix6_assessment.py').read_bytes())
    trace = 'research_rag/tests/fixtures/atomic_cellfix5_full39_assessments.json'
    rows = [json.loads(line) for line in (PARENT/'artifact/verifier39/predictions.jsonl').read_text().splitlines()]
    fixtures = []
    for case,row in zip(cases,rows):
        assert case['example_id']==row['example_id']
        events = [e for e in row['result']['trace'] if e['stage']!='decompose' and e.get('valid')]
        fixtures.append({'case':case, 'parts':[{'part':p['part'], 'output':e['output']} for p,e in zip(row['result']['parts'],events)]})
    dump(SOURCE/trace,fixtures)

    parent=json.loads((PARENT/'workspace'/CRITERIA).read_text())
    # Read literal metadata without importing torch during every local rebuild.
    # load_frozen subsequently verifies it against the real imported modules.
    metadata={'policy':'atomic-verifier-constrained-v8-cellfix6',
        'decoder':copy.deepcopy(parent['structured_decoder']), 'prompts':{}}
    for name, symbol, key in (('04_factchecker/inference/atomic_verifier.py','DECOMPOSE_PROMPT','decompose'),
            ('04_factchecker/inference/assessment_rules.py','PROMPT','assess')):
        assignments=[node for node in ast.parse((SOURCE/name).read_text(encoding='utf-8')).body
            if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id==symbol for t in node.targets)]
        assert len(assignments)==1
        metadata['prompts'][key]=ast.literal_eval(assignments[0].value)
    metadata['decoder'].update(policy='atomic-schema-decoding-v5-cellfix6',
        assessment_evidence_guards='explicit_absence_and_scope',ordered_metric_measurement_binding=True)
    contract=copy.deepcopy(json.loads((SOURCE/'research_rag/evaluation'/parent['contract_file']).read_text()))
    contract['version']='atomic-contract-constrained-v8-cellfix6'
    contract['assessment_revision']={
        'identity':'Require evidence identifying the exact target; no inferred workload-to-system alias. Contexts unchanged; strict-identity-v1 revises two labels and three rationales separately from original fixtures.',
        'truth':'Positive predicate before quantifier; missing evidence is unknown. Existing ALL/SOME/NONE aggregation unchanged.',
        'evidence_guards':'Finite explicit missing-result, month and opposed hyphenated-condition checks. Rejections enter bounded repair; model output is not rewritten to a desired label.',
        'numeric':'Shared non-unit vocabulary; same-metric ordered pairs narrowed only without negation/modality/retraction. A single omitted object modifier requires an explicit for-the-same-object plural source clause.',
        'limits':'Guards do not prove entailment or coverage. No full coreference parser, inferred unit conversion or production promotion. Independent validation and new model inference remain required.'}
    contract_name='atomic_verifier_contract_v8_cellfix6.json'
    dump(SOURCE/'research_rag/evaluation'/contract_name,contract)
    extra=[test,trace,'04_factchecker/inference/assessment_rules.py']
    criteria=copy.deepcopy(parent)
    criteria.update(version=metadata['policy'],policy=metadata['policy'],structured_decoder=metadata['decoder'],
        contract_file=contract_name,contract_sha256=sha((SOURCE/'research_rag/evaluation'/contract_name).read_bytes()),
        annotation_file=OVERLAY,annotation_sha256=sha(overlay.read_bytes()),annotation_version='strict-identity-v1',
        source_sha256={n:sha((SOURCE/n).read_bytes()) for n in list(parent['source_sha256'])+extra},
        prompt_sha256={k:sha(v.encode()) for k,v in metadata['prompts'].items()})
    criteria['limitations'] += [contract['assessment_revision']['limits'],
        'Two development gold labels revised with user authorization under strict-identity-v1. Historical results remain scored on original gold; any rescore is explicitly distinguished from new inference.']
    changed={'version','policy','structured_decoder','contract_file','contract_sha256','source_sha256','prompt_sha256','limitations'}
    assert all(criteria[k]==parent[k] for k in parent.keys()-changed)
    assert criteria['prompt_sha256']['decompose']==parent['prompt_sha256']['decompose']
    dump(SOURCE/CRITERIA,criteria)
    names=sorted(set(manifest)|set(extra)|{'research_rag/evaluation/'+OVERLAY,'research_rag/evaluation/'+contract_name})
    inputs={n:{'size':(SOURCE/n).stat().st_size,'sha256':sha((SOURCE/n).read_bytes())} for n in names}
    record={'candidate':criteria['policy'],'status':'local_candidate_not_notebook_release',
        'source_root':str(SOURCE),'criteria_sha256':sha((SOURCE/CRITERIA).read_bytes()),'input_manifest':inputs,
        'parent_criteria_sha256':preservation['parent_criteria_sha256'],
        'model_budget_gate_unchanged':True,'decomposition_prompt_unchanged':True,
        'assessment_prompt_changed':True,'annotation_version':'strict-identity-v1',
        'new_model_inference_completed':False,'promoted_to_serving':False}
    dump(ROOT/'docs/atomic-verifier-cellfix6-candidate.json',record)
    print(json.dumps({'candidate':record['candidate'],'source':str(SOURCE),'input_files':len(inputs),'criteria_sha256':record['criteria_sha256']}))


if __name__=='__main__':
    build()
