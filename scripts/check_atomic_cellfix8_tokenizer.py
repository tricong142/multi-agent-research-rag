"""Exercise the pinned Qwen token filter; no weights or new predictions."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'research-runs/atomic-cellfix8-candidate/workspace'
sys.path.insert(0,str(SOURCE))


def main():
    started=time.perf_counter()
    print('Loading pinned tokenizer and building vocabulary tree; no weights.',flush=True)
    from research_rag.evaluation import evaluate_atomic_verifier as r
    from research_rag.tests.test_atomic_smoke_cellfix3 import scoped,request
    from research_rag.tests.test_atomic_verifier import assessment,observation,numeric,operand
    from research_rag.tests.test_atomic_assessment_cellfix7 import LedgerTests
    from research_rag.tests import test_atomic_assessment_v8 as h
    from research_rag.tests.test_atomic_decoding import Sequence
    from transformers import AutoTokenizer
    criteria,_,_,_,_,baseline,_=r.load_frozen(r.CRITERIA)
    folder=SOURCE/'04_factchecker/checkpoints/factchecker_merged'
    for name,expected in baseline['model_metadata']['shared_tokenizer_files'].items():
        assert r.sha256(folder/name)==expected
    tokenizer=AutoTokenizer.from_pretrained(folder,local_files_only=True)
    backend=r.decoding.ConstrainedAtomicBackend(None,tokenizer)
    paths=[]
    claim,p,ctx,raw=LedgerTests().sample()
    paths.append(('keyed_two_sentence_counts',claim,p,ctx,raw,True))
    bad=deepcopy(raw);bad['observations'][0]['numeric']['q1']=bad['observations'][0]['numeric']['q0']
    paths.append(('duplicated_requirement',claim,p,ctx,bad,False))
    bad=deepcopy(raw);bad['observations'][0]['numeric'].pop('q1')
    paths.append(('missing_requirement',claim,p,ctx,bad,False))
    claim='The audit used handwritten forms.';ctx='The audit did not use any handwritten forms.'
    p=scoped(claim,'audit','used handwritten forms');raw=assessment([observation('audit','false',ctx)])
    paths.append(('explicit_denial',claim,p,ctx,raw,True))
    bad=deepcopy(raw);bad['scope_match']='mismatched'
    paths.append(('counterevidence_as_scope_mismatch',claim,p,ctx,bad,False))
    bad=deepcopy(raw);bad['observations'][0]['truth']='unknown'
    paths.append(('counterevidence_as_unknown',claim,p,ctx,bad,False))
    ctx='The audit protocol was not reported.';raw=assessment([observation('audit','unknown',ctx)])
    paths.append(('genuine_missing_evidence',claim,p,ctx,raw,True))
    claim='All channels improved after calibration.'
    ctx='Two channels improved after calibration, but a third channel worsened.'
    p=scoped(claim,'channels','improved',quantifier='all',time='after calibration')
    raw=assessment([observation('a third channel','false',ctx)])
    paths.append(('single_counterexample',claim,p,ctx,raw,True))
    claim='The update increased precision.';ctx='Precision rose from 0.71 before the update to 0.88 afterward.'
    p=scoped(claim,'update','precision')
    raw=assessment([observation('update','true',ctx,numeric('change',ctx,operand('0.71'),operand('0.88')))])
    paths.append(('old_ordered_change_preserved',claim,p,ctx,raw,True))
    bad=deepcopy(raw);bad['observations'][0]['numeric'].update(left=operand('0.88'),right=operand('0.71'))
    paths.append(('reversed_change_rejected',claim,p,ctx,bad,False))
    claim='On the Falcon corpus, the parser reduced latency.'
    ctx='The parser reduced latency on the Falcon corpus. Results on other corpora are unknown.'
    p=scoped(claim,'parser','latency',condition='On the Falcon corpus')
    raw=assessment([observation('parser','true','The parser reduced latency on the Falcon corpus.')])
    paths.append(('scoped_support_without_other_corpora',claim,p,ctx,raw,True))
    bad=deepcopy(raw);bad['missing_information']=['Results on other corpora.']
    paths.append(('irrelevant_missing_information_rejected',claim,p,ctx,bad,False))
    boundary=deepcopy(raw);boundary['observations'][0]['explanation']='x'*64;boundary['explanation']='x'*64
    paths.append(('both_explanation_boundaries_close_at_64',claim,p,ctx,boundary,True))
    bad=deepcopy(boundary);bad['observations'][0]['explanation']+='x'
    paths.append(('explanation_65_rejected',claim,p,ctx,bad,False))
    results=[]
    for name,claim,p,ctx,raw,expected in paths:
        path_started=time.perf_counter()
        print('Checking '+name,flush=True)
        callback=backend.generation_options(request(claim,p,ctx))['prefix_allowed_tokens_fn']
        text=json.dumps(json.loads(h.AssessmentTokenFilterTests().ordered(raw)),separators=(',',':'))
        ids=Sequence([tokenizer.eos_token_id]);accepted=True
        for token in tokenizer.encode(text,add_special_tokens=False):
            if token in callback(0,ids):ids.append(token);continue
            for char in tokenizer.decode([token]):
                pieces=tokenizer.encode(char,add_special_tokens=False)
                assert len(pieces)==1 and tokenizer.decode(pieces)==char
                if pieces[0] not in callback(0,ids):accepted=False;break
                ids.append(pieces[0])
            if not accepted:break
        if accepted:
            assert tokenizer.decode(ids[1:])==text
            accepted=tokenizer.eos_token_id in callback(0,ids)
        assert accepted==expected,(name,accepted,expected)
        if accepted:assert len(ids)<=criteria['max_new_tokens']
        results.append({'case':name,'accepted':accepted,'expected':expected,'legal_path_tokens':len(ids) if accepted else None,
            'elapsed_seconds':round(time.perf_counter()-path_started,3)})
    # Replay the canonical BPE path for the exact received malformed prefix.
    # No character fallback here: this specifically catches the old fast cache.
    from lmformatenforcer import TokenEnforcer, JsonSchemaParser, CharacterLevelParserConfig
    trace_path=SOURCE/'research_rag/tests/fixtures/atomic_cellfix7_smoke_traces.json'
    sample=next(v for v in json.loads(trace_path.read_bytes()) if v['case']['example_id']=='contract:both_supported')
    trace=sample['result']['trace'][1];payload=json.loads(trace['messages'][1]['content'])
    msg=request(payload['claim'],payload['part'],payload['context'])
    schema,_=r.decoding.schema_for(msg)
    config=CharacterLevelParserConfig();config.force_json_field_order=True;config.max_consecutive_whitespaces=4
    config.alphabet+=''.join(sorted(set(payload['claim']+payload['context'])-set(config.alphabet)))
    old=TokenEnforcer(backend.tokenizer_data,JsonSchemaParser(schema,config=config));old.root_parser.config=config
    ids=Sequence([tokenizer.eos_token_id])
    encoded=tokenizer.encode(trace['raw_output'],add_special_tokens=False)
    for token in encoded:
        assert token in old.get_allowed_tokens(ids).allowed_tokens
        ids.append(token)
    assert tokenizer.eos_token_id in old.get_allowed_tokens(ids).allowed_tokens
    callback=backend.generation_options(msg)['prefix_allowed_tokens_fn']
    ids=Sequence([tokenizer.eos_token_id]);rejected_at=None
    for index,token in enumerate(encoded):
        allowed=callback(0,ids)
        assert tokenizer.eos_token_id not in allowed,'EOS before a complete JSON object'
        if token not in allowed:rejected_at=index;break
        ids.append(token)
    assert rejected_at is not None,'Malformed prefix must not reach EOS'
    prefix_check={'old_parser_allows_eos_on_malformed_prefix':True,
        'new_parser_rejects_prefix':True,'rejected_at_bpe_token':rejected_at,
        'prefix_bpe_tokens':len(encoded),'original_model_generated_tokens':111,
        'no_character_fallback_used':True}
    output={'candidate':criteria['policy'],'criteria_sha256':r.sha256(r.CRITERIA),
        'kind':'real_pinned_tokenizer_handcrafted_path_check','checks':results,
        'exact_malformed_prefix_replay':prefix_check,'elapsed_seconds':round(time.perf_counter()-started,3),
        'weights_loaded':False,'model_inference_completed':False}
    (ROOT/'docs/atomic-verifier-cellfix8-tokenizer-check.json').write_text(json.dumps(output,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(output))


if __name__=='__main__':main()
