"""Prospective blind label/evidence experiment; never modifies serving or calls Gemini."""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import time

from .compare_confidence_backends import model_loader, sha256, write_json
from .compare_factchecker import TracedBackend, build_label_challenges, score_label_challenges

verifier = importlib.import_module("04_factchecker.inference.verifier")
ROOT = Path(__file__).resolve().parents[2]
CRITERIA = Path(__file__).with_name("blind_verifier_criteria.json")


def assess(backend, row, criteria):
    started = time.perf_counter()
    attempts, decision, repair_issue = [], None, None
    model = verifier.BlindVerifier(backend, max_new_tokens=criteria["max_new_tokens"],
                                  prompt_profile=criteria.get("verifier_prompt_profile", "baseline_v1"))
    for attempt in range(1, criteria["max_attempts"] + 1):
        try:
            options = {"repair_issue": repair_issue} if repair_issue else {}
            decision = model.verify(row["claim"], row["context"], repair=attempt > 1, **options)
            attempts.append({"attempt": attempt, "ok": True})
            break
        except ValueError as exc:
            failure = {"attempt": attempt, "ok": False, "error_type": type(exc).__name__}
            if criteria.get("repair_feedback_policy") == "quote_membership_v1":
                repair_issue = ("quote_membership" if str(exc) ==
                    "Every evidence quote must be an exact substring of the supplied context" else None)
                failure["validation_issue"] = repair_issue or "output_schema"
            attempts.append(failure)
        except Exception as exc:
            attempts.append({"attempt": attempt, "ok": False, "error_type": type(exc).__name__})
            break  # Repair only malformed output, not a failed backend.
    return {"example_id": row["example_id"], "status": "ok" if decision else "verification_failed",
            "verification": decision.as_dict() if decision else None, "attempts": attempts,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3)}


def score(outputs, cases, criteria):
    policy = criteria.get('comparison_policy', 'selected_wrong_label')
    if policy not in ('selected_wrong_label', 'all_labels'):
        raise ValueError('Unknown verifier comparison policy')
    expected = {row["example_id"]: row for row in cases}
    ids = [row["example_id"] for row in outputs]
    complete = len(ids) == len(set(ids)) == criteria["cases_per_backend"] and set(ids) == set(expected)
    correct = wrong = false_support = failed = 0
    comparisons, groups, families = [], {}, {}
    for output in outputs:
        row = expected[output["example_id"]]
        decision = (verifier.validate_verification(output["verification"], row["context"])
                    if output["status"] == "ok" else None)
        failed += decision is None
        correct += decision is not None and decision.assessed_label == row["label"]
        wrong_labels = ([label for label in ('support', 'contradict', 'not_enough_info') if label != row['label']]
                        if policy == 'all_labels' else [criteria['wrong_label_map'][row['label']]])
        wrong += decision is not None and decision.assessed_label in wrong_labels
        false_support += decision is not None and decision.assessed_label == "support" and row["label"] != "support"
        for kind, proposed in [('correct', row['label'])] + [('wrong', label) for label in wrong_labels]:
            comparisons.append({"example_id": row["example_id"], "variant": kind,
                "proposed_label": proposed, **verifier.compare_with_judge(decision, proposed)})
        for bucket, name in ((groups, row.get('dataset_group', 'original_contracts')),
                             (families, row.get('family', 'original_contracts'))):
            stats = bucket.setdefault(name, {'n': 0, 'correct_labels': 0, 'false_support': 0, 'runtime_failed_rows': 0})
            stats['n'] += 1
            stats['correct_labels'] += decision is not None and decision.assessed_label == row['label']
            stats['false_support'] += decision is not None and decision.assessed_label == 'support' and row['label'] != 'support'
            stats['runtime_failed_rows'] += decision is None
    checks = {"all_cases_present": complete, "no_runtime_failures": failed == 0,
              "all_correct_labels_recognized": correct == criteria["min_correct_labels_recognized"],
              "no_wrong_label_agreements": wrong <= criteria["max_wrong_label_agreements"],
              "no_false_support": false_support == 0,
              "attempt_budget": all(1 <= len(r["attempts"]) <= criteria["max_attempts"] for r in outputs)}
    result = {"n": len(outputs), "correct_labels_recognized": correct, "wrong_label_agreements": wrong,
            "false_support": false_support, "runtime_failed_rows": failed,
            "backend_calls": sum(len(r["attempts"]) for r in outputs),
            "elapsed_ms": round(sum(r["elapsed_ms"] for r in outputs), 3),
            "checks": checks, "automated_gate_pass": all(checks.values())}
    if criteria.get('dataset_groups'):
        required_groups = criteria['dataset_groups']
        checks['each_dataset_group_complete_and_correct'] = set(groups) == set(required_groups) and all(
            groups[name]['n'] == groups[name]['correct_labels'] == count for name, count in required_groups.items())
        result['dataset_groups'], result['families'] = groups, families
    if policy == 'all_labels':
        by_id = {r['example_id']: r for r in outputs}
        predicted = [by_id[r['example_id']]['verification']['assessed_label']
                     if r['example_id'] in by_id and by_id[r['example_id']]['status'] == 'ok'
                     else '__verification_failed__' for r in cases]
        result['classification'] = importlib.import_module('04_factchecker.eval_factchecker').metrics(
            [r['label'] for r in cases], predicted)
        result['comparison_policy'] = policy
        result['wrong_alternatives_tested'] = 2 * len(outputs)
    result['automated_gate_pass'] = all(checks.values())
    return result, comparisons


def frozen_file(criteria_path, name, digest):
    if not isinstance(name, str) or Path(name).name != name or name in ('', '.', '..'):
        raise ValueError('Frozen input must be a filename in the criteria directory')
    path = criteria_path.with_name(name)
    if sha256(path) != digest:
        raise ValueError('Frozen input changed; freeze new criteria before inference')
    return path


def load_cases(criteria_path, criteria):
    contracts = frozen_file(criteria_path, 'factchecker_contract_cases.jsonl', criteria['contracts_sha256'])
    original = [json.loads(line) for line in contracts.read_text(encoding='utf-8').splitlines() if line.strip()]
    paths = {'original_contracts': contracts}
    cases = list(original)
    if criteria.get('supplemental_cases_file'):
        extra = frozen_file(criteria_path, criteria['supplemental_cases_file'], criteria['supplemental_cases_sha256'])
        cases.extend(json.loads(line) for line in extra.read_text(encoding='utf-8').splitlines() if line.strip())
        paths['scope_regression'] = extra
    if len(cases) != criteria['cases_per_backend'] or len({r['example_id'] for r in cases}) != len(cases):
        raise ValueError('Unexpected verifier case count or duplicate IDs')
    if any(r.get('label') not in ('support', 'contradict', 'not_enough_info')
           or not isinstance(r.get('claim'), str) or not r['claim'].strip()
           or not isinstance(r.get('context'), str) for r in cases):
        raise ValueError('Invalid verifier case input or gold label')
    if criteria.get('dataset_groups'):
        actual = {name: sum(r.get('dataset_group', 'original_contracts') == name for r in cases)
                  for name in {r.get('dataset_group', 'original_contracts') for r in cases}}
        if actual != criteria['dataset_groups']:
            raise ValueError('Dataset group counts differ from frozen criteria')
    return original, cases, paths


def run_experiment(output_dir: Path, backend_loader, *, criteria_path: Path = CRITERIA):
    criteria = json.loads(criteria_path.read_text(encoding="utf-8"))
    prompt_profile = criteria.get("verifier_prompt_profile", "baseline_v1")
    if prompt_profile not in verifier.PROMPT_PROFILES:
        raise ValueError("Unknown verifier prompt profile in criteria")
    if criteria.get('prompt_sha256') and hashlib.sha256(verifier.PROMPT_PROFILES[prompt_profile].encode()).hexdigest() != criteria['prompt_sha256']:
        raise ValueError('Frozen prompt changed; freeze new criteria before inference')
    if criteria.get('comparison_policy', 'selected_wrong_label') not in ('selected_wrong_label', 'all_labels'):
        raise ValueError('Unknown verifier comparison policy')
    if criteria.get('repair_feedback_policy') not in (None, 'quote_membership_v1'):
        raise ValueError('Unknown verifier repair feedback policy')
    original, cases, input_paths = load_cases(criteria_path, criteria)
    if criteria['max_attempts'] < 1 or len(criteria['backends']) * len(cases) * criteria['max_attempts'] != criteria['maximum_total_backend_calls']:
        raise ValueError('Generation call budget differs from frozen case/backend/attempt limits')
    baseline_path = frozen_file(criteria_path, 'blind_verifier_repair_baseline.json', criteria['baseline_sha256'])
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    challenges = build_label_challenges(original, criteria["baseline_label_challenges"])
    before = baseline["predictions"]
    if {(r["example_id"], r["gold_label"], r["predicted_label"]) for r in before} != {
            (r["example_id"], r["label"], r["proposed_label"]) for r in challenges}:
        raise ValueError("Historical baseline does not match the controlled label cases")
    historical = historical_path = historical_cases = None
    if criteria.get('historical_verifier_file'):
        historical_path = frozen_file(criteria_path, criteria['historical_verifier_file'], criteria['historical_verifier_sha256'])
        historical = json.loads(historical_path.read_text(encoding='utf-8'))
        scope = historical.get('comparison_scope', 'original_contracts')
        if scope not in ('original_contracts', 'all_cases'):
            raise ValueError('Unknown historical verifier comparison scope')
        historical_cases = cases if scope == 'all_cases' else original
        if [r['example_id'] for r in historical['predictions']] != [r['example_id'] for r in historical_cases]:
            raise ValueError('Historical verifier baseline does not match the comparison cases')
        if scope == 'all_cases' and historical.get('input_sha256') != {name: sha256(path) for name, path in input_paths.items()}:
            raise ValueError('Historical verifier inputs differ from the comparison cases')
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "criteria.json").write_bytes(criteria_path.read_bytes())
    (output_dir / "baseline.json").write_bytes(baseline_path.read_bytes())
    write_json(output_dir / "cases.json", cases)
    for name, path in input_paths.items():
        (output_dir / (name + '.jsonl')).write_bytes(path.read_bytes())
    write_json(output_dir / "baseline-metrics.json", score_label_challenges(
        before, criteria["baseline_label_challenges"], criteria["baseline_threshold"]))
    if historical is not None:
        (output_dir / 'historical-verifier-baseline.json').write_bytes(historical_path.read_bytes())
        historical_groups = {name: sum(r.get('dataset_group', 'original_contracts') == name for r in historical_cases)
                             for name in {r.get('dataset_group', 'original_contracts') for r in historical_cases}}
        original_criteria = {**criteria, 'cases_per_backend': len(historical_cases),
                             'min_correct_labels_recognized': len(historical_cases), 'dataset_groups': historical_groups}
        old_metrics, _ = score(historical['predictions'], historical_cases, original_criteria)
        write_json(output_dir / 'historical-verifier-metrics.json', old_metrics)
    provenance = {"criteria_sha256": sha256(criteria_path), "models": {}, "prompt": verifier.PROMPT_PROFILES[prompt_profile],
        "verifier_prompt_profile": prompt_profile,
        "repair_feedback_policy": criteria.get('repair_feedback_policy'),
        'input_sha256': {name: sha256(path) for name, path in input_paths.items()},
        "source_sha256": {name: sha256(ROOT / name) for name in (
            "04_factchecker/inference/verifier.py", "04_factchecker/inference/judge.py",
            "research_rag/evaluation/compare_blind_verifier.py",
            "research_rag/evaluation/compare_confidence_backends.py", "research_rag/evaluation/compare_factchecker.py")},
        "serving_modified": False, "cost_usd": None, "limitations": criteria["limitations"]}
    write_json(output_dir / "provenance.json", provenance)
    metrics = {}
    with (output_dir / "evidence-review.jsonl").open("x", encoding="utf-8") as review:
        for kind in criteria["backends"]:
            with backend_loader(kind, criteria) as (backend, metadata):
                provenance["models"][kind] = metadata
                if historical is not None:
                    keys = ('model_files', 'shared_tokenizer_files', 'repo_id', 'revision',
                            'dtype', 'quantization', 'seed', 'do_sample', 'max_new_tokens')
                    pairing = {key: metadata.get(key) == historical['model_metadata'].get(key) for key in keys}
                    provenance['historical_verifier_pairing'] = pairing
                write_json(output_dir / "provenance.json", provenance)
                if historical is not None and not all(pairing.values()):
                    raise ValueError('Historical verifier artifacts or generation settings differ; preserve provenance before comparing prompts')
                outputs = []
                with (output_dir / (kind + ".jsonl")).open("x", encoding="utf-8") as predictions, \
                        (output_dir / (kind + "-calls.jsonl")).open("x", encoding="utf-8") as trace:
                    for row in cases:
                        calls = []
                        traced = TracedBackend(backend, "blind_verifier", {"backend": kind,
                            "example_id": row["example_id"]}, trace, calls)
                        output = assess(traced, row, criteria)
                        predictions.write(json.dumps(output, ensure_ascii=False) + "\n")
                        predictions.flush()
                        outputs.append(output)
                        review.write(json.dumps({"backend": kind, **row, **output,
                            "review_status": "pending", "reviewer": "",
                            "judgments": dict.fromkeys(criteria["human_review_rubric"])}, ensure_ascii=False) + "\n")
                        review.flush()
                metrics[kind], comparisons = score(outputs, cases, criteria)
                write_json(output_dir / (kind + "-comparisons.json"), comparisons)
                write_json(output_dir / "metrics.json", metrics)
                print(json.dumps({"backend": kind, **metrics[kind]}), flush=True)
    complete = len(metrics) == len(criteria["backends"]) and all(m["n"] == criteria["cases_per_backend"] for m in metrics.values())
    qualifying = [name for name, m in metrics.items() if m["automated_gate_pass"]]
    result = {"experiment_completed": complete, "prediction_count": sum(m["n"] for m in metrics.values()),
        "backend_calls": sum(m["backend_calls"] for m in metrics.values()),
        "automated_gate_pass": complete and bool(qualifying), "qualifying_profiles": qualifying,
        "human_review": "pending", "overall_pass": False, "promoted_to_serving": False, "cost_usd": None}
    write_json(output_dir / "summary.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--criteria", type=Path, default=CRITERIA)
    parser.add_argument("--online-model-downloads", action="store_true")
    args = parser.parse_args()
    result = run_experiment(args.output_dir, model_loader(online=args.online_model_downloads), criteria_path=args.criteria)
    print(json.dumps(result, indent=2))
    return 0 if result["automated_gate_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
