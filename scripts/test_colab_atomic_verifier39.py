"""Check the exact full39 payload/admission without loading weights or running CUDA."""
import ast
import base64
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile
from scripts.atomic_release_test_support import v7_file

ROOT = Path(__file__).resolve().parents[1]
RUN = '20261016T024708Z-a57ee72a'


def cells_and_assignments():
    notebook = json.loads((ROOT / 'scripts/colab_atomic_verifier39_v7.ipynb').read_text(encoding='utf-8'))
    cells = [cell['source'] for cell in notebook['cells'] if cell['cell_type'] == 'code']
    values = {}
    for cell in (cells[0], cells[2]):
        for node in ast.parse(cell).body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in (
                            'payload', 'payload_sha256', 'manifest', 'probe_zip_b64', 'probe_zip_sha256', 'review_b64', 'review_sha256'):
                        values[target.id] = ast.literal_eval(node.value)
    return cells, values


class Full39ColabTests(unittest.TestCase):
    def test_cells_compile_and_model_stage_cannot_start_without_admission(self):
        cells, _ = cells_and_assignments()
        self.assertEqual(len(cells), 4)
        for cell in cells:
            compile(cell, 'full39-test', 'exec')
        self.assertIn('require_probe_review', cells[2])
        self.assertNotIn('files.upload', cells[2])
        self.assertIn('timeout=5520', cells[3])
        self.assertIn("'--probe-dir'", cells[3])
        self.assertNotIn("'--decomposition-probe'", cells[3])
        self.assertIn("'probe-admission'", cells[3].splitlines()[0])
        statuses = {name: {'exit_code': 0} for name in (
            'regression', 'cuda-preflight', 'probe-validate-only', 'verifier-validate-only')}
        run = Mock()
        with self.assertRaises(AssertionError):
            exec(cells[3], {'statuses': statuses, 'run': run})
        run.assert_not_called()

    def test_embedded_probe_review_source_and_release_are_exact(self):
        _, values = cells_and_assignments()
        for key, hash_key in (('payload', 'payload_sha256'), ('probe_zip_b64', 'probe_zip_sha256'),
                              ('review_b64', 'review_sha256')):
            self.assertEqual(hashlib.sha256(base64.b64decode(values[key], validate=True)).hexdigest(), values[hash_key])
        raw_probe = base64.b64decode(values['probe_zip_b64'])
        self.assertEqual(raw_probe, (ROOT / 'research-runs/colab-atomic-v7' / RUN / 'original-output.zip').read_bytes())
        review = base64.b64decode(values['review_b64'])
        self.assertEqual(review, (ROOT / 'docs' / ('semantic-review-v7-' + RUN + '.json')).read_bytes())
        self.assertEqual(json.loads(review)['reviewer'], 'tricong')
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(values['payload']))) as archive:
            self.assertEqual(set(archive.namelist()), set(values['manifest']))
            for name, record in values['manifest'].items():
                raw = archive.read(name)
                self.assertEqual(raw, v7_file(name).read_bytes(), name)
                self.assertEqual(len(raw), record['size'])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), record['sha256'])
        release = json.loads((ROOT / 'docs/atomic-verifier-v7-full39-colab-release.json').read_text())
        self.assertTrue(release['human_review_embedded'])
        for name, digest in release['files'].items():
            self.assertEqual(hashlib.sha256(v7_file(name).read_bytes()).hexdigest(), digest)

    def test_isolated_exact_payload_admits_confirmed_human_and_rejects_tampering(self):
        _, values = cells_and_assignments()
        with tempfile.TemporaryDirectory(dir=ROOT / 'research-runs') as temp:
            runtime = Path(temp)
            with zipfile.ZipFile(io.BytesIO(base64.b64decode(values['payload']))) as archive:
                for name in archive.namelist():
                    target = (runtime / name).resolve()
                    self.assertTrue(target.is_relative_to(runtime.resolve()))
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(name))
            probe = runtime / 'reviewed-probe'
            with zipfile.ZipFile(io.BytesIO(base64.b64decode(values['probe_zip_b64']))) as archive:
                for name in archive.namelist():
                    if name.startswith('decomposition-probe/'):
                        target = (probe / name.split('/', 1)[1]).resolve()
                        self.assertTrue(target.is_relative_to(probe.resolve()))
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(archive.read(name))
            (probe / 'semantic-review.json').write_bytes(base64.b64decode(values['review_b64']))
            check = '''import json, sys
from pathlib import Path
from unittest.mock import patch
from research_rag.evaluation import evaluate_atomic_verifier as d
assert Path(d.__file__).resolve().is_relative_to(Path.cwd())
probe=Path('reviewed-probe')
human=d.require_probe_review(probe)
assert human['reviewer']=='tricong'
review_path=probe/'semantic-review.json'
review_bytes=review_path.read_bytes()
original=json.loads(review_bytes)
for change in (lambda r:r.update(reviewer_kind='assistant'), lambda r:r.update(review_completed=False),
               lambda r:r.update(predictions_sha256='0'*64), lambda r:r['cases'][0]['judgments'].update(quantifier_preserved=False)):
    bad=json.loads(review_bytes);change(bad)
    review_path.write_text(json.dumps(bad))
    with patch.object(d,'model_loader') as loader, patch.object(sys,'argv',['test','--output-dir','unused','--probe-dir',str(probe)]):
        try:d.main()
        except ValueError:pass
        else:raise AssertionError('Tampered review admitted')
        loader.assert_not_called()
    assert not Path('unused').exists()
review_path.write_bytes(review_bytes)
prediction=probe/'predictions.jsonl';raw=prediction.read_bytes()
prediction.write_bytes(raw+b'\\n')
try:d.require_probe_review(probe)
except ValueError:pass
else:raise AssertionError('Review did not bind prediction bytes')
prediction.write_bytes(raw)
assert d.require_probe_review(probe)==human
print('Isolated real probe admission + tamper guards: passed; no model loaded')
'''
            result = subprocess.run([sys.executable, '-c', check], cwd=runtime,
                env={**os.environ, 'PYTHONPATH': str(runtime), 'HF_HUB_OFFLINE': '1'},
                capture_output=True, text=True, timeout=90)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('no model loaded', result.stdout)

    @unittest.skipUnless(shutil.which('node'), 'Node is needed only for the optional offline HTML exporter check')
    def test_human_form_starts_unsigned_and_export_checks_each_case(self):
        page = (ROOT / 'docs' / ('HUMAN_REVIEW_V7_' + RUN + '.html')).read_text(encoding='utf-8')
        self.assertEqual(page.count('type="checkbox"'), 90)
        self.assertNotIn(' checked', page)
        template = json.loads(re.search(r'<script id="template" type="application/json">(.*?)</script>', page, re.S)[1])
        script = re.search(r'<script>\s*(.*?)</script>', page, re.S)[1]
        self.assertFalse(template['review_completed'])
        check = '''const vm=require('vm'), assert=require('assert');
const data=JSON.parse(process.argv[1]);const script=process.argv[2];
const person={value:''};const cards=data.cases.map((r,i)=>({dataset:{index:String(i)},
 notes:{value:'Synthetic exporter test only'}, inputs:Object.keys(r.judgments).map(k=>({dataset:{key:k},checked:false})),
 querySelectorAll(){return this.inputs},querySelector(){return this.notes}}));
const ctx=vm.createContext({document:{getElementById(id){return id==='template'?{textContent:JSON.stringify(data)}:id==='reviewer'?person:{addEventListener(){}}},
 querySelectorAll(){return cards}}});
vm.runInContext(script,ctx);
assert.throws(()=>vm.runInContext('makeReview()',ctx));person.value='Synthetic exporter test reviewer';
assert.throws(()=>vm.runInContext('makeReview()',ctx));
cards.forEach(c=>c.inputs.forEach(i=>i.checked=true));cards[0].notes.value='';
assert.throws(()=>vm.runInContext('makeReview()',ctx));cards[0].notes.value='Synthetic exporter test only';
const result=vm.runInContext('makeReview()',ctx);assert.equal(result.cases.length,18);
assert(result.review_completed);assert.equal(result.predictions_sha256,data.predictions_sha256);
assert.equal(result.criteria_sha256,data.criteria_sha256);
assert(result.cases.every(r=>Object.values(r.judgments).every(v=>v===true)));
console.log('Synthetic exporter checks passed; no file signed or written');
'''
        result = subprocess.run(['node', '-e', check, json.dumps(template), script],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('no file signed or written', result.stdout)


if __name__ == '__main__':
    unittest.main()
