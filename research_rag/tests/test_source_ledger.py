"""Test the r9 ledger contract and aggregation with recorded-style replies."""

from importlib import import_module
import json

import pytest


ledger = import_module('04_factchecker.inference.source_ledger')
decoder = import_module('04_factchecker.inference.atomic_decoding')
pilot = import_module('scripts.run_factcheck_verdict')


def propose(label, ids):
    return dict(label=label, evidence_ids=ids, confidence=None, reasoning='Initial model assessment.')


def part(text, relation, ids=('S1',)):
    return dict(claim_text=text, relation=relation, evidence_ids=list(ids), observation='The source reports the result.')


def run(case, replies):
    seen = []

    def generate(messages):
        prompt = messages[0]['content']
        decoder.schema_for(messages)
        seen.append(prompt)
        expected_prompt, reply = next(replies)
        assert prompt == expected_prompt
        return reply

    _, result, check = pilot.assess_case(case, generate, evidence_format='ids', source_id_policy=ledger.POLICY)
    assert next(replies, None) is None
    for span in result['evidence_spans']:
        assert case['context'][span['start']:span['end']] == span['text']
    return result, check, seen


def test_reference_numbers_do_not_trigger_quantitative_compile():
    assert not ledger.quantities_to_prove('In Table 1, Group 2 exceeded the GPT-4 baseline.')
    assert [q['value'] for q in ledger.quantities_to_prove('In Table 1, Group 2 reached 8.5%.')] == ['8.5']
    assert [q['value'] for q in ledger.quantities_to_prove('The batch size was 2,048.')] == ['2048']


def test_swapped_metric_polarity_refutes_initial_support():
    # Same failure mechanism as the retired ACL 2025 case, with distinct names.
    first = 'The accuracy difference was significant'
    second = 'but the recall difference was not significant.'
    case = dict(claim=f'{first} {second}',
                context='Recall was significantly different (p = 0.012), whereas accuracy was not (p = 0.52).')
    result, check, _ = run(case, iter([
        (pilot.verdict.SOURCE_ID_PROMPT, propose('support', ['S1'])),
        (ledger.LEDGER_PROMPT, {'parts': [part(first, 'entails'), part(second, 'refutes')]}),
        (ledger.RELATION_PROMPT, dict(relation='refutes', observation='Accuracy was not significant.')),
        (ledger.RELATION_PROMPT, dict(relation='refutes', observation='Recall was significant.')),
    ]))
    assert result['label'] == 'contradict'
    assert check['parts'][0]['relation'] == 'refutes'


def test_reconsiders_early_abstention_using_source():
    case = dict(claim='The encoder was frozen.', context='The encoder weights were kept fixed.')
    result, _, _ = run(case, iter([
        (pilot.verdict.SOURCE_ID_PROMPT, propose('not_enough_info', [])),
        (ledger.LEDGER_PROMPT, {'parts': [part(case['claim'], 'entails')]}),
        (ledger.RELATION_PROMPT, dict(relation='entails', observation='Encoder weights were kept fixed.')),
    ]))
    assert (result['label'], result['evidence_ids']) == ('support', ['S1'])


@pytest.mark.parametrize('bad_parts', ['missing', 'invented_id', 'unsplit'])
def test_incomplete_or_ungrounded_ledger_abstains(bad_parts):
    claim = 'The system was faster but used more memory.'
    case = dict(claim=claim, context='The system was faster.')
    items = {
        'missing': [part('The system was faster', 'entails')],
        'invented_id': [part(claim, 'entails', ['S9'])],
        'unsplit': [part(claim, 'entails')],
    }
    bad = (ledger.LEDGER_PROMPT, {'parts': items[bad_parts]})
    result, _, _ = run(case, iter([(pilot.verdict.SOURCE_ID_PROMPT, propose('support', ['S1'])), bad, bad]))
    assert result['label'] == 'not_enough_info'


def test_semantic_confirmation_cannot_replace_numeric_proof():
    case = dict(claim='The method achieved 91% accuracy.', context='Another method achieved 91% accuracy.')
    result, check, _ = run(case, iter([
        (pilot.verdict.SOURCE_ID_PROMPT, propose('support', ['S1'])),
        (pilot.verdict.NUMERIC_CLAIM_PROMPT, {'requirements': [], 'unresolved': ['method']}),
        (pilot.verdict.NUMERIC_CLAIM_PROMPT, {'requirements': [], 'unresolved': ['method']}),
        (ledger.LEDGER_PROMPT, {'parts': [part(case['claim'], 'entails')]}),
    ]))
    assert result['label'] == 'not_enough_info'
    assert check['numeric_check']['stage'] == 'compile_claim'


def test_ledger_request_never_receives_gold():
    case = dict(claim='The optimizer converged.', context='The optimizer diverged.')
    segments = pilot.verdict.source_segments(case['context'])

    def generate(messages):
        assert set(json.loads(messages[1]['content'])) == {'claim', 'segments'}
        return {'parts': [part(case['claim'], 'unresolved', [])]}

    assert ledger.check(case['claim'], segments, [], generate)['label'] == 'not_enough_info'
