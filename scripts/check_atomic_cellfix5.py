"""Diagnostic replay and real-tokenizer feasibility; never run model inference."""
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'research-runs/atomic-cellfix5-frozen/workspace'
PARENT = ROOT/'research-runs/audit-cellfix4-fresh-20261017T111605Z-9505cc47'
sys.path.insert(0, str(SOURCE))

from research_rag.evaluation import evaluate_atomic_verifier as runner
from research_rag.tests.test_atomic_decomposition_v5 import plan
from research_rag.tests.test_atomic_decoding import Sequence, messages
from research_rag.tests.test_atomic_metric_cellfix5 import NOVEL


def main():
    assert Path(runner.__file__).resolve().is_relative_to(SOURCE)
    criteria, *_ = runner.load_frozen(runner.CRITERIA)
    atomic = importlib.import_module('04_factchecker.inference.atomic_verifier')
    decoder = importlib.import_module('04_factchecker.inference.atomic_decoding')
    parent = json.loads((PARENT/'workspace/research_rag/evaluation/atomic_verifier_criteria_v8.json').read_text())
    release = json.loads((ROOT/'docs/atomic-verifier-cellfix4-fresh-colab-release.json').read_text())
    for name, digest in release['files'].items():
        assert runner.sha256(ROOT/name) == digest, name
    for name, item in release['payload_files'].items():
        assert runner.sha256(PARENT/'workspace'/name) == item['sha256'], name

    # Replay original records against the new validation functions, with their
    # ORIGINAL policy/budget metadata. Never relabel them as new candidate runs.
    probe = PARENT/'artifact/decomposition-probe'
    cases = {r['example_id']: r for r in json.loads((probe/'cases.json').read_text())}
    effective = {**parent, **parent['decomposition_probe']}
    expected_bad = {'decompose:010','decompose:014','decompose:018'}
    replay = []
    paths = []
    for line in (probe/'predictions.jsonl').read_text().splitlines():
        row = json.loads(line)
        claim = cases[row['example_id']]['claim']
        event = next(e for e in reversed(row['result']['trace']) if e.get('valid'))
        try:
            runner.replay_result(row['result'], claim, '', effective)
        except ValueError as exc:
            assert row['example_id'] in expected_bad and str(exc) == 'metric_property_not_canonical', (row['example_id'], str(exc))
            verdict = str(exc)
        else:
            assert row['example_id'] not in expected_bad
            verdict = 'unchanged_valid'
        replay.append({'example_id':row['example_id'],'new_validation_of_old_trace':verdict})
        paths.append((row['example_id']+'/original', claim, event['output'], row['example_id'] not in expected_bad))
    assert len(replay) == 18

    smoke = PARENT/'artifact/assessment-smoke'
    smoke_cases = {r['example_id']:r for r in json.loads((smoke/'cases.json').read_text())}
    effective = {**parent,'cases_per_backend':12}
    smoke_replay = []
    for line in (smoke/'predictions.jsonl').read_text().splitlines():
        row = json.loads(line)
        case = smoke_cases[row['example_id']]
        label = runner.replay_result(row['result'],case['claim'],case['context'],effective)
        assert label == row['result']['assessed_label']
        smoke_replay.append({'example_id':row['example_id'],'original_label_unchanged':True})
    assert len(smoke_replay) == 12

    # These are handcrafted legal alternatives, not generated predictions.
    fixture = SOURCE/'research_rag/tests/fixtures/atomic_cellfix4_metric_traces.json'
    for row in json.loads(fixture.read_text()):
        raw = deepcopy(row['output'])
        raw['parts'][0]['scope']['metric'] = row['expected_metric']
        paths.append((row['example_id']+'/synthetic_canonical_alternative',row['claim'],raw,True))
    for index,(claim,entity,metric,time,condition,quantifier) in enumerate(NOVEL):
        raw=plan(claim,entity=entity,metric=metric,time=time,condition=condition,quantifier=quantifier)
        paths.append((f'novel:{index}/canonical',claim,raw,True))
        bad=deepcopy(raw);bad['parts'][0]['scope']['metric']=metric.split()[-1]
        if bad != raw:
            paths.append((f'novel:{index}/dropped_modifier',claim,bad,False))
    for claim,entity,metric,condition in (
            ('Compilation took seven minutes.','Compilation','took seven minutes',''),
            ('The audit evaluated six systems on three datasets.','audit','evaluated six systems','on three datasets')):
        paths.append((metric,claim,plan(claim,entity=entity,metric=metric,condition=condition),True))

    from transformers import AutoTokenizer
    import torch
    baseline=json.loads((runner.CRITERIA.parent/criteria['baseline_file']).read_text())
    folder=ROOT/'04_factchecker/checkpoints/factchecker_merged'
    hashes=baseline['model_metadata']['shared_tokenizer_files']
    for name,digest in hashes.items():
        assert runner.sha256(folder/name)==digest,name
    tokenizer=AutoTokenizer.from_pretrained(folder,local_files_only=True)
    backend=decoder.ConstrainedAtomicBackend(None,tokenizer)
    checks=[]
    for name,claim,raw,expected in paths:
        callback=backend.generation_options(messages(claim))['prefix_allowed_tokens_fn']
        ids=Sequence([tokenizer.eos_token_id])
        splits=[]
        text=json.dumps(raw,separators=(',',':'))
        allowed_path=True
        for token in tokenizer.encode(text,add_special_tokens=False):
            if token in callback(0,ids):
                ids.append(token)
                continue
            # As in the existing v8 check, free text punctuation may need a
            # different legal tokenization. The decoded JSON must stay identical.
            piece=tokenizer.decode([token]);splits.append(piece)
            for char in piece:
                encoded=tokenizer.encode(char,add_special_tokens=False)
                assert len(encoded)==1 and tokenizer.decode(encoded)==char
                if encoded[0] not in callback(0,ids):
                    allowed_path=False
                    break
                ids.append(encoded[0])
            if not allowed_path:
                break
        if allowed_path:
            assert tokenizer.decode(ids[1:])==text
            allowed_path=tokenizer.eos_token_id in callback(0,ids)
        assert allowed_path is expected,(name,expected)
        if allowed_path:
            assert len(ids)<=criteria['max_new_tokens']
        checks.append({'case':name,'accepted':allowed_path,'expected_accepted':expected,
            'legal_path_tokens_including_eos':len(ids) if allowed_path else None,
            'split_pieces':splits})

    result={'kind':'offline_diagnostic_replay_and_real_tokenizer_feasibility',
        'model_inference_completed':False,'full39_inference_started':False,
        'criteria_sha256':runner.sha256(runner.CRITERIA),
        'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'original_cellfix4_release_preserved':True,'old_probe_trace_checks':replay,
        'old_smoke_trace_checks':smoke_replay,'real_qwen_tokenizer_checks':checks,
        'shared_tokenizer_files':hashes,'torch_version':torch.__version__,
        'cuda_available':torch.cuda.is_available(),
        'note':'Old traces retain their original policy and results. Canonical alternatives and novel fixtures are handcrafted. These checks do not measure new model accuracy, false support or human review.'}
    out=ROOT/'docs/atomic-verifier-cellfix5-offline-check.json'
    out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'output':str(out),'old_probe':len(replay),'old_smoke':len(smoke_replay),
        'tokenizer_checks':len(checks),'cuda_available':result['cuda_available']}))


if __name__=='__main__':
    main()
