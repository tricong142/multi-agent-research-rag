"""Rebind unchanged reviewed validation data to cf9 under the user's explicit request."""
import importlib.util
import json
from pathlib import Path
import hashlib

AUTHORIZATION = 'User requested: Giữ bộ validation30 đã review, chưa dùng để tune; lập binding/lock mới khi đổi candidate.'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def verify(folder, criteria_sha256):
    folder=Path(folder)
    binding=json.loads((folder/'binding.json').read_bytes())
    if binding.get('candidate_criteria_sha256')!=criteria_sha256 or binding.get('authorization')!=AUTHORIZATION:
        raise ValueError('Candidate validation binding/authorization mismatch')
    spec=importlib.util.spec_from_file_location('original_validation_review',folder/'original/review_gate.py')
    gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
    review=(folder/'annotation-review.json').read_bytes()
    old=gate.admit(folder/'original',json.loads(review))
    old['review_sha256']=sha(review)
    if old!=json.loads((folder/'original-lock.json').read_bytes()):
        raise ValueError('Original human annotation admission changed')
    expected={'original_manifest_sha256':sha((folder/'original/manifest.json').read_bytes()),
              'annotation_review_sha256':sha(review),'original_lock_sha256':sha((folder/'original-lock.json').read_bytes()),
              'cases_sha256':sha((folder/'original/cases.jsonl').read_bytes()),
              'inputs_sha256':sha((folder/'original/inputs.jsonl').read_bytes()),
              'protocol_sha256':sha((folder/'original/criteria.json').read_bytes()),
              'development_overlap_sha256':sha((folder/'development-overlap.json').read_bytes())}
    if any(binding.get(k)!=value for k,value in expected.items()):
        raise ValueError('Validation data, gold, review or protocol changed')
    if binding.get('inference_completed') is not False or binding.get('validation_used_for_tuning') is not False:
        raise ValueError('This preregistration cannot reuse exposed candidate outcomes')
    overlap=json.loads((folder/'development-overlap.json').read_bytes())
    if overlap.get('criteria_sha256')!=criteria_sha256 or overlap['flags']:
        raise ValueError('Development overlap screen is stale or unresolved')
    return binding


def build(root):
    root=Path(root)
    from scripts.atomic_validation_review import admit, json_bytes, write_once
    candidate=json.loads((root/'docs/atomic-verifier-cellfix9-candidate.json').read_bytes())
    source=root/'docs/validation/atomic-cellfix6-v1'
    dest=root/'docs/validation/atomic-cellfix9-v1'
    raw=(source/'annotation-review-cellfix6-v1.json').read_bytes()
    old=admit(source,json.loads(raw));old['review_sha256']=sha(raw)
    if old!=json.loads((source/'validation-lock.json').read_bytes()):
        raise ValueError('Original validation lock does not match human review')
    # Keep the whole original packet, including its original candidate binding.
    manifest=json.loads((source/'manifest.json').read_bytes())
    overlap=(root/'docs/atomic-verifier-cellfix9-validation-overlap.json').read_bytes()
    if json.loads(overlap)['criteria_sha256']!=candidate['criteria_sha256'] or json.loads(overlap)['flags']:
        raise ValueError('Complete development overlap screening before binding')
    for name in set(manifest['files'])|{'manifest.json'}:
        write_once(dest/'original'/name,(source/name).read_bytes())
    write_once(dest/'annotation-review.json',raw)
    write_once(dest/'original-lock.json',(source/'validation-lock.json').read_bytes())
    write_once(dest/'development-overlap.json',overlap)
    binding={'version':'atomic-cellfix9-validation-binding-v1','candidate':candidate['candidate'],
        'candidate_criteria_sha256':candidate['criteria_sha256'],'authorization':AUTHORIZATION,
        'binding_kind':'new candidate preregistration reusing unchanged human-reviewed gold',
        'new_human_signature_created':False,'original_reviewer':old['reviewer'],'original_reviewed_on':old['reviewed_on'],
        'original_manifest_sha256':sha((source/'manifest.json').read_bytes()),
        'annotation_review_sha256':sha(raw),'original_lock_sha256':sha((source/'validation-lock.json').read_bytes()),
        'cases_sha256':sha((source/'cases.jsonl').read_bytes()),'inputs_sha256':sha((source/'inputs.jsonl').read_bytes()),
        'protocol_sha256':sha((source/'criteria.json').read_bytes()),'cases':30,'papers':10,
        'development_overlap_sha256':sha(overlap),
        'validation_used_for_tuning':False,'inference_completed':False}
    write_once(dest/'binding.json',json_bytes(binding))
    write_once(dest/'binding_gate.py',Path(__file__).read_bytes())
    verify(dest,candidate['criteria_sha256'])
    return dest


if __name__=='__main__':
    print(build(Path(__file__).resolve().parents[1]))
