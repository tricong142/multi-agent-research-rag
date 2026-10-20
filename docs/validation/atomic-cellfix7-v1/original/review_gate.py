"""Offline integrity/admission for a human-reviewed validation packet; no inference."""
import argparse
from datetime import date
import hashlib
import json
from pathlib import Path, PurePosixPath

CHECKS = ('gold_label', 'exact_evidence', 'missing_information', 'identity_metric_quantity', 'scope_population_relation')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def write_once(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f'Immutable artifact differs; use a new version: {path}')
    else:
        with path.open('xb') as stream:
            stream.write(data)


def packet(folder):
    folder = Path(folder)
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    for name, item in manifest['files'].items():
        rel = PurePosixPath(name)
        if rel.is_absolute() or '..' in rel.parts or '\\' in name or ':' in name:
            raise ValueError('Unsafe packet path')
        data = (folder / name).read_bytes()
        if len(data) != item['size'] or digest(data) != item['sha256']:
            raise ValueError(f'Packet hash mismatch: {name}')
    rows = [json.loads(line) for line in (folder / 'cases.jsonl').read_text(encoding='utf-8').splitlines()]
    if len(rows) != manifest['cases'] or len({r['id'] for r in rows}) != len(rows):
        raise ValueError('Case count/identity mismatch')
    for row in rows:
        if row['proposed_gold'] not in ('support', 'contradict', 'not_enough_info'):
            raise ValueError('Invalid proposed label')
        for span in row['evidence']:
            if row['context'][span['start']:span['end']] != span['quote']:
                raise ValueError('Evidence is not verbatim')
        if row['proposed_gold'] == 'not_enough_info' and not row['missing_information'].strip():
            raise ValueError('NEI needs explicit missing information')
    return manifest, rows


def admit(folder, review):
    folder = Path(folder)
    manifest, rows = packet(folder)
    expected = digest((folder / 'manifest.json').read_bytes())
    if review.get('manifest_sha256') != expected or review.get('candidate_criteria_sha256') != manifest['candidate_criteria_sha256']:
        raise ValueError('Review is bound to a different packet/candidate')
    if review.get('review_type') != 'human' or review.get('human_attestation') is not True:
        raise ValueError('Direct human review is required; AI review is not a human signature')
    if not isinstance(review.get('reviewer'), str) or not review['reviewer'].strip():
        raise ValueError('Reviewer name is required')
    date.fromisoformat(review.get('reviewed_on', ''))
    for flag in ('provenance_limits_acknowledged', 'no_candidate_outcomes_seen', 'protocol_accepted'):
        if review.get(flag) is not True:
            raise ValueError(f'Missing review declaration: {flag}')
    decisions = review.get('decisions')
    if not isinstance(decisions, list) or len(decisions) != len(rows):
        raise ValueError('Every case must have one review')
    by_id = {r.get('id'): r for r in decisions}
    if set(by_id) != {r['id'] for r in rows} or len(by_id) != len(decisions):
        raise ValueError('Duplicate/missing/unexpected review case')
    for row in rows:
        decision = by_id[row['id']]
        if decision.get('accepted_label') != row['proposed_gold']:
            raise ValueError('Annotation change requires a new packet version before inference')
        if decision.get('checks') != {name: True for name in CHECKS}:
            raise ValueError(f'Incomplete or rejected criteria: {row["id"]}')
        if not isinstance(decision.get('note'), str) or not decision['note'].strip():
            raise ValueError(f'Human note missing: {row["id"]}')
    overlap = json.loads((folder / 'overlap-report.json').read_text(encoding='utf-8'))
    if overlap['flags'] or overlap['document_overlap']:
        raise ValueError('Unresolved overlap requires a revised packet, not a checkbox override')
    return {'version': manifest['version'], 'status': 'locked_after_human_annotation',
            'manifest_sha256': expected, 'candidate_criteria_sha256': manifest['candidate_criteria_sha256'],
            'reviewer': review['reviewer'].strip(), 'reviewed_on': review['reviewed_on'],
            'cases': len(rows), 'papers': manifest['papers'], 'inference_completed': False,
            'scope': 'Verifier pilot on supplied paragraphs; not unseen pretraining data or pipeline E2E',
            'signature_kind': 'self-attested human review; not cryptographic identity verification'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet', type=Path, required=True)
    parser.add_argument('--review', type=Path)
    parser.add_argument('--lock', type=Path)
    args = parser.parse_args()
    manifest, rows = packet(args.packet)
    if args.review:
        raw = args.review.read_bytes()
        result = admit(args.packet, json.loads(raw))
        result['review_sha256'] = digest(raw)
        if args.lock:
            write_once(args.lock, json_bytes(result))
    elif args.lock:
        raise ValueError('Cannot lock without human review')
    else:
        result = {'integrity_valid': True, 'cases': len(rows), 'human_review': 'pending',
                  'candidate_criteria_sha256': manifest['candidate_criteria_sha256']}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
