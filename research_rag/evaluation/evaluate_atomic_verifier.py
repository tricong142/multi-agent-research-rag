"""Frozen, isolated atomic-verifier development experiment with a hard process deadline."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib
import json
from pathlib import Path
import sys
import time

from .compare_blind_verifier import frozen_file, load_cases, score as score_legacy
from .compare_confidence_backends import model_loader, sha256, write_json
from .compare_factchecker import TracedBackend


atomic = importlib.import_module('04_factchecker.inference.atomic_verifier')
decoding = importlib.import_module('04_factchecker.inference.atomic_decoding')
ROOT = Path(__file__).resolve().parents[2]
CRITERIA = Path(__file__).with_name('atomic_verifier_criteria_v5.json')
LABELS = ('support', 'contradict', 'not_enough_info')


def write_summary(path, value):
    pending = path.with_name(path.name + '.partial')
    write_json(pending, value)
    for attempt in range(4):
        try:
            pending.replace(path)
            return
        except PermissionError as exc:
            # Windows can briefly deny replacement; keep the previous snapshot
            # intact. Persistent permission failures must still stop the run.
            if sys.platform != 'win32' or getattr(exc, 'winerror', None) != 5 or attempt == 3:
                raise
            time.sleep(0.05 * (attempt + 1))


def load_frozen(criteria_path):
    criteria = json.loads(criteria_path.read_text(encoding='utf-8'))
    if criteria['policy'] != atomic.POLICY or criteria['backends'] != ['base_instruct']:
        raise ValueError('Unsupported atomic policy/backend')
    if criteria.get('structured_decoder') != decoding.DECODER:
        raise ValueError('Frozen structured decoder changed')
    for key in ('max_calls_per_case', 'max_attempts', 'max_new_tokens', 'cases_per_backend',
                'case_deadline_seconds', 'process_timeout_seconds'):
        if type(criteria[key]) is not int or criteria[key] < 1:
            raise ValueError('Invalid frozen budget: ' + key)
    if (criteria['maximum_total_backend_calls'] != criteria['cases_per_backend'] * criteria['max_calls_per_case'] or
            criteria['maximum_generated_tokens'] != criteria['maximum_total_backend_calls'] * criteria['max_new_tokens']):
        raise ValueError('Frozen experiment budget inconsistent')
    if (criteria['min_correct_labels_recognized'] != criteria['cases_per_backend'] or
            criteria['max_false_support'] != 0 or criteria['max_runtime_failed_rows'] != 0):
        raise ValueError('Required development gate changed')
    expected_prompts = {'decompose': atomic.DECOMPOSE_PROMPT, 'assess': atomic.ASSESS_PROMPT}
    if criteria['prompt_sha256'] != {k: hashlib.sha256(v.encode()).hexdigest() for k, v in expected_prompts.items()}:
        raise ValueError('Frozen atomic prompts changed')
    for name, digest in criteria['source_sha256'].items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or sha256(path) != digest:
            raise ValueError('Frozen source changed: ' + name)
    contract = frozen_file(criteria_path, criteria['contract_file'], criteria['contract_sha256'])
    original, cases, inputs = load_cases(criteria_path, criteria)
    baseline_path = frozen_file(criteria_path, criteria['baseline_file'], criteria['baseline_sha256'])
    baseline = json.loads(baseline_path.read_text(encoding='utf-8'))
    if baseline['input_sha256'] != {name: sha256(path) for name, path in inputs.items()}:
        raise ValueError('Baseline inputs differ from frozen regressions')
    metrics, _ = score_legacy(baseline['predictions'], cases, {**criteria, 'comparison_policy': 'all_labels',
                                  'max_attempts': 2, 'max_wrong_label_agreements': 0})
    if metrics['correct_labels_recognized'] != 37 or metrics['false_support'] != 2:
        raise ValueError('Recorded logic_v3 baseline does not match audited 37/39 result')
    probe_configuration(criteria, cases, criteria_path)
    return criteria, cases, inputs, contract, baseline_path, baseline, metrics


def probe_configuration(criteria, cases, criteria_path):
    probe = criteria['decomposition_probe']
    path = frozen_file(criteria_path, probe['cases_file'], probe['cases_sha256'])
    claims = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    if (len(claims) != 18 or any(set(row) != {'example_id', 'claim'} for row in claims) or
            len({r['example_id'] for r in claims}) != 18 or
            len({r['claim'] for r in claims}) != 18 or
            {r['claim'] for r in claims} != {r['claim'] for r in cases}):
        raise ValueError('Probe must contain exactly the 18 unique development claims without labels/context')
    if (probe['max_calls_per_case'] != 2 or probe['maximum_total_backend_calls'] != 36 or
            probe['maximum_generated_tokens'] != 36 * criteria['max_new_tokens'] or
            probe['process_timeout_seconds'] != 2400 or probe['minimum_valid_decompositions'] != 18 or
            probe['human_review_rubric'] != ['factual_predicates_not_fragments', 'all_requirements_preserved',
                'quantifier_preserved', 'entity_metric_binding_correct', 'time_condition_scope_correct']):
        raise ValueError('Probe gate/budgets differ from required protocol')
    return {**criteria, **probe, 'cases_per_backend': 18}, claims, path


def replay_result(result, claim, context, criteria):
    """Recompute valid decisions from recorded model outputs; never accept a stored label blindly."""
    if result['policy'] != criteria['policy'] or result['claim_verified'] is not False or result['promoted_to_serving'] is not False:
        raise ValueError('Invalid experimental result policy')
    trace = result['trace']
    expected_budget = {'max_calls': criteria['max_calls_per_case'], 'max_attempts': criteria['max_attempts'],
                       'max_new_tokens': criteria['max_new_tokens'],
                       'timeout_seconds': criteria.get('case_deadline_seconds', result['budget']['timeout_seconds'])}
    if result['budget'] != expected_budget:
        raise ValueError('Result budget differs from frozen criteria')
    if result['backend_calls'] != len(trace) or not 1 <= len(trace) <= criteria['max_calls_per_case']:
        raise ValueError('Invalid result call count')
    probe = result.get('evaluation_mode') == 'decomposition'
    if result.get('evaluation_mode') not in ('verification', 'decomposition'):
        raise ValueError('Unknown evaluation mode')
    plan, parts, previous, previous_stage, previous_attempt = None, [], None, None, 0
    for event in trace:
        if not 1 <= event['attempt'] <= criteria['max_attempts'] or event['max_new_tokens'] != criteria['max_new_tokens']:
            raise ValueError('Trace exceeds frozen generation budget')
        payload = json.loads(event['messages'][1]['content'])
        base_prompt = atomic.DECOMPOSE_PROMPT if event['stage'] == 'decompose' else atomic.ASSESS_PROMPT
        attempt = previous_attempt + 1 if event['stage'] == previous_stage else 1
        if event['attempt'] != attempt or event['messages'] != atomic.request_messages(
                base_prompt, payload, previous if attempt > 1 else None):
            raise ValueError('Trace prompt/attempt sequence differs from frozen policy')
        previous = event
        previous_stage, previous_attempt = event['stage'], event['attempt']
        if event['stage'] == 'decompose':
            if payload != {'claim': claim}:
                raise ValueError('Decomposition input changed or leaked label')
            if event.get('validation_issue') and event.get('validation_detail') != atomic.validation_detail(
                    event.get('output'), claim, event['validation_issue']):
                raise ValueError('Trace repair detail differs from source validation')
            if event.get('valid') is True:
                if plan is not None:
                    raise ValueError('Duplicate valid decomposition')
                plan = atomic.normalize_decomposition(event['output'], claim)
        else:
            if probe or plan is None or len(parts) >= len(plan['parts']):
                raise ValueError('Part trace without a valid plan')
            part = plan['parts'][len(parts)]
            if event['stage'] != 'part_' + str(len(parts) + 1) or payload != {'claim': claim, 'part': part, 'context': context}:
                raise ValueError('Assessment input changed or leaked label')
            if event.get('valid') is True:
                parts.append(atomic.assess_part(event['output'], part, context))
    if result['decomposition'] != plan or result['parts'] != parts:
        raise ValueError('Stored plan/parts disagree with replay')
    if result['status'] == 'completed':
        if (plan is None or plan['unresolved'] or (not probe and len(parts) != len(plan['parts']))
                or result['stop_reason'] != 'completed'):
            raise ValueError('Completed result has an incomplete plan')
        if probe:
            if parts or result['assessed_label'] is not None:
                raise ValueError('Decomposition probe cannot return evidence decisions or labels')
            return None
        labels = [p['assessed_label'] for p in parts]
        label = 'contradict' if 'contradict' in labels else 'support' if all(v == 'support' for v in labels) else 'not_enough_info'
        if result['assessed_label'] != label:
            raise ValueError('Aggregate label disagrees with replay')
        return label
    if result['status'] != 'incomplete' or result['assessed_label'] is not None:
        raise ValueError('Incomplete result must not have an aggregate label')
    return None


def score(outputs, cases, criteria):
    expected = {r['example_id']: r for r in cases}
    ids = [r['example_id'] for r in outputs]
    if len(ids) != len(set(ids)) or any(i not in expected for i in ids):
        raise ValueError('Duplicate or unknown predictions')
    correct = failed = false_support = rejected_support = calls = 0
    groups, confusion, stops = {}, Counter(), Counter()
    checks = {'all_cases_present': set(ids) == set(expected)}
    for row in outputs:
        case, result = expected[row['example_id']], row['result']
        if result.get('evaluation_mode') != 'verification':
            raise ValueError('Full verifier requires evidence assessment')
        prediction = replay_result(result, case['claim'], case['context'], criteria)
        gold = case['label']
        correct += prediction == gold
        failed += prediction is None
        false_support += prediction == 'support' and gold != 'support'
        rejected_support += gold == 'support' and prediction != 'support'
        calls += result['backend_calls']
        confusion[(gold, prediction or '__incomplete__')] += 1
        stops[result['stop_reason']] += 1
        group = groups.setdefault(case.get('dataset_group', 'original_contracts'), {'n': 0, 'correct': 0, 'false_support': 0, 'failed': 0})
        group['n'] += 1
        group['correct'] += prediction == gold
        group['false_support'] += prediction == 'support' and gold != 'support'
        group['failed'] += prediction is None
    checks.update(all_labels_correct=correct == criteria['min_correct_labels_recognized'],
                  no_false_support=false_support <= criteria['max_false_support'],
                  no_runtime_failures=failed <= criteria['max_runtime_failed_rows'],
                  within_call_budget=calls <= criteria['maximum_total_backend_calls'],
                  each_group_complete_and_correct=set(groups) == set(criteria['dataset_groups']) and all(
                      groups[k]['n'] == groups[k]['correct'] == n for k, n in criteria['dataset_groups'].items()))
    return {'n': len(outputs), 'correct_labels': correct, 'false_support': false_support,
            'runtime_failed_rows': failed, 'gold_support_rejected': rejected_support,
            'gold_support_count': sum(r['label'] == 'support' for r in cases),
            'backend_calls': calls, 'checks': checks, 'automated_gate_pass': all(checks.values()),
            'dataset_groups': groups, 'stop_reasons': dict(stops),
            'confusion': [{'gold': g, 'prediction': p, 'n': count} for (g, p), count in sorted(confusion.items())]}


def score_probe(outputs, cases, criteria):
    expected = {r['example_id']: r for r in cases}
    ids = [r['example_id'] for r in outputs]
    if len(ids) != len(set(ids)) or any(i not in expected for i in ids):
        raise ValueError('Duplicate or unknown probe predictions')
    valid = calls = 0
    for row in outputs:
        result = row['result']
        if result.get('evaluation_mode') != 'decomposition':
            raise ValueError('Probe must only perform decomposition')
        replay_result(result, expected[row['example_id']]['claim'], '', criteria)
        valid += result['status'] == 'completed'
        calls += result['backend_calls']
    checks = {'all_claims_present': set(ids) == set(expected),
              'all_decompositions_valid': valid == criteria['minimum_valid_decompositions'],
              'within_call_budget': calls <= criteria['maximum_total_backend_calls']}
    return {'n': len(outputs), 'valid_decompositions': valid, 'incomplete': len(outputs) - valid,
            'backend_calls': calls, 'checks': checks, 'automated_gate_pass': all(checks.values()),
            'semantic_review': 'pending', 'label_accuracy': None}


def decoding_trace_complete(generations, messages, criteria):
    return len(generations) == len(messages) and bool(generations) and all(
        event.get('structured_decoder') == criteria['structured_decoder'] and
        event.get('schema_sha256') == decoding.schema_sha256(decoding.schema_for(request)[0])
        for event, request in zip(generations, messages))


def require_probe_review(directory, criteria_path=CRITERIA):
    """Bind a human review to this exact candidate and replay the probe before admission."""
    criteria, cases, _, _, _, baseline, _ = load_frozen(criteria_path)
    effective, claims, _ = probe_configuration(criteria, cases, criteria_path)
    if (directory / 'criteria.json').read_bytes() != criteria_path.read_bytes():
        raise ValueError('Probe was run against different frozen criteria')
    summary = json.loads((directory / 'summary.json').read_text(encoding='utf-8'))
    if (summary.get('experiment_completed') is not True or summary.get('automated_gate_pass') is not True or
            summary.get('evaluation_mode') != 'decomposition' or summary.get('prediction_count') != 18):
        raise ValueError('Probe must finish successfully before semantic admission')
    provenance = json.loads((directory / 'provenance.json').read_text(encoding='utf-8'))
    model = provenance.get('model') or {}
    if (provenance.get('criteria_sha256') != sha256(criteria_path) or
            provenance.get('source_sha256') != criteria['source_sha256'] or
            provenance.get('prompt_sha256') != criteria['prompt_sha256'] or
            model.get('max_new_tokens') != criteria['max_new_tokens'] or
            model.get('structured_decoder') != criteria['structured_decoder'] or
            any(model.get(k) != baseline['model_metadata'].get(k) for k in (
                'model_files', 'shared_tokenizer_files', 'repo_id', 'revision', 'dtype', 'quantization', 'seed', 'do_sample'))):
        raise ValueError('Probe provenance/model does not match frozen candidate')
    prediction_path = directory / 'predictions.jsonl'
    outputs = [json.loads(line) for line in prediction_path.read_text(encoding='utf-8').splitlines()]
    if not score_probe(outputs, claims, effective)['automated_gate_pass']:
        raise ValueError('Probe structure gate failed; full 39-case run blocked')
    events = [json.loads(line) for line in (directory / 'calls.jsonl').read_text(encoding='utf-8').splitlines()]
    generations = [e for e in events if e['event'] == 'generation']
    messages = [e['messages'] for row in outputs for e in row['result']['trace']]
    if not decoding_trace_complete(generations, messages, criteria):
        raise ValueError('Probe token-constraint trace missing or mismatched')
    review = json.loads((directory / 'semantic-review.json').read_text(encoding='utf-8'))
    if (review.get('predictions_sha256') != sha256(prediction_path) or
            review.get('criteria_sha256') != sha256(criteria_path) or
            review.get('reviewer_kind') != 'human' or not isinstance(review.get('reviewer'), str) or
            not review['reviewer'].strip() or
            review.get('review_completed') is not True):
        raise ValueError('Completed human review bound to this probe is required')
    rows = review.get('cases', [])
    if len(rows) != len(claims) or {r['example_id'] for r in rows} != {r['example_id'] for r in claims}:
        raise ValueError('Review must cover every unique probe claim once')
    for row in rows:
        if (set(row.get('judgments', {})) != set(effective['human_review_rubric']) or
                any(v is not True for v in row['judgments'].values()) or not isinstance(row.get('notes'), str) or
                not row['notes'].strip()):
            raise ValueError('Every semantic criterion must pass with a written review note')
    return {'probe_predictions_sha256': sha256(prediction_path),
            'semantic_review_sha256': sha256(directory / 'semantic-review.json'), 'reviewer': review['reviewer']}


class RecordingBackend:
    """Persist call admission before executing a potentially blocking backend."""
    def __init__(self, backend, handle, case_id, counter, maximum, generation_stats=None):
        self.backend, self.handle, self.case_id = backend, handle, case_id
        self.counter, self.maximum = counter, maximum
        self.generation_stats = generation_stats if generation_stats is not None else []

    def generate_json(self, messages, *, max_new_tokens):
        if self.counter[0] >= self.maximum:
            raise RuntimeError('experiment_call_budget_exhausted')
        self.counter[0] += 1
        call_id = self.counter[0]
        self.handle.write(json.dumps({'event': 'call_started', 'call_id': call_id,
            'example_id': self.case_id, 'messages': messages, 'max_new_tokens': max_new_tokens}, ensure_ascii=False) + '\n')
        self.handle.flush()
        calls = []
        traced = TracedBackend(self.backend, 'atomic_verifier', {'call_id': call_id,
                               'example_id': self.case_id, 'event': 'call_finished'}, self.handle, calls)
        previous = getattr(self.backend, 'on_generation', None)
        def record_generation(event):
            self.generation_stats.append(event)
            self.handle.write(json.dumps({**event, 'event': 'generation', 'call_id': call_id,
                                          'example_id': self.case_id}, ensure_ascii=False) + '\n')
            self.handle.flush()
            if previous is not None:
                previous(event)
        if hasattr(self.backend, 'on_generation'):
            self.backend.on_generation = record_generation
        try:
            return traced.generate_json(messages, max_new_tokens=max_new_tokens)
        finally:
            if hasattr(self.backend, 'on_generation'):
                self.backend.on_generation = previous


def run_experiment(output_dir, backend_loader, *, criteria_path=CRITERIA, decomposition_probe=False):
    criteria, cases, inputs, contract, baseline_path, baseline, baseline_metrics = load_frozen(criteria_path)
    if decomposition_probe:
        criteria, cases, probe_path = probe_configuration(criteria, cases, criteria_path)
        inputs = {'probe-claims': probe_path}
    output_dir.mkdir(parents=True, exist_ok=False)
    for name, path in {'criteria.json': criteria_path, 'contract.json': contract,
                       'baseline.json': baseline_path, **{name + '.jsonl': p for name, p in inputs.items()}}.items():
        (output_dir / name).write_bytes(path.read_bytes())
    write_json(output_dir / 'cases.json', cases)
    write_json(output_dir / 'baseline-metrics.json', baseline_metrics)
    provenance = {'criteria_sha256': sha256(criteria_path), 'source_sha256': criteria['source_sha256'],
                  'prompt_sha256': criteria['prompt_sha256'], 'model': None,
                  'serving_modified': False, 'cost_usd': None, 'limitations': criteria['limitations']}
    write_json(output_dir / 'provenance.json', provenance)
    started, outputs, counter, generation_stats = time.perf_counter(), [], [0], []
    summary = {'experiment_completed': False, 'prediction_count': 0, 'backend_calls': 0,
               'automated_gate_pass': False, 'human_review': 'pending', 'overall_pass': False,
               'promoted_to_serving': False, 'cost_usd': None, 'status': 'running',
               'evaluation_mode': 'decomposition' if decomposition_probe else 'verification'}
    write_summary(output_dir / 'summary.json', summary)
    with backend_loader('base_instruct', criteria) as (backend, metadata):
        pairing_keys = ('model_files', 'shared_tokenizer_files', 'repo_id', 'revision', 'dtype', 'quantization', 'seed', 'do_sample')
        pairing = {k: metadata.get(k) == baseline['model_metadata'].get(k) for k in pairing_keys}
        provenance.update(model=metadata, historical_model_pairing=pairing)
        write_json(output_dir / 'provenance.json', provenance)
        if (not all(pairing.values()) or metadata.get('max_new_tokens') != criteria['max_new_tokens'] or
                metadata.get('structured_decoder') != criteria['structured_decoder']):
            raise ValueError('Model/revision/tokenizer/generation settings differ from frozen experiment')
        with (output_dir / 'predictions.jsonl').open('x', encoding='utf-8') as predictions, \
             (output_dir / 'calls.jsonl').open('x', encoding='utf-8') as trace, \
             (output_dir / 'evidence-review.jsonl').open('x', encoding='utf-8') as review:
            for case in cases:
                traced = RecordingBackend(backend, trace, case['example_id'], counter, criteria['maximum_total_backend_calls'], generation_stats)
                model = atomic.AtomicVerifier(traced, max_calls=criteria['max_calls_per_case'],
                    max_attempts=criteria['max_attempts'], max_new_tokens=criteria['max_new_tokens'],
                    timeout_seconds=criteria['case_deadline_seconds'])
                result = model.verify(case['claim'], case.get('context', ''), decomposition_only=decomposition_probe)
                row = {'example_id': case['example_id'], 'result': result}
                replay_result(result, case['claim'], case.get('context', ''), criteria)
                predictions.write(json.dumps(row, ensure_ascii=False) + '\n')
                predictions.flush()
                outputs.append(row)
                review.write(json.dumps({**case, **row, 'review_status': 'pending', 'reviewer': '',
                    'judgments': dict.fromkeys(criteria['human_review_rubric'])}, ensure_ascii=False) + '\n')
                review.flush()
                summary.update(prediction_count=len(outputs), backend_calls=counter[0],
                               last_case_id=case['example_id'])
                write_summary(output_dir / 'summary.json', summary)
                print(json.dumps({'case': case['example_id'], 'label': result['assessed_label'],
                      'calls': result['backend_calls'], 'stop': result['stop_reason']}), flush=True)
    metrics = (score_probe if decomposition_probe else score)(outputs, cases, criteria)
    measured = len(generation_stats) == counter[0]
    generated = sum(e['generated_tokens'] for e in generation_stats) if measured else None
    metrics['generated_tokens'] = generated
    metrics['prompt_tokens'] = sum(e['prompt_tokens'] for e in generation_stats) if measured else None
    metrics['checks']['within_measured_token_budget'] = (not measured or
        generated <= criteria['maximum_generated_tokens'] and all(e['generated_tokens'] <= criteria['max_new_tokens'] for e in generation_stats))
    call_messages = [event['messages'] for row in outputs for event in row['result']['trace']]
    metrics['checks']['structured_decoding_trace_complete'] = measured and decoding_trace_complete(
        generation_stats, call_messages, criteria)
    metrics['automated_gate_pass'] = all(metrics['checks'].values())
    assert counter[0] == metrics['backend_calls']
    write_json(output_dir / 'metrics.json', metrics)
    if decomposition_probe:
        write_json(output_dir / 'semantic-review.json', {
            'predictions_sha256': sha256(output_dir / 'predictions.jsonl'), 'criteria_sha256': sha256(criteria_path),
            'reviewer': '', 'reviewer_kind': '', 'review_completed': False,
            'cases': [{'example_id': row['example_id'], 'claim': case['claim'],
                       'judgments': dict.fromkeys(criteria['human_review_rubric']), 'notes': ''}
                      for row, case in zip(outputs, cases)]})
    else:
        old = {r['example_id']: r['verification']['assessed_label'] if r['status'] == 'ok' else None for r in baseline['predictions']}
        comparisons = [{'example_id': row['example_id'], 'gold': case['label'],
                        'baseline_label': old[row['example_id']], 'candidate_label': row['result']['assessed_label']}
                       for row, case in zip(outputs, cases)]
        write_json(output_dir / 'comparisons.json', comparisons)
    summary.update(experiment_completed=True, automated_gate_pass=metrics['automated_gate_pass'],
                   status='automated_pass_human_pending' if metrics['automated_gate_pass'] else 'automated_gates_failed',
                   elapsed_ms=round((time.perf_counter() - started) * 1000, 3))
    write_summary(output_dir / 'summary.json', summary)
    return summary


def admitted_calls(path):
    count, truncated = 0, False
    lines = path.read_text(encoding='utf-8').splitlines() if path.exists() else []
    for index, line in enumerate(lines):
        try:
            count += json.loads(line).get('event') == 'call_started'
        except json.JSONDecodeError:
            if index != len(lines) - 1:
                raise ValueError('Corrupt trace before final line')
            truncated = True
    return count, truncated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--criteria', default=CRITERIA, type=Path)
    parser.add_argument('--online-model-downloads', action='store_true')
    parser.add_argument('--validate-only', action='store_true')
    parser.add_argument('--decomposition-probe', action='store_true')
    parser.add_argument('--probe-dir', type=Path, help='Successful v2 probe with completed semantic-review.json; required for 39 cases')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    criteria, cases, *_ = load_frozen(args.criteria)
    if args.decomposition_probe:
        criteria, _, _ = probe_configuration(criteria, cases, args.criteria)
    if args.validate_only:
        print(json.dumps({'freeze_valid': True, 'cases': criteria['cases_per_backend'],
                          'maximum_calls': criteria['maximum_total_backend_calls']}))
        return
    if args.output_dir.exists():
        parser.error('Output already exists; preserve it and start a new run')
    admission = None
    if not args.decomposition_probe:
        if args.probe_dir is None:
            parser.error('Run the 18-claim probe and complete semantic review first; --probe-dir is required')
        admission = require_probe_review(args.probe_dir, args.criteria)
    if not args.worker:
        from research_rag.local import run_worker
        code = run_worker([sys.executable, '-u', '-m', __spec__.name, *sys.argv[1:], '--worker'],
                          criteria['process_timeout_seconds'])
        if code == 124 and args.output_dir.exists():
            path = args.output_dir / 'summary.json'
            result = json.loads(path.read_text()) if path.exists() else {}
            calls = args.output_dir / 'calls.jsonl'
            admitted, truncated = admitted_calls(calls)
            result.update(experiment_completed=False, automated_gate_pass=False, overall_pass=False,
                          promoted_to_serving=False, human_review='pending', stop_reason='process_timeout', status='timed_out')
            result['backend_calls'] = admitted
            result['trace_truncated_tail'] = truncated
            write_summary(path, result)
        raise SystemExit(code)
    try:
        result = run_experiment(args.output_dir, decoding.constrained_loader(model_loader(online=args.online_model_downloads)),
                                criteria_path=args.criteria, decomposition_probe=args.decomposition_probe)
        if admission:
            write_json(args.output_dir / 'probe-admission.json', admission)
    except Exception as exc:
        if args.output_dir.exists():
            path = args.output_dir / 'summary.json'
            failure = json.loads(path.read_text()) if path.exists() else {}
            failure.update(experiment_completed=False, automated_gate_pass=False, overall_pass=False,
                promoted_to_serving=False, human_review='pending', status='failed', stop_reason='worker_error', error_type=type(exc).__name__)
            write_summary(path, failure)
        print(json.dumps({'error_type': type(exc).__name__, 'status': 'worker_error'}), file=sys.stderr)
        raise SystemExit(2)
    print(json.dumps(result, indent=2))
    if not result['automated_gate_pass']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
