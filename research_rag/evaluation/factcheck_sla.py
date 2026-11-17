"""Evaluate verifier safety and coverage from paired labels or a confusion table."""
import argparse
from collections import Counter
import json
from pathlib import Path


LABELS = ('support', 'contradict', 'not_enough_info')
INCOMPLETE = '__incomplete__'


def score(confusion):
    counts = Counter()
    for row in confusion:
        gold, prediction, n = row['gold'], row['prediction'], row['n']
        if gold not in LABELS or prediction not in (*LABELS, INCOMPLETE) or type(n) is not int or n < 0:
            raise ValueError('Invalid confusion row')
        counts[gold, prediction] += n
    actual = {label: sum(n for (g, _), n in counts.items() if g == label) for label in LABELS}
    if not all(actual.values()):
        raise ValueError('SLA evaluation needs gold cases in every class')
    total = sum(actual.values())
    per_class = {}
    for label in LABELS:
        tp = counts[label, label]
        predicted = sum(n for (_, p), n in counts.items() if p == label)
        per_class[label] = dict(gold=actual[label], predicted=predicted, correct=tp,
                                precision=tp / predicted if predicted else 0.0,
                                recall=tp / actual[label], f1=2 * tp / (predicted + actual[label]))
    non_support = total - actual['support']
    false_support = counts['contradict', 'support'] + counts['not_enough_info', 'support']
    answerable = actual['support'] + actual['contradict']
    missed = sum(counts[g, p] for g in ('support', 'contradict') for p in ('not_enough_info', INCOMPLETE))
    incomplete = sum(counts[g, INCOMPLETE] for g in LABELS)
    macro_f1 = sum(row['f1'] for row in per_class.values()) / len(LABELS)
    support_precision = per_class['support']['precision']
    checks = dict(zero_false_support=false_support == 0, support_precision_at_least_85=support_precision >= .85,
                  macro_f1_at_least_85=macro_f1 >= .85, answerable_abstention_at_most_15=100 * missed <= 15 * answerable)
    return dict(cases=total, false_support=false_support, non_support_gold=non_support,
                false_support_rate=false_support / non_support, support_precision=support_precision,
                macro_f1=macro_f1, answerable_cases=answerable, answerable_abstentions=missed,
                answerable_abstention_rate=missed / answerable,
                overall_abstention_rate=(sum(counts[g, 'not_enough_info'] for g in LABELS) + incomplete) / total,
                incomplete=incomplete, per_class=per_class, checks=checks, sla_pass=all(checks.values()))


def compare(cases, predictions):
    expected = [c['example_id'] for c in cases]
    actual = [p['example_id'] for p in predictions]
    if len(set(expected)) != len(expected) or actual != expected:
        raise ValueError('Predictions must cover every case exactly once in gold order')
    counts = Counter((c['label'], p['result']['assessed_label'] if p['result']['status'] == 'completed' else INCOMPLETE)
                     for c, p in zip(cases, predictions))
    return score(dict(gold=g, prediction=p, n=n) for (g, p), n in counts.items())


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    source = cli.add_mutually_exclusive_group(required=True)
    source.add_argument('--metrics', type=Path, help='Historical metrics.json containing confusion')
    source.add_argument('--cases', type=Path, help='Gold cases.json in prediction order')
    cli.add_argument('--predictions', type=Path, help='Required with --cases')
    args = cli.parse_args()
    if bool(args.cases) != bool(args.predictions):
        cli.error('--cases and --predictions must be provided together')
    if args.metrics:
        report = score(json.loads(args.metrics.read_bytes())['confusion'])
    else:
        report = compare(json.loads(args.cases.read_bytes()),
                         [json.loads(row) for row in args.predictions.read_bytes().splitlines()])
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['sla_pass'] else 1)


if __name__ == '__main__':
    main()
