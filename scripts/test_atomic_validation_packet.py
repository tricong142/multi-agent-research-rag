"""Integrity/admission tests; synthetic approvals exist only in disposable test folders."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.atomic_validation_review import CHECKS, admit, digest, packet, write_once
from scripts.prepare_atomic_validation_v1 import near, tokens

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'docs/validation/atomic-cellfix6-v1'


def simulated_review():
    result=json.loads((DATA/'annotation-review.template.json').read_text(encoding='utf-8'))
    result.update(reviewer='TEST_FIXTURE_NOT_A_HUMAN_SIGNOFF',reviewed_on='2026-10-18',human_attestation=True,
                  provenance_limits_acknowledged=True,no_candidate_outcomes_seen=True,protocol_accepted=True)
    _,rows=packet(DATA)
    for decision,row in zip(result['decisions'],rows):
        decision.update(accepted_label=row['proposed_gold'],checks=dict.fromkeys(CHECKS,True),
                        note='Simulated lifecycle fixture only; never an actual annotation approval.')
    return result


class ValidationPacketTests(unittest.TestCase):
    def test_integrity_exact_quotes_and_blind_model_inputs(self):
        m,rows=packet(DATA)
        inputs=[json.loads(line) for line in (DATA/'inputs.jsonl').read_text(encoding='utf-8').splitlines()]
        self.assertEqual(inputs,[{k:r[k] for k in ('id','claim','context')} for r in rows])
        self.assertEqual(len(rows),30)
        self.assertEqual(len({r['group_id'] for r in rows}),10)
        self.assertEqual(m['proposed_label_counts'],{'support':10,'contradict':10,'not_enough_info':10})
        self.assertFalse(m['human_adjudication_complete'])
        self.assertFalse(m['inference_completed'])
        for row in rows:
            self.assertEqual(digest(row['context'].encode()),row['source']['context_sha256'])
            self.assertLessEqual(len(row['context'].split()),600)
            self.assertLessEqual(len(row['claim'].split()),80)

    def test_human_review_template_cannot_admit(self):
        with self.assertRaisesRegex(ValueError,'human review'):
            admit(DATA,json.loads((DATA/'annotation-review.template.json').read_text()))

    def test_simulated_complete_review_is_accepted_only_as_protocol_fixture(self):
        result=admit(DATA,simulated_review())
        self.assertEqual(result['cases'],30)
        self.assertFalse(result['inference_completed'])
        self.assertEqual(result['signature_kind'],'self-attested human review; not cryptographic identity verification')

    def test_wrong_candidate_or_manifest_rejected(self):
        for name in ('candidate_criteria_sha256','manifest_sha256'):
            review=simulated_review();review[name]='0'*64
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'different packet'):
                admit(DATA,review)

    def test_missing_duplicate_and_extra_cases_rejected(self):
        for mutation in ('missing','duplicate','unknown'):
            review=simulated_review()
            if mutation=='missing': review['decisions'].pop()
            elif mutation=='duplicate': review['decisions'][-1]=review['decisions'][0]
            else: review['decisions'][-1]['id']='unexpected'
            with self.subTest(mutation=mutation),self.assertRaises(ValueError): admit(DATA,review)

    def test_rejected_unchecked_and_truthy_non_boolean_criteria_rejected(self):
        for value in (False,None,'true'):
            for check in CHECKS:
                review=simulated_review();review['decisions'][0]['checks'][check]=value
                with self.subTest(value=value,check=check),self.assertRaises(ValueError): admit(DATA,review)

    def test_gold_change_and_empty_note_rejected(self):
        review=simulated_review();review['decisions'][0]['accepted_label']='contradict'
        with self.assertRaisesRegex(ValueError,'new packet version'): admit(DATA,review)
        review=simulated_review();review['decisions'][0]['note']=' '
        with self.assertRaisesRegex(ValueError,'note missing'): admit(DATA,review)

    def test_ai_or_unacknowledged_provenance_and_prior_outcomes_rejected(self):
        for field,value in [('review_type','ai'),('reviewer',''),('reviewed_on','not-a-date'),
                            ('human_attestation',False),('provenance_limits_acknowledged',False),
                            ('no_candidate_outcomes_seen',False),('protocol_accepted',False)]:
            review=simulated_review();review[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError): admit(DATA,review)

    def test_changed_bytes_fail_and_immutable_file_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'research-runs') as folder:
            dest=Path(folder)/'packet';shutil.copytree(DATA,dest)
            (dest/'inputs.jsonl').write_text('changed')
            with self.assertRaisesRegex(ValueError,'hash mismatch'): packet(dest)
            with self.assertRaisesRegex(ValueError,'Immutable artifact'): write_once(dest/'inputs.jsonl',b'new')

    def test_near_duplicate_detectors_on_new_sentences(self):
        a='The cedar sensor recorded stable readings during the entire field trial.'
        for b in (a.upper(),a.replace('cedar','birch'),a+' Additional data were collected.'):
            self.assertTrue(near(tokens(a),tokens(b))[0])
        self.assertFalse(near(tokens(a),tokens('A glacier moved slowly across the valley.'))[0])

    def test_report_documents_known_limits_and_zero_screening_flags(self):
        report=json.loads((DATA/'overlap-report.json').read_text())
        self.assertEqual(report['flags'],[])
        self.assertEqual(report['document_overlap'],[])
        self.assertTrue(report['selected_in_test_candidate'])
        self.assertGreater(len(report['scanned_files_sha256']),30)
        self.assertTrue(any('pretraining' in value for value in report['limitations']))

    def test_review_form_does_not_preapprove(self):
        source=(DATA/'REVIEW.html').read_text(encoding='utf-8')
        self.assertEqual(source.count('<article data-id='),30)
        self.assertEqual(source.count('type="checkbox" data-check='),150)
        self.assertNotIn('checked="',source)
        self.assertNotIn('checked>',source)
        self.assertIn('related_not_proof_of_absence',source)


if __name__=='__main__':
    unittest.main(verbosity=2)
