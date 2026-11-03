"""Targeted counterfactual checks on copies; never new model predictions."""
from copy import deepcopy
import importlib
import importlib.util
import json
import sys

from scripts.audit_atomic_cellfix15_validation30 import BASE, OUT, SOURCE, REPORT, read, rows, sha, parser_accepts
from scripts.atomic_validation_review import json_bytes


def main():
    audit = read(REPORT)
    assert audit['all_predictions_and_calls_replayed']
    inputs = read(OUT / 'input-manifest.json')
    for name, expected in inputs.items():
        assert sha((SOURCE / name).read_bytes()) == expected['sha256'], name
    sys.path.insert(0, str(SOURCE))
    a = importlib.import_module('04_factchecker.inference.atomic_verifier')
    d = importlib.import_module('04_factchecker.inference.atomic_decoding')
    q = importlib.import_module('04_factchecker.inference.numeric_verifier')
    dec = importlib.import_module('04_factchecker.inference.assessment_decisions')
    ev = importlib.import_module('04_factchecker.inference.assessment_evidence')
    sub = importlib.import_module('04_factchecker.inference.cellfix14_decomposition')
    request_cache = importlib.import_module('04_factchecker.inference.cellfix14_runtime').decode_request
    outputs = {row['example_id'][-3:]: row['result'] for row in rows(OUT / 'validation30/predictions.jsonl')}
    cases = {c['example_id'][-3:]: c for c in read(OUT / 'validation30/cases.json')}
    report = {'new_inference': False, 'counterfactual_records_are_not_predictions': True,
              'source_edits': False, 'decomposition': {}, 'assessment': {}}
    # Proposed source spans only test the existing validator, not model reachability.
    substitutions = {'009': 'sentence', '015': 'prediction', '020': '80 events',
                     '021': 'news articles', '023': 'eight named-entity categories', '025': 'proposed model'}
    for cid, entity in substitutions.items():
        raw = deepcopy(outputs[cid]['trace'][0]['output'])
        part = raw['parts'][-1]
        before = sub.subject_issue(part['scope'], part['quote'])
        part['scope']['entity'] = entity
        try:
            a.normalize_decomposition(raw, cases[cid]['claim'])
        except ValueError as exc:
            result = str(exc)
        else:
            result = 'accepted'
        report['decomposition'][cid] = dict(original_subject_issue=before,
            entity_tested=entity, edited_record_validation=result)
    # Identical population/predicate with postposed ALL, and a normal leading ALL.
    post = 'The news articles are all written in French.'
    lead = 'All news articles are written in French.'
    scope = dict(entity='news articles', metric='written in French', time='', condition='')
    report['postposed_all_minimal_pair'] = {s: sub.subject_issue(scope, s) for s in (post, lead)}
    for cid in ('005', '007', '008', '011', '013', '014', '019', '022', '026', '029'):
        trace = next(t for t in outputs[cid]['trace'] if t['stage'] != 'decompose')
        request = json.loads(trace['messages'][1]['content'])
        part, context = request['part'], request['context']
        with request_cache(None):
            schema, source = d.schema_for(trace['messages'])
        obs_schema = schema['properties']['observations']['items']
        branches = obs_schema.get('anyOf', [obs_schema])
        item = dict(allowed_truths=sorted({v for b in branches for v in b['properties']['truth'].get('enum', [])}),
                    decision_evidence=dec.decision_evidence(part, context),
                    population=ev._population(part, context), population_witness=ev.population_witness(part, context),
                    numeric_requirements=q.numeric_requirements(part['quote']),
                    numeric_source_requirements=q.numeric_requirements(context),
                    numeric_choice_counts=[len(g) for g in dec.numeric_choices(part, context)])
        if cid in ('013', '014'):
            record = trace['output']['observations'][0]['numeric']
            item['original_numeric'] = q.check_numeric(record, part['quote'], context, metric=part['scope']['metric'])
            changed_context = context.replace('which is not good enough BIBREF1', 'which is good enough BIBREF1')
            changed_record = deepcopy(record)
            changed_record['source_quote'] = changed_record['source_quote'].replace('which is not good enough BIBREF1', 'which is good enough BIBREF1')
            item['diagnostic_only_remove_not'] = q.check_numeric(changed_record, part['quote'], changed_context, metric=part['scope']['metric'])
        if cid == '007':
            record = deepcopy(trace['output']['observations'][0]['numeric'])
            record['right'] = deepcopy(record['left'])
            item['same_value_operand_numeric'] = q.check_numeric(record, part['quote'], context, metric=part['scope']['metric'])
            changed = deepcopy(trace['output'])
            changed['observations'][0]['numeric'] = record
            item['same_value_operand_schema_allowed'] = parser_accepts(schema, source, json.dumps(changed, ensure_ascii=False), d)
            try:
                item['same_value_operand_assessment'] = a.assess_part(changed, part, context)['assessed_label']
            except ValueError as exc:
                item['same_value_operand_assessment'] = str(exc)
        if cid in ('011', '019'):
            changed = deepcopy(trace['output'])
            if cid == '011':
                changed['observations'][0]['member'] = '14,769 actions'
            else:
                member = 'plane crash events'
                quote = context.split('. ', 1)[0] + '.'
                changed['coverage'] = dict(complete=True, members=[member], quotes=[quote])
                changed['observations'][0].update(member=member, truth='true', quotes=[quote])
            item['corrected_ledger_schema_allowed'] = parser_accepts(schema, source, json.dumps(changed, ensure_ascii=False), d)
            try:
                item['corrected_ledger_assessment'] = a.assess_part(changed, part, context)['assessed_label']
            except ValueError as exc:
                item['corrected_ledger_assessment'] = str(exc)
            item['corrected_ledger'] = changed
        report['assessment'][cid] = item
        print(cid, 'truths=', item['allowed_truths'], 'numeric_choices=', item['numeric_choice_counts'], flush=True)
    target = BASE / 'targeted-diagnostics.json'
    target.write_bytes(json_bytes(report))
    print(str(target))


if __name__ == '__main__':
    main()
