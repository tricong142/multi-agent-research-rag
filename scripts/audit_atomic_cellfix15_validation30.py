"""Read-only replay of received Validation30; no model inference or gold edits."""
from collections import Counter
import hashlib
import importlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import zipfile

from scripts.audit_atomic_cellfix3 import extract
from scripts.atomic_validation_review import write_once, json_bytes
from scripts.atomic_cellfix15_replay_compat import patch_workflow

ROOT = Path(__file__).resolve().parents[1]
RUN = '20261102T163553Z-ed00dfbc'
BASE = ROOT / 'research-runs' / ('audit-cellfix15-validation30-' + RUN)
OUT, SOURCE = BASE / 'artifact', BASE / 'workspace'
ARCHIVE = ROOT.parent / ('output-cellfix15-kaggle-' + RUN + ' (1).zip')
REPORT = ROOT / 'docs' / ('atomic-verifier-cellfix15-validation30-audit-' + RUN + '.json')
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def rows(path):
    return [json.loads(v) for v in path.read_bytes().splitlines()]


def parser_accepts(schema, source, serialized, decoder):
    from lmformatenforcer import JsonSchemaParser, CharacterLevelParserConfig
    CheckedParser = importlib.import_module('04_factchecker.inference.decoder_parser').CheckedParser
    config = CharacterLevelParserConfig()
    config.force_json_field_order = decoder.DECODER['strict_field_order']
    config.max_consecutive_whitespaces = decoder.DECODER['max_consecutive_whitespaces']
    config.alphabet += ''.join(sorted(set(source) - set(config.alphabet)))
    parser = CheckedParser(JsonSchemaParser(schema, config=config))
    try:
        for character in serialized:
            parser = parser.add_character(character)
    except ValueError:
        return False
    return parser.can_end()


def main():
    release = read(ROOT / 'docs/atomic-verifier-cellfix15-release.json')
    for name, expected in release['files'].items():
        assert sha((ROOT / name).read_bytes()) == expected, name
    raw = ARCHIVE.read_bytes()
    write_once(BASE / 'original-output.zip', raw)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        assert len(z.infolist()) < 1000 and sum(i.file_size for i in z.infolist()) < 256 * 1024**2
        manifest = json.loads(z.read('output-manifest.json'))
        assert manifest['run_id'] == RUN
        names = [v['path'] for v in manifest['files']]
        assert len(names) == len(set(names))
        assert set(z.namelist()) == set(names) | {'output-manifest.json'}
        for item in manifest['files']:
            data = z.read(item['path'])
            assert len(data) == item['size'] and sha(data) == item['sha256'], item['path']
        payload = z.read('frozen-inputs.zip')
        inputs = json.loads(z.read('input-manifest.json'))
        assert inputs == release['payload_files'] and sha(payload) == release['payload_sha256']
        extract(z, OUT)
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        assert set(z.namelist()) == set(inputs)
        for name, item in inputs.items():
            data = z.read(name)
            assert len(data) == item['size'] and sha(data) == item['sha256'], name
        extract(z, SOURCE)
    for key in ('candidate', 'criteria_sha256', 'payload_sha256'):
        assert read(OUT / 'notebook-provenance.json')[key] == release[key]
    standalone = {}
    for name in ('predictions.jsonl', 'calls.jsonl'):
        blob = (ROOT.parent / name).read_bytes()
        assert blob == (OUT / 'validation30' / name).read_bytes(), name
        standalone[name] = sha(blob)
    compatible = OUT / 'compatibility/cellfix15-full39-replay-v1/atomic_workflow_cellfix15.py'
    assert compatible.read_bytes() == patch_workflow((SOURCE / 'atomic_workflow_cellfix15.py').read_bytes())
    print('Verified archive, standalone files and frozen payload; loading local replay code.', flush=True)
    sys.path.insert(0, str(SOURCE))
    spec = importlib.util.spec_from_file_location('cf15_dev30_audit', compatible)
    w = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w)
    r = w.r
    request_cache = importlib.import_module('04_factchecker.inference.cellfix14_runtime').decode_request
    assert Path(r.__file__).resolve().is_relative_to(SOURCE)
    frozen, all_cases, _, _, _, baseline, _ = r.load_frozen(r.CRITERIA)
    binding, criteria, cases = w.configuration(SOURCE / 'validation/cellfix15')
    assert binding == read(OUT / 'validation-lock.json') == read(OUT / 'validation30/validation-binding.json')
    assert criteria == read(OUT / 'validation30/criteria.json')
    assert cases == read(OUT / 'validation30/cases.json')
    for original, reviewed in [('decomposition-probe', 'reviewed-probe'), ('verifier39', 'reviewed-verifier39')]:
        assert {p.name: p.read_bytes() for p in (OUT / original).iterdir() if p.name != 'semantic-review.json'} == {
            p.name: p.read_bytes() for p in (OUT / reviewed).iterdir() if p.name != 'semantic-review.json'}
    assert r.require_probe_review(OUT / 'reviewed-probe') == read(OUT / 'verifier39/probe-admission.json')
    with request_cache(None):
        admission = w.require_full39(OUT / 'reviewed-verifier39', OUT / 'reviewed-probe')
    assert admission == read(OUT / 'validation30/full39-admission.json')
    print('Verified probe and full39 admission; replaying Validation30.', flush=True)
    provenance = read(OUT / 'validation30/provenance.json')
    assert provenance['criteria_sha256'] == release['criteria_sha256']
    for key in ('source_sha256', 'prompt_sha256'):
        assert provenance[key] == frozen[key]
    for key in ('model_files', 'shared_tokenizer_files', 'repo_id', 'revision', 'dtype', 'quantization', 'seed', 'do_sample'):
        assert provenance['model'][key] == baseline['model_metadata'][key]
    assert provenance['model']['structured_decoder'] == frozen['structured_decoder']
    assert provenance['model']['max_new_tokens'] == frozen['max_new_tokens']
    assert provenance['validation_binding_sha256'] == sha((SOURCE / 'validation/cellfix15/binding.json').read_bytes())
    outputs, events = rows(OUT / 'validation30/predictions.jsonl'), rows(OUT / 'validation30/calls.jsonl')
    assert [row['example_id'] for row in outputs] == [c['example_id'] for c in cases]
    # This validates the triplets against prediction messages and parsed outputs,
    # replays aggregation, and recomputes every stored automated metric.
    with request_cache(None):
        metrics = w.measured_score(outputs, cases, criteria, events)
    assert metrics == read(OUT / 'validation30/metrics.json')
    write_once(BASE / 'metrics-replayed.json', json_bytes(metrics))
    print('All metrics recomputed exactly; checking individual validator errors and parser paths.', flush=True)
    case_finished = [e['example_id'] for e in events if e['event'] == 'case_finished']
    assert case_finished == [c['example_id'] for c in cases]
    generations = {e['call_id']: e for e in events if e['event'] == 'generation'}
    decisions = importlib.import_module('04_factchecker.inference.assessment_decisions')
    evidence = importlib.import_module('04_factchecker.inference.assessment_evidence')
    focus = importlib.import_module('04_factchecker.inference.assessment_focus')
    numeric = importlib.import_module('04_factchecker.inference.numeric_verifier')
    details, issues, call_id = [], Counter(), 0
    for case, row in zip(cases, outputs):
        print('Checking ' + case['example_id'], flush=True)
        result = row['result']
        r.replay_result(result, case['claim'], case['context'], criteria)
        traces = []
        for trace in result['trace']:
            call_id += 1
            gen = generations[call_id]
            assert gen['json_valid'] is True and gen['parse_error_type'] is None
            request = json.loads(trace['messages'][1]['content'])
            raw_output = trace['output']
            before = json.dumps(raw_output, sort_keys=True)
            with request_cache(None):
                schema, source = r.decoding.schema_for(trace['messages'])
            assert parser_accepts(schema, source, gen['raw_output'], r.decoding), (case['example_id'], call_id)
            try:
                if trace['stage'] == 'decompose':
                    checked = r.atomic.normalize_decomposition(raw_output, request['claim'])
                else:
                    checked = r.atomic.assess_part(raw_output, request['part'], request['context'])
            except ValueError as exc:
                assert trace.get('valid') is not True and str(exc) == trace.get('validation_issue'), (case['example_id'], str(exc))
                checked = {'replayed_error': str(exc)}
            else:
                assert trace['valid'] is True and not trace.get('validation_issue')
            assert before == json.dumps(raw_output, sort_keys=True)
            issues[trace.get('validation_issue') or 'valid'] += 1
            item = {'call_id': call_id, 'stage': trace['stage'], 'issue': trace.get('validation_issue'),
                    'schema_accepts_actual_output': True, 'raw_output': raw_output, 'replayed': checked,
                    'generated_tokens': gen['generated_tokens']}
            if trace['stage'] != 'decompose' and result['assessed_label'] != case['label']:
                part = request['part']
                item['decision_evidence'] = decisions.decision_evidence(part, case['context'])
                item['numeric_choices'] = decisions.numeric_choices(part, case['context'])
                item['population_witness'] = evidence.population_witness(part, case['context'])
                item['observation_diagnostics'] = [dict(
                    citation_issue=evidence.citation_issue(part, o['member'], o['quotes'], o['truth']),
                    focus_issue=focus.observation_focus_issue(part, o['member'], o['quotes'], o['truth'], case['context']),
                    numeric_check=numeric.check_numeric(o['numeric'], part['quote'], case['context'], metric=part['scope']['metric'])
                        if isinstance(o['numeric'], dict) and 'kind' in o['numeric'] else None)
                    for o in raw_output.get('observations', [])]
            traces.append(item)
        details.append({**case, 'prediction': result['assessed_label'], 'status': result['status'],
                        'stop_reason': result['stop_reason'], 'elapsed_ms': result['elapsed_ms'],
                        'correct': result['assessed_label'] == case['label'], 'traces': traces})
    assert call_id == len(generations) == metrics['backend_calls']
    classification = read(OUT / 'validation30/classification.json')
    for label, entry in classification['per_label'].items():
        tp = sum(c['label'] == row['result']['assessed_label'] == label for c, row in zip(cases, outputs))
        actual = sum(c['label'] == label for c in cases)
        predicted = sum(row['result']['assessed_label'] == label for row in outputs)
        assert entry == dict(precision=tp/predicted if predicted else None, recall=tp/actual if actual else None,
                             gold_count=actual, predicted_count=predicted)
    assert classification['per_paper'] == metrics['dataset_groups']
    assert classification['false_support'] == metrics['false_support']
    assert classification['non_support_gold_count'] == sum(c['label'] != 'support' for c in cases)
    assert classification['latency_ms'] == [v['result']['elapsed_ms'] for v in outputs]
    summary = read(OUT / 'validation30/summary.json')
    assert summary['experiment_completed'] is True and summary['prediction_count'] == 30
    assert summary['backend_calls'] == call_id and summary['automated_gate_pass'] == metrics['automated_gate_pass']
    assert summary['validation30_used_for_tuning'] is True and summary['independent_validation_completed'] is False
    for item in manifest['files']:
        assert sha((OUT / item['path']).read_bytes()) == item['sha256'], item['path']
    for name, expected in release['files'].items():
        assert sha((ROOT / name).read_bytes()) == expected, name
    report = dict(run_id=RUN, archive_sha256=sha(raw), verified_output_files=len(manifest['files']),
                  verified_payload_files=len(inputs), standalone_sha256=standalone,
                  criteria_sha256=release['criteria_sha256'], compatibility_worker_sha256=sha(compatible.read_bytes()),
                  prerequisite_admission_replayed=True, all_predictions_and_calls_replayed=True,
                  all_actual_outputs_match_reconstructed_schema=True,
                  metrics_recomputed_exactly=True, classification_recomputed_exactly=True,
                  metrics=metrics, event_counts=dict(Counter(e['event'] for e in events)),
                  validation_issues=dict(issues), summary=summary, cases=details,
                  original_outputs_and_frozen_release_unchanged=True, new_model_inference=False,
                  limitations=['File consistency does not attest the remote host.',
                               'Schema replay checks JSON constraints, not a new model generation.',
                               'Semantic audit is AI analysis, not a human approval or independent holdout.'])
    REPORT.write_bytes(json_bytes(report))
    print(json.dumps({k: v for k, v in report.items() if k not in ('cases', 'metrics', 'summary')}, indent=2))


if __name__ == '__main__':
    main()
