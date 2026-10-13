"""Package the frozen atomic experiment using the previously exercised Kaggle setup."""
import ast
import base64
import hashlib
import json
from pathlib import Path
from pprint import pformat
import zlib

ROOT = Path(__file__).resolve().parents[1]


def build():
    template = json.loads((ROOT / 'scripts/kaggle_blind_verifier_logic_v3.ipynb').read_text(encoding='utf-8'))
    code = [c['source'] if isinstance(c['source'], str) else ''.join(c['source']) for c in template['cells'] if c['cell_type'] == 'code']
    tree = ast.parse(code[1])
    old_patch = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == 'verifier_patch' for t in node.targets))
    names = [item['path'] for item in old_patch] + [
        '04_factchecker/inference/atomic_verifier.py', '04_factchecker/inference/numeric_verifier.py',
        '04_factchecker/inference/evidence_screen.py', 'research_rag/evaluation/evaluate_atomic_verifier.py',
        'research_rag/evaluation/atomic_verifier_contract_v5.json', 'research_rag/evaluation/atomic_verifier_criteria_v5.json',
        'research_rag/evaluation/atomic_verifier_logic_v3_baseline.json',
        'research_rag/evaluation/decomposition_probe_claims_v2.jsonl',
        'research_rag/tests/test_atomic_verifier.py', 'research_rag/tests/test_atomic_experiment.py']
    frozen = json.loads((ROOT / 'research_rag/evaluation/atomic_verifier_criteria_v5.json').read_text())
    names += [name for name in frozen['source_sha256'] if name not in names]
    assert len(names) == len(set(names))
    payload = []
    old_runtime = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == 'runtime_patch' for t in node.targets))
    original_hashes = {item['path']: item['sha256'] for item in old_runtime + old_patch}
    for name in names:
        data = (ROOT / name).read_bytes()
        item = {'path': name, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                'payload': base64.b64encode(zlib.compress(data)).decode()}
        if name in original_hashes:
            item['base_sha256'] = original_hashes[name]
        payload.append(item)
    assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == 'verifier_patch' for t in node.targets))
    lines = code[1].splitlines(keepends=True)
    setup = ''.join(lines[:assignment.lineno - 1]) + 'verifier_patch = ' + pformat(payload, width=100) + '\n' + ''.join(lines[assignment.end_lineno:])
    setup = setup.replace("assert not target.exists(), 'Unexpected preexisting verifier source: ' + item['path']",
        "if target.exists():\n        assert hashlib.sha256(target.read_bytes()).hexdigest() in (item['sha256'], item.get('base_sha256', item['sha256'])), 'Overlapping source differs: ' + item['path']")
    setup = setup.replace("run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')",
                          "import uuid\nrun_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]")
    setup = setup.replace("if required and code: raise RuntimeError(name + ' failed; inspect its saved stderr')",
        "if required and code:\n        print((out / (name + '.stderr.log')).read_text()[-12000:], flush=True)\n        raise RuntimeError(name + ' failed; inspect its saved stderr')")
    setup = setup.replace("print('SETUP COMPLETE; inspect preflight before running the next cell')\n", '')
    # Both must pass before cell 3; validate-only never loads a model.
    setup = setup.replace("run('pip-check',", "run('structured-decoder', [python, '-m', 'pip', 'install', '--disable-pip-version-check', '-r', 'requirements-atomic-verifier.txt'])\nrun('pip-check',")
    setup += "run('atomic-freeze-check', [python, '-m', 'research_rag.evaluation.evaluate_atomic_verifier', '--output-dir', str(out/'decomposition-probe'), '--decomposition-probe', '--validate-only'])\n"
    setup += "print('SETUP COMPLETE: atomic-verifier-constrained-v5-20261013; runtime tests, preflight and freeze check passed')\n"
    run = '''assert statuses.get('preflight', {}).get('exit_code') == 0 and statuses.get('atomic-freeze-check', {}).get('exit_code') == 0, 'Complete cell 2 first'
diagnostic_env = env.copy()
diagnostic_env.pop('HF_HUB_OFFLINE', None)
diagnostic_env.pop('TRANSFORMERS_OFFLINE', None)
code = run('decomposition-probe', [python, '-u', '-m', 'research_rag.evaluation.evaluate_atomic_verifier',
    '--output-dir', str(out / 'decomposition-probe'), '--decomposition-probe', '--online-model-downloads'],
    child_env=diagnostic_env, timeout=2520, required=False)
for filename in ('summary.json', 'metrics.json'):
    path = out / 'decomposition-probe' / filename
    print(filename, path.read_text() if path.exists() else 'Incomplete: inspect status and saved logs.')
bundle()
print('ZIP:', out.with_suffix('.zip'))
print('Exit 1 means a quality gate may have failed; 124 means process timeout. Preserve all output.')
print('Save Version WITH Output, download ZIP, then stop GPU. Review all 18 decompositions before 39 cases.')
'''
    intro = '# Decomposition probe v5 — 18 development claims only\n\nNEW private Kaggle notebook, GPU T4 and Internet ON; three CODE cells.\n1. Mount the existing Five Agents Workspace / Runtime Diagnostics datasets.\n2. Create isolated runtime with venv --without-pip; apply verified patches;\n   run contract tests, preflight and frozen source/data/prompt checks.\n3. Run ONLY decomposition for 18 unique inspected development claims using\n   pinned Qwen2.5-3B-Instruct. No evidence assessment, label generation or Gemini.\n\nThe model returns exact quotes, quantifier and a four-field scope OBJECT.\nCode derives start/end and checks uniqueness, order, coverage and shared scope.\nLeading AND at a later predicate boundary is allowed; inner AND still requires\nseparation. Scope errors identify the rejected field, and dataset restrictions\nbelong in condition. Syntax repairs regenerate without echoing malformed JSON.\nV5 enforces the JSON schema during token generation with lm-format-enforcer\n0.11.3, using a core adapter compatible with Transformers 5.16.1.\nQuotes/scope values come from exact claim spans; unambiguous quantifiers are\nrestricted from claim wording. No gold labels are used. At most 80 claim words.\nClaims without AND keep one complete quote. Simple temporal/dataset scope is\nrestricted in the schema and checked after generation; repair reports the\nrelated failures together. Population modifiers must remain attached to entity.\nSupported grammar is English AND and simple temporal/dataset phrases.\nNamed properties are preferred over generic verbs in scope.metric.\nFrozen version: atomic-verifier-constrained-v5-20261013.\nMaximum 2 calls/claim, 2 attempts, 1536 generated tokens/call, 180 seconds/claim;\n36 calls and 55296 generated tokens total. Hard process deadline 2400 seconds\nincludes model loading/downloads; notebook watchdog 2520 seconds. These are caps.\nDo not rerun cell 3 in an existing run. Preserve failed output as evidence.\n\nAutomated gate: all 18 valid, complete decompositions. This DOES NOT establish\ncorrect predicate meaning. Inspect predictions.jsonl and evidence-review.jsonl.\nsemantic-review.json starts pending; a human must review every claim for factual\npredicates, coverage, quantifiers, entity/metric and time/condition scope.\nDo not fill all true without reviewing. A structurally valid noun fragment can\nstill be semantically wrong. These seen cases are not independent held-out data.\nThe 39-case runner requires a matching passed probe and completed semantic review.\nNo serving promotion. Download ZIP with Output and send it for review; stop GPU.\n'
    cells = [{'cell_type': 'markdown', 'metadata': {}, 'source': intro}]
    for index, body in enumerate((code[0], setup, run), 1):
        compile(body, 'atomic-cell-' + str(index), 'exec')
        cells.append({'cell_type': 'code', 'metadata': {}, 'source': body, 'execution_count': None, 'outputs': []})
    target = ROOT / 'scripts/kaggle_decomposition_probe_v5.ipynb'
    target.write_text(json.dumps({'cells': cells, 'metadata': template['metadata'], 'nbformat': 4, 'nbformat_minor': 4},
                                ensure_ascii=False, indent=2), encoding='utf-8')
    print(target.name, 'SHA256:', hashlib.sha256(target.read_bytes()).hexdigest())
    return target


if __name__ == '__main__':
    build()
