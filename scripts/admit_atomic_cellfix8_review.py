"""Admit the user's exported human review against the preserved cf8 probe."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from scripts.atomic_validation_review import json_bytes,write_once

RUN='20261020T061934Z-c87bce57'
BASE=REPO/'research-runs'/('audit-cellfix8-fresh-'+RUN)
PACK=REPO/'docs/reviews'/('cellfix8-'+RUN)
SOURCE=BASE/'workspace'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    original=REPO.parent/'semantic-review (1).json'
    raw=original.read_bytes();review=json.loads(raw)
    release=json.loads((REPO/'docs/atomic-verifier-cellfix8-release.json').read_bytes())
    for name,item in release['payload_files'].items():
        assert sha(SOURCE/name)==item['sha256'],name
    for name,digest in release['files'].items():assert sha(REPO/name)==digest,name
    probe=BASE/'artifact/decomposition-probe'
    before={p.relative_to(probe).as_posix():sha(p) for p in probe.rglob('*') if p.is_file()}
    assert review['run_id']==RUN and review['candidate']==release['candidate']
    assert review['criteria_sha256']==release['criteria_sha256']
    assert review['predictions_sha256']==sha(probe/'predictions.jsonl')
    assert review['reviewer_kind']=='human' and review['review_completed'] is True
    assert review['human_review_completed'] is True
    assert isinstance(review['reviewer'],str) and review['reviewer'].strip()
    assert review['ai_review_sha256']==sha(PACK/'semantic-review.json')
    cases=json.loads((probe/'cases.json').read_bytes())
    predictions=[json.loads(s) for s in (probe/'predictions.jsonl').read_bytes().splitlines()]
    rubric=json.loads((probe/'criteria.json').read_bytes())['decomposition_probe']['human_review_rubric']
    items=review['cases'];assert len(items)==18 and len({r['example_id'] for r in items})==18
    indexed={r['example_id']:r for r in items}
    assert set(indexed)=={c['example_id'] for c in cases}
    for case,prediction in zip(cases,predictions):
        item=indexed[case['example_id']]
        assert item['claim']==case['claim']
        assert item['decomposition']==prediction['result']['decomposition']
        assert set(item['judgments'])==set(rubric)
        assert all(v is True for v in item['judgments'].values())
        assert isinstance(item['notes'],str) and item['notes'].strip()
    human=PACK/'human'
    write_once(human/'semantic-review.json',raw)
    admitted=BASE/'reviewed-probe-human'
    if not admitted.exists():shutil.copytree(probe,admitted)
    for name,digest in before.items():
        if name!='semantic-review.json':assert sha(admitted/name)==digest,name
    target=admitted/'semantic-review.json'
    if target.read_bytes()!=(probe/'semantic-review.json').read_bytes():
        assert target.read_bytes()==raw,'Preserve the previously admitted review'
    target.write_bytes(raw)
    sys.path.insert(0,str(SOURCE))
    spec=importlib.util.spec_from_file_location('human_admission_workflow',SOURCE/'atomic_workflow_cellfix8.py')
    w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
    admission=w.r.require_probe_review(admitted)
    assert admission['reviewer']==review['reviewer']
    assert admission['semantic_review_sha256']==hashlib.sha256(raw).hexdigest()
    assert before=={p.relative_to(probe).as_posix():sha(p) for p in probe.rglob('*') if p.is_file()}
    assert json.loads((probe/'semantic-review.json').read_bytes())['review_completed'] is False
    cell=(PACK/'RUN_FULL39_AFTER_HUMAN_REVIEW.py').read_text(encoding='utf-8')
    marker="        assert len(uploaded)==1,'Upload exactly the new probe semantic-review.json.'"
    assert cell.count(marker)==1
    # Reject a wrong upload before creating reviewed-probe in the Colab output.
    guard="\n        assert hashlib.sha256(next(iter(uploaded.values()))).hexdigest()=="+repr(sha(human/'semantic-review.json'))+", 'Upload the exact human review already audited; filename suffix (1) is allowed.'"
    cell=cell.replace(marker,marker+guard,1)
    compile(cell,'RUN_FULL39_ADMITTED','exec')
    write_once(human/'RUN_FULL39.py',cell.encode('utf-8'))
    report={'run_id':RUN,'candidate':release['candidate'],'reviewer':review['reviewer'],
        'reviewer_kind':'human','reviewed_on':review['reviewed_on'],'claims':18,'parts':20,
        'accepted_criteria':90,'human_review_completed':True,'file_preserved_byte_for_byte':True,
        'input_filename':original.name,'input_sha256':hashlib.sha256(raw).hexdigest(),
        'criteria_sha256':release['criteria_sha256'],'predictions_sha256':review['predictions_sha256'],
        'ai_review_reference_verified':True,'admission_passed':True,'admission':admission,
        'original_unsigned_artifacts_unchanged':True,'frozen_release_unchanged':True,
        'full39_ready_for_audited_colab_session':True,'full39_executed':False,
        'full39_accuracy_measured':False,'full39_false_support_measured':False,
        'validation30_executed':False,'serving_promoted':False,
        'handoff_cell_sha256':sha(human/'RUN_FULL39.py')}
    write_once(human/'admission.json',json_bytes(report))
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
