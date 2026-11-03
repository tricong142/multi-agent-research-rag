"""Bind exposed validation30-v1 as development; never issue a new human signature."""
import hashlib
import json
from pathlib import Path


def sha(raw):return hashlib.sha256(raw).hexdigest()


def verify(folder,criteria_sha256):
    folder=Path(folder);record=json.loads((folder/'binding.json').read_bytes())
    if (record['candidate_criteria_sha256']!=criteria_sha256 or record['evaluation_role']!='development'
            or record['validation_used_for_tuning'] is not True or record['independent_validation_completed'] is not False
            or record['new_human_signature_created'] is not False):
        raise ValueError('Exposed data must remain development, bound to this candidate')
    for name,expected in record['original_files_sha256'].items():
        if sha((folder/name).read_bytes())!=expected:raise ValueError('Original annotation/data changed: '+name)
    return record


def build(root):
    from scripts.atomic_validation_review import write_once,json_bytes
    root=Path(root);candidate=json.loads((root/'docs/atomic-verifier-cellfix14-candidate.json').read_bytes())
    source=root/'docs/validation/atomic-cellfix13-v1';dest=root/'docs/validation/atomic-cellfix14-dev30-v1'
    names=['annotation-review.json','original-lock.json']
    names += [p.relative_to(source).as_posix() for p in sorted((source/'original').rglob('*')) if p.is_file() and '__pycache__' not in p.parts]
    for name in names:write_once(dest/name,(source/name).read_bytes())
    record=dict(version='cellfix14-development-binding-v1',candidate=candidate['candidate'],
        candidate_criteria_sha256=candidate['criteria_sha256'],evaluation_role='development',
        validation_used_for_tuning=True,independent_validation_completed=False,new_human_signature_created=False,
        original_annotation_preserved=True,inference_completed=False,cases=30,papers=10,
        original_files_sha256={name:sha((source/name).read_bytes()) for name in names})
    # Draft binding can change with candidate edits; released packets are immutable.
    if (root/'docs/atomic-verifier-cellfix14-release.json').exists():
        write_once(dest/'binding.json',json_bytes(record));write_once(dest/'binding_gate.py',Path(__file__).read_bytes())
    else:
        dest.mkdir(parents=True,exist_ok=True)
        (dest/'binding.json').write_bytes(json_bytes(record));(dest/'binding_gate.py').write_bytes(Path(__file__).read_bytes())
    verify(dest,candidate['criteria_sha256']);return dest
