"""Check the exact v8 notebook payload and admission guards without GPU inference."""
import ast
import base64
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def notebook():
    raw = json.loads((ROOT / 'scripts/colab_atomic_verifier_v8_smoke_probe.ipynb').read_text())
    cells = [c['source'] for c in raw['cells'] if c['cell_type'] == 'code']
    values = {target.id: ast.literal_eval(node.value) for node in ast.parse(cells[0]).body
              if isinstance(node, ast.Assign) for target in node.targets
              if isinstance(target, ast.Name) and target.id in ('payload', 'payload_sha256', 'manifest')}
    return cells, values


class V8ColabTests(unittest.TestCase):
    def test_released_metadata_cannot_be_rewritten(self):
        from scripts import build_colab_atomic_v8 as builder
        with tempfile.TemporaryDirectory(dir=ROOT / 'research-runs') as directory:
            runtime = Path(directory)
            for folder in ('docs', 'scripts', 'research_rag/evaluation'):
                (runtime / folder).mkdir(parents=True)
            for name in (builder.CRITERIA, 'research_rag/evaluation/atomic_verifier_contract_v8.json',
                         'scripts/build_colab_atomic_v8.py', 'scripts/build_colab_atomic_probe.py',
                         'scripts/freeze_atomic_verifier_v8.py'):
                (runtime / name).write_text('Synthetic packaging fixture only')
            helper = 'def bundle(): pass\ndef run(*args, **kwargs): pass\n'
            (runtime / 'scripts/colab_decomposition_probe_v7.ipynb').write_text(json.dumps({
                'cells': [{'cell_type': 'code', 'source': helper}]}))
            with (patch.object(builder, 'ROOT', runtime), patch.object(builder, 'package', return_value=(
                    {'version': 'synthetic-test', 'source_sha256': {'research_rag/tests/test_synthetic.py': 'unused'}},
                    {}, b'not executed')),
                    patch.object(sys, 'argv', ['build', '--release']), redirect_stdout(io.StringIO())):
                builder.build()
                release = runtime / 'docs/atomic-verifier-v8-colab-release.json'
                original = release.read_bytes()
                builder.build()
                self.assertEqual(release.read_bytes(), original)
                tampered = json.loads(original)
                tampered['human_review'] = 'tampered fixture'
                release.write_text(json.dumps(tampered))
                with self.assertRaisesRegex(ValueError, 'metadata is immutable'):
                    builder.build()

    def test_hashes_paths_and_frozen_files_match_exact_payload(self):
        cells, values = notebook()
        self.assertEqual(len(cells), 5)
        for cell in cells:
            compile(cell, 'v8-notebook-test', 'exec')
        payload = base64.b64decode(values['payload'], validate=True)
        self.assertEqual(hashlib.sha256(payload).hexdigest(), values['payload_sha256'])
        frozen = json.loads((ROOT / 'research_rag/evaluation/atomic_verifier_criteria_v8.json').read_text())
        self.assertTrue(set(frozen['source_sha256']) <= set(values['manifest']))
        self.assertIn('research_rag/tests/fixtures/atomic_v8_v7_assessments.json', values['manifest'])
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(len(archive.namelist()), len(values['manifest']))
            self.assertEqual(set(archive.namelist()), set(values['manifest']))
            for name, item in values['manifest'].items():
                relative = PurePosixPath(name)
                self.assertFalse(relative.is_absolute() or '..' in relative.parts or '\\' in name)
                self.assertNotIn('.env', relative.parts)
                self.assertFalse(name.endswith(('.safetensors', '.bin', '.pem', '.key')))
                data = archive.read(name)
                self.assertEqual(len(data), item['size'])
                self.assertEqual(hashlib.sha256(data).hexdigest(), item['sha256'])
                self.assertEqual(data, (ROOT / name).read_bytes(), name)
        release_path = ROOT / 'docs/atomic-verifier-v8-colab-release.json'
        if not release_path.exists():
            release_path = ROOT / 'research-runs/atomic-v8-draft-colab-release.json'
        release = json.loads(release_path.read_text())
        self.assertEqual(release['payload_sha256'], values['payload_sha256'])
        self.assertEqual(release['payload_files'], values['manifest'])
        for name, digest in release['files'].items():
            self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), digest, name)
        self.assertFalse(release['fresh_gpu_inference_completed'])
        self.assertFalse(release['full39_runs_automatically'])

    def test_smoke_and_probe_cannot_start_without_prerequisites(self):
        cells, _ = notebook()
        run = Mock()
        with self.assertRaises(AssertionError):
            exec(cells[3], {'statuses': {}, 'run': run})
        run.assert_not_called()
        with self.assertRaises(AssertionError):
            exec(cells[4], {'smoke_passed': False, 'run': run})
        run.assert_not_called()
        self.assertIn("'--assessment-smoke'", cells[3])
        self.assertIn("'--decomposition-probe'", cells[4])
        self.assertIn("['automated_gate_pass'] is True", cells[3])
        for cell in cells[3:]:
            self.assertIn('timeout=2520', cell)
            self.assertNotIn("'--worker'", cell)
            self.assertNotIn("'--probe-dir'", cell)
            self.assertIn('bundle()', cell)
        self.assertNotIn('semantic-review.json', cells[0])

    def test_v8_preserves_data_model_and_budgets_but_requires_new_review(self):
        previous = json.loads((ROOT / 'research_rag/evaluation/atomic_verifier_criteria_v7.json').read_text())
        frozen = json.loads((ROOT / 'research_rag/evaluation/atomic_verifier_criteria_v8.json').read_text())
        changed = {'version', 'policy', 'structured_decoder', 'contract_file', 'contract_sha256',
                   'source_sha256', 'prompt_sha256', 'limitations'}
        for name in previous.keys() - changed:
            self.assertEqual(previous[name], frozen[name], name)
        self.assertEqual(previous['prompt_sha256']['decompose'], frozen['prompt_sha256']['decompose'])
        self.assertNotEqual(previous['prompt_sha256']['assess'], frozen['prompt_sha256']['assess'])
        from research_rag.evaluation import evaluate_atomic_verifier as driver
        old = ROOT / 'research-runs/colab-atomic-v7/20261016T024708Z-a57ee72a/reviewed-probe'
        with self.assertRaisesRegex(ValueError, 'different frozen criteria'):
            driver.require_probe_review(old)

    def test_isolated_payload_runs_frozen_regression_and_three_validate_only_modes(self):
        _, values = notebook()
        with tempfile.TemporaryDirectory(dir=ROOT / 'research-runs') as directory:
            runtime = Path(directory)
            with zipfile.ZipFile(io.BytesIO(base64.b64decode(values['payload']))) as archive:
                for name in values['manifest']:
                    target = (runtime / name).resolve()
                    self.assertTrue(target.is_relative_to(runtime.resolve()))
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(name))
            env = {**os.environ, 'PYTHONPATH': str(runtime), 'HF_HUB_OFFLINE': '1'}
            frozen = json.loads((runtime / 'research_rag/evaluation/atomic_verifier_criteria_v8.json').read_text())
            modules = [Path(name).with_suffix('').as_posix().replace('/', '.')
                       for name in frozen['source_sha256']
                       if name.startswith('research_rag/tests/') and name.endswith('.py')]
            check = '''import json, sys, unittest
from pathlib import Path
from research_rag.evaluation import evaluate_atomic_verifier as driver
assert Path(driver.__file__).resolve().is_relative_to(Path.cwd())
suite = unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:])
count = suite.countTestCases()
assert count > 0
result = unittest.TextTestRunner(verbosity=2).run(suite)
print(json.dumps({'discovered': count, 'executed': result.testsRun}))
raise SystemExit(0 if result.wasSuccessful() else 1)
'''
            result = subprocess.run([sys.executable, '-c', check, *modules], cwd=runtime,
                env=env, capture_output=True, text=True, timeout=300)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            counts = json.loads(result.stdout.splitlines()[-1])
            self.assertEqual(counts['discovered'], counts['executed'])
            self.assertIn('test_atomic_assessment_v8', result.stderr)
            print('V8 isolated frozen tests:', counts['executed'], flush=True)
            for flag, cases, calls in (('--decomposition-probe', 18, 36),
                                       ('--assessment-smoke', 12, 96), (None, 39, 312)):
                command = [sys.executable, '-m', 'research_rag.evaluation.evaluate_atomic_verifier',
                           '--output-dir', str(runtime / 'unused'), '--validate-only']
                if flag:
                    command.append(flag)
                result = subprocess.run(command, cwd=runtime, env=env, capture_output=True,
                                        text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                output = json.loads(result.stdout)
                self.assertEqual((output['cases'], output['maximum_calls']), (cases, calls))
                self.assertFalse((runtime / 'unused').exists())


if __name__ == '__main__':
    unittest.main()
