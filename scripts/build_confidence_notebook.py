"""Reuse the hashed setup to build a confidence-only manual GPU diagnostic."""
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
source = json.loads((ROOT / "scripts/kaggle_autonomy_validation.ipynb").read_text(encoding="utf-8"))
setup_cells = [cell for cell in source["cells"] if cell["cell_type"] == "code"][:2]
execute = '''offline = env.copy()
offline.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
diagnostic = out / 'confidence-step1'
run('confidence-step1', [python, '-u', '-m', 'research_rag.evaluation.compare_factchecker',
    '--comparison', 'confidence', '--output-dir', str(diagnostic)],
    child_env=offline, timeout=5400, required=False)
for filename in ('gate-results.json', 'metrics.json'):
    path = diagnostic / filename
    print(filename, path.read_text() if path.exists() else 'Missing; inspect status and stderr.')
bundle()
print('Save Version WITH Output, verify the saved ZIP, then stop the GPU session.')
print('A failed gate is evidence to inspect. Do not change thresholds or discard failed rows.')
'''
compile(execute, "confidence-notebook", "exec")
cells = [{"cell_type": "markdown", "metadata": {}, "source":
    "# Confidence contract — Step 1 (2026-10-09)\n"
    "Keep Private. Enable GPU T4 and Internet; attach the existing workspace and diagnostics v2 datasets. "
    "Run these THREE code cells in order, one at a time. This diagnostic uses the local merged Fact-Checker weights; "
    "no Gemini key is needed. The second cell installs dependencies, checks hashes and runs contract tests. "
    "The third evaluates 3 profiles on the same 30 dev + 12 synthetic + 5 observed failures = 141 predictions. "
    "The five failures contain four distinct claim/context pairs and assistant-reviewed labels. "
    "Judge, threshold 0.7 and maximum 3 attempts per stage are fixed; criteria are saved before inference. "
    "Only the experimental profile changes the confidence system prompt; it is not promoted automatically. "
    "This is development/regression, not final E2E or proof of calibrated confidence. "
    "A nonzero stage exit is preserved in status.json; inspect gate-results.json and explanations. "
    "Do not rerun cell 3 over the same output. Save the evidence and start a fresh session for another run.\n"},
    *setup_cells, {"cell_type": "code", "metadata": {}, "source": execute, "execution_count": None, "outputs": []}]
target = ROOT / "scripts/kaggle_confidence_validation.ipynb"
target.write_text(json.dumps(dict(cells=cells, metadata=source["metadata"], nbformat=4, nbformat_minor=4),
                            ensure_ascii=False, indent=2), encoding="utf-8")
print(target)
print("Bytes:", target.stat().st_size, "SHA256:", hashlib.sha256(target.read_bytes()).hexdigest())
