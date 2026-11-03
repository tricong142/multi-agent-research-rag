"""Validate draft/released notebooks, frozen parent and unchanged scoring code."""
import hashlib
import gc
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PackagingResult(unittest.TextTestResult):
    def startTest(self, test):
        # Notebook simulations leave callback cycles holding large payload strings.
        gc.collect()
        super().startTest(test)


def main():
    names = ['test_colab_cellfix16','test_atomic_cellfix16_workflow',
             'test_cellfix16_cell6','test_cellfix16_cell7','test_cellfix16_packaging']
    exact = 'scripts.test_colab_cellfix16.Cellfix16NotebookTests.test_extracted_payload_runs_all_four_validate_only_modes'
    def remaining(suite):
        for test in suite:
            if isinstance(test,unittest.TestSuite):
                yield from remaining(test)
            elif test.id() != exact:
                yield test
    with (ROOT/'research-runs/cellfix16-packaging.log').open('w',encoding='utf-8') as stream:
        runner = unittest.TextTestRunner(stream=stream,verbosity=2,resultclass=PackagingResult)
        # Run the child-process payload check before loading the in-process runtime.
        # Otherwise two runtime copies compete for this Windows machine's RAM.
        first = runner.run(unittest.defaultTestLoader.loadTestsFromName(exact))
        suite = unittest.defaultTestLoader.loadTestsFromNames(['scripts.'+n for n in names])
        second = runner.run(unittest.TestSuite(remaining(suite)))
    results = [first,second]
    passed = all(r.wasSuccessful() for r in results)
    parent = json.loads((ROOT/'docs/atomic-verifier-cellfix15-candidate.json').read_bytes())
    candidate = json.loads((ROOT/'docs/atomic-verifier-cellfix16-candidate.json').read_bytes())
    release = json.loads((ROOT/'docs/atomic-verifier-cellfix15-release.json').read_bytes())
    for name,expected in release['files'].items():
        assert sha(ROOT/name) == expected, name
    before = Path(parent['source_root']);after = Path(candidate['source_root'])
    for name,item in parent['input_manifest'].items():
        assert sha(before/name) == item['sha256'], name
    for name in ['research_rag/evaluation/evaluate_atomic_verifier.py']:
        assert (before/name).read_bytes() == (after/name).read_bytes(), 'Scoring/evaluation changed'
    from scripts.atomic_cellfix15_replay_compat import patch_workflow
    old = patch_workflow((ROOT/'scripts/atomic_cellfix15_workflow.py').read_bytes()).decode('utf-8').replace('\r\n','\n')
    new = (ROOT/'scripts/atomic_cellfix16_workflow.py').read_text(encoding='utf-8')
    assert new.replace('cellfix16','cellfix15') == old, 'Workflow/gates changed'
    # This is the user's current notebook; preserve it, including its disabled gate.
    current = ROOT/'scripts/kaggle_atomic_verifier_cellfix14.ipynb'
    assert sha(current) == 'ead61ef878aa0ff014131a904a4321c2ddc9df6741078bb11d9e1f3d054162e4'
    regression = json.loads((ROOT/'docs/atomic-verifier-cellfix16-validation.json').read_bytes())
    token = json.loads((ROOT/'docs/atomic-verifier-cellfix16-tokenizer-check.json').read_bytes())
    report = dict(candidate=candidate['candidate'],criteria_sha256=candidate['criteria_sha256'],
        regression_tests=regression['regression_tests'],token_paths=len(token['checks']),
        packaging_tests=sum(r.testsRun for r in results),packaging_tests_passed=passed,
        failures=sum(len(r.failures) for r in results),errors=sum(len(r.errors) for r in results),parent_release_files_unchanged=len(release['files']),
        parent_candidate_inputs_unchanged=len(parent['input_manifest']),scoring_and_workflow_unchanged=True,
        current_cellfix14_notebook_unchanged=True,model_inference_completed=False,
        validation30_used_for_tuning=True,evaluation_role='development',independent_validation_completed=False)
    path = ROOT/'research-runs/cellfix16-payload-validate-only.json'
    if path.exists():report['exact_payload_validate_only'] = json.loads(path.read_bytes())
    (ROOT/'docs/atomic-verifier-cellfix16-packaging-validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))
    if not passed:
        print((ROOT/'research-runs/cellfix16-packaging.log').read_text(encoding='utf-8')[-12000:])
        raise SystemExit(1)


if __name__ == '__main__':
    main()
