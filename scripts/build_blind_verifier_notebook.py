"""Reuse the already exercised GPU setup; add only the isolated verifier experiment."""
import base64
import argparse
import hashlib
import json
from pathlib import Path
from pprint import pformat
import zlib

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
mode = parser.add_mutually_exclusive_group()
mode.add_argument('--scope-v2', action='store_true')
mode.add_argument('--scope-regression', action='store_true')
mode.add_argument('--logic-v3', action='store_true')
args = parser.parse_args()
original = json.loads((ROOT / "scripts/kaggle_confidence_backends.ipynb").read_text(encoding="utf-8"))
original_code = [cell["source"] for cell in original["cells"] if cell["cell_type"] == "code"]
paths = ("04_factchecker/inference/verifier.py", "research_rag/evaluation/compare_blind_verifier.py",
         "research_rag/evaluation/blind_verifier_criteria.json", "research_rag/evaluation/blind_verifier_repair_baseline.json",
         "research_rag/tests/test_blind_verifier.py", "research_rag/evaluation/blind_verifier_scope_criteria.json")
if args.scope_regression or args.logic_v3:
    paths += ('research_rag/evaluation/blind_verifier_scope_regression_cases.jsonl',
              'research_rag/evaluation/blind_verifier_scope_regression_criteria.json',
              'research_rag/evaluation/blind_verifier_base_v1_baseline.json',
              'research_rag/tests/test_blind_verifier_regression.py')
if args.logic_v3:
    paths += ('research_rag/evaluation/blind_verifier_logic_v3_criteria.json',
              'research_rag/evaluation/blind_verifier_scope_v2_baseline.json',
              'research_rag/tests/test_blind_verifier_logic.py')
payload = []
for name in paths:
    data = (ROOT / name).read_bytes()
    payload.append({"path": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                    "payload": base64.b64encode(zlib.compress(data)).decode()})
supplement = '''verifier_patch = __PAYLOAD__
for item in verifier_patch:
    relative = PurePosixPath(item['path'])
    assert not relative.is_absolute() and '..' not in relative.parts
    target = root / relative
    assert not target.exists(), 'Unexpected preexisting verifier source: ' + item['path']
    data = zlib.decompress(base64.b64decode(item['payload'], validate=True))
    assert len(data) == item['size'] and hashlib.sha256(data).hexdigest() == item['sha256']
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
(out / 'verifier-patch-manifest.json').write_text(json.dumps(
    [{k: v for k, v in item.items() if k != 'payload'} for item in verifier_patch], indent=2))

'''.replace("__PAYLOAD__", pformat(payload, width=100))
anchor = "env = os.environ.copy()"
assert original_code[1].count(anchor) == 1
setup = original_code[1].replace(anchor, supplement + anchor, 1)
run = '''assert statuses.get('preflight', {}).get('state') == 'completed' and statuses['preflight'].get('exit_code') == 0, 'Complete cell 2 setup/preflight first'
diagnostic_env = env.copy()
diagnostic_env.pop('HF_HUB_OFFLINE', None)
diagnostic_env.pop('TRANSFORMERS_OFFLINE', None)
run('blind-verifier', [python, '-u', '-m', 'research_rag.evaluation.compare_blind_verifier',
    '--output-dir', str(out / 'blind-verifier'), '--online-model-downloads'],
    child_env=diagnostic_env, timeout=5400, required=False)
for filename in ('summary.json', 'metrics.json', 'baseline-metrics.json'):
    result = out / 'blind-verifier' / filename
    print(filename, result.read_text() if result.exists() else 'Incomplete: inspect saved status/stderr.')
bundle()
print('Save Version WITH Output; download the ZIP and stop the GPU session.')
print('Human evidence review remains pending. Serving repair is unchanged.')
'''
instructions = """# Blind verifier — separate GPU development experiment

NEW Private Kaggle notebook, GPU T4 and Internet ON. Use the existing Five Agents
Workspace and Runtime Diagnostics v2 datasets; cell 1 mounts them. No Gemini
Secret or Reader requests. Three code cells: mount, setup/tests, experiment.
Cell 2 installs the previously exercised GPU runtime and a hashed verifier patch.
It uses venv --without-pip and installs wrapt. Run cell 3 only after setup passes.
Two backends (merged checkpoint, pinned base Qwen2.5-3B-Instruct), 12 unique cases
each, at most two attempts per case: at most 48 generation calls. Each model sees
only claim/context. The scorer compares each result with two proposed labels
afterward; those comparisons are not independent samples. Historical repair is
included from the audited run, not rerun. No automatic promotion or integration.
Weights may download about 6.2 GB if the pinned base snapshot is absent. One
model is loaded at a time. Keep all output, including failed gates. Exit 1 can
mean the experiment completed but no candidate passed. Review summary/status.
This is inspected synthetic development data, not independent final evaluation.
"""
if args.scope_v2 or args.scope_regression or args.logic_v3:
    criteria_name = ('blind_verifier_logic_v3_criteria.json' if args.logic_v3 else
                     'blind_verifier_scope_regression_criteria.json' if args.scope_regression else 'blind_verifier_scope_criteria.json')
    run = run.replace("'--output-dir', str(out / 'blind-verifier'), '--online-model-downloads'",
                      "'--output-dir', str(out / 'blind-verifier'), '--online-model-downloads',\n"
                      "    '--criteria', str(root / 'research_rag/evaluation/" + criteria_name + "')")
    instructions = instructions.replace('# Blind verifier — separate GPU development experiment',
        '# Base verifier scope_v2 — candidate prompt repair')
    instructions = instructions.replace('Two backends (merged checkpoint, pinned base Qwen2.5-3B-Instruct), 12 unique cases\neach, at most two attempts per case: at most 48 generation calls.',
        'Only pinned base Qwen2.5-3B-Instruct, 12 original regression cases,\nat most two attempts per case: at most 24 generation calls.')
    instructions += '\nStep 1 candidate only. Expanded regression and independent evaluation are pending.\n'
if args.scope_regression or args.logic_v3:
    instructions = instructions.replace('# Base verifier scope_v2 — candidate prompt repair',
        '# Base verifier scope_v2 — expanded development regression')
    instructions = instructions.replace('12 original regression cases,\nat most two attempts per case: at most 24 generation calls.',
        '39 unique regression cases (12 original + 27 contrastive cases),\nat most two attempts per case: at most 78 generation calls.')
    instructions = instructions.replace('with two proposed labels', 'with all three proposed labels')
    instructions = instructions.replace('Step 1 candidate only. Expanded regression and independent evaluation are pending.',
        'Historical base verifier v1 is also included without new inference, compared only on the original 12 contracts. '
        'Dataset groups and all wrong label alternatives are scored. Prompt/data hashes are checked before model loading. '
        'The 27 new cases are assistant-authored synthetic development data; independent annotation and semantic review remain pending.')
    run = run.replace("'baseline-metrics.json')", "'baseline-metrics.json', 'historical-verifier-metrics.json')")
if args.logic_v3:
    instructions = instructions.replace('scope_v2', 'logic_v3')
    instructions = instructions.replace('Historical base verifier v1 is also included without new inference, compared only on the original 12 contracts.',
        'Historical scope_v2 is included without new inference and scored on all 39 cases, including its failed row. '
        'This candidate changes the decision procedure prompt and supplies fixed quote-membership feedback on repair. '
        'Their individual effects are not isolated. The development gate remains 39/39, zero false support or runtime failures.')
cells = [{"cell_type": "markdown", "metadata": {}, "source": instructions}]
for body in (original_code[0], setup, run):
    compile(body, "blind-verifier-notebook", "exec")
    cells.append({"cell_type": "code", "metadata": {}, "source": body, "execution_count": None, "outputs": []})
name = ('kaggle_blind_verifier_logic_v3.ipynb' if args.logic_v3 else
        'kaggle_blind_verifier_scope_regression.ipynb' if args.scope_regression else
        'kaggle_blind_verifier_scope_v2.ipynb' if args.scope_v2 else 'kaggle_blind_verifier.ipynb')
target = ROOT / 'scripts' / name
target.write_text(json.dumps({"cells": cells, "metadata": original["metadata"], "nbformat": 4,
                             "nbformat_minor": 4}, ensure_ascii=False, indent=2), encoding="utf-8")
print(target.name, "SHA256:", hashlib.sha256(target.read_bytes()).hexdigest())
