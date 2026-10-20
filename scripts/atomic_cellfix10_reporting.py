"""Render checked decisions, while retaining raw model prose only for audit."""
import re

OBSERVATION_NOTE = 'Predicate evidence recorded.'
ASSESSMENT_NOTE = 'Assess the recorded evidence ledger.'
REASONS = {
    'source_evidence_absent': 'Source evidence for this claim part',
    'target_binding_unresolved': 'Evidence identifying the claimed target in the reported results',
    'comparison_unresolved': 'An in-scope baseline/comparison establishing the claimed change',
    'measurement_unreported': 'The unreported in-scope measurement/result',
    'population_results_unresolved': 'A closed target population and the remaining member results',
    'scoped_evidence_unresolved': 'Evidence resolving this predicate for the claimed target and scope',
}


def missing_reason(part, context):
    from .atomic_verifier import target_entity, target_members, other_named_target, _PROPERTY_HEADS
    from .assessment_evidence import metric_present
    from .assessment_rules import clauses, scope_conflict, _MISSING
    from .numeric_verifier import direction
    if not context.strip():
        return 'source_evidence_absent'
    if part['quantifier'] == 'atomic' and target_entity(part) and not target_members(part, context):
        return 'target_binding_unresolved'
    # Only explicit source absence licenses these specific reasons. A lone
    # number is not evidence that its comparison is absent from the whole text.
    baseline_pattern = (
            r'\b(?:no|without)\s+(?:before[- ]\w+|baseline|comparative|comparison)\b'
            r'|\b(?:baseline|before[- ]\w+|comparative change)\b[^.;]*\b(?:not reported|unreported|not measured)\b')
    if direction(part['quote']) and metric_present(part, context):
        wanted = set(re.findall(r'[a-z]+', part['scope']['metric'].lower())) & _PROPERTY_HEADS
        for clause in clauses(context):
            mentioned = set(re.findall(r'[a-z]+', clause.lower())) & _PROPERTY_HEADS
            if (re.search(baseline_pattern, clause, re.I) and not scope_conflict(part, clause)
                    and not other_named_target(part, clause) and (not mentioned or wanted & mentioned)):
                return 'comparison_unresolved'
    if any(metric_present(part, c) and _MISSING.search(c) and not scope_conflict(part, c)
           and not other_named_target(part, c)
           for c in clauses(context)):
        return 'measurement_unreported'
    if part['quantifier'] != 'atomic':
        return 'population_results_unresolved'
    return 'scoped_evidence_unresolved'


def missing_text(reason, part):
    scope = part['scope']
    restrictions = '; '.join(f'{k}={scope[k]}' for k in ('time', 'condition') if scope[k])
    return (REASONS[reason] + f": target={scope['entity']}; predicate/metric={scope['metric']}"
            + ('; ' + restrictions if restrictions else '') + '.')


def reporting_issue(raw, part, context):
    codes = [v for v in raw['missing_information'] if v in REASONS]
    if codes and (len(raw['missing_information']) != 1 or codes != [missing_reason(part, context)]):
        return 'missing_reason_binding'
    return None


def render(result, raw, part, context):
    """Called only after validation; cannot change truth, citations or label."""
    result = dict(result)
    q, label = part['quantifier'], result['assessed_label']
    observations = []
    for obs in result['observations']:
        truth = obs['truth']
        wording = {'true': 'satisfies', 'false': 'does not satisfy',
                   'unknown': 'has unresolved evidence for'}[truth]
        text = (f"Member {obs['member']!r} {wording} the positive predicate "
                f"{part['scope']['metric']!r}, before applying {q.upper()}.")
        if obs['numeric_result'] is not None:
            text += ' See the checked numeric records and their source quotes.'
        observations.append({**obs, 'model_explanation': obs['explanation'], 'explanation': text})
    result['observations'] = observations
    result['model_missing_information'] = list(raw['missing_information'])
    if label == 'not_enough_info':
        reason = missing_reason(part, context)
        result['missing_reason'] = reason
        result['missing_information'] = [missing_text(reason, part)]
        text = 'The checked ledger does not decide this claim part. ' + result['missing_information'][0]
    else:
        result['missing_reason'] = None
        result['missing_information'] = []
        text = {
            ('atomic', 'support'): 'The checked in-scope evidence establishes this predicate.',
            ('atomic', 'contradict'): 'The checked in-scope evidence refutes this predicate.',
            ('all', 'support'): 'The complete checked population satisfies the predicate for every member.',
            ('all', 'contradict'): 'A checked member fails the predicate, refuting ALL.',
            ('some', 'support'): 'A checked member satisfies the predicate, establishing SOME.',
            ('some', 'contradict'): 'The complete checked population has no true member, refuting SOME.',
            ('none', 'support'): 'The complete checked population has no true member, establishing NONE.',
            ('none', 'contradict'): 'A checked member satisfies the predicate, refuting NONE.',
        }[(q, label)]
    result['explanation'] = text
    result['explanation_origin'] = 'validated_ledger_renderer_v1'
    if q != 'atomic':
        from .assessment_evidence import _population
        population = _population(part, context)
        result['population_binding_basis'] = population['binding_basis'] if population else 'model_ledger'
    return result


def constrain_schema(schema, part, context):
    props = schema['properties']
    props['explanation'] = {'type': 'string', 'enum': [ASSESSMENT_NOTE]}
    props['missing_information']['items'] = {'type': 'string', 'enum': [missing_reason(part, context)]}
    props['missing_information']['maxItems'] = min(1, props['missing_information'].get('maxItems', 4))
    items = props['observations']['items']
    for branch in items.get('anyOf', [items]):
        branch['properties']['explanation'] = {'type': 'string', 'enum': [OBSERVATION_NOTE]}
    return schema
