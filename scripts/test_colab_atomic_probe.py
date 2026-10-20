"""Exercise the exact Colab payload independently of the checkout."""
import ast
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
from scripts.atomic_release_test_support import v7_file


ROOT = Path(__file__).resolve().parents[1]


class ColabAtomicProbeTests(unittest.TestCase):
    def test_exact_payload_passes_frozen_regression_and_both_validation_modes(self):
        notebook = json.loads((ROOT / 'scripts/colab_decomposition_probe_v7.ipynb').read_text(encoding='utf-8'))
        cells = [cell['source'] for cell in notebook['cells'] if cell['cell_type'] == 'code']
        self.assertEqual(len(cells), 4)
        for cell in cells:
            compile(cell, 'colab-payload-test', 'exec')
        assignments = {target.id: ast.literal_eval(node.value) for node in ast.parse(cells[0]).body
                       if isinstance(node, ast.Assign) for target in node.targets
                       if isinstance(target, ast.Name) and target.id in ('payload', 'payload_sha256', 'manifest')}
        payload = base64.b64decode(assignments['payload'], validate=True)
        self.assertEqual(hashlib.sha256(payload).hexdigest(), assignments['payload_sha256'])
        manifest = assignments['manifest']
        frozen = json.loads((ROOT / 'research_rag/evaluation/atomic_verifier_criteria_v7.json').read_text())
        self.assertTrue(set(frozen['source_sha256']) <= set(manifest))
        self.assertIn('research_rag/tests/test_atomic_metric_v7.py', frozen['source_sha256'])
        self.assertFalse(any(name.endswith('.safetensors') or '.env' in Path(name).parts for name in manifest))
        with tempfile.TemporaryDirectory(dir=ROOT / 'research-runs') as directory:
            runtime = Path(directory)
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                self.assertEqual(len(archive.namelist()), len(manifest))
                self.assertEqual(set(archive.namelist()), set(manifest))
                for name in archive.namelist():
                    target = (runtime / name).resolve()
                    self.assertTrue(target.is_relative_to(runtime.resolve()))
                    data = archive.read(name)
                    self.assertEqual(len(data), manifest[name]['size'])
                    self.assertEqual(hashlib.sha256(data).hexdigest(), manifest[name]['sha256'])
                    self.assertEqual(data, v7_file(name).read_bytes())
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
            env = {**os.environ, 'PYTHONPATH': str(runtime), 'HF_HUB_OFFLINE': '1'}
            modules = [Path(name).with_suffix('').as_posix().replace('/', '.')
                       for name in frozen['source_sha256'] if name.startswith('research_rag/tests/')]
            check = '''import json, sys, unittest
suite = unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:])
count = suite.countTestCases()
assert count > 0
result = unittest.TextTestRunner(verbosity=2).run(suite)
print(json.dumps({'discovered': count, 'executed': result.testsRun}))
raise SystemExit(0 if result.wasSuccessful() else 1)
'''
            tests = subprocess.run([sys.executable, '-c', check, *modules], cwd=runtime,
                                   env=env, capture_output=True, text=True, timeout=180)
            self.assertEqual(tests.returncode, 0, tests.stdout + tests.stderr)
            discovered = json.loads(tests.stdout.splitlines()[-1])
            self.assertEqual(discovered['discovered'], discovered['executed'])
            self.assertIn('test_atomic_metric_v7', tests.stderr)
            for probe, expected in ((True, 18), (False, 39)):
                command = [sys.executable, '-m', 'research_rag.evaluation.evaluate_atomic_verifier',
                           '--output-dir', str(runtime / 'unused'), '--validate-only']
                if probe:
                    command.append('--decomposition-probe')
                result = subprocess.run(command, cwd=runtime, env=env, capture_output=True,
                                        text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(json.loads(result.stdout)['cases'], expected)
                self.assertFalse((runtime / 'unused').exists())
        self.assertIn('timeout=2520', cells[3])
        self.assertNotIn("'--worker'", cells[3])
        self.assertIn("'--decomposition-probe'", cells[3])
        self.assertNotIn("'--probe-dir'", cells[3])

    def test_release_manifest_matches_actual_files(self):
        release = json.loads((ROOT / 'docs/atomic-verifier-v7-colab-release.json').read_text())
        for name, digest in release['files'].items():
            self.assertEqual(hashlib.sha256(v7_file(name).read_bytes()).hexdigest(), digest)
        self.assertEqual(hashlib.sha256((ROOT / 'research_rag/evaluation/atomic_verifier_criteria_v7.json').read_bytes()).hexdigest(),
                         release['criteria_sha256'])

    def test_v7_preserves_model_data_base_prompts_and_all_budgets(self):
        previous = json.loads((ROOT / 'research_rag/evaluation/atomic_verifier_criteria_v6.json').read_text())
        candidate = json.loads((ROOT / 'research_rag/evaluation/atomic_verifier_criteria_v7.json').read_text())
        versioned = {'version', 'policy', 'structured_decoder', 'contract_file', 'contract_sha256', 'source_sha256', 'limitations'}
        self.assertEqual(previous.keys(), candidate.keys())
        for key in previous.keys() - versioned:
            self.assertEqual(previous[key], candidate[key], key)
        changed = {name for name in previous['source_sha256']
                   if previous['source_sha256'][name] != candidate['source_sha256'][name]}
        self.assertEqual(changed, {'04_factchecker/inference/atomic_verifier.py',
            '04_factchecker/inference/atomic_decoding.py',
            'research_rag/evaluation/evaluate_atomic_verifier.py',
            'research_rag/tests/test_atomic_experiment.py'})
        self.assertEqual(set(candidate['source_sha256']) - set(previous['source_sha256']),
                         {'research_rag/tests/test_atomic_metric_v7.py'})
        self.assertEqual(candidate['structured_decoder']['policy'], 'atomic-schema-decoding-v4')
        self.assertEqual({k: v for k, v in previous['structured_decoder'].items() if k != 'policy'},
                         {k: v for k, v in candidate['structured_decoder'].items() if k != 'policy'})

    def test_preserved_v5_and_v6_snapshots_replay_and_cannot_admit_v7(self):
        for version, successor, run, passed in (
            ('v5', 'v6', '20261015T103401Z-723b3e4a', True),
            ('v6', 'v7', '20261015T155608Z-9262cfd5', False),
        ):
            with self.subTest(version=version):
                self.check_snapshot(version, successor, run, passed)

    def check_snapshot(self, version, successor, run, passed):
        record = json.loads((ROOT / ('docs/atomic-verifier-' + version + '-preserved-before-' + successor + '.json')).read_text())
        snapshot = Path(record['snapshot'])
        manifest_path = snapshot / 'snapshot-manifest.json'
        self.assertEqual(hashlib.sha256(manifest_path.read_bytes()).hexdigest(), record['manifest_sha256'])
        manifest = json.loads(manifest_path.read_text())
        for name, item in manifest['files'].items():
            raw = (snapshot / name).read_bytes()
            self.assertEqual(len(raw), item['size'])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), item['sha256'], name)
        self.assertEqual(hashlib.sha256(Path(record['archive']).read_bytes()).hexdigest(), record['archive_sha256'])
        probe_name = 'research-runs/colab-atomic-' + version + '/' + run + '/output/decomposition-probe'
        check = '''import json, sys
from pathlib import Path
from research_rag.evaluation import evaluate_atomic_verifier as d
assert Path(d.__file__).resolve().is_relative_to(Path.cwd())
c, cases, *_ = d.load_frozen(d.CRITERIA)
effective, claims, _ = d.probe_configuration(c, cases, d.CRITERIA)
p = Path(sys.argv[1])
rows = [json.loads(line) for line in (p/'predictions.jsonl').read_text().splitlines()]
assert c['policy'] == 'atomic-verifier-constrained-' + sys.argv[2]
assert len(rows) == len(claims) == 18
for row, claim in zip(rows, claims):
    assert row['example_id'] == claim['example_id']
    assert d.replay_result(row['result'], claim['claim'], '', effective) is None
assert d.score_probe(rows, claims, effective)['automated_gate_pass'] == json.loads(sys.argv[3])
print(sys.argv[2] + ' replay: 18/18')
'''
        result = subprocess.run([sys.executable, '-B', '-c', check, probe_name, version, json.dumps(passed)], cwd=snapshot,
            env={**os.environ, 'PYTHONPATH': str(snapshot), 'HF_HUB_OFFLINE': '1', 'PYTHONDONTWRITEBYTECODE': '1'},
            capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(version + ' replay: 18/18', result.stdout)
        from research_rag.evaluation import evaluate_atomic_verifier as runner
        with self.assertRaisesRegex(ValueError, 'different frozen criteria'):
            runner.require_probe_review(ROOT / probe_name)


if __name__ == '__main__':
    unittest.main()
