"""Verify the portable notebook without importing or running any model cell."""
import ast
import base64
import zlib
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
import zipfile


ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK = ROOT / "scripts/kaggle_resume_validation.ipynb"


class ValidationNotebookTests(unittest.TestCase):
    def cells(self):
        return [cell["source"] for cell in json.loads(NOTEBOOK.read_text(encoding="utf-8"))["cells"]
                if cell["cell_type"] == "code"]

    def test_blind_verifier_notebook_embeds_current_sources_and_requires_setup(self):
        notebook = json.loads((ROOT / 'scripts/kaggle_blind_verifier.ipynb').read_text(encoding='utf-8'))
        cells = [cell['source'] for cell in notebook['cells'] if cell['cell_type'] == 'code']
        self.assertEqual(len(cells), 3)
        for cell in cells:
            compile(cell, 'blind-verifier-notebook', 'exec')
        tree = ast.parse(cells[1])
        entries = ast.literal_eval(next(node.value for node in tree.body if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == 'verifier_patch' for target in node.targets)))
        self.assertEqual(len(entries), 6)
        for item in entries:
            data = zlib.decompress(base64.b64decode(item['payload'], validate=True))
            self.assertEqual(data, (ROOT / item['path']).read_bytes())
            self.assertEqual(hashlib.sha256(data).hexdigest(), item['sha256'])
        previous = json.loads((ROOT / 'scripts/kaggle_confidence_backends.ipynb').read_text(encoding='utf-8'))
        previous_setup = [cell['source'] for cell in previous['cells'] if cell['cell_type'] == 'code'][1]
        start = cells[1].index('verifier_patch = ')
        end = cells[1].index('env = os.environ.copy()', start)
        self.assertEqual(cells[1][:start] + cells[1][end:], previous_setup)
        self.assertIn("'--without-pip'", cells[1])
        self.assertIn("'wrapt==2.1.2'", cells[1])
        self.assertNotIn('get_secret', '\n'.join(cells))
        scope = {'statuses': {}, 'run': Mock()}
        with self.assertRaisesRegex(AssertionError, 'Complete cell 2'):
            exec(cells[2], scope)
        scope['run'].assert_not_called()
        self.assertIn('compare_blind_verifier', cells[2])
        self.assertNotIn('compare_confidence_backends', cells[2])

    def test_scope_verifier_notebook_routes_to_base_only_criteria(self):
        notebook = json.loads((ROOT / 'scripts/kaggle_blind_verifier_scope_v2.ipynb').read_text(encoding='utf-8'))
        cells = [cell['source'] for cell in notebook['cells'] if cell['cell_type'] == 'code']
        self.assertEqual(len(cells), 3)
        for cell in cells:
            compile(cell, 'scope-verifier-notebook', 'exec')
        tree = ast.parse(cells[1])
        entries = ast.literal_eval(next(node.value for node in tree.body if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == 'verifier_patch' for target in node.targets)))
        self.assertEqual(len(entries), 6)
        for item in entries:
            data = zlib.decompress(base64.b64decode(item['payload'], validate=True))
            self.assertEqual(data, (ROOT / item['path']).read_bytes())
            self.assertEqual(hashlib.sha256(data).hexdigest(), item['sha256'])
        criteria_path = 'research_rag/evaluation/blind_verifier_scope_criteria.json'
        self.assertIn("'--criteria', str(root / '" + criteria_path + "')", cells[2])
        criteria = json.loads((ROOT / criteria_path).read_text())
        self.assertEqual(criteria['backends'], ['base_instruct'])
        self.assertEqual(criteria['verifier_prompt_profile'], 'scope_v2')
        self.assertNotIn('get_secret', '\n'.join(cells))
        scope = {'statuses': {}, 'run': Mock()}
        with self.assertRaisesRegex(AssertionError, 'Complete cell 2'):
            exec(cells[2], scope)
        scope['run'].assert_not_called()

    def test_expanded_scope_notebook_embeds_frozen_cases_baseline_and_gate(self):
        notebook = json.loads((ROOT / 'scripts/kaggle_blind_verifier_scope_regression.ipynb').read_text(encoding='utf-8'))
        cells = [c['source'] for c in notebook['cells'] if c['cell_type'] == 'code']
        self.assertEqual(len(cells), 3)
        for cell in cells:
            compile(cell, 'expanded-scope-notebook', 'exec')
        tree = ast.parse(cells[1])
        entries = ast.literal_eval(next(node.value for node in tree.body if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == 'verifier_patch' for t in node.targets)))
        self.assertEqual(len(entries), 10)
        for item in entries:
            data = zlib.decompress(base64.b64decode(item['payload'], validate=True))
            self.assertEqual(data, (ROOT / item['path']).read_bytes())
            self.assertEqual(hashlib.sha256(data).hexdigest(), item['sha256'])
        name = 'research_rag/evaluation/blind_verifier_scope_regression_criteria.json'
        self.assertIn("'--criteria', str(root / '" + name + "')", cells[2])
        criteria = json.loads((ROOT / name).read_text())
        self.assertEqual(criteria['backends'], ['base_instruct'])
        self.assertEqual(criteria['cases_per_backend'], 39)
        self.assertEqual(criteria['maximum_total_backend_calls'], 78)
        self.assertEqual(criteria['comparison_policy'], 'all_labels')
        self.assertEqual(criteria['dataset_groups'], {'original_contracts': 12, 'scope_regression': 27})
        self.assertNotIn('get_secret', '\n'.join(cells))
        scope = {'statuses': {}, 'run': Mock()}
        with self.assertRaisesRegex(AssertionError, 'Complete cell 2'):
            exec(cells[2], scope)
        scope['run'].assert_not_called()

    def test_logic_verifier_notebook_embeds_policy_and_all_case_historical_baseline(self):
        notebook = json.loads((ROOT / 'scripts/kaggle_blind_verifier_logic_v3.ipynb').read_text(encoding='utf-8'))
        cells = [c['source'] for c in notebook['cells'] if c['cell_type'] == 'code']
        self.assertEqual(len(cells), 3)
        for cell in cells:
            compile(cell, 'logic-verifier-notebook', 'exec')
        tree = ast.parse(cells[1])
        entries = ast.literal_eval(next(node.value for node in tree.body if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == 'verifier_patch' for t in node.targets)))
        self.assertEqual(len(entries), 13)
        for item in entries:
            data = zlib.decompress(base64.b64decode(item['payload'], validate=True))
            self.assertEqual(data, (ROOT / item['path']).read_bytes())
            self.assertEqual(hashlib.sha256(data).hexdigest(), item['sha256'])
        name = 'research_rag/evaluation/blind_verifier_logic_v3_criteria.json'
        self.assertIn("'--criteria', str(root / '" + name + "')", cells[2])
        self.assertIn('historical-verifier-metrics.json', cells[2])
        self.assertIn("'--without-pip'", cells[1])
        self.assertNotIn('get_secret', '\n'.join(cells))
        criteria = json.loads((ROOT / name).read_text())
        self.assertEqual(criteria['verifier_prompt_profile'], 'logic_v3')
        self.assertEqual(criteria['repair_feedback_policy'], 'quote_membership_v1')
        snapshot = json.loads((ROOT / 'research_rag/evaluation' / criteria['historical_verifier_file']).read_text())
        self.assertEqual(snapshot['comparison_scope'], 'all_cases')
        self.assertEqual(len(snapshot['predictions']), 39)
        scope = {'statuses': {}, 'run': Mock()}
        with self.assertRaisesRegex(AssertionError, 'Complete cell 2'):
            exec(cells[2], scope)
        scope['run'].assert_not_called()

    def test_confidence_notebook_uses_current_setup_and_only_confidence_diagnostic(self):
        notebook = json.loads((ROOT / "scripts/kaggle_confidence_validation.ipynb").read_text(encoding="utf-8"))
        cells = [c["source"] for c in notebook["cells"] if c["cell_type"] == "code"]
        self.assertEqual(len(cells), 3)
        self.assertEqual(cells[1], self.cells()[0])
        for source in cells:
            compile(source, "confidence-notebook", "exec")
        self.assertIn("'--comparison', 'confidence'", cells[2])
        self.assertIn("required=False", cells[2])
        self.assertNotIn("GEMINI_API_KEY", cells[2])
        self.assertNotIn("autonomy-e2e", cells[2])

    def test_component_notebooks_run_only_selected_component_with_current_payload(self):
        for name, expected in (("kaggle_confidence_backends.ipynb", 3), ("kaggle_reader_diagnostics.ipynb", 4)):
            with self.subTest(name=name):
                notebook = json.loads((ROOT / "scripts" / name).read_text(encoding="utf-8"))
                cells = [c["source"] for c in notebook["cells"] if c["cell_type"] == "code"]
                self.assertEqual(len(cells), expected)
                self.assertEqual(cells[1], self.cells()[0])
                for source in cells:
                    compile(source, name, "exec")
                inference = "\n".join(cells[2:])
                if expected == 3:
                    self.assertIn("compare_confidence_backends", inference)
                    self.assertIn("--online-model-downloads", inference)
                    self.assertNotIn("GEMINI_API_KEY", inference)
                    self.assertNotIn("reader_reliability", inference)
                else:
                    self.assertIn((ROOT / 'scripts/kaggle_gemini_probe.py').read_text(encoding='utf-8'), cells[0])
                    self.assertLess(cells[0].index("assert gemini_availability"), cells[0].index('import kagglehub'))
                    self.assertIn("gemini-availability.json", cells[2])
                    self.assertIn("last_reader_finished_at = gemini_probe_finished_at", cells[2])
                    self.assertIn("page=3", cells[2])
                    self.assertIn("--replay-dir", cells[2])
                    self.assertIn("get('state') == 'completed'", cells[3])
                    self.assertNotIn("compare_factchecker", inference)
                    self.assertNotIn("reader-smoke", inference)

    def test_gemini_probe_handles_availability_failures_without_leaking_secrets(self):
        from scripts.kaggle_gemini_probe import check_gemini_endpoint
        secret = 'sensitive-test-key'
        metadata = {'name': 'models/gemini-3.6-flash'}
        generated = {'candidates': [{'content': {'parts': [{'text': '{"ok": true}'}]}, 'finishReason': 'STOP'}],
                     'usageMetadata': {'totalTokenCount': 12, 'account': secret}}
        cases = [
            ('ok', [(200, metadata), (200, generated)], True),
            ('quota', [(200, metadata), (429, {'error': {'status': 'RESOURCE_EXHAUSTED', 'message': secret}})], False),
            ('unavailable', [(200, metadata), (503, {'error': {'status': 'UNAVAILABLE', 'message': secret}})], False),
            ('forbidden', [(403, {'error': {'status': 'PERMISSION_DENIED', 'message': secret}})], False),
            ('generation_forbidden', [(200, metadata), (403, {'error': {'status': 'PERMISSION_DENIED',
                'message': 'API key was reported as leaked: ' + secret,
                'details': [{'@type': 'type.googleapis.com/google.rpc.ErrorInfo',
                             'reason': 'API_KEY_SERVICE_BLOCKED', 'metadata': {'consumer': secret}},
                            {'@type': 'type.googleapis.com/google.rpc.ErrorInfo', 'reason': secret}]}})], False),
            ('generation_forbidden_no_details', [(200, metadata), (403, {'error': {
                'status': 'PERMISSION_DENIED',
                'message': 'Permission denied to call generateContent for model gemini-3.6-flash. Key: ' + secret}})], False),
            ('wrong_model', [(200, {'name': 'models/another-model'})], False),
            ('html_error', [(503, b'<html>' + secret.encode() + b'</html>')], False),
            ('no_candidates', [(200, metadata), (200, {'candidates': []})], False),
            ('numeric_true', [(200, metadata), (200, {'candidates': [{'content': {'parts': [{'text': '{"ok": 1}'}]}}]})], False),
            ('timeout', [(200, metadata), TimeoutError(secret)], False),
        ]
        for name, responses, expected in cases:
            with self.subTest(name=name):
                connections = []
                for response in responses:
                    connection = Mock()
                    if isinstance(response, Exception):
                        connection.getresponse.side_effect = response
                    else:
                        code, body = response
                        connection.getresponse.return_value = Mock(status=code)
                        connection.getresponse.return_value.read.return_value = body if isinstance(body, bytes) else json.dumps(body).encode()
                    connections.append(connection)
                secret_module = Mock()
                secret_module.UserSecretsClient.return_value.get_secret.return_value = secret
                with patch.dict(sys.modules, {'kaggle_secrets': secret_module}), \
                     patch('http.client.HTTPSConnection', side_effect=connections) as factory:
                    result = check_gemini_endpoint()
                self.assertIs(result['endpoint_available'], expected)
                self.assertEqual(factory.call_count, len(responses))
                self.assertNotIn(secret, json.dumps(result))
                if not expected:
                    self.assertIn('failure_stage', result)
                if name == 'generation_forbidden':
                    self.assertEqual(result['failure_stage'], 'generation')
                    self.assertEqual(result['failure_reason'], 'http_error')
                    self.assertEqual(result['requests'][-1]['error_reasons'], ['API_KEY_SERVICE_BLOCKED'])
                    self.assertEqual(result['requests'][-1]['message_hint'], 'API_KEY_REPORTED_LEAKED')
                if name == 'generation_forbidden_no_details':
                    self.assertEqual(result['failure_stage'], 'generation')
                    self.assertEqual(result['requests'][-1]['error_reasons'], [])
                    self.assertEqual(result['requests'][-1]['error_message_redacted'],
                        'Permission denied to call generateContent for model gemini-3.6-flash. Key: [REDACTED]')
                for connection in connections:
                    connection.close.assert_called_once()
                    args, kwargs = connection.request.call_args
                    self.assertNotIn(secret, args[1])
                    self.assertEqual(kwargs['headers']['x-goog-api-key'], secret)
                if name in ('quota', 'unavailable', 'html_error'):
                    self.assertEqual(result['requests'][-1]['http_status'], 429 if name == 'quota' else 503)
                if expected:
                    self.assertEqual(result['requests'][-1]['usage'], {'totalTokenCount': 12})
        with patch.dict(sys.modules, {'kaggle_secrets': Mock()}), patch('http.client.HTTPSConnection') as factory:
            self.assertFalse(check_gemini_endpoint('../invalid')['endpoint_available'])
            factory.assert_not_called()

    def test_gemini_message_redaction_preserves_cause_and_removes_sensitive_values(self):
        from scripts.kaggle_gemini_probe import redact_gemini_error_message
        from urllib.parse import quote, quote_plus
        key = 'private-test-key/+ with-space'
        identifiers = [key, quote(key, safe=''), quote_plus(key), 'AIza' + 'x' * 35,
                       'person@example.test', 'worker@sample.iam.gserviceaccount.com',
                       'https://example.test/?key=hidden', 'projects/private-project',
                       'project "other-private-project"', '123456789012', '192.0.2.1', '2001:db8::1',
                       'access_token=private-token', 'Authorization:private-header',
                       'Bearer private-bearer', 'project:private-project-id']
        message = 'Permission denied for generateContent.\n' + ' ; '.join(identifiers)
        redacted = redact_gemini_error_message(message, key)
        self.assertTrue(redacted.startswith('Permission denied for generateContent.'))
        for value in identifiers:
            self.assertNotIn(value, redacted)
        for value in ('other-private-project', 'private-token', 'private-header', 'private-bearer', 'private-project-id'):
            self.assertNotIn(value, redacted)
        # A long provider message must not retain a partial credential at the cut.
        self.assertEqual(redact_gemini_error_message('x' * 995 + key, key), 'x' * 995 + '[REDA...')
        for value in (None, {}, 123):
            self.assertEqual(redact_gemini_error_message(value, key), '')

    def test_standalone_gemini_diagnostic_keeps_failure_without_running_reader(self):
        notebook = json.loads((ROOT / 'scripts/kaggle_gemini_access_check.ipynb').read_text(encoding='utf-8'))
        cells = [c['source'] for c in notebook['cells'] if c['cell_type'] == 'code']
        self.assertEqual(len(cells), 1)
        source = cells[0]
        self.assertIn((ROOT / 'scripts/kaggle_gemini_probe.py').read_text(encoding='utf-8'), source)
        self.assertNotIn('import kagglehub', source)
        self.assertNotIn('run_reader_component', source)
        compile(source, 'standalone-probe', 'exec')
        # Execute the reporting suffix against a failed probe; no real network calls.
        tree = ast.parse(source)
        suffix = tree.body[next(i for i, node in enumerate(tree.body)
                                if isinstance(node, ast.Import) and node.names[0].name == 'os'):]
        failure = {'endpoint_available': False, 'requests': [{'http_status': 403,
                   'error_message_redacted': 'Permission denied'}]}
        with tempfile.TemporaryDirectory() as temp, patch('pathlib.Path', return_value=Path(temp)):
            scope = dict(check_gemini_endpoint=Mock(return_value=failure), time=time, json=json)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exec(compile(ast.Module(body=suffix, type_ignores=[]), 'diagnostic-report', 'exec'), scope)
            scope['check_gemini_endpoint'].assert_called_once()
            self.assertIn('PROBE_FAILED', output.getvalue())
            self.assertNotIn('PROBE_PASS', output.getvalue())
            self.assertEqual(json.loads(scope['gemini_probe_path'].read_text()), failure)

    def test_reader_full_pdf_requires_successful_stage_and_original_quality_gate(self):
        notebook = json.loads((ROOT / "scripts/kaggle_reader_diagnostics.ipynb").read_text(encoding="utf-8"))
        source = [c["source"] for c in notebook["cells"] if c["cell_type"] == "code"][3]
        for state, code, gate, allowed in (("completed", 0, True, True),
                ("failed", 1, True, False), ("completed", 1, True, False),
                ("completed", 0, False, False), ("completed", 0, "true", False)):
            with self.subTest(state=state, code=code, gate=gate), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp)
                (out / "reader-failed-page").mkdir()
                (out / "reader-failed-page/summary.json").write_text(json.dumps({"automated_gate_pass": gate}))
                calls = []
                scope = dict(out=out, json=json,
                    statuses={"reader-failed-page": {"state": state, "exit_code": code}},
                    run_reader_component=lambda *a, **k: calls.append((a, k)), bundle=lambda: None)
                with contextlib.redirect_stdout(io.StringIO()):
                    if allowed:
                        exec(source, scope)
                        self.assertEqual(calls, [(('reader-real',), {'timeout': 5400})])
                    else:
                        with self.assertRaises(AssertionError):
                            exec(source, scope)
                        self.assertEqual(calls, [])

    def test_reader_503_retry_preserves_original_and_refuses_repeated_or_unrelated_failures(self):
        notebook = json.loads((ROOT / 'scripts/kaggle_reader_retry_503.ipynb').read_text(encoding='utf-8'))
        cells = [c['source'] for c in notebook['cells'] if c['cell_type'] == 'code']
        self.assertEqual(len(cells), 2)
        for source in cells:
            compile(source, 'reader-retry', 'exec')
        main = json.loads((ROOT / 'scripts/kaggle_reader_diagnostics.ipynb').read_text(encoding='utf-8'))
        self.assertEqual(cells[1], [c['source'] for c in main['cells'] if c['cell_type'] == 'code'][3])
        original, retry = 'reader-failed-page', 'reader-failed-page-retry-1'
        manifest_hash = hashlib.sha256((ROOT / 'research_rag/evaluation/reader_real_manifest.jsonl').read_bytes()).hexdigest()
        for case in ('pass', 'fail_again', '403', '429', 'mixed_errors', 'wrong_page', 'changed_model',
                     'changed_manifest', 'already_attempted', 'orphaned_log', 'lost_runtime'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                out = Path(temp)
                (out / original).mkdir()
                counts = {'503': 3, 'not_available': 1}
                if case in ('403', '429'):
                    counts = {case: 1}
                elif case == 'mixed_errors':
                    counts['429'] = 1
                summary = {'automated_gate_pass': False, 'api': {'http_status_counts': counts}}
                (out / original / 'summary.json').write_text(json.dumps(summary))
                (out / original / 'criteria.json').write_text(json.dumps({
                    'selected_page': 0 if case == 'wrong_page' else 3,
                    'configured_model': 'gemini-3.6-flash',
                    'manifest_sha256': 'different' if case == 'changed_manifest' else manifest_hash}))
                before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in (out / original).iterdir()}
                statuses = {original: {'state': 'failed', 'exit_code': 1}}
                if case == 'already_attempted':
                    statuses[retry] = {'state': 'failed', 'exit_code': 1}
                if case == 'orphaned_log':
                    (out / (retry + '.stdout.log')).write_text('saved evidence')
                calls = []
                def run_component(name, *, page, timeout):
                    calls.append((name, page, timeout))
                    (out / name).mkdir()
                    passed = case == 'pass'
                    statuses[name] = {'state': 'completed' if passed else 'failed', 'exit_code': 0 if passed else 1}
                    (out / name / 'summary.json').write_text(json.dumps({'automated_gate_pass': passed}))
                scope = dict(out=out, statuses=statuses, root=ROOT,
                    python=str(out / 'missing-python') if case == 'lost_runtime' else sys.executable,
                    env={'GEMINI_MODEL': 'different' if case == 'changed_model' else 'gemini-3.6-flash'},
                    run_reader_component=run_component)
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    if case in ('pass', 'fail_again'):
                        exec(cells[0], scope)
                        self.assertEqual(calls, [(retry, 3, 900)])
                        self.assertIn('READER_PROBE_PASS:' if case == 'pass' else 'READER_PROBE_FAILED:', output.getvalue())
                        with self.assertRaisesRegex(AssertionError, 'One manual retry already attempted'):
                            exec(cells[0], scope)
                        self.assertEqual(len(calls), 1)
                    else:
                        with self.assertRaises(AssertionError):
                            exec(cells[0], scope)
                        self.assertEqual(calls, [])
                self.assertEqual(statuses[original], {'state': 'failed', 'exit_code': 1})
                self.assertEqual(before, {p.name: (p.read_bytes(), p.stat().st_mtime_ns)
                                          for p in (out / original).iterdir()})
                if case == 'orphaned_log':
                    self.assertEqual((out / (retry + '.stdout.log')).read_text(), 'saved evidence')
        with self.assertRaisesRegex(AssertionError, 'EXISTING Reader notebook session'):
            exec(cells[0], {})

    def test_reader_full_pdf_uses_retry_result_and_never_falls_back_to_an_old_pass(self):
        notebook = json.loads((ROOT / 'scripts/kaggle_reader_retry_503.ipynb').read_text(encoding='utf-8'))
        full = [c['source'] for c in notebook['cells'] if c['cell_type'] == 'code'][1]
        for state, code, gate, allowed in (('completed', 0, True, True),
                ('failed', 1, True, False), ('running', None, True, False),
                ('interrupted', None, True, False), ('completed', 0, False, False),
                ('completed', 0, 'true', False)):
            with self.subTest(state=state, gate=gate), tempfile.TemporaryDirectory() as temp:
                out = Path(temp)
                retry = 'reader-failed-page-retry-1'
                (out / retry).mkdir()
                (out / retry / 'summary.json').write_text(json.dumps({'automated_gate_pass': gate}))
                # Opposite original result proves that the latest attempt controls the gate.
                statuses = {'reader-failed-page': {'state': 'failed' if allowed else 'completed',
                                                 'exit_code': 1 if allowed else 0},
                            retry: {'state': state, 'exit_code': code}}
                calls = []
                scope = dict(out=out, statuses=statuses, json=json, bundle=lambda: None,
                             run_reader_component=lambda *a, **k: calls.append((a, k)))
                with contextlib.redirect_stdout(io.StringIO()):
                    if allowed:
                        exec(full, scope)
                        self.assertEqual(calls, [(('reader-real',), {'timeout': 5400})])
                    else:
                        with self.assertRaises(AssertionError):
                            exec(full, scope)
                        self.assertEqual(calls, [])

    def test_reader_endpoint_notebook_contains_current_sources_and_blocks_failed_setup_and_reruns(self):
        notebook = json.loads((ROOT / 'scripts/kaggle_reader_endpoint_comparison.ipynb').read_text(encoding='utf-8'))
        cells = [c['source'] for c in notebook['cells'] if c['cell_type'] == 'code']
        self.assertEqual(len(cells), 2)
        for source in cells:
            compile(source, 'cpu-endpoint-notebook', 'exec')
        tree = ast.parse(cells[0])
        entries = ast.literal_eval(next(node.value for node in tree.body if isinstance(node, ast.Assign)
                                       and any(isinstance(t, ast.Name) and t.id == 'entries' for t in node.targets)))
        paths = {r['path'] for r in entries}
        self.assertEqual(len(paths), len(entries))
        self.assertNotIn('torch', paths)
        for row in entries:
            path = PurePosixPath(row['path'])
            self.assertFalse(path.is_absolute())
            self.assertNotIn('..', path.parts)
            data = zlib.decompress(base64.b64decode(row['payload'], validate=True))
            self.assertEqual(hashlib.sha256(data).hexdigest(), row['sha256'])
            if row['path'] not in ('inputs.json', 'train_agent2_reader/__init__.py'):
                self.assertEqual(data, (ROOT / row['path']).read_bytes())
            if row['path'] == 'inputs.json':
                fixture = json.loads(data)
                self.assertEqual(fixture['page_no'], 3)
                self.assertEqual(fixture['critique_summary']['num_blocks'], 128)
                self.assertEqual(fixture['pdf_sha256'], hashlib.sha256(
                    (ROOT / 'research_rag/evaluation/pdfs/qasper_2021.pdf').read_bytes()).hexdigest())
        for setup_completed in (False, True):
            with self.subTest(setup_completed=setup_completed), tempfile.TemporaryDirectory() as temp:
                out = Path(temp)
                code_dir = out / 'code'
                code_dir.mkdir()
                secrets = Mock()
                secrets.return_value.get_secret.return_value = 'private-cell-key'
                if setup_completed:
                    (out / 'setup-status.json').write_text('{"state":"completed"}')
                process = Mock()
                process.wait.return_value = 1
                scope = dict(out=out, code_dir=code_dir, python=sys.executable, Path=Path, json=json,
                             os=os, subprocess=subprocess, time=time, UserSecretsClient=secrets,
                             bundle_endpoint=Mock())
                with patch.object(subprocess, 'Popen', return_value=process) as spawn, \
                        contextlib.redirect_stdout(io.StringIO()):
                    if not setup_completed:
                        with self.assertRaisesRegex(AssertionError, 'Cell 1 did not complete'):
                            exec(cells[1], scope)
                        spawn.assert_not_called()
                        secrets.assert_not_called()
                    else:
                        exec(cells[1], scope)
                        self.assertEqual(json.loads((out / 'status.json').read_text())['state'], 'failed')
                        self.assertNotIn('private-cell-key', (out / 'status.json').read_text())
                        self.assertNotIn('GEMINI_API_KEY', scope['child_env'])
                        scope['bundle_endpoint'].assert_called_once()
                        with self.assertRaisesRegex(AssertionError, 'Already attempted'):
                            exec(cells[1], scope)
                        self.assertEqual(spawn.call_count, 1)

    def test_reader_endpoint_setup_bypasses_ensurepip_and_records_bootstrap_failure(self):
        notebook = json.loads((ROOT / 'scripts/kaggle_reader_endpoint_comparison.ipynb').read_text(encoding='utf-8'))
        source = next(c['source'] for c in notebook['cells'] if c['cell_type'] == 'code')
        tree = ast.parse(source)
        selected = [node for node in tree.body if (isinstance(node, ast.FunctionDef) and node.name == 'find_bootstrap_pip')
                    or isinstance(node, ast.Try)]
        program = compile(ast.Module(body=selected, type_ignores=[]), 'setup-without-ensurepip', 'exec')
        for failure in (None, 'install_sdk', 'sitecustomize'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temp:
                out = Path(temp)
                secrets = Mock()
                secrets.UserSecretsClient.return_value.get_secret.return_value = 'private-setup-key'
                calls = []
                def run(command, **kwargs):
                    calls.append(command)
                    if command[-1] == '--help':
                        return subprocess.CompletedProcess(command, 0 if command[0] == 'path-pip' else 1,
                                                           '--python <python>' if command[0] == 'path-pip' else '', '')
                    if '-m' in command and 'venv' in command:
                        self.assertIn('--without-pip', command)
                    if 'install' in command:
                        self.assertEqual(command[:3], ['path-pip', '--python', 'target-python'])
                        self.assertIn('pip==26.2.1', command)
                        self.assertIn('wrapt==2.1.2', command)
                        if failure == 'install_sdk':
                            raise subprocess.CalledProcessError(7, command)
                    if '-c' in command:
                        self.assertIn("assert version('wrapt') == '2.1.2'", command[-1])
                        if failure == 'sitecustomize':
                            return subprocess.CompletedProcess(command, 0, '', 'Error in sitecustomize; missing wrapt')
                    return subprocess.CompletedProcess(command, 0, '', '')
                scope = dict(out=out, code_dir=out / 'code', venv=out / 'venv', python='target-python',
                             sys=sys, subprocess=subprocess, shutil=__import__('shutil'), json=json,
                             setup_status={'state': 'running', 'stage': 'create_venv'}, bundle_endpoint=Mock())
                with patch.dict(sys.modules, {'kaggle_secrets': secrets}), \
                        patch.object(subprocess, 'run', side_effect=run), \
                        patch('shutil.which', return_value='path-pip'):
                    if failure == 'install_sdk':
                        with self.assertRaises(subprocess.CalledProcessError):
                            exec(program, scope)
                    elif failure == 'sitecustomize':
                        with self.assertRaisesRegex(RuntimeError, 'Python startup failed'):
                            exec(program, scope)
                    else:
                        exec(program, scope)
                status = json.loads((out / 'setup-status.json').read_text())
                self.assertEqual(status['state'], 'failed' if failure else 'completed')
                if failure == 'install_sdk':
                    self.assertEqual(status['stage'], 'install_sdk')
                    self.assertEqual(status['exit_code'], 7)
                    secrets.UserSecretsClient.assert_not_called()
                elif failure == 'sitecustomize':
                    self.assertEqual(status['stage'], 'validate_sdk')
                    self.assertEqual(status['error_type'], 'RuntimeError')
                    self.assertIn('Error in sitecustomize', (out / 'setup.stderr.log').read_text())
                    secrets.UserSecretsClient.assert_not_called()
                else:
                    self.assertIsNone(scope['secret_check'])
                self.assertNotIn('private-setup-key', (out / 'setup-status.json').read_text())
                scope['bundle_endpoint'].assert_called_once()

    def test_reader_wrapt_fix_preserves_setup_and_blocks_probe_after_startup_failure(self):
        source = (ROOT / 'scripts/kaggle_reader_wrapt_fix.cell.py').read_text(encoding='utf-8')
        compile(source, 'wrapt-repair-cell', 'exec')
        for failure in (None, 'install', 'startup'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temp:
                out = Path(temp)
                original = '{"state": "completed", "stage": "complete", "sdk": "2.22.0"}'
                (out / 'setup-status.json').write_text(original)
                calls = []
                def run(command, **kwargs):
                    calls.append(command)
                    if 'install' in command:
                        self.assertEqual(command[:3], ['parent-pip', '--python', 'target-python'])
                        self.assertIn('wrapt==2.1.2', command)
                        if failure == 'install':
                            raise subprocess.CalledProcessError(2, command)
                    if '-c' in command and failure == 'startup':
                        return subprocess.CompletedProcess(command, 0, '', 'Error in sitecustomize; missing wrapt')
                    return subprocess.CompletedProcess(command, 0, '', '')
                scope = dict(out=out, python='target-python', setup_status=json.loads(original),
                             find_bootstrap_pip=lambda: ['parent-pip'], bundle_endpoint=Mock(),
                             subprocess=subprocess, json=json)
                with patch.object(subprocess, 'run', side_effect=run), contextlib.redirect_stdout(io.StringIO()):
                    if failure == 'install':
                        with self.assertRaises(subprocess.CalledProcessError):
                            exec(source, scope)
                    elif failure == 'startup':
                        with self.assertRaisesRegex(RuntimeError, 'sitecustomize still fails'):
                            exec(source, scope)
                    else:
                        exec(source, scope)
                    with self.assertRaisesRegex(AssertionError, 'repair was already attempted'):
                        exec(source, scope)
                self.assertEqual((out / 'setup-before-wrapt.json').read_text(), original)
                status = json.loads((out / 'setup-status.json').read_text())
                self.assertEqual(status['state'], 'failed' if failure else 'completed')
                self.assertEqual(len(calls), 1 if failure == 'install' else 2 if failure else 3)
                scope['bundle_endpoint'].assert_called_once()
                if failure == 'startup':
                    self.assertIn('Error in sitecustomize', (out / 'wrapt.stderr.log').read_text())
                # The existing cell-2 guard must also reject a failed repair.
                if failure:
                    notebook = json.loads((ROOT / 'scripts/kaggle_reader_endpoint_comparison.ipynb').read_text(encoding='utf-8'))
                    cell2 = [c['source'] for c in notebook['cells'] if c['cell_type'] == 'code'][1]
                    scope.update(python=sys.executable, Path=Path)
                    with self.assertRaisesRegex(AssertionError, 'Cell 1 did not complete'):
                        exec(cell2, scope)

    def test_external_pip_manages_a_real_venv_created_without_ensurepip(self):
        # Offline integration: the target has no pip, and parent pip operates inside it.
        with tempfile.TemporaryDirectory(prefix='reader-no-pip-', dir=ROOT / 'research-runs') as temp:
            target = Path(temp).resolve() / 'env'
            self.assertTrue(target.is_relative_to(ROOT.resolve()))
            subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(target)],
                           check=True, capture_output=True, timeout=120)
            python = target / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
            check = subprocess.run([str(python), '-c', 'import importlib.util; assert importlib.util.find_spec("pip") is None'],
                                   check=True, capture_output=True, timeout=30)
            result = subprocess.run([sys.executable, '-m', 'pip', '--python', str(python), 'list',
                                     '--format=json', '--disable-pip-version-check'],
                                    check=True, capture_output=True, text=True, timeout=60)
            self.assertEqual(json.loads(result.stdout), [])

    def test_gemini_probe_identifies_secret_failure_before_any_gemini_request(self):
        from scripts.kaggle_gemini_probe import check_gemini_endpoint
        backend_error = type('BackendError', (Exception,), {})
        for stage in ('create_secret_client', 'read_kaggle_secret'):
            with self.subTest(stage=stage):
                secret_module = Mock()
                target = (secret_module.UserSecretsClient if stage == 'create_secret_client' else
                          secret_module.UserSecretsClient.return_value.get_secret)
                target.side_effect = backend_error('sensitive-error-content')
                with patch.dict(sys.modules, {'kaggle_secrets': secret_module}), \
                     patch('http.client.HTTPSConnection') as connection:
                    result = check_gemini_endpoint()
                connection.assert_not_called()
                self.assertEqual(result['requests'], [])
                self.assertFalse(result['endpoint_available'])
                self.assertEqual(result['error_type'], 'BackendError')
                self.assertEqual(result['failure_stage'], stage)
                self.assertNotIn('sensitive-error-content', json.dumps(result))

    def test_reader_preflight_assertion_reports_generation_403(self):
        notebook = json.loads((ROOT / 'scripts/kaggle_reader_diagnostics.ipynb').read_text(encoding='utf-8'))
        source = next(c['source'] for c in notebook['cells'] if c['cell_type'] == 'code')
        guard = next(node for node in ast.parse(source).body if isinstance(node, ast.Assert))
        scope = {'gemini_availability': {'endpoint_available': False, 'failure_stage': 'generation',
                                        'failure_reason': 'http_error'},
                 'probe_last_request': {'http_status': 403, 'api_status': 'PERMISSION_DENIED'}}
        with self.assertRaisesRegex(AssertionError, 'stage=generation; HTTP=403; API=PERMISSION_DENIED; reason=http_error'):
            exec(compile(ast.Module(body=[guard], type_ignores=[]), 'preflight-guard', 'exec'), scope)

    def test_completion_notebook_uses_current_patch_and_exact_failed_pdf(self):
        notebook = json.loads((ROOT / "scripts/kaggle_completion_validation.ipynb").read_text(encoding="utf-8"))
        cells = [c["source"] for c in notebook["cells"] if c["cell_type"] == "code"]
        self.assertEqual(len(cells), 6)
        self.assertEqual(cells[1], self.cells()[0])
        for source in cells:
            compile(source, "completion-notebook", "exec")
        self.assertIn("'--comparison', 'explanation'", cells[2])
        self.assertIn("timeout=900", cells[3])
        self.assertIn("get('state') == 'completed'", cells[4])
        self.assertIn("get('state') == 'completed'", cells[5])
        tree = ast.parse(cells[3])
        fixture = ast.literal_eval(next(node.value for node in tree.body if isinstance(node, ast.Assign)
                                  and any(isinstance(t, ast.Name) and t.id == "fixture" for t in node.targets)))
        data = zlib.decompress(base64.b64decode(fixture["payload"], validate=True))
        self.assertEqual(hashlib.sha256(data).hexdigest(), fixture["sha256"])
        self.assertEqual(data, (ROOT / "research-runs/autonomy-v1-20260930/extra-pages.pdf").read_bytes())
        # Only execute the fixture restoration prefix, stopping before credentials or API code.
        prefix = tree.body[2:next(i for i, node in enumerate(tree.body) if isinstance(node, ast.Assign)
                          and any(isinstance(t, ast.Name) and t.id == "reader_env" for t in node.targets))]
        with tempfile.TemporaryDirectory() as temp:
            scope = dict(out=Path(temp), json=json, base64=base64, zlib=zlib, hashlib=hashlib)
            exec(compile(ast.Module(body=prefix, type_ignores=[]), "restore-reader-fixture", "exec"), scope)
            restored = Path(temp) / "reader-fixture/page0.jsonl"
            row = json.loads(restored.read_text())
            self.assertEqual(row["expected_spans"][0]["page_no"], 0)
            original_mtime = restored.stat().st_mtime_ns
            exec(compile(ast.Module(body=prefix, type_ignores=[]), "restore-reader-fixture", "exec"), scope)
            self.assertEqual(restored.stat().st_mtime_ns, original_mtime)

    def test_cells_compile_and_patch_matches_current_sources(self):
        cells = self.cells()
        self.assertEqual(len(cells), 4)
        for index, source in enumerate(cells):
            compile(source, f"cell-{index}", "exec")
        assignment = next(node for node in ast.parse(cells[0]).body if isinstance(node, ast.Assign)
                          and any(isinstance(t, ast.Name) and t.id == "runtime_patch" for t in node.targets))
        entries = ast.literal_eval(assignment.value)
        paths = {item["path"] for item in entries}
        self.assertEqual(len(paths), len(entries))
        self.assertTrue({"research_rag/controller.py", "research_rag/local.py", "research_rag/adapters.py",
                         "research_rag/observe.py", "requirements-orchestrator.txt",
                         "train_agent3_summarizer/node.py", "research_rag/tests/test_autonomy.py"} <= paths)
        for item in entries:
            relative = PurePosixPath(item["path"])
            self.assertFalse(relative.is_absolute())
            self.assertNotIn("..", relative.parts)
            payload = zlib.decompress(base64.b64decode(item["payload"], validate=True))
            self.assertEqual(hashlib.sha256(payload).hexdigest(), item["sha256"])
            self.assertEqual(len(payload), item["size"])
            self.assertEqual(payload, (ROOT / relative).read_bytes(), "Rebuild the notebook after editing runtime")

    def test_runner_preserves_success_failure_and_archive_hashes(self):
        functions = [node for node in ast.parse(self.cells()[0]).body
                     if isinstance(node, ast.FunctionDef) and node.name in {"run", "bundle"}]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out = root / "output"
            out.mkdir()
            scope = dict(out=out, root=root, statuses={}, run_id="synthetic-local-test", env=os.environ.copy(),
                         os=os, time=time, signal=signal, subprocess=subprocess, json=json,
                         zipfile=zipfile, hashlib=hashlib)
            exec(compile(ast.Module(body=functions, type_ignores=[]), "notebook-helpers", "exec"), scope)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(scope["run"]("ok", [sys.executable, "-c", "print(123)"]), 0)
                self.assertEqual(scope["run"]("failure", [sys.executable, "-c", "raise SystemExit(3)"], required=False), 3)
                with self.assertRaises(RuntimeError):
                    scope["run"]("required", [sys.executable, "-c", "raise SystemExit(2)"])
                with self.assertRaises(AssertionError):
                    scope["run"]("ok", [sys.executable, "-c", "print(456)"])
            self.assertEqual((out / "ok.stdout.log").read_text().strip(), "123")
            self.assertEqual(scope["statuses"]["required"]["state"], "failed")
            with zipfile.ZipFile(out.with_suffix(".zip")) as archive:
                manifest = json.loads(archive.read("output-manifest.json"))
                self.assertEqual(len(manifest["files"]), 7)
                for item in manifest["files"]:
                    data = archive.read(item["path"])
                    self.assertEqual(len(data), item["size"])
                    self.assertEqual(hashlib.sha256(data).hexdigest(), item["sha256"])

    def test_autonomy_notebook_restores_exact_frozen_suite(self):
        notebook = json.loads((ROOT / "scripts/kaggle_autonomy_validation.ipynb").read_text(encoding="utf-8"))
        cells = [cell["source"] for cell in notebook["cells"] if cell["cell_type"] == "code"]
        self.assertEqual(len(cells), 4)
        self.assertEqual(cells[1], self.cells()[0], "Rebuild autonomy notebook after the setup changes")
        for source in cells:
            compile(source, "autonomy-notebook", "exec")
        with tempfile.TemporaryDirectory() as temp:
            scope = dict(out=Path(temp), Path=Path, base64=base64, zlib=zlib,
                         hashlib=hashlib, statuses={}, bundle=lambda: None)
            with contextlib.redirect_stdout(io.StringIO()):
                exec(compile(cells[2], "unpack-frozen-suite", "exec"), scope)
            from research_rag.evaluation.autonomy import verify_frozen
            suite = Path(temp) / "autonomy-v1"
            manifest, cases = verify_frozen(suite)
            self.assertEqual(len(cases), 8)
            for name in [*manifest["files"], "frozen-manifest.json"]:
                self.assertEqual((suite / name).read_bytes(),
                                 (ROOT / "research-runs/autonomy-v1-20260930" / name).read_bytes())

    def test_autonomy_unpack_resumes_partial_files_and_preserves_results_on_rerun(self):
        notebook = json.loads((ROOT / "scripts/kaggle_autonomy_validation.ipynb").read_text(encoding="utf-8"))
        source = [c["source"] for c in notebook["cells"] if c["cell_type"] == "code"][2]
        with tempfile.TemporaryDirectory() as temp:
            suite = Path(temp) / "autonomy-v1"
            suite.mkdir()
            cases = suite / "cases.json"
            cases.write_bytes((ROOT / "research-runs/autonomy-v1-20260930/cases.json").read_bytes())
            original_mtime = cases.stat().st_mtime_ns
            scope = dict(out=Path(temp), Path=Path, base64=base64, zlib=zlib,
                         hashlib=hashlib, statuses={}, bundle=lambda: None)
            with contextlib.redirect_stdout(io.StringIO()):
                exec(source, scope)
                self.assertEqual(cases.stat().st_mtime_ns, original_mtime)
                (suite / "results").mkdir()
                result = suite / "results/summary.json"
                result.write_bytes(b'{"status":"saved-evidence"}')
                before = {p.relative_to(suite): (p.read_bytes(), p.stat().st_mtime_ns)
                          for p in suite.rglob("*") if p.is_file()}
                exec(source, scope)
                after = {p.relative_to(suite): (p.read_bytes(), p.stat().st_mtime_ns)
                         for p in suite.rglob("*") if p.is_file()}
                self.assertEqual(before, after)
                cases.write_bytes(b"modified")
                with self.assertRaisesRegex(AssertionError, "Existing frozen file differs"):
                    exec(source, scope)
                self.assertEqual(cases.read_bytes(), b"modified")
                self.assertEqual(result.read_bytes(), b'{"status":"saved-evidence"}')

    def test_autonomy_unpack_refuses_missing_inputs_after_e2e_attempt(self):
        notebook = json.loads((ROOT / "scripts/kaggle_autonomy_validation.ipynb").read_text(encoding="utf-8"))
        source = [c["source"] for c in notebook["cells"] if c["cell_type"] == "code"][2]
        for marker in ("results", "status"):
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as temp:
                suite = Path(temp) / "autonomy-v1"
                suite.mkdir()
                if marker == "results":
                    (suite / "results").mkdir()
                statuses = {"autonomy-e2e": {"state": "failed"}} if marker == "status" else {}
                scope = dict(out=Path(temp), Path=Path, base64=base64, zlib=zlib,
                             hashlib=hashlib, statuses=statuses, bundle=lambda: None)
                with self.assertRaisesRegex(AssertionError, "Frozen file missing after E2E started"):
                    exec(source, scope)
                self.assertFalse((suite / "cases.json").exists())


if __name__ == "__main__":
    unittest.main()
