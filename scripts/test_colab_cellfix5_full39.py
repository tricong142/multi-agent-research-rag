"""Exercise full39 handoff guards without loading a model or running inference."""
import ast
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock,patch
import zipfile

from scripts import test_colab_cellfix3_fresh as h

ROOT=Path(__file__).resolve().parents[1]
TARGET=ROOT/'scripts/colab_atomic_verifier39_cellfix5.ipynb'
REQUIRED=(*h.PREREQUISITES,'probe-admission')


class Full39Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patcher=patch.object(h,'TARGET',TARGET);cls.patcher.start()
        cls.addClassCleanup(cls.patcher.stop)

    def test_payload_original_probe_review_and_release_hashes(self):
        book,cells,values=h.notebook();self.assertEqual(len(cells),4)
        self.assertEqual(book['metadata']['accelerator'],'GPU')
        for c in cells:compile(c,'full39','exec')
        literals={t.id:ast.literal_eval(n.value) for n in ast.parse(cells[0]).body
            if isinstance(n,ast.Assign) and isinstance(n.value,ast.Constant)
            for t in n.targets if isinstance(t,ast.Name)}
        for key,digest in (('payload','payload_sha256'),('probe_zip_b64','probe_zip_sha256'),('review_b64','review_sha256')):
            raw=base64.b64decode(literals[key],validate=True)
            self.assertEqual(hashlib.sha256(raw).hexdigest(),literals[digest])
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(values['payload']))) as z:
            self.assertEqual(len(z.namelist()),84)
            for name,item in values['manifest'].items():
                self.assertEqual(hashlib.sha256(z.read(name)).hexdigest(),item['sha256'])
        catalog=ROOT/'docs/atomic-verifier-cellfix5-full39-colab-release.json'
        if not catalog.exists():catalog=ROOT/'research-runs/cellfix5-full39-draft-release.json'
        released=json.loads(catalog.read_text(encoding='utf-8'))
        for name,digest in released['files'].items():
            self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),digest)
        self.assertFalse(released['new_probe_inference_required'])
        self.assertFalse(released['full39_inference_completed'])

    def test_fresh_setup_preserves_unsigned_original_and_installs_human_copy(self):
        with h.started() as (s,colab,cells):
            old=json.loads((s['original_probe']/'decomposition-probe/semantic-review.json').read_text())
            current=json.loads((s['reviewed_probe']/'semantic-review.json').read_text())
            self.assertFalse(old['review_completed']);self.assertTrue(current['review_completed'])
            self.assertEqual(current['reviewer_kind'],'human')
            self.assertEqual(len(current['cases']),18)
            self.assertEqual(sum(sum(v is True for v in r['judgments'].values()) for r in current['cases']),90)
            for p in (s['original_probe']/'decomposition-probe').iterdir():
                if p.name!='semantic-review.json':self.assertEqual((s['reviewed_probe']/p.name).read_bytes(),p.read_bytes())
            self.assertTrue((s['out']/'probe-original.zip').exists())
            colab.files.download.assert_not_called()

    def test_failed_admission_stops_before_regression_and_model_cache(self):
        with h.started() as (s,colab,cells):
            s['run']=Mock(side_effect=RuntimeError('admission rejected'))
            with self.assertRaisesRegex(RuntimeError,'admission rejected'):exec(cells[2],s)
            self.assertEqual(s['run'].call_count,1)
            self.assertEqual(s['run'].call_args.args[0],'probe-admission')
            self.assertIn('require_probe_review',s['run'].call_args.args[1][-1])
            colab.files.download.assert_called_once()

    def test_real_embedded_review_admission_and_tamper_rejection_without_model(self):
        with h.started() as (s,colab,cells):
            program='''import json,sys
from pathlib import Path
from unittest.mock import patch
from research_rag.evaluation import evaluate_atomic_verifier as e
assert Path(e.__file__).resolve().is_relative_to(Path.cwd())
directory=Path(sys.argv[1])
with patch.object(e,'model_loader') as loader:
    admitted=e.require_probe_review(directory)
    review_path=directory/'semantic-review.json'
    review=json.loads(review_path.read_text(encoding='utf-8'))
    review['cases'][0]['judgments']['entity_metric_binding_correct']=False
    review_path.write_text(json.dumps(review),encoding='utf-8')
    try:e.require_probe_review(directory)
    except ValueError as exc:assert str(exc)=='Every semantic criterion must pass with a written review note'
    else:raise AssertionError('Failed criterion admitted')
    loader.assert_not_called()
print(json.dumps({'admitted':admitted,'tampered_criterion_rejected':True,'model_loaded':False}))
'''
            env={**os.environ,'PYTHONPATH':str(s['root']),'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1'}
            result=subprocess.run([sys.executable,'-c',program,str(s['reviewed_probe'])],cwd=s['root'],
                env=env,capture_output=True,text=True,encoding='utf-8',timeout=300)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            record=json.loads(result.stdout)
            expected=json.loads((ROOT/'docs/atomic-verifier-cellfix5-human-admission-20261017T173345Z-905edcb5.json').read_text(encoding='utf-8'))
            self.assertEqual(record['admitted']['semantic_review_sha256'],expected['semantic_review_sha256'])
            self.assertTrue(record['tampered_criterion_rejected']);self.assertFalse(record['model_loaded'])
            colab.files.download.assert_not_called()

    def test_full39_missing_prerequisites_blocks_inference_and_archives(self):
        with h.started() as (s,colab,cells):
            s['run']=Mock()
            with self.assertRaisesRegex(AssertionError,'Complete cells 1-3'):exec(cells[3],s)
            s['run'].assert_not_called();colab.files.download.assert_called_once()
            self.assertFalse(s['full39_passed'])

    def simulate(self,exit_code,metrics):
        with h.started() as (s,colab,cells):
            s['statuses'].update({n:{'exit_code':0,'state':'completed'} for n in REQUIRED})
            def run(name,command,**options):
                self.assertEqual(name,'verifier39')
                self.assertEqual(options,{'timeout':5520,'required':False})
                self.assertNotIn('--decomposition-probe',command)
                self.assertNotIn('--assessment-smoke',command)
                self.assertEqual(command[command.index('--probe-dir')+1],str(s['reviewed_probe']))
                folder=s['out']/'verifier39';folder.mkdir()
                (folder/'metrics.json').write_text(json.dumps(metrics))
                s['statuses'][name]={'exit_code':exit_code,'state':'completed' if exit_code==0 else 'failed'}
                return exit_code
            s['run']=Mock(side_effect=run)
            exec(cells[3],s)
            self.assertEqual(s['run'].call_count,1);colab.files.download.assert_called_once()
            self.assertTrue(s['out'].with_suffix('.zip').exists())
            return s['full39_passed']

    def test_confirmed_full39_success_uses_reviewed_probe_and_exact_quality_gate(self):
        self.assertTrue(self.simulate(0,{'automated_gate_pass':True,'n':39,'correct_labels':39,'false_support':0,'runtime_failed_rows':0}))

    def test_failed_full39_preserves_archive_and_does_not_report_pass(self):
        self.assertFalse(self.simulate(1,{'automated_gate_pass':False,'n':12,'correct_labels':1,'false_support':2,'runtime_failed_rows':8}))

    def test_stale_gate_cannot_override_wrong_count_or_false_support(self):
        self.assertFalse(self.simulate(0,{'automated_gate_pass':True,'n':38,'correct_labels':38,'false_support':0,'runtime_failed_rows':0}))
        self.assertFalse(self.simulate(0,{'automated_gate_pass':True,'n':39,'correct_labels':38,'false_support':1,'runtime_failed_rows':0}))

    def test_existing_full39_output_is_never_overwritten(self):
        with h.started() as (s,colab,cells):
            s['statuses'].update({n:{'exit_code':0} for n in REQUIRED})
            folder=s['out']/'verifier39';folder.mkdir();marker=folder/'keep.txt';marker.write_text('keep')
            s['run']=Mock()
            with self.assertRaisesRegex(AssertionError,'Run already has'):exec(cells[3],s)
            s['run'].assert_not_called();self.assertEqual(marker.read_text(),'keep')
            colab.files.download.assert_called_once()


if __name__=='__main__':unittest.main(verbosity=2)
