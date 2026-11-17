"""Regression tests for the R8 source-ID repair policy."""

from importlib import import_module

import pytest


pilot = import_module('scripts.run_factcheck_verdict')
comparison = import_module('04_factchecker.inference.source_comparison')
decoder = import_module('04_factchecker.inference.atomic_decoding')


def run(claim, context, replies):
    responses = iter(replies)

    def generate(messages):
        decoder.schema_for(messages)
        prompt, response = next(responses)
        assert messages[0]['content'] == prompt
        return response

    _, final, check = pilot.assess_case(dict(claim=claim, context=context), generate, evidence_format='ids',
                                        source_id_policy=comparison.POLICY)
    assert next(responses, None) is None
    for span in final['evidence_spans']:
        assert span['text'] == context[span['start']:span['end']]
    return final, check


def proposal(label='support', ids=('S1',)):
    return pilot.verdict.SOURCE_ID_PROMPT, dict(label=label, evidence_ids=list(ids), confidence=None, reasoning='Initial vote.')


@pytest.mark.parametrize('proof,claim,context,edits', [
    (comparison.refute_table_rank, 'On Atlas GeoQA, Relay led all two comparison methods in accuracy.',
     'Table 4. Framework accuracy (%) with Atlas.\nTask | Relay | Base | Other\nGeoQA | 56 | 61 | 42',
     [('with Atlas', 'with Orion'), ('GeoQA |', 'HistQA |'), ('| 61 |', '| N/A |'),
      ('accuracy (%)', 'latency (%)'), ('| 61 |', '| 56 |'), ('Atlas.\n', 'Atlas.\nResults for Orion.\n')]),
    (comparison.refute_test_size_comparison, 'The study uses fewer test sentences for Welsh than for Dutch.',
     'Table 1. Test data for selected target languages in the translation study.\n'
     'Target language | Script | Dataset size\nDutch | Latin | 611\nWelsh | Latin | 930',
     [('Test data', 'Training data'), ('Dataset size', 'Vocab size'), ('Welsh |', 'Polish |'), ('930', 'unknown')]),
    (comparison.refute_universal_improvement, 'Minimal prompting improved all 12 evaluated models on the Atlas held-out rounds.',
     'The Atlas experiment evaluated 12 models on 200 held-out rounds. '
     'Compared with the unprompted protocol, the minimally prompted protocol improved scores for 9 of the 12 models.',
     [('The Atlas', 'The Orion'), ('held-out rounds. ', 'held-out rounds.\n\n'), ('9 of the 12', '12 of the 12'),
      ('unprompted protocol', 'few-shot protocol')]),
    (comparison.refute_screening_threshold, 'The Atlas scoring screen allowed a candidate with a mean rating of 2.9 to pass that stage.',
     'Atlas candidates passed two quality-control stages. The formatting stage removed corrupt rows. '
     'In the scoring stage, the grader excluded candidates whose mean score was below 3.',
     [('Atlas candidates', 'Orion candidates'), ('the scoring stage', 'the review stage'), ('below 3', 'below 2.9'),
      ('rows. ', 'rows.\n\n'), ('grader excluded', 'grader never excluded'), ('below 3.', 'below 3 in the pilot.')]),
])
def test_refutations_require_the_exact_cohort_metric_and_condition(proof, claim, context, edits):
    final, _ = run(claim, context, [proposal('not_enough_info', ())])
    assert final['label'] == 'contradict'
    for old, new in edits:
        assert old in context
        changed = context.replace(old, new)
        assert proof(claim, changed, pilot.verdict.source_segments(changed)) is None


@pytest.mark.parametrize('proof,claim,context,wrong', [
    (comparison.prove_agent_memory_roles,
     'Atlas gives workers local memory and uses a Chair that monitors the shared memory to coordinate them.',
     'Atlas supplies a shared bus. Workers retain their own local memory. '
     'The Chair observes the shared memory to coordinate workers.',
     [('Atlas supplies', 'Orion supplies'), ('The Chair', 'The Worker'), ('shared memory to', 'local memory to')]),
    (comparison.prove_adapter_scope,
     'The training setup shares the Planner adapter across phases while training phase-specific adapters for the Reviewer.',
     'In the Atlas training setup, the Planner uses one LoRA adapter across the entire workflow. '
     'For the Reviewer, we train distinct adapters for the three phases.',
     [('the Planner', 'the Router'), ('distinct adapters', 'one adapter'), ('workflow. ', 'workflow.\n\n')]),
])
def test_support_binds_both_clauses_to_their_roles(proof, claim, context, wrong):
    final, check = run(claim, context, [proposal('contradict')])
    assert final['label'] == 'support'
    assert len(check['parts']) == 2
    assert ' '.join(part['claim_text'] for part in check['parts']) == claim
    assert {key for part in check['parts'] for key in part['evidence_ids']} == set(final['evidence_ids'])
    for old, new in wrong:
        changed = context.replace(old, new)
        assert proof(claim, changed, pilot.verdict.source_segments(changed)) is None
    partial = context.rsplit('. ', 1)[0] + '.'
    assert proof(claim, partial, pilot.verdict.source_segments(partial)) is None


def test_partial_evidence_vote_needs_individually_confirmed_claim_fragments():
    ledger = import_module('04_factchecker.inference.source_ledger')
    first = 'The encoder is frozen'
    second = 'and its vocabulary is shared.'
    claim = f'{first} {second}'
    context = 'The encoder weights remain fixed. The encoder and decoder use the same vocabulary.'
    vote = pilot.verdict.EVIDENCE_CHECK_PROMPT, dict(label='support',
                                                    reasoning='The second detail is not directly addressed.')
    confirmed = ledger.RELATION_PROMPT, dict(relation='entails', observation='The source confirms the fragment.')
    clauses = ledger._fixed_clauses(claim)
    assert [c['text'] for c in clauses] == [first, second]
    assert [claim[c['start']:c['end']] for c in clauses] == [first, second]
    fragments = [dict(clause_id=c['clause_id'], evidence_ids=[key], observation=text, relation='entails')
                 for c, (key, text) in zip(clauses, (('S1', context.split('. ')[0]),
                                                    ('S2', context.split('. ')[1])), strict=True)]
    selected = [(ledger.FIXED_CLAUSE_PROMPT, fragment) for fragment in fragments]
    duplicate = (ledger.FIXED_CLAUSE_PROMPT, {**fragments[1], 'clause_id': 'C1'})
    result, _ = run(claim, context, [proposal(), vote, selected[0], duplicate, confirmed])
    assert result['label'] == 'not_enough_info'
    result, check = run(claim, context, [proposal(), vote, *selected, confirmed, confirmed])
    assert (result['label'], result['evidence_ids']) == ('support', ['S1', 'S2'])
    assert [p['clause_id'] for p in check['parts']] == ['C1', 'C2']
    result, _ = run(claim, context.split('. ')[0] + '.', [proposal(), vote, *selected, confirmed])
    assert result['label'] == 'not_enough_info'
    unresolved = ledger.RELATION_PROMPT, dict(relation='unresolved', observation='Missing evidence.')
    other = 'A different encoder and decoder use the same vocabulary.'
    wrong = (ledger.FIXED_CLAUSE_PROMPT, {**fragments[1], 'observation': other})
    no_alternative = ledger.CLAUSE_RETRY_PROMPT, dict(clause_id='C2', relation='unresolved', evidence_ids=[], observation='')
    result, _ = run(claim, context.split('. ')[0] + '. ' + other,
                    [proposal(), vote, selected[0], wrong, confirmed, unresolved, no_alternative])
    assert result['label'] == 'not_enough_info'
    assert not ledger._fixed_clauses('The system uses images and text.')
    assert not ledger._fixed_clauses('The encoder is frozen and its vocabulary is shared or changed.')
    assert not ledger._fixed_clauses('The paper reports that the encoder is frozen and the decoder uses word tokens.')


@pytest.mark.parametrize('alternate_label,confirmation,final_label', [
    ('entails', 'entails', 'support'),
    ('entails', 'unresolved', 'not_enough_info'),
    ('unresolved', None, 'not_enough_info'),
])
def test_failed_clause_searches_unused_sources_and_checks_the_combined_scope(alternate_label, confirmation, final_label):
    import json

    ledger = import_module('04_factchecker.inference.source_ledger')
    claim = 'The encoder is frozen and its vocabulary is shared.'
    context = 'The encoder weights remain fixed. The encoder shares a vocabulary with its decoder.'
    if confirmation == 'unresolved':
        context = context.replace('The encoder shares', 'A different encoder shares')
    segments = pilot.verdict.source_segments(context)
    ids_seen = []
    confirmed = []

    def generate(messages):
        payload = json.loads(messages[1]['content'])
        prompt = messages[0]['content']
        schema, _ = decoder.schema_for(messages)
        ids = list(payload['segments'])
        if prompt in (ledger.FIXED_CLAUSE_PROMPT, ledger.CLAUSE_RETRY_PROMPT):
            clause_id = payload['clause']['clause_id']
            ids_seen.append((clause_id, ids))
            if prompt == ledger.CLAUSE_RETRY_PROMPT:
                assert ids == ['S2'] and payload['scope_context'] == {'S1': segments['S1']['text']}
                assert schema['properties']['evidence_ids']['items']['enum'] == ['S2']
                return dict(clause_id=clause_id, relation=alternate_label,
                            evidence_ids=['S2'] if alternate_label == 'entails' else [],
                            observation=segments['S2']['text'] if alternate_label == 'entails' else '')
            return dict(clause_id=clause_id, relation='entails', evidence_ids=['S1'], observation=segments['S1']['text'])
        assert prompt == ledger.RELATION_PROMPT
        confirmed.append(ids)
        if payload['fragment'].startswith('The encoder'):
            relation = 'entails'
        else:
            relation = confirmation if ids == ['S1', 'S2'] else 'unresolved'
        return dict(relation=relation, observation='Independently checked the indicated sources.')

    result = ledger.check(claim, segments, ['S1'], generate, require_parts=True)
    assert result['label'] == final_label
    assert result['evidence_ids'] == (['S1', 'S2'] if final_label == 'support' else [])
    assert ids_seen == [('C1', ['S1', 'S2']), ('C2', ['S1', 'S2']), ('C2', ['S2'])]
    assert confirmed == ([['S1'], ['S1'], ['S1', 'S2']] if confirmation else [['S1'], ['S1']])


def test_table_comparison_uses_the_requested_column_and_operator():
    context = 'Table 8. Review corpus.\n\nLanguage | Docs | Classes\nPolish | 18,201 | 5\nItalian | 17,890 | 9'
    claim = 'The Polish review corpus in Table 8 contains fewer documents than the Italian review corpus.'
    final, check = run(claim, context, [proposal()])
    assert final['label'] == 'contradict'
    assert check['method'] == 'deterministic_source_comparison'
    assert run(claim.replace('fewer', 'more'), context, [proposal('contradict')])[0]['label'] == 'support'


def test_rank_uses_only_the_caption_scope_and_selected_method_column():
    claim = 'On rendered inputs, Atlas led the three models in average F1 under linear probing.'
    context = ('Selected average F1 scores from Table 4 for rendered inputs.\n'
               'Model | Prompt-based classifier | Linear probe\nAtlas | 0.8 | 0.6\n'
               'Nova | 0.5 | 0.7\nOrion | 0.2 | 0.3')
    verdict, _ = run(claim, context, [proposal('not_enough_info', ())])
    assert verdict['label'] == 'contradict' and verdict['evidence_ids'] == ['S1', 'S2']
    for changed_claim, changed_context in (
        (claim.replace('linear probing', 'prompt-based classifier'), context),
        (claim, context.replace('Linear probe', 'Prompt-based classifier')),
        (claim, context.replace('Linear probe', 'Nonlinear probe')),
        (claim, context.replace('from Table 4 for rendered', 'from Table 4 for raw')),
        (claim, context.replace('average F1', 'average accuracy')),
        (claim, context.replace('Nova | 0.5 | 0.7\n', '')),
        (claim, context.replace('0.7', '70%')),
        (claim, context.replace('Orion', 'Nova')),
    ):
        assert comparison.refute_table_rank(changed_claim, changed_context,
                                             pilot.verdict.source_segments(changed_context)) is None


def test_scoped_advantage_requires_two_matching_point_estimates():
    claim = 'Dense retrieval had an advantage over Exact match after the labeled rows were removed.'
    earlier = 'Under full coverage, Dense retrieval scored 0.91 F1.'
    measured = ('In a condition where the labeled rows were removed, Dense retrieval scored 0.4 F1 '
                'and the Exact match baseline scored 0.76.')
    context = f'{earlier} {measured}'
    verdict, _ = run(claim, context, [proposal()])
    assert verdict['label'] == 'contradict' and verdict['evidence_ids'] == ['S2']
    swapped = (earlier + ' In a condition where the labeled rows were removed, '
               'the Exact match baseline scored 0.76 F1 and Dense retrieval scored 0.4 F1.')
    assert run(claim, swapped, [proposal()])[0]['label'] == 'contradict'
    for changed in (
        context.replace(' and the Exact match baseline scored 0.76', ''),
        context.replace('0.76.', '0.76 accuracy.'),
        context.replace(' and the Exact match baseline', '. Under full coverage, the Exact match baseline'),
        context.replace('were removed', 'were retained'),
        context.replace('0.76', '0.32'),
        context.replace('0.76', '76%'),
        context + ' ' + measured.replace('0.76', '0.32'),
    ):
        assert comparison.refute_scoped_advantage(claim, pilot.verdict.source_segments(changed)) is None


def test_translation_rank_uses_unique_leaders_in_the_same_direction():
    claim = 'In English-to-Hindi, the higher-COMET feature also obtained the higher BLEU score.'
    context = ('Table 4 compares video features for the reported test split.\n'
               'Feature | En–Hi COMET | En-Hi BLEU | En–Mr BLEU\n'
               'Atlas | 77.2 | 21.1 | 30\nNova | 75.1 | 24.8 | 20')
    verdict, _ = run(claim, context, [proposal('not_enough_info', ())])
    assert verdict['label'] == 'contradict' and verdict['evidence_ids'] == ['S1', 'S2']
    reordered = ('Table 4 compares video features for the reported test split.\n'
                 'Feature | en-hi bleu | en–hi comet | en-mr bleu\n'
                 'Atlas | 21.1 | 77.2 | 30\nNova | 24.8 | 75.1 | 20')
    assert run(claim, reordered, [proposal()])[0]['label'] == 'contradict'
    for changed in (
        context.replace('En-Hi BLEU', 'En–Od BLEU'),
        context.replace('En–Mr BLEU', 'English-to-Hindi BLEU'),
        context.replace('En–Hi COMET', 'Hi–En COMET'),
        context.replace('75.1', '77.2'),
        context.replace('24.8', '21.1'),
        context.replace('24.8', 'N/A'),
    ):
        assert comparison.refute_shared_translation_lead(claim, changed,
                                                          pilot.verdict.source_segments(changed)) is None


def test_outperformance_uses_each_metrics_direction():
    claim = ('In Atlas’s quality evaluation, Atlas-small outperformed the human reviewers '
             'on ICC as well as on mean absolute error.')
    context = ('Table 2. Quality evaluation.\nEvaluator | MAE | Intraclass Correlation Coefficient\n'
               'Human reviewers | 0.60 | 0.83\nAtlas-small | 0.51 | 0.78')
    final, _ = run(claim, context, [proposal()])
    assert final['label'] == 'contradict'
    assert 'Intraclass Correlation Coefficient' in final['reasoning']
    assert run(claim, context.replace('0.78', '0.84'), [proposal('contradict')])[0]['label'] == 'support'
    assert run(claim, context.replace('0.78', '0.83'), [proposal()])[0]['label'] == 'contradict'
    for changed in (context.replace('Quality', 'Latency'), context.replace('0.78', '78%'),
                    context.replace('Quality evaluation', 'Results transferred from the quality evaluation'),
                    context.replace('Atlas-small', 'Atlas-large'), context.replace('0.78', '0.78 ± 0.02'),
                    context + '\nAtlas-small | 0.51 | 0.84', context + '\n\n' + context):
        assert comparison.compare_table_preferences(claim, changed, pilot.verdict.source_segments(changed)) is None


def test_percentage_direction_binds_metric_treatment_and_baseline():
    claim = 'Relative to the baseline, Atlas reports that retrieved demonstrations increased the error measure by 18%.'
    context = ('Atlas compares prompts enriched with retrieved demonstrations to baseline models. '
               'It reports accuracy gains of 18%, an 18% decrease in errors, and a 3% increase in recall.')
    final, _ = run(claim, context, [proposal()])
    assert final['label'] == 'contradict'
    assert len(final['evidence_ids']) == 2
    for changed in (context.replace('decrease', 'increase'), context.replace('baseline', 'ablated'),
                    context.replace('18% decrease', '18 percentage points decrease'),
                    context.replace('retrieved', 'synthetic'), context.replace('Atlas', 'Orion'),
                    context.replace('decrease in errors', 'decrease in latency'),
                    context.replace('increase in recall', 'increase in errors'),
                    context.replace('18% decrease', '18% possible decrease'),
                    context.replace('models. It', 'models.\n\nIt')):
        assert comparison.refute_relative_change(claim, changed, pilot.verdict.source_segments(changed)) is None


def test_screening_quorum_checks_the_required_approvals_for_the_same_panel():
    claim = 'An Atlas record could pass human screening with approval from exactly three of its four reviewers.'
    context = ('Four annotators screened each Atlas record independently. '
               'Passing required approval from all four, along with a valid explanation.')
    final, _ = run(claim, context, [proposal()])
    assert final['label'] == 'contradict'
    assert len(final['evidence_ids']) == 2
    for changed in (context.replace('Atlas', 'Orion'), context.replace('all four', 'three of the four'),
                    context.replace('Four annotators', 'Five annotators'), context.replace('all four', 'all three'),
                    context.replace('record independently. ', 'record independently.\n\n'),
                    context.replace('with a valid explanation', 'with an explanation or an exception')):
        assert comparison.refute_screening_quorum(claim, changed, pilot.verdict.source_segments(changed)) is None
    assert comparison.refute_screening_quorum(claim.replace('exactly three', 'exactly four'), context,
                                              pilot.verdict.source_segments(context)) is None


def test_table_with_wrong_scope_or_missing_cell_cannot_support():
    context = 'Table 8. Review corpus.\n\nLanguage | Docs\nPolish | 18,201\nItalian | 17,890'
    claim = 'The Polish legal corpus in Table 8 contains more documents than the Italian legal corpus.'
    assert run(claim, context, [proposal()])[0]['label'] == 'not_enough_info'
    assert run(claim.replace('legal', 'review'), context.replace('17,890', 'N/A'), [proposal()])[0]['label'] == 'not_enough_info'


def test_table_comparison_checks_roster_scope_against_the_source():
    claim = "Among the three classification datasets in Atlas's Table 8, Polish has a higher F1 than Italian for Atlas."
    context = ('Table 8. Atlas classification results.\n\n'
               'Dataset | Method | F1\nPolish | Atlas | 0.63\nItalian | Atlas | 0.76\nSpanish | Atlas | 0.55')
    final, _ = run(claim, context, [proposal()])
    assert final['label'] == 'contradict'
    assert final['evidence'][-1].startswith('Dataset | Method | F1')
    assert run(claim.replace('higher', 'lower'), context, [proposal()])[0]['label'] == 'support'
    for changed in (context.replace('Table 8', 'Table 80'), context.replace('classification', 'retrieval'),
                    context.replace('Atlas classification', 'Other classification'),
                    context.replace('Italian | Atlas', 'Italian | Other'),
                    context.replace('Dataset |', 'Model |'),
                    context.replace('Spanish |', 'Italian |'), context.rsplit('\n', 1)[0]):
        assert run(claim, changed, [proposal()])[0]['label'] == 'not_enough_info'


def test_source_grounded_model_versions_are_not_measurements():
    claim = 'The speech pipeline uses Aurora 2.5 Flash Preview TTS for synthesis.'
    context = 'Aurora 2.5 Flash Preview TTS synthesizes the recordings.'
    assert not comparison.quantities(claim, [context])
    assert comparison.quantities(claim, [context.replace('2.5', '2.6')])
    assert comparison.quantities(claim, [context.replace('2.5', '12.5')])
    assert comparison.quantities('Atlas reports 2.5 percentage points of improvement.', [context])
    assert comparison.quantities('Atlas contains 2.5 million records.', [context])
    assert comparison.quantities('Atlas 2.5 Million Records', ['Atlas 2.5 Million Records'])
    final, _ = run(claim, context, [proposal(), (
        pilot.verdict.EVIDENCE_CHECK_PROMPT, dict(label='support', reasoning='The named model synthesizes the recordings.'))])
    assert final['label'] == 'support'


def test_task_and_metric_ids_keep_actual_counts_and_scores():
    claim = 'On Benchmark 2025 Task 1, Atlas obtained 85.3 P@10 over 10 trials.'
    assert [item['value'] for item in comparison.quantities(claim)] == ['85.3', '10']
    assert [item['value'] for item in comparison.quantities('The study collected 2025 task examples.')] == ['2025']


def test_scoped_table_binds_model_metric_dataset_criterion_and_value():
    claim = "Blue's Agreement of 0.73 on Reviews was obtained under the Graded criterion."
    context = ('Dataset | Criterion | Model | Value | Metric\n'
               'Reviews | Graded | Blue | 0.65 | Agreement\n'
               'Reviews | Binary | Blue | 0.73 | Agreement\n'
               'Reports | Graded | Blue | 0.73 | Agreement\n'
               'Reviews | Graded | Red | 0.73 | Agreement\n'
               'Reviews | Graded | Blue | 0.73 | Accuracy')
    final, check = run(claim, context, [])
    assert final['label'] == 'contradict'
    assert final['evidence'] == [context]
    assert check['method'] == 'scoped_table_value'
    assert run(claim.replace('0.73', '0.65'), context, [])[0]['label'] == 'support'
    for changed in (
        context.replace('Reviews | Graded | Blue | 0.65 | Agreement\n', ''),
        context.replace('0.65 | Agreement', '65% | Agreement'),
        context + '\nReviews | Graded | Blue | 0.73 | Agreement',
    ):
        assert comparison.compare_scoped_table_value(claim, changed, pilot.verdict.source_segments(changed)) is None
    qualified = claim.replace('on Reviews', 'on Reviews in the pilot')
    assert comparison.compare_scoped_table_value(qualified, context, pilot.verdict.source_segments(context)) is None


def test_group_ratio_preserves_operands_and_count_scale():
    claim = ('In RelayBench, the reported number of routed messages is more than three times '
             'the reported number of direct messages.')
    context = 'RelayBench contains 2.4 thousand messages, split into 500 direct messages and 1.9 thousand routed messages.'
    final, _ = run(claim, context, [proposal()])
    assert final['label'] == 'support'
    assert final['evidence'] == [context]
    assert run(claim.replace('more than', 'less than'), context, [proposal()])[0]['label'] == 'contradict'
    for changed in (context.replace('RelayBench', 'OtherBench'), context.replace('500', '0'),
                    context.replace('2.4 thousand', '2 thousand'), context.replace('1.9 thousand', '1.9'),
                    context.replace('direct messages', 'direct packets')):
        assert comparison.compare_group_ratio(claim, pilot.verdict.source_segments(changed)) is None


def test_duration_conversion_requires_same_corpus_and_language_scope():
    claim = 'SpeechBench contains 2.5 minutes of speech in total, across Polish and Dutch.'
    context = ('SpeechBench adapts test questions into spoken inputs. The final dataset spans Dutch and Polish. '
               'It contains 120 questions and 2.5 hours of audio, or approximately 151 minutes.')
    final, _ = run(claim, context, [proposal('not_enough_info', ())])
    assert final['label'] == 'contradict'
    assert final['evidence_ids'] == ['S1', 'S2', 'S3']
    assert run(claim.replace('2.5', '150'), context, [proposal()])[0]['label'] == 'support'
    for changed in (context.replace('Dutch', 'Spanish'), context.replace('questions and', 'questions and up to'),
                    context.replace('Polish. It', 'Polish.\n\nIt'),
                    context.replace('Dutch and Polish', 'Northern Dutch and Polish')):
        assert comparison.compare_total_duration(claim, changed, pilot.verdict.source_segments(changed)) is None
    approximate = claim.replace('2.5', '151')
    assert comparison.compare_total_duration(approximate, context, pilot.verdict.source_segments(context)) is None


def test_maximum_duration_is_bound_to_the_named_protocol_and_not_the_target():
    claim = 'Atlas’s audio quality-control protocol set a maximum clip duration of one minute.'
    context = ('For Atlas, the quality-control protocol applied 0.5 seconds of silence padding. '
               'The target clip duration was ten to twenty seconds, with a maximum duration of 60 seconds.')
    final, _ = run(claim, context, [proposal('not_enough_info', ())])
    assert final['label'] == 'support' and final['evidence_ids'] == ['S1', 'S2']
    final, _ = run(claim.replace('one minute', 'twenty seconds'), context, [proposal()])
    assert final['label'] == 'contradict' and final['evidence_ids'] == ['S1', 'S2']
    for changed in (context.replace('Atlas', 'Orion'), context.replace('target clip', 'target segment'),
                    context.replace('maximum duration', 'maximum segment duration'),
                    context.replace('maximum duration', 'mean duration'),
                    context.replace('padding. ', 'padding.\n\n'),
                    context.replace('twenty seconds', 'twenty seconds for testing'),
                    context.replace('60 seconds.', '60 seconds for testing.'),
                    context + ' ' + context.replace('60', '50')):
        assert comparison.compare_maximum_duration(claim, changed, pilot.verdict.source_segments(changed)) is None


def test_mirrored_augmentation_binds_the_retained_count_and_both_reversed_fields():
    claim = 'Swapping both responses and their explanations doubled the validated Atlas set from 75 to 150 records.'
    context = ('The Atlas validation stage retained 75 of 220 generated records. '
               'We paired each retained record with a mirrored record, reversing both the response order '
               'and the corresponding explanation order. Table 1 reports 150 records after this augmentation.')
    final, _ = run(claim, context, [proposal('not_enough_info', ())])
    assert final['label'] == 'support' and final['evidence_ids'] == ['S1', 'S2', 'S3']
    final, _ = run(claim.replace('75 to 150', '80 to 160'), context, [proposal()])
    assert final['label'] == 'contradict'
    for changed in (context.replace('Atlas', 'Orion'), context.replace('each', 'some'),
                    context.replace('and the corresponding explanation order', ''),
                    context.replace('Table 1 reports 150', 'Table 1 reports 149'),
                    context.replace('records. We', 'records.\n\nWe'),
                    context.replace('after this augmentation', 'before this augmentation')):
        assert comparison.compare_mirrored_augmentation(claim, changed, pilot.verdict.source_segments(changed)) is None


def test_even_sample_uses_a_unique_exhaustive_partition():
    claim = "The bilingual evaluation study's 80-answer human-labeled set included 45 French answers."
    context = 'The authors sampled 80 generated answers for human annotation, dividing the sample evenly between French and Italian.'
    final, _ = run(claim, context, [proposal('not_enough_info', ())])
    assert final['label'] == 'contradict'
    assert final['evidence'] == [context]
    for changed in (context.replace('evenly', 'mostly'), context.replace('French', 'English'),
                    context.replace('French and Italian', 'French, Italian and English'),
                    context.replace('80 generated', '79 generated'), context.replace('human annotation', 'automatic annotation'),
                    context + ' We sampled 80 generated answers for human annotation.'):
        assert comparison.compare_even_sample(claim, pilot.verdict.source_segments(changed)) is None


def test_configuration_table_keeps_model_context_decoding_and_metric_together():
    claim = ('With greedy decoding on CorpusA, giving Atlas a context window of three sentences '
             'lowered its pronoun F1 relative to sentence-level translation.')
    context = ('Table 8 (CorpusA dataset). G denotes greedy decoding. Context length 0 is sentence-level.\n'
               'Model | Context length | Decoding | Pronoun F1 | BLEU\n'
               'Atlas | 0 | G | 32.0 | 82.0\nAtlas | 3 | G | 50.0 | 70.0\n'
               'Atlas | 3 | Q | 29.0 | 83.0\nOther | 3 | G | 20.0 | 84.0')
    final, _ = run(claim, context, [proposal()])
    assert final['label'] == 'contradict'
    assert '50.0 versus 32.0' in final['reasoning']
    assert run(claim.replace('lowered', 'raised'), context, [proposal()])[0]['label'] == 'support'
    for changed in (context.replace('CorpusA dataset', 'CorpusB dataset'),
                    context.replace('Atlas | 3 | G', 'Atlas | 5 | G'),
                    context.replace('length 0 is sentence-level', 'length 5 is sentence-level'),
                    context + '\nAtlas | 3 | G | 25.0 | 70.0'):
        assert comparison.compare_table_configuration(claim, changed, pilot.verdict.source_segments(changed)) is None


def test_annotation_table_requires_the_exact_task_and_metric():
    claim = ('The macro-F1 of 0.841 reported for Atlas trained on Expert-A annotations '
             'was obtained in the multi-class CorpusA task.')
    context = ('Table 9. CorpusA evaluation. Precision, recall and F1 are macro-averaged across languages.\n'
               'Task | Annotation LLM | Transformer | Precision | F1\n'
               'Binary | Expert-A | Atlas | 0.842 | 0.841\n'
               'Multi-class | Expert-A | Atlas | 0.841 | 0.656\n'
               'Multi-class | Expert-B | Atlas | 0.683 | 0.841')
    final, _ = run(claim, context, [proposal()])
    assert final['label'] == 'contradict'
    assert '0.656' in final['reasoning']
    assert run(claim.replace('0.841', '0.656'), context, [proposal()])[0]['label'] == 'support'
    for changed in (context.replace('macro-averaged', 'micro-averaged'),
                    context.replace('Multi-class | Expert-A', 'Multi-class | Expert-C'),
                    context + '\nMulti-class | Expert-A | Atlas | 0.683 | 0.841'):
        assert comparison.compare_table_configuration(claim, changed, pilot.verdict.source_segments(changed)) is None


def test_statistical_contrast_keeps_polarity_attached_to_each_metric():
    context = ('Falcon and Osprey were compared. While the Recall scores assigned to the two models were statistically distinct '
               '(p = 0.013), the same cannot be said for the Precision scores (p = 0.53).')
    claim = ('For Falcon and Osprey, the human evaluation found a statistically significant difference in Precision '
             'but no significant difference in Recall.')
    final, _ = run(claim, context, [proposal(ids=('S2',))])
    assert final['label'] == 'contradict'
    assert comparison.compare_significance(claim.replace('Osprey', 'Albatross'), context,
                                           pilot.verdict.source_segments(context), ['S2']) is None


def test_respectively_uses_observed_order_and_the_matching_population():
    context = 'The models ran for 21k and 15k steps in the runs with 12 and 80 languages, respectively.'
    claim = 'The run with 80 languages used 21,000 training steps, more than the run with 12 languages.'
    assert run(claim, context, [proposal()])[0]['label'] == 'contradict'
    assert comparison.compare_parallel('In an ablation, ' + claim[0].lower() + claim[1:], context,
                                       pilot.verdict.source_segments(context)) is None


def test_named_value_pairs_keep_metric_split_and_direction():
    context = 'On the training set, the speech system achieves F1 scores of 70.2 (English) and 72.5 (Polish).'
    claim = 'On the speech training set, the English system obtained a higher F1 score than the Polish system.'
    assert run(claim, context, [proposal()])[0]['label'] == 'contradict'
    assert comparison.compare_measure_list(claim.replace('training', 'test'),
                                           pilot.verdict.source_segments(context)) is None


def test_grounded_recovery_cannot_invent_membership_or_quantities():
    context = 'The shared benchmarks cover 44 languages.'
    segments = pilot.verdict.source_segments(context)
    for claim, quantitative, reason in [
        ('Japanese was present in both shared benchmarks.', False, 'unbound_claim_name'),
        ('The benchmark covers 43 languages.', True, 'numeric_support_requires_structured_proof'),
    ]:
        raw = dict(label='support', evidence_ids=['S1'], observation=context)
        assert comparison.verify_recovery(raw, claim, segments, quantitative=quantitative) == (None, reason)


@pytest.mark.parametrize('label', ['support', 'contradict'])
def test_recovery_requires_verbatim_source(label):
    claim, context = 'The encoder stayed frozen.', 'The encoder parameters were fixed throughout training.'
    final, check = run(claim, context, [proposal('not_enough_info', ()),
                                      (comparison.RECOVERY_PROMPT, dict(label=label, evidence_ids=['S1'],
                                                                        observation='The encoder was frozen.'))])
    assert final['label'] == 'not_enough_info'
    assert check['reason'] == 'nonverbatim_recovery_observation'


def test_recovery_can_confirm_support_and_refute_an_initial_support_vote():
    evidence = 'The encoder parameters were fixed throughout training.'
    recovery = lambda label: (comparison.RECOVERY_PROMPT, dict(label=label, evidence_ids=['S1'], observation=evidence))
    checking = lambda label: (pilot.verdict.EVIDENCE_CHECK_PROMPT, dict(label=label, reasoning='Check the encoder.'))
    final, _ = run('The encoder stayed frozen.', evidence,
                   [proposal('not_enough_info', ()), recovery('support'), checking('support')])
    assert final['label'] == 'support'
    final, _ = run('The encoder was updated.', evidence, [proposal(), checking('contradict'), recovery('contradict')])
    assert final['label'] == 'contradict'


def test_keep_verified_refutation_without_a_recovery_vote():
    claim = 'The fitted exponent for training loss varies with model size and data size.'
    context = 'The exponent of the training loss remains invariant to model size N and data size D.'
    check = (pilot.verdict.EVIDENCE_CHECK_PROMPT, dict(label='contradict', reasoning='It remains invariant.'))
    final, trace = run(claim, context, [proposal(), check])
    assert final['label'] == 'contradict'
    assert trace['method'] == 'explicit_invariance'
    assert final['evidence'] == [context]
    for different in (context.replace('data size', 'batch size'), context.replace('exponent', 'gradient'),
                      context.replace('remains invariant', 'is not invariant')):
        assert comparison.refute_invariance(claim, pilot.verdict.source_segments(different)) is None


def test_refute_per_item_count_checks_the_evaluation_cohort_and_item():
    claim = 'The study recruited 24 reviewers across 8 sites and assigned exactly two reviewers to each generated response.'
    context = 'We recruited 24 reviewers across 8 sites.7 Each model-generated response was rated by four participants.'
    final, _ = run(claim, context, [proposal('contradict')])
    assert final['label'] == 'contradict'
    assert final['evidence'] == [context]
    for changed in (context.replace('8 sites', '6 sites'), context.replace('response', 'prompt'),
                    context.replace('was rated by', 'could be rated by'),
                    context.replace('four participants', 'two participants')):
        assert comparison.refute_per_item_count(claim, pilot.verdict.source_segments(changed)) is None


def test_opposite_direction_retains_the_same_comparator_and_population():
    claim = 'Relative to Base, Alpha and Beta show lower cost and greater error across domains.'
    context = ('Alpha and Beta models achieve lower runtime compared to Base, but also achieve lower MSE, '
               'indicating lower error across domains.')
    check = (pilot.verdict.EVIDENCE_CHECK_PROMPT, dict(label='contradict', reasoning='Error is lower.'))
    final, trace = run(claim, context, [proposal(), check])
    assert final['label'] == 'contradict'
    assert trace['method'] == 'scoped_direction'
    for changed in (context.replace('compared to Base', 'compared to Another'),
                    context.replace('across domains', 'across languages'),
                    context.replace('achieve lower MSE', 'achieve lower MSE than Another')):
        assert comparison.refute_comparative_direction(claim, pilot.verdict.source_segments(changed)) is None
    assert comparison.refute_comparative_direction(claim.replace('and greater', 'or greater'),
                                                  pilot.verdict.source_segments(context)) is None


def test_input_roles_bind_to_the_correct_score_and_model_setup():
    claim = ('For recall, the fine-tuned evaluation metric passes the passage to the NLI model as the premise '
             'and the query as the hypothesis.')
    context = ('To train our metric, we fine-tune an NLI encoder. We fine-tune it for precision and recall. '
               'For the precision score, we use the query as premise and the passage as hypothesis; '
               'for the recall score, we use the passage as premise and the query as hypothesis.')
    assert run(claim, context, [proposal('not_enough_info', ())])[0]['label'] == 'support'
    assert run(claim.replace('For recall', 'For precision'), context,
               [proposal('not_enough_info', ())])[0]['label'] == 'contradict'
    for changed in (context.replace('NLI encoder', 'retrieval encoder'),
                    context.replace('recall score', 'coverage score'),
                    context.replace('for precision and recall. ', 'for precision and recall.\n\n')):
        assert comparison.compare_scoped_input_roles(claim, changed, pilot.verdict.source_segments(changed)) is None


def test_training_configuration_checks_each_repeated_value_and_its_run():
    claim = ('BlueLM was pretrained from scratch with sequences of 1,024 tokens and a batch size of 1,024, '
             'processing roughly one million tokens per step.')
    context = ('We pretrain BlueLM from scratch. We use a sequence length of 1,024, and a batch size of 1,024, '
               'yielding approximately 1 million tokens per step.')
    assert run(claim, context, [proposal(ids=('S2',))])[0]['evidence_ids'] == ['S1', 'S2']
    changed_batch = context.replace('batch size of 1,024', 'batch size of 512')
    assert run(claim, changed_batch, [proposal(ids=('S2',))])[0]['label'] == 'contradict'
    for changed in (context.replace('BlueLM', 'RedLM'), context.replace('per step', 'per epoch'),
                    context.replace('scratch. ', 'scratch.\n\n')):
        assert comparison.compare_training_configuration(claim, changed, pilot.verdict.source_segments(changed)) is None


def test_subject_descriptor_is_verified_separately_from_the_measurement():
    claim = 'The model with 18 routing layers has as many active parameters as the dense baseline.'
    context = ('We compare our proposed baseline to the 200M-parameter model with 18 routing layers. '
               'They both have 100M active parameters.')
    assert not comparison.quantities(claim)
    assert comparison.quantities(claim.replace('as many active parameters as the dense baseline', '60 active parameters'))
    verdict, _ = run(claim, context, [proposal(ids=('S2',)), (
        pilot.verdict.EVIDENCE_CHECK_PROMPT, dict(label='support', reasoning='The cited models have equal counts.'))])
    assert verdict['label'] == 'support'
    assert verdict['evidence_ids'] == ['S1', 'S2']
    verdict, _ = run(claim, context.replace('18 routing layers', '20 routing layers'), [proposal(ids=('S2',))])
    assert verdict['label'] == 'not_enough_info'


def test_numeric_scope_is_not_an_exclusive_predicate():
    parser = import_module('04_factchecker.inference.decoder_parser')
    claim = "Blue's kappa of 0.65 on Corpus was measured under the Grade criterion."
    scope = [dict(text='Corpus', key='dataset'), dict(text='Grade criterion', key='criterion')]
    scalar = dict(subjects=[dict(text='Blue', key='blue')], property=dict(text='kappa', key='kappa'),
                  scope=scope, relation='eq', cue='on',
                  values=[dict(kind='number', text='0.65', key='value', unit='')])
    duplicate = {**scalar, 'relation': 'only', 'cue': 'under',
                 'values': [dict(kind='text', text='Grade criterion', key='criterion', unit='')]}
    raw = dict(requirements=[scalar, duplicate], unresolved=[])
    normalized = pilot.verdict._numeric_claim_records(raw, claim, bind_repeated=True)
    facts = parser.parse_requirements(normalized, claim, numeric_binding=True, bind_repeated=True)
    assert len(facts) == 1
    assert [s.span.text for s in facts[0].scope] == ['Corpus', 'was measured under the Grade criterion']
    assert len(pilot.verdict._numeric_claim_records(raw, claim.replace('under', 'only under'),
                                                   bind_repeated=True)['requirements']) == 2


def test_numeric_literals_bind_to_their_own_property():
    parser = import_module('04_factchecker.inference.decoder_parser')
    context = 'The training run used a window length of 1024 tokens and a batch size of 1024 samples.'

    def fact(field, unit):
        return dict(evidence=[context], subjects=[dict(text='training run', key='training run')],
                    property=dict(text=field, key=field), scope=[], relation='eq', cue='',
                    values=[dict(kind='number', text='1024', key='1024', unit=unit)])

    rows = {'facts': [fact('window length', 'tokens'), fact('batch size', 'samples')]}
    a, b = parser.parse_observations(rows, context, bind_repeated=True)
    assert a.values[0].mention.span.start == context.index('1024')
    assert b.values[0].mention.span.start == context.rindex('1024')
    with pytest.raises(ValueError, match='unit_not_attached_to_operand'):
        parser.parse_observations({'facts': [fact('window length', 'samples')]}, context, bind_repeated=True)


def test_repeated_values_remain_bound_through_the_verifier():
    claim = 'The encoder used window length 1024 tokens and batch size 1024 samples.'

    def fact(field, value, unit):
        return dict(subjects=[dict(text='encoder', key='encoder')], property=dict(text=field, key=field),
                    scope=[], relation='eq', cue='', values=[dict(kind='number', text=value, key=value, unit=unit)])

    for batch, expected in [('1024', 'support'), ('512', 'contradict')]:
        context = f'The encoder used window length 1024 tokens and batch size {batch} samples.'
        requirements = [fact('used window length', '1024', 'tokens'), fact('batch size', '1024', 'samples')]
        observations = [fact('used window length', '1024', 'tokens'), fact('batch size', batch, 'samples')]
        source = {'facts': [{**item, 'evidence_ids': ['S1'], 'assertion': ''} for item in observations]}
        final, check = run(claim, context, [proposal(),
                           (pilot.verdict.NUMERIC_CLAIM_PROMPT, dict(requirements=requirements, unresolved=[])),
                           (pilot.verdict.NUMERIC_SOURCE_PROMPT, source)])
        assert final['label'] == expected
        assert check['method'] == 'numeric_binding'


def test_compile_repeated_count_noun_preserves_each_and_other_count():
    parser = import_module('04_factchecker.inference.decoder_parser')
    claim = 'The study recruited 36 reviewers across 13 sites and assigned exactly two reviewers to each response.'

    def fact(subject, field, value, scopes):
        return dict(subjects=[dict(text=subject, key=subject)], property=dict(text=field, key=field),
                    scope=[dict(text=s, key=s) for s in scopes], relation='eq', cue='',
                    values=[dict(kind='number', text=value, key=value, unit='')])

    raw = dict(requirements=[fact('study', 'recruited', '36', ['reviewers', 'across 13 sites']),
                             fact('response', 'assigned', 'two', ['two reviewers', 'to each response'])], unresolved=[])
    compiled = pilot.verdict._numeric_claim_records(raw, claim, bind_repeated=True)
    facts = parser.parse_requirements(compiled, claim, numeric_binding=True, bind_repeated=True)
    assert [f.values[0].unit for f in facts] == ['reviewers', 'reviewers']
    assert [f.scope[0].span.text for f in facts] == ['across 13 sites', 'to each response']
    raw['requirements'][1]['scope'].pop()
    incomplete = pilot.verdict._numeric_claim_records(raw, claim, bind_repeated=True)
    with pytest.raises(ValueError, match='uncovered_claim_content'):
        parser.parse_requirements(incomplete, claim, numeric_binding=True, bind_repeated=True)


def test_compile_whole_token_and_keep_conditions_bound_to_their_value():
    parser = import_module('04_factchecker.inference.decoder_parser')
    claim = "Model's agreement of 0.82 on CorpusA was obtained under the strict condition."
    fact = dict(evidence=[claim], subjects=[dict(text='Model', key='model')],
                property=dict(text='agreement', key='agreement'),
                scope=[dict(text='CorpusA', key='dataset'), dict(text='strict condition', key='criterion')],
                relation='eq', cue='on', values=[dict(kind='number', text='0.82', key='0.82', unit='')])
    action = {**fact, 'cue': 'under', 'values': [dict(kind='text', text='obtained', key='observed', unit='')]}
    parser.parse_requirements(dict(requirements=[fact, action], unresolved=[]), claim,
                              numeric_binding=True, bind_repeated=True)
    context = 'Model reported agreement of 0.82 on CorpusA for the loose condition and 0.61 on CorpusB for the strict condition.'
    for value, dataset, condition, valid in [
        ('0.82', 'CorpusA', 'strict condition', False), ('0.61', 'CorpusA', 'strict condition', False),
        ('0.82', 'CorpusA', 'loose condition', True), ('0.61', 'CorpusB', 'strict condition', True),
    ]:
        observation = {**fact, 'evidence': [context], 'cue': '',
                       'scope': [dict(text=dataset, key='dataset'), dict(text=condition, key='criterion')],
                       'values': [dict(kind='number', text=value, key=value, unit='')]}
        observations = parser.parse_observations({'facts': [observation]}, context, bind_repeated=True)
        if valid:
            assert pilot.verdict._check_numeric_facts(observations, context, bind_repeated=True) == observations
        else:
            with pytest.raises(ValueError, match=r'numeric_(target|scope)_crosses_parallel_measurement'):
                pilot.verdict._check_numeric_facts(observations, context, bind_repeated=True)


def test_compiler_normalizes_explicit_transitions_without_losing_qualifiers():
    parser = import_module('04_factchecker.inference.decoder_parser')
    claim = 'Deduplication lowered the size of the dataset from 120 to 60.'
    raw = dict(requirements=[dict(
        subjects=[dict(text='dataset', key='dataset')],
        property=dict(text='lowered the size', key='size'),
        scope=[dict(text='Deduplication', key='deduplication')],
        relation='eq', cue='from 120 to 60',
        values=[dict(kind='number', text=value, key=value, unit='') for value in ('120', '60')],
    )], unresolved=[])
    compiled = pilot.verdict._numeric_claim_records(raw, claim, bind_repeated=True)
    facts = parser.parse_requirements(compiled, claim, numeric_binding=True, bind_repeated=True)
    assert facts[0].relation == 'transition'
    assert [v.number for v in facts[0].values] == [120, 60]
    assert facts[0].scope[0].span.text == 'Deduplication'
    raw['requirements'][0]['property']['text'] = 'doubled the size'
    with pytest.raises(ValueError, match='inconsistent_transition_direction'):
        pilot.verdict._numeric_claim_records(raw, claim.replace('lowered', 'doubled'), bind_repeated=True)


def test_compiler_rejects_multiple_measurements_inside_one_scalar_record():
    parser = import_module('04_factchecker.inference.decoder_parser')
    claim = 'The encoder used window length 1024 tokens and batch size 1024 samples.'
    fact = dict(evidence=[claim], subjects=[dict(text='encoder', key='encoder')],
                property=dict(text='used', key='configuration'), scope=[], relation='eq', cue='',
                values=[dict(kind='number', text='1024', key='window', unit='tokens'),
                        dict(kind='number', text='1024', key='batch', unit='samples')])
    with pytest.raises(ValueError, match='multiple_scalar_operands_need_fields'):
        parser.parse_requirements(dict(requirements=[fact], unresolved=[]), claim,
                                  numeric_binding=True, bind_repeated=True)


def test_numeric_routing_distinguishes_compound_terms_and_model_ids():
    assert comparison.quantities('The gpt-4 model used one-versus-all.') == []
    assert [q['value'] for q in comparison.quantities('The gpt-4 model used one-versus-all with C=1.5.')] == ['1.5']
    assert comparison.quantities('The operating temperature-4 degrees was recorded.')
    assert comparison.quantities('The trial reported a two-fold increase.')
    assert comparison.quantities('The trial had a three-year follow-up.')
    assert comparison.quantities('The difference was −4.2 percent.')


def test_recovery_restores_unique_source_punctuation():
    context = 'Three reviewers chose “yes” in the voting round.'
    raw = dict(label='contradict', evidence_ids=['S1'], observation=context.replace('“', '"').replace('”', '"'))
    result, reason = comparison.verify_recovery(raw, 'Three reviewers chose no.',
                                                pilot.verdict.source_segments(context), quantitative=True)
    assert reason is None
    assert result['reasoning'] == context
