"""Real pinned Qwen tokenizer feasibility. Never load weights or generate labels."""
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'research-runs/atomic-cellfix6-candidate/workspace'
sys.path.insert(0,str(SOURCE))


def main():
    from research_rag.evaluation import evaluate_atomic_verifier as r
    from research_rag.tests.test_atomic_smoke_cellfix3 import scoped,request
    from research_rag.tests.test_atomic_verifier import assessment,observation,numeric,operand
    from research_rag.tests.test_atomic_assessment_v8 import AssessmentTokenFilterTests
    from research_rag.tests.test_atomic_decoding import Sequence
    from transformers import AutoTokenizer
    criteria,_,_,_,_,baseline,_=r.load_frozen(r.CRITERIA)
    folder=ROOT/'04_factchecker/checkpoints/factchecker_merged'
    hashes=baseline['model_metadata']['shared_tokenizer_files']
    for name,digest in hashes.items():assert r.sha256(folder/name)==digest,name
    tokenizer=AutoTokenizer.from_pretrained(folder,local_files_only=True)
    backend=r.decoding.ConstrainedAtomicBackend(None,tokenizer)
    paths=[]
    claim='The update increased precision.'
    ctx='Precision rose from 0.71 before the update to 0.88 afterward.'
    part=scoped(claim,'update','precision')
    raw=assessment([observation('update','true',ctx,numeric('change',ctx,operand('0.71'),operand('0.88')))])
    paths.append(('dimensionless_afterward',claim,part,ctx,raw,True))
    bad=deepcopy(raw);bad['observations'][0]['numeric'].update(left=operand('0.88'),right=operand('0.71'))
    paths.append(('reversed_pair',claim,part,ctx,bad,False))
    bad=deepcopy(raw);bad['observations'][0]['numeric']=None
    paths.append(('required_numeric_missing',claim,part,ctx,bad,False))
    claim='The update reduced mean packet latency.'
    ctx='For the same packets and conditions, mean latency was 63 ms before the update and 47 ms after it.'
    part=scoped(claim,'update','mean packet latency')
    raw=assessment([observation('update','true',ctx,numeric('change',ctx,operand('63','ms'),operand('47','ms')))])
    paths.append(('source_modifier_binding',claim,part,ctx,raw,True))
    claim='The relay failed.';ctx='The relay status was not reported.';part=scoped(claim,'relay','failed')
    for truth in ('unknown','false'):
        raw=assessment([observation('relay',truth,ctx)])
        paths.append(('missing_'+truth,claim,part,ctx,raw,truth=='unknown'))
    claim='Every valve remained open.'
    ctx='The entire valve fleet was Iris and Oak. Iris remained open. Oak remained open.'
    part=scoped(claim,'valve','remained open',quantifier='all')
    raw=assessment([observation(m,'true',ctx) for m in ('Iris','Oak')],complete=True)
    paths.append(('closed_population',claim,part,ctx,raw,True))
    results=[]
    for name,claim,part,ctx,raw,expected in paths:
        callback=backend.generation_options(request(claim,part,ctx))['prefix_allowed_tokens_fn']
        text=AssessmentTokenFilterTests().ordered(raw)
        text=json.dumps(json.loads(text),separators=(',',':'))
        ids=Sequence([tokenizer.eos_token_id]);accepted=True;split=[]
        for token in tokenizer.encode(text,add_special_tokens=False):
            if token in callback(0,ids):ids.append(token);continue
            piece=tokenizer.decode([token]);split.append(piece)
            for char in piece:
                tokens=tokenizer.encode(char,add_special_tokens=False)
                assert len(tokens)==1 and tokenizer.decode(tokens)==char
                if tokens[0] not in callback(0,ids):accepted=False;break
                ids.append(tokens[0])
            if not accepted:break
        if accepted:
            assert tokenizer.decode(ids[1:])==text
            accepted=tokenizer.eos_token_id in callback(0,ids)
        assert accepted==expected,(name,accepted,expected)
        if accepted:assert len(ids)<=criteria['max_new_tokens']
        results.append({'case':name,'accepted':accepted,'expected':expected,
            'legal_path_tokens_including_eos':len(ids) if accepted else None,'split_pieces':split})
    output={'kind':'handcrafted_output_tokenizer_feasibility','candidate':criteria['policy'],
        'criteria_sha256':r.sha256(r.CRITERIA),'tokenizer_hashes':hashes,'checks':results,
        'weights_loaded':False,'model_inference_completed':False}
    path=ROOT/'docs/atomic-verifier-cellfix6-tokenizer-check.json'
    path.write_text(json.dumps(output,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checks':len(results),'accepted':sum(x['accepted'] for x in results),'model_inference_completed':False}))


if __name__=='__main__':main()
