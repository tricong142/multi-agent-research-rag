"""Additional development-role, failed-usage and Kaggle integrity checks."""
import ast
import base64
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'research-runs/atomic-cellfix17-candidate/workspace'
sys.path.insert(0,str(SOURCE))


class PackagingTests(unittest.TestCase):
    def test_exposed_data_cannot_claim_independence(self):
        from scripts.atomic_cellfix17_binding import verify
        candidate=json.loads((ROOT/'docs/atomic-verifier-cellfix17-candidate.json').read_bytes())
        folder=ROOT/'docs/validation/atomic-cellfix17-dev30-v1'
        record=verify(folder,candidate['criteria_sha256'])
        self.assertEqual(record['evaluation_role'],'development')
        self.assertTrue(record['validation_used_for_tuning'])
        self.assertFalse(record['independent_validation_completed'])
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);bad=dict(record,evaluation_role='independent')
            (path/'binding.json').write_text(json.dumps(bad))
            with self.assertRaisesRegex(ValueError,'development'):verify(path,candidate['criteria_sha256'])

    def test_kaggle_payload_is_identical_and_controls_stay_off(self):
        from scripts.atomic_validation_review import digest
        def code(name):
            book=json.loads((ROOT/'scripts'/name).read_bytes())
            return [''.join(c['source']) for c in book['cells'] if c['cell_type']=='code']
        kaggle=code('kaggle_atomic_verifier_cellfix17.ipynb');colab=code('colab_atomic_verifier_cellfix17.ipynb')
        self.assertEqual(len(kaggle),7)
        def values(source):
            return {n.targets[0].id:ast.literal_eval(n.value) for n in ast.parse(source).body
                if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id in ('payload','manifest','payload_sha256','criteria_sha256')}
        self.assertEqual(values(kaggle[0]),values(colab[0]))
        data=values(kaggle[0]);blob=base64.b64decode(data['payload'],validate=True)
        self.assertEqual(digest(blob),data['payload_sha256'])
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            self.assertEqual(set(z.namelist()),set(data['manifest']))
            for name,item in data['manifest'].items():self.assertEqual(digest(z.read(name)),item['sha256'])
        for cell in kaggle:
            compile(cell,'kaggle14','exec');self.assertNotIn('google.colab',cell)
        self.assertIn('RUN_FULL39 = False',kaggle[5]);self.assertIn('RUN_VALIDATION30 = False',kaggle[6])

    def test_missing_generation_usage_fails_gate_without_crashing(self):
        from scripts import atomic_cellfix17_workflow as w
        criteria={'max_new_tokens':1536,'maximum_generated_tokens':1536}
        trace={'messages':[],'cooperative_deadline':True,'validation_issue':'deadline_exceeded'}
        outputs=[{'example_id':'TEST_ONLY','result':{'trace':[trace]}}]
        events=[{'event':'call_started','call_id':1,'example_id':'TEST_ONLY','messages':[]},
                {'event':'generation','call_id':1,'example_id':'TEST_ONLY','raw_output':None,'json_valid':False,
                 'usage_complete':False,'generated_tokens':None,'prompt_tokens':7},
                {'event':'call_finished','call_id':1,'example_id':'TEST_ONLY','messages':[]}]
        with patch.object(w.r,'score',return_value={'backend_calls':1,'checks':{'no_runtime_failures':False}}),patch.object(w.r,'decoding_trace_complete',return_value=False):
            metrics=w.measured_score(outputs,[],criteria,events)
        self.assertIsNone(metrics['generated_tokens']);self.assertFalse(metrics['usage_complete'])
        self.assertFalse(metrics['automated_gate_pass'])


if __name__=='__main__':unittest.main()
