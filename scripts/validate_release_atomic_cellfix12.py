"""Validate one final manifest sequentially, then release its standalone notebook."""
from contextlib import redirect_stdout
import importlib
import json
from pathlib import Path
import sys
import unittest

from scripts.atomic_validation_review import digest, json_bytes

ROOT = Path(__file__).resolve().parents[1]


def stage(name, fn):
    path = ROOT/'research-runs'/('cellfix12-final-'+name+'.log')
    print('Starting '+name, flush=True)
    try:
        with path.open('w',encoding='utf-8') as stream, redirect_stdout(stream):
            fn()
    except SystemExit as exc:
        if exc.code not in (0,None):
            print(path.read_text(encoding='utf-8')[-5000:],flush=True)
            raise
    print('Passed '+name, flush=True)


def main():
    if (ROOT/'docs/atomic-verifier-cellfix12-release.json').exists():
        raise ValueError('Release exists; verify its catalog instead of mutating it')
    from scripts.build_atomic_cellfix12_candidate import build
    stage('build',build)
    from scripts import check_atomic_cellfix12 as regression
    stage('regression',regression.main)
    from scripts import check_atomic_cellfix12_tokenizer as tokenizer
    stage('tokenizer',tokenizer.main)
    from scripts import check_cellfix12_validation_overlap as overlap
    stage('overlap',overlap.main)
    from scripts import replay_atomic_cellfix12_baseline as replay
    stage('baseline-replay',replay.main)
    from scripts import build_colab_cellfix12 as notebook
    stage('notebook-draft',notebook.build)
    results = {}
    path = ROOT/'research-runs/cellfix12-packaging-tests.log'
    with path.open('w',encoding='utf-8') as stream, redirect_stdout(stream):
        for name in ('test_colab_cellfix12','test_atomic_cellfix12_workflow','test_cellfix12_cell6','test_cellfix12_cell7'):
            module = importlib.import_module('scripts.'+name)
            suite = unittest.defaultTestLoader.loadTestsFromModule(module)
            result = unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
            results[name] = {'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors)}
            if not result.wasSuccessful():
                raise AssertionError('Packaging/gate tests failed: '+name+'; see '+str(path))
    print('Passed packaging/gate tests '+json.dumps(results),flush=True)
    stage('release',lambda:notebook.build(release=True))
    candidate = json.loads((ROOT/'docs/atomic-verifier-cellfix12-candidate.json').read_bytes())
    release = json.loads((ROOT/'docs/atomic-verifier-cellfix12-release.json').read_bytes())
    for name,expected in release['files'].items():
        assert digest((ROOT/name).read_bytes()) == expected, name
    for name,item in candidate['input_manifest'].items():
        raw = (Path(candidate['source_root'])/name).read_bytes()
        assert len(raw) == item['size'] and digest(raw) == item['sha256'], name
    payload_checks = json.loads((ROOT/'research-runs/cellfix12-payload-validate-only.json').read_bytes())
    regression_report = json.loads((ROOT/'docs/atomic-verifier-cellfix12-validation.json').read_bytes())
    token_report = json.loads((ROOT/'docs/atomic-verifier-cellfix12-tokenizer-check.json').read_bytes())
    for report in (release,regression_report,token_report):
        assert report['criteria_sha256'] == candidate['criteria_sha256']
    report = {'candidate':candidate['candidate'],'criteria_sha256':candidate['criteria_sha256'],
        'notebook':str(notebook.TARGET),'notebook_sha256':digest(notebook.TARGET.read_bytes()),
        'candidate_files':len(candidate['input_manifest']),'payload_files':len(release['payload_files']),
        'regression_tests':regression_report['regression_tests'],'regression_pass':regression_report['all_regression_passed'],
        'token_filter_paths':len(token_report['checks']),
        'token_filter_pass':all(c['accepted']==c['expected'] for c in token_report['checks']),
        'packaging_gate_tests':results,'payload_validate_only':payload_checks,
        'release_catalog_valid':True,'candidate_hashes_valid':True,
        'new_model_inference_completed':False,'probe_human_review':'pending_new_predictions',
        'full39_human_review':'pending_new_predictions','validation30_inference_completed':False,
        'promoted_to_serving':False}
    (ROOT/'docs/atomic-verifier-cellfix12-packaging-validation.json').write_bytes(json_bytes(report))
    print(json.dumps(report),flush=True)


if __name__ == '__main__':
    main()
