"""Local packaging checks; Kaggle runtime does not contain the notebook source."""
import ast
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zlib
from scripts.atomic_release_test_support import v7_file


ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / 'research_rag/evaluation'


def notebook():
    nb = json.loads((ROOT / 'scripts/kaggle_decomposition_probe_v7.ipynb').read_text(encoding='utf-8'))
    cells = [c['source'] if isinstance(c['source'], str) else ''.join(c['source'])
             for c in nb['cells'] if c['cell_type'] == 'code']
    patches = {target.id: ast.literal_eval(node.value) for node in ast.parse(cells[1]).body
        if isinstance(node, ast.Assign) for target in node.targets
        if isinstance(target, ast.Name) and target.id in ('runtime_patch', 'verifier_patch')}
    return cells, patches


class AtomicNotebookTests(unittest.TestCase):
    def test_notebook_compiles_and_embeds_all_frozen_sources_and_unique_run_id(self):
        cells, patches = notebook()
        self.assertEqual(len(cells), 3)
        for cell in cells:
            compile(cell, 'atomic-notebook-test', 'exec')
        self.assertIn('uuid.uuid4()', cells[1])
        self.assertIn("'--without-pip'", cells[1])
        self.assertIn("'--validate-only'", cells[1])
        self.assertIn('timeout=2520', cells[2])
        self.assertIn('atomic-verifier-constrained-v7-20261016', cells[1])
        self.assertLess(cells[1].index("run('structured-decoder'"), cells[1].index("run('pip-check'"))
        self.assertLess(cells[1].index("run('atomic-freeze-check'"),
                        cells[1].index("print('SETUP COMPLETE:"))
        by_path = {item['path']: item for item in patches['verifier_patch']}
        trace_fixture = (ROOT / 'scripts/fixtures/summary_trace_pre_v5.py.txt').read_bytes()
        self.assertEqual(by_path['research_rag/tests/test_summary_trace.py']['base_sha256'],
                         hashlib.sha256(trace_fixture).hexdigest())
        criteria = json.loads((EVAL / 'atomic_verifier_criteria_v7.json').read_text())
        self.assertTrue(set(criteria['source_sha256']) <= set(by_path))
        self.assertIn('research_rag/tests/test_atomic_metric_v7.py', criteria['source_sha256'])
        self.assertEqual(criteria['policy'], 'atomic-verifier-constrained-v7')
        self.assertEqual(criteria['structured_decoder']['policy'], 'atomic-schema-decoding-v4')
        previous = json.loads((EVAL / 'atomic_verifier_criteria_v6.json').read_text())
        versioned = {'version', 'policy', 'structured_decoder', 'contract_file', 'contract_sha256',
                     'source_sha256', 'prompt_sha256', 'limitations'}
        self.assertEqual(previous.keys(), criteria.keys())
        for key in criteria.keys() - versioned:
            self.assertEqual(previous[key], criteria[key], key)
        self.assertEqual(previous['prompt_sha256'], criteria['prompt_sha256'])
        self.assertEqual({k: v for k, v in previous['structured_decoder'].items() if k != 'policy'},
                         {k: v for k, v in criteria['structured_decoder'].items() if k != 'policy'})
        for name, item in by_path.items():
            data = zlib.decompress(base64.b64decode(item['payload'], validate=True))
            self.assertEqual(len(data), item['size'])
            self.assertEqual(hashlib.sha256(data).hexdigest(), item['sha256'])
            self.assertEqual(data, v7_file(name).read_bytes())
        for item in patches['runtime_patch']:
            if item['path'] in by_path:
                self.assertIn(item['sha256'], (by_path[item['path']]['sha256'], by_path[item['path']].get('base_sha256')))
        release = json.loads((ROOT / 'docs/atomic-verifier-v7-release.json').read_text(encoding='utf-8'))
        self.assertEqual(release['version'], criteria['version'])
        for name, digest in release['files'].items():
            self.assertEqual(hashlib.sha256(v7_file(name).read_bytes()).hexdigest(), digest, name)

    def test_patched_runtime_discovers_tests_and_validates_freeze_without_notebook(self):
        _, patches = notebook()
        with tempfile.TemporaryDirectory(dir=ROOT / 'research-runs') as directory:
            runtime = Path(directory)
            # Copy base package entry files; then apply exactly the embedded patches.
            files = (list((ROOT / 'research_rag').glob('*.py')) +
                     list((ROOT / '04_factchecker').glob('*.py')) +
                     list((ROOT / '04_factchecker/inference').glob('*.py')) + [
                         EVAL / '__init__.py', ROOT / 'research_rag/tests/__init__.py',
                         EVAL / 'factchecker_contract_cases.jsonl'])
            for source in files:
                if source.exists():
                    target = runtime / source.relative_to(ROOT)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(v7_file(source.relative_to(ROOT)).read_bytes())
            # Reproduce the existing diagnostics file that v7 must replace.
            trace_target = runtime / 'research_rag/tests/test_summary_trace.py'
            trace_target.parent.mkdir(parents=True, exist_ok=True)
            trace_target.write_bytes((ROOT / 'scripts/fixtures/summary_trace_pre_v5.py.txt').read_bytes())
            for items in patches.values():
                for item in items:
                    target = (runtime / item['path']).resolve()
                    self.assertTrue(target.is_relative_to(runtime.resolve()))
                    if items is patches['verifier_patch'] and target.exists():
                        self.assertIn(hashlib.sha256(target.read_bytes()).hexdigest(),
                                      (item['sha256'], item.get('base_sha256', item['sha256'])), item['path'])
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(zlib.decompress(base64.b64decode(item['payload'], validate=True)))
            self.assertFalse((runtime / 'scripts').exists())
            env = {**os.environ, 'PYTHONPATH': str(runtime), 'HF_HUB_OFFLINE': '1'}
            expected_tests = unittest.defaultTestLoader.discover(
                str(ROOT / 'research_rag/tests'), pattern='test_atomic_experiment.py').countTestCases()
            self.assertGreater(expected_tests, 0)
            probe = '''import sys, unittest
suite = unittest.defaultTestLoader.discover('research_rag/tests', pattern='test_atomic_experiment.py')
assert suite.countTestCases() == int(sys.argv[1]), 'Runtime discovery differs from the source tests'
for group in suite:
    for cases in group:
        for case in cases:
            assert 'test_notebook_compiles' not in case.id(), 'Local packaging test leaked into runtime'
freeze = unittest.defaultTestLoader.loadTestsFromName(
    'test_atomic_experiment.AtomicExperimentTests.test_freeze_contains_39_cases_312_calls_and_original_gate')
result = unittest.TextTestRunner(verbosity=2).run(freeze)
raise SystemExit(0 if result.wasSuccessful() else 1)
'''
            result = subprocess.run([sys.executable, '-c', probe, str(expected_tests)],
                cwd=runtime, env=env, capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('Ran 1 test', result.stderr)
            self.assertIn('\nOK', result.stderr)
            validated = subprocess.run([sys.executable, '-m', 'research_rag.evaluation.evaluate_atomic_verifier',
                '--output-dir', str(runtime / 'probe'), '--decomposition-probe', '--validate-only'],
                cwd=runtime, env=env, capture_output=True, text=True, timeout=120)
            self.assertEqual(validated.returncode, 0, validated.stdout + validated.stderr)
            self.assertEqual(json.loads(validated.stdout)['cases'], 18)
            self.assertFalse((runtime / 'probe').exists())

    def test_setup_fix_preserves_model_prompts_data_and_budgets(self):
        old = json.loads((EVAL / 'atomic_verifier_criteria.json').read_text())
        fixed = json.loads((EVAL / 'atomic_verifier_criteria_setup2.json').read_text())
        self.assertEqual(old.keys(), fixed.keys())
        for key in old.keys() - {'version', 'source_sha256'}:
            self.assertEqual(old[key], fixed[key], key)
        changed = {name for name in old['source_sha256']
                   if old['source_sha256'][name] != fixed['source_sha256'][name]}
        self.assertEqual(changed, {'research_rag/tests/test_atomic_experiment.py',
                                  'research_rag/evaluation/evaluate_atomic_verifier.py'})


if __name__ == '__main__':
    unittest.main()
