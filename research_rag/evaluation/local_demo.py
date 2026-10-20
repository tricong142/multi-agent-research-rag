"""Per-agent local diagnostics with explicit execution provenance; no model downloads."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import html
import importlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ('retrieval', 'reader', 'summarizer', 'factchecker', 'writer')
TESTS = {
    'retrieval': ['research_rag.tests.test_integration.RetrievalTests',
                  'research_rag.tests.test_planning.PlanningTests.test_retrieval_agent_changes_query_and_tool_from_feedback'],
    'reader': ['research_rag.tests.test_reader_smoke', 'research_rag.tests.test_layout_windowing',
               'research_rag.tests.test_reader_api_retry'],
    'summarizer': ['research_rag.tests.test_summary_trace', 'research_rag.tests.test_evidence_formatting'],
    'factchecker': ['research_rag.tests.test_confidence_repair', 'research_rag.tests.test_confidence_diagnostic'],
    'writer': ['05_writer.tests.test_loop_and_schema', '05_writer.tests.test_inference_actions'],
}


def save_json(path, value):
    with Path(path).open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')


def save_rows(path, rows):
    with Path(path).open('x', encoding='utf-8') as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')


def fingerprint(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return {'path': str(Path(path).resolve()), 'sha256': digest.hexdigest()}


def contract_tests(agent, out):
    suite = unittest.defaultTestLoader.loadTestsFromNames(TESTS[agent])
    with (out / 'tests.detail.log').open('x', encoding='utf-8') as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    failed = len(result.failures) + len(result.errors)
    metrics = {'execution_mode': 'contract_tests_with_test_doubles', 'model_inference': False,
               'tests_run': result.testsRun, 'passed': result.testsRun - failed - len(result.skipped)
                    - len(result.expectedFailures) - len(result.unexpectedSuccesses),
               'failures': len(result.failures), 'errors': len(result.errors),
               'skipped': len(result.skipped), 'expected_failures': len(result.expectedFailures),
               'unexpected_successes': len(result.unexpectedSuccesses),
               'success': result.wasSuccessful() and result.testsRun > 0,
               'failed_test_ids': [case.id() for case, _ in result.failures + result.errors],
               'note': 'These tests check behavior and contracts; their pass rate is not model accuracy.'}
    save_json(out / 'tests.json', metrics)
    return metrics['success']


def retrieval_demo(out):
    from research_rag.evaluate import read_jsonl
    from research_rag.retrieval import RetrievalAgent, RetrievalService, CORPUS_PATH, INDEX_DIR
    qrels = ROOT / 'research_rag/evaluation/retrieval_smoke_qrels.jsonl'
    rows = read_jsonl(qrels)
    service = RetrievalService(offline=True)
    started = time.perf_counter()
    service._load_static()
    load_ms = (time.perf_counter() - started) * 1000
    corpus_ids = {row['doc_id'] for row in service._rows}
    agent = RetrievalAgent(service, policy='bm25')
    predictions, recalls, latencies = [], [], []
    for row in rows:
        relevant = set(row['relevant_doc_ids'])
        if not relevant or not relevant <= corpus_ids:
            raise ValueError('Qrels must reference known corpus IDs')
        result = agent.run(state={'question': row['query'], 'search_count': 0,
                         'budget': {'max_searches': 1}, 'retrieval_history': []}, top_k=5)
        found = {chunk['doc_id'] for chunk in result['chunks']}
        recalls.append(len(found & relevant) / len(relevant))
        latencies.append(result['trace'][0]['elapsed_ms'])
        predictions.append({**row, 'known_positive_hit': bool(found & relevant), 'result': result})
    save_rows(out / 'predictions.jsonl', predictions)
    return {'execution_mode': 'live_local_bm25_agent', 'model_inference': False,
            'n': len(rows), 'top_k': 5, 'known_positive_hit_at_5': sum(v > 0 for v in recalls) / len(rows),
            'known_positive_recall_at_5': statistics.mean(recalls), 'artifact_load_ms': round(load_ms, 2),
            'latency_ms_mean': statistics.mean(latencies),
            'latency_ms_p95': sorted(latencies)[math.ceil(.95 * len(latencies)) - 1],
            'dense_fallback_queries': sum(bool(p['result'].get('warning')) for p in predictions),
            'inputs': [fingerprint(qrels), fingerprint(CORPUS_PATH), fingerprint(INDEX_DIR / 'bm25_index.pkl')],
            'note': 'Ten project-authored queries with confirmed positives, not exhaustive qrels or independent held-out data. Dense encoder and training LoRA router were not run.'}


def reader_demo(out):
    from research_rag.evaluate import read_jsonl
    from research_rag.evaluation.reader_smoke import score_extractions
    from train_agent2_reader.tools.tool_alt_segmentation import extract_with_pymupdf, has_native_text_layer
    manifest = ROOT / 'research_rag/evaluation/reader_smoke_manifest.jsonl'
    rows, extractions, inputs = read_jsonl(manifest), [], [fingerprint(manifest)]
    started = time.perf_counter()
    for row in rows:
        path = (manifest.parent / row['pdf_path']).resolve()
        if not path.is_relative_to(manifest.parent.resolve()):
            raise ValueError('Fixture PDF outside manifest directory')
        inputs.append(fingerprint(path))
        if not has_native_text_layer(str(path)):
            extractions.append({'pdf_path': row['pdf_path'], 'error_type': 'NoNativeTextLayer'})
            continue
        blocks = extract_with_pymupdf(str(path))
        if not blocks:
            extractions.append({'pdf_path': row['pdf_path'], 'error_type': 'NoNativeTextLayer'})
        else:
            extractions.append({'pdf_path': row['pdf_path'], 'chunks': [
                {'text': block.text, 'metadata': {'page_no': block.page_no},
                 'bbox': block.bbox, 'source_tool': block.source_tool} for block in blocks]})
    save_rows(out / 'extractions.jsonl', extractions)
    return {'execution_mode': 'live_reader_tool_only', 'model_inference': False,
            **score_extractions(rows, extractions), 'inputs': inputs,
            'elapsed_ms': round((time.perf_counter() - started) * 1000, 2),
            'scope': 'Actual PyMuPDF extraction tool. Reader router, Gemini critic, LayoutLMv3 and OCR not executed. The scan remains a failure in the all-PDF denominator.'}


def stored_demo(agent, out):
    from research_rag.evaluate import read_jsonl, factchecker_metrics, summarizer_evidence_metrics
    path = ROOT / ('train_agent3_summarizer/data/eval_results.jsonl' if agent == 'summarizer'
                   else '04_factchecker/data/eval_predictions.jsonl')
    rows = read_jsonl(path)
    metrics = (summarizer_evidence_metrics if agent == 'summarizer' else factchecker_metrics)(rows)
    save_rows(out / 'predictions.jsonl', rows)
    return {'execution_mode': 'stored_prediction_scoring', 'model_inference': False,
            **metrics, 'inputs': [fingerprint(path)],
            'provenance_note': 'Recomputed metrics from existing predictions, not local inference. This runner does not certify their original model revision or independent annotation. The development data may overlap training.'}


def writer_demo(out):
    evaluator = importlib.import_module('05_writer.eval_writer')
    node = importlib.import_module('05_writer.node').WriterNode()
    path = ROOT / '05_writer/data/writer_eval_candidates.jsonl'
    cases = evaluator.read_jsonl(path)
    predictions = []
    started = time.perf_counter()
    for case in cases:
        predictions.append({'example_id': case['example_id'], **node(case)})
    save_rows(out / 'predictions.jsonl', predictions)
    return {'execution_mode': 'live_writer_offline_baseline', 'model_inference': False,
            **evaluator.evaluate(cases, predictions), 'inputs': [fingerprint(path)],
            'elapsed_ms': round((time.perf_counter() - started) * 1000, 2),
            'note': 'Actual WriterNode conservative baseline, without the trained LLM. Inputs are derived candidate claims, not independently verified gold. Exact-copy support is a proxy; human faithfulness can remain null and warning incidence can be 100%.'}


def worker(stage, agent, out):
    if stage == 'tests':
        return 0 if contract_tests(agent, out) else 1
    if stage == 'preflight':
        from research_rag.preflight import inspect_host, inspect_models, inspect_faiss
        value = {'host': inspect_host(), 'models': inspect_models(), 'faiss': inspect_faiss(),
                 'reader': {'gemini_key_configured': bool(os.environ.get('GEMINI_API_KEY')),
                            'tesseract_available': __import__('shutil').which('tesseract') is not None}}
        save_json(out / 'preflight.json', value)
        return 0
    started = time.perf_counter()
    value = (retrieval_demo(out) if agent == 'retrieval' else reader_demo(out) if agent == 'reader'
             else writer_demo(out) if agent == 'writer' else stored_demo(agent, out))
    value['worker_elapsed_ms'] = round((time.perf_counter() - started) * 1000, 2)
    save_json(out / 'metrics.json', value)
    return 0


def run_stage(stage, agent, out, timeout):
    command = [sys.executable, '-m', 'research_rag.evaluation.local_demo', '--worker', stage,
               '--agent', agent, '--output-root', str(out)]
    started = time.perf_counter()
    with (out / f'{stage}.stdout.log').open('x', encoding='utf-8') as stdout, \
            (out / f'{stage}.stderr.log').open('x', encoding='utf-8') as stderr:
        try:
            code = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=timeout,
                         env={**os.environ, 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1'}).returncode
        except subprocess.TimeoutExpired:
            code = 124
    artifact = out / ('preflight.json' if stage == 'preflight' else stage + '.json')
    value = json.loads(artifact.read_text(encoding='utf-8')) if artifact.exists() else None
    if code == 0 and value is None:
        code = 1
    return {'state': 'completed' if code == 0 else 'timed_out' if code == 124 else 'failed',
            'exit_code': code, 'elapsed_ms': round((time.perf_counter() - started) * 1000, 2), 'result': value}


def model_status(agent, preflight):
    if not preflight:
        return 'Chua xac dinh: preflight that bai.'
    if agent == 'retrieval':
        return 'BM25 chay truc tiep; dense va LoRA router chua chay.'
    if agent == 'reader':
        missing = [name for name, present in preflight.get('reader', {}).items() if not present]
        return 'Reader day du chua chay. Thieu: ' + ', '.join(missing) if missing else 'Reader day du chua chay trong demo nay.'
    models = preflight.get('models', {})
    if agent == 'summarizer':
        available = all(models.get(key, {}).get('base_cache', {}).get('weights_complete') is True
                        for key in ('summarizer_generator', 'summarizer_critic'))
    elif agent == 'writer':
        available = models.get('writer', {}).get('base_cache', {}).get('weights_complete') is True
    else:
        available = models.get('factchecker', {}).get('checkpoint', {}).get('weights_complete') is True
    if not available:
        return 'Chua chay model: thieu base weights trong local cache.'
    if not preflight.get('host', {}).get('cuda_available'):
        return 'Chua chay model: host CPU, can kiem tra du RAM truoc inference.'
    return 'Co artifact; model inference khong nam trong luot diagnostic nay.'


def render_report(summary):
    rows = []
    for agent, result in summary['agents'].items():
        tests = result['tests']['result'] or {}
        metrics = result['metrics']['result'] or {}
        selected = {k: metrics[k] for k in ('n', 'n_cases', 'known_positive_hit_at_5',
                   'overall_exact_span_rate', 'span_coverage', 'verbatim_span_rate', 'accuracy', 'macro_f1',
                   'schema_validity_rate', 'faithfulness_score', 'low_confidence_warning_rate') if k in metrics}
        evidence = json.dumps(selected, ensure_ascii=False, indent=2)
        test_text = f"{tests.get('passed', 0)}/{tests.get('tests_run', 0)}; {result['tests']['state']}"
        prediction_file = 'extractions.jsonl' if agent == 'reader' else 'predictions.jsonl'
        rows.append('<tr><td>' + html.escape(agent) + '</td><td>' + html.escape(test_text) + '</td><td>' +
                    html.escape(metrics.get('execution_mode', result['metrics']['state'])) + '</td><td><pre>' +
                    html.escape(evidence) + '</pre></td><td>' + html.escape(result['model_status']) +
                    f'</td><td><a href="{agent}/metrics.json">Metrics</a> · <a href="{agent}/tests.detail.log">Tests</a> · '
                    f'<a href="{agent}/{prediction_file}">Predictions</a></td></tr>')
    return ('<!doctype html><html lang="vi"><meta charset="utf-8"><title>Local agent diagnostics</title>'
            '<style>body{font:16px system-ui;margin:28px;color:#172437}table{border-collapse:collapse;width:100%}'
            'td,th{border:1px solid #cad4df;padding:12px;vertical-align:top}pre{white-space:pre-wrap;font-size:13px}'
            'th{background:#eaf0f7}a{color:#1649a3}</style><h1>Demo kiểm tra từng agent</h1>'
            '<p>Test logic dùng backend giả lập. Các metrics ghi rõ lượt chạy trực tiếp hoặc chấm predictions cũ. '
            '<strong>Chưa xác nhận cả năm model fine-tune chạy trên local.</strong></p><p>Run: ' +
            html.escape(summary['run_id']) + '</p><table><thead><tr><th>Agent</th><th>Test logic</th>'
            '<th>Nguồn metrics</th><th>Metrics</th><th>Model local</th><th>Bằng chứng</th></tr></thead><tbody>' +
            ''.join(rows) + '</tbody></table><p>0.7 = 70%. Null = chưa đo/thiếu nhãn; không phải 0%. '
            'Test pass không phải độ chính xác model. <a href="summary.json">Summary</a> · '
            '<a href="preflight.json">Host/models</a></p></html>')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent', choices=('all',) + AGENTS, default='all')
    parser.add_argument('--output-root', type=Path, default=ROOT / 'research-runs/local-agent-demo')
    parser.add_argument('--timeout', type=int, default=180, help='Per subprocess; measured separately for each stage')
    parser.add_argument('--worker', choices=('tests', 'metrics', 'preflight'), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error('--timeout must be positive')
    if args.worker:
        return worker(args.worker, args.agent, args.output_root)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = args.output_root / (stamp + '-' + uuid.uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    print('PREFLIGHT: checking host and local artifacts; no model download', flush=True)
    preflight = run_stage('preflight', 'all', out, args.timeout)
    results = {}
    for agent in AGENTS if args.agent == 'all' else (args.agent,):
        folder = out / agent
        folder.mkdir()
        print('RUNNING:', agent, flush=True)
        tests = run_stage('tests', agent, folder, args.timeout)
        metrics = run_stage('metrics', agent, folder, args.timeout)
        results[agent] = {'tests': tests, 'metrics': metrics,
                          'model_status': model_status(agent, preflight['result'])}
        print(agent, 'tests=' + tests['state'], 'metrics=' + metrics['state'], flush=True)
    summary = {'run_id': out.name, 'preflight': preflight, 'agents': results,
               'all_trained_models_evaluated_locally': False,
               'quality_acceptance': 'pending independent model/evidence evaluation', 'model_downloads': False}
    save_json(out / 'summary.json', summary)
    (out / 'report.html').write_text(render_report(summary), encoding='utf-8')
    print('REPORT:', out / 'report.html', flush=True)
    print('SUMMARY:', out / 'summary.json', flush=True)
    return 0 if preflight['state'] == 'completed' and all(
        stage['state'] == 'completed' for result in results.values() for stage in (result['tests'], result['metrics'])) else 1


if __name__ == '__main__':
    raise SystemExit(main())
