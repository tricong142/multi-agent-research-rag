"""Bound human review, full39 admission and independent validation30 runner."""
from collections import Counter
import argparse
import html
import importlib.util
import json
from pathlib import Path
import sys
import time

from research_rag.evaluation import evaluate_atomic_verifier as r


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def rows(path):
    return [json.loads(s) for s in Path(path).read_text(encoding='utf-8').splitlines()]


def binding(folder):
    spec=importlib.util.spec_from_file_location('cf10_binding_gate',Path(folder)/'binding_gate.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.verify(folder,r.sha256(r.CRITERIA))


def require_human_review(directory, cases, rubric):
    directory=Path(directory)
    review=read(directory/'semantic-review.json')
    if (review.get('criteria_sha256')!=r.sha256(r.CRITERIA)
            or review.get('predictions_sha256')!=r.sha256(directory/'predictions.jsonl')
            or review.get('reviewer_kind')!='human' or review.get('review_completed') is not True
            or not isinstance(review.get('reviewer'),str) or not review['reviewer'].strip()):
        raise ValueError('Completed human review bound to this candidate and predictions is required')
    items=review.get('cases',[])
    if len(items)!=len(cases) or len({v['example_id'] for v in items})!=len(cases) or {v['example_id'] for v in items}!={c['example_id'] for c in cases}:
        raise ValueError('Human review must cover every case once')
    for item in items:
        if (set(item.get('judgments',{}))!=set(rubric) or any(v is not True for v in item['judgments'].values())
                or not isinstance(item.get('notes'),str) or not item['notes'].strip()):
            raise ValueError('All semantic criteria and notes are required')
    return {'reviewer':review['reviewer'],'semantic_review_sha256':r.sha256(directory/'semantic-review.json')}


def measured_score(outputs, cases, criteria, events):
    score=r.score(outputs,cases,criteria)
    generations=[e for e in events if e['event']=='generation']
    starts=[e for e in events if e['event']=='call_started']
    finishes=[e for e in events if e['event']=='call_finished']
    traces=[t for row in outputs for t in row['result']['trace']]
    trace_ids=[row['example_id'] for row in outputs for t in row['result']['trace']]
    if not len(starts)==len(finishes)==len(traces)==score['backend_calls']:
        raise ValueError('Incomplete call trace')
    indexed={g['call_id']:g for g in generations}
    if len(indexed)!=len(generations) or not set(indexed)<=set(range(1,len(traces)+1)):
        raise ValueError('Duplicate/unknown generation event')
    for i,(start,finish,trace) in enumerate(zip(starts,finishes,traces),1):
        if (start['call_id']!=i or finish['call_id']!=i
                or start['example_id']!=trace_ids[i-1] or finish['example_id']!=trace_ids[i-1]
                or start['messages']!=trace['messages'] or finish['messages']!=trace['messages']):
            raise ValueError('Call trace disagrees with predictions')
        gen=indexed.get(i)
        if gen is not None:
            if gen['example_id']!=trace_ids[i-1]:raise ValueError('Generation belongs to another case')
            if 'output' in trace:
                if json.loads(gen['raw_output'])!=trace['output'] or finish.get('parsed_output')!=trace['output']:
                    raise ValueError('Parsed generation differs from prediction')
            elif gen['raw_output']!=trace.get('raw_output') or gen['json_valid'] is not False:
                raise ValueError('Invalid generation raw text was not preserved')
    score['generated_tokens']=sum(g['generated_tokens'] for g in generations)
    score['prompt_tokens']=sum(g['prompt_tokens'] for g in generations)
    score['checks']['within_measured_token_budget']=(len(generations)==len(traces) and score['generated_tokens']<=criteria['maximum_generated_tokens']
        and all(g['generated_tokens']<=criteria['max_new_tokens'] for g in generations))
    score['checks']['structured_decoding_trace_complete']=r.decoding_trace_complete(generations,[t['messages'] for t in traces],criteria)
    score['checks']['cooperative_deadline_trace_complete']=all(t.get('cooperative_deadline') is True for t in traces)
    score['automated_gate_pass']=all(score['checks'].values())
    return score


def require_full39(directory, probe):
    directory=Path(directory)
    criteria,cases,_,_,_,baseline,_=r.load_frozen(r.CRITERIA)
    summary=read(directory/'summary.json')
    if summary.get('experiment_completed') is not True or summary.get('automated_gate_pass') is not True or summary.get('prediction_count')!=39:
        raise ValueError('Successful full39 is required before validation30')
    r.require_probe_review(Path(probe))
    if (directory/'criteria.json').read_bytes()!=r.CRITERIA.read_bytes():
        raise ValueError('Full39 criteria changed')
    if read(directory/'cases.json')!=cases:
        raise ValueError('Full39 review cases differ from frozen data')
    provenance=read(directory/'provenance.json')
    model=provenance.get('model') or {}
    pairing=('model_files','shared_tokenizer_files','repo_id','revision','dtype','quantization','seed','do_sample')
    if (provenance['criteria_sha256']!=r.sha256(r.CRITERIA) or provenance['source_sha256']!=criteria['source_sha256']
            or provenance['prompt_sha256']!=criteria['prompt_sha256']
            or any(model.get(k)!=baseline['model_metadata'].get(k) for k in pairing)
            or model.get('max_new_tokens')!=criteria['max_new_tokens'] or model.get('structured_decoder')!=criteria['structured_decoder']):
        raise ValueError('Full39 provenance changed')
    score=measured_score(rows(directory/'predictions.jsonl'),cases,criteria,rows(directory/'calls.jsonl'))
    if score!=read(directory/'metrics.json') or not score['automated_gate_pass']:
        raise ValueError('Full39 gate failed on replay')
    review=require_human_review(directory,cases,criteria['human_review_rubric'])
    return {**review,'full39_predictions_sha256':r.sha256(directory/'predictions.jsonl')}


def make_review(directory, mode):
    directory=Path(directory)
    criteria,all_cases,*_=r.load_frozen(r.CRITERIA)
    rubric=(r.probe_configuration(criteria,all_cases,r.CRITERIA)[0] if mode=='probe' else criteria)['human_review_rubric']
    cases=read(directory/'cases.json');outputs=rows(directory/'predictions.jsonl')
    template={'criteria_sha256':r.sha256(r.CRITERIA),'predictions_sha256':r.sha256(directory/'predictions.jsonl'),
        'reviewer':'','reviewer_kind':'human','review_completed':False,
        'cases':[{'example_id':c['example_id'],'claim':c['claim'],'judgments':dict.fromkeys(rubric),'notes':''} for c in cases]}
    target=directory/'semantic-review.json'
    if not target.exists():r.write_json(target,template)
    cards=[]
    labels={'factual_predicates_not_fragments':'Part là factual predicate đầy đủ',
        'all_requirements_preserved':'Giữ đủ yêu cầu, số liệu, đơn vị và quan hệ',
        'quantifier_preserved':'Đúng lượng từ và population',
        'entity_metric_binding_correct':'Đúng chủ thể và metric',
        'time_condition_scope_correct':'Đúng scope thời gian và điều kiện',
        'label_correct':'Nhãn đúng theo evidence', 'quote_relevant':'Trích dẫn liên quan và đúng scope',
        'explanation_follows_evidence':'Giải thích đi theo evidence, không suy diễn',
        'all_claim_parts_checked':'Đã kiểm đủ mọi part và quantity',
        'missing_information_specific':'Thông tin còn thiếu được nêu cụ thể và đúng'}
    for case,row in zip(cases,outputs):
        fields=''.join('<label><input type="checkbox" data-key="'+html.escape(k)+'"> '+html.escape(labels.get(k,k))+'</label><br>' for k in rubric)
        cards.append('<article data-id="'+html.escape(case['example_id'])+'"><h2>'+html.escape(case['example_id'])+'</h2><h3>'+html.escape(case['claim'])
            +'</h3><pre>'+html.escape(case.get('context',''))+'</pre><details><summary>Prediction và evidence</summary><pre>'
            +html.escape(json.dumps({k:v for k,v in row['result'].items() if k!='trace'},ensure_ascii=False,indent=2))
            +'</pre></details>'+fields+'<textarea placeholder="Ghi chú bắt buộc"></textarea></article>')
    script='''const seed=SEED;document.querySelector('button').onclick=()=>{const data=JSON.parse(JSON.stringify(seed));data.reviewer=document.querySelector('#name').value.trim();data.review_completed=document.querySelector('#done').checked;data.cases=data.cases.map((row,i)=>{const card=document.querySelectorAll('article')[i];row.judgments=Object.fromEntries([...card.querySelectorAll('[data-key]')].map(x=>[x.dataset.key,x.checked]));row.notes=card.querySelector('textarea').value.trim();return row;});const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)+'\\n'],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='semantic-review.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};'''.replace('SEED',json.dumps(template,ensure_ascii=False).replace('<','\\u003c'))
    source='<!doctype html><meta charset="utf-8"><title>Human review '+mode+'</title><style>body{max-width:1000px;margin:30px auto;font:16px/1.6 system-ui}article{border:1px solid #bbb;padding:20px;margin:20px 0}pre{white-space:pre-wrap}textarea{width:95%;min-height:80px}</style><h1>Human review '+mode+'</h1><p>Đọc đủ claim/context/prediction. Xác nhận từng tiêu chí, ghi chú riêng. Chỉ tích khi thực sự đạt; file thiếu hoặc tiêu chí trượt sẽ bị chặn. Giải thích explanation được code dựng từ ledger đã kiểm; model_explanation và model_missing_information là output gốc để audit. Luôn đối chiếu ledger với source: lời giải thích nhất quán không tự chứng minh nhãn đúng. Kiểm population_binding_basis nếu dùng quy ước complete selection-set.</p><label>Tên reviewer <input id="name"></label><label><input id="done" type="checkbox"> Tôi đã trực tiếp review toàn bộ các ca.</label>'+''.join(cards)+'<button>Xuất semantic-review.json</button><script>'+script+'</script>'
    (directory/'HUMAN_REVIEW.html').write_text(source,encoding='utf-8')


def configuration(folder):
    spec=binding(folder)
    original=Path(folder)/'original'
    gold=rows(original/'cases.jsonl');blind=rows(original/'inputs.jsonl')
    if blind!=[{k:row[k] for k in ('id','claim','context')} for row in gold]:
        raise ValueError('Blind validation inputs disagree with reviewed cases')
    frozen,*_=r.load_frozen(r.CRITERIA)
    cases=[{'example_id':v['id'],'claim':v['claim'],'context':v['context'],'label':v['proposed_gold'],
            'dataset_group':v['group_id']} for v in gold]
    criteria={**frozen,'cases_per_backend':30,'min_correct_labels_recognized':30,
        'maximum_total_backend_calls':240,'maximum_generated_tokens':368640,
        'dataset_groups':dict(Counter(c['dataset_group'] for c in cases))}
    return spec,criteria,cases


def run_validation(output, probe, full39, folder, loader):
    spec,criteria,cases=configuration(folder)
    admission=require_full39(full39,probe)
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    r.write_json(output/'criteria.json',criteria);r.write_json(output/'cases.json',cases)
    r.write_json(output/'validation-binding.json',spec);r.write_json(output/'full39-admission.json',admission)
    started=time.perf_counter();outputs=[];counter=[0];stats=[]
    summary={'experiment_completed':False,'automated_gate_pass':False,'overall_pass':False,'human_review':'pending',
             'promoted_to_serving':False,'evaluation_mode':'independent_verifier_validation','status':'running'}
    r.write_summary(output/'summary.json',summary)
    _,_,_,_,_,baseline,_=r.load_frozen(r.CRITERIA)
    with loader('base_instruct',criteria) as (backend,metadata):
        keys=('model_files','shared_tokenizer_files','repo_id','revision','dtype','quantization','seed','do_sample')
        if (any(metadata.get(k)!=baseline['model_metadata'].get(k) for k in keys)
                or metadata.get('structured_decoder')!=criteria['structured_decoder']
                or metadata.get('max_new_tokens')!=criteria['max_new_tokens']):
            raise ValueError('Validation model/settings differ from frozen candidate')
        r.write_json(output/'provenance.json',{'criteria_sha256':r.sha256(r.CRITERIA),
            'source_sha256':criteria['source_sha256'],'prompt_sha256':criteria['prompt_sha256'],'model':metadata,
            'validation_binding_sha256':r.sha256(Path(folder)/'binding.json'),'serving_modified':False})
        with (output/'predictions.jsonl').open('x',encoding='utf-8') as predictions,(output/'calls.jsonl').open('x',encoding='utf-8') as calls:
            for case in cases:
                traced=r.RecordingBackend(backend,calls,case['example_id'],counter,240,stats)
                model=r.atomic.AtomicVerifier(traced,max_calls=criteria['max_calls_per_case'],max_attempts=criteria['max_attempts'],
                    max_new_tokens=criteria['max_new_tokens'],timeout_seconds=criteria['case_deadline_seconds'])
                result=model.verify(case['claim'],case['context'])
                r.replay_result(result,case['claim'],case['context'],criteria)
                row={'example_id':case['example_id'],'result':result};outputs.append(row)
                predictions.write(json.dumps(row,ensure_ascii=False)+'\n');predictions.flush()
                summary.update(prediction_count=len(outputs),backend_calls=counter[0],last_case_id=case['example_id'])
                r.write_summary(output/'summary.json',summary)
                print(json.dumps({'case':case['example_id'],'prediction':result['assessed_label'],'stop':result['stop_reason']}),flush=True)
    metrics=measured_score(outputs,cases,criteria,rows(output/'calls.jsonl'))
    per_label={}
    for label in r.LABELS:
        tp=sum(c['label']==label==row['result']['assessed_label'] for c,row in zip(cases,outputs))
        predicted=sum(row['result']['assessed_label']==label for row in outputs);actual=sum(c['label']==label for c in cases)
        per_label[label]={'precision':tp/predicted if predicted else None,'recall':tp/actual if actual else None,'gold_count':actual,'predicted_count':predicted}
    r.write_json(output/'metrics.json',metrics)
    r.write_json(output/'classification.json',{'per_label':per_label,'false_support':metrics['false_support'],
        'non_support_gold_count':sum(c['label']!='support' for c in cases),'per_paper':metrics['dataset_groups'],
        'latency_ms':[row['result']['elapsed_ms'] for row in outputs]})
    summary.update(experiment_completed=True,automated_gate_pass=metrics['automated_gate_pass'],
                   status='automated_pass_human_pending' if metrics['automated_gate_pass'] else 'automated_gates_failed',
                   elapsed_ms=round((time.perf_counter()-started)*1000,3))
    r.write_summary(output/'summary.json',summary)
    make_review(output,'validation')
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--make-review',type=Path);parser.add_argument('--review-mode',choices=['probe','full39','validation'])
    parser.add_argument('--output-dir',type=Path);parser.add_argument('--probe-dir',type=Path)
    parser.add_argument('--full39-dir',type=Path);parser.add_argument('--binding-dir',type=Path)
    parser.add_argument('--validate-only',action='store_true');parser.add_argument('--worker',action='store_true')
    parser.add_argument('--admit-full39',action='store_true')
    parser.add_argument('--online-model-downloads',action='store_true')
    args=parser.parse_args()
    if args.make_review:
        make_review(args.make_review,args.review_mode);return
    if args.admit_full39:
        print(json.dumps(require_full39(args.full39_dir,args.probe_dir)));return
    if not args.binding_dir:parser.error('--binding-dir required')
    configuration(args.binding_dir)
    if args.validate_only:
        print(json.dumps({'freeze_valid':True,'cases':30,'maximum_calls':240,'prerequisites_required_for_inference':True}));return
    if not args.output_dir or not args.probe_dir or not args.full39_dir:parser.error('Output, probe and full39 directories required')
    require_full39(args.full39_dir,args.probe_dir)
    if args.output_dir.exists():raise ValueError('Preserve previous results and use a new output directory')
    if not args.worker:
        from research_rag.local import run_worker
        code=run_worker([sys.executable,'-u',str(Path(__file__).resolve()),*sys.argv[1:],'--worker'],5400)
        if code==124 and args.output_dir.exists():
            summary=read(args.output_dir/'summary.json')
            summary.update(experiment_completed=False,automated_gate_pass=False,status='timed_out',stop_reason='process_timeout')
            r.write_summary(args.output_dir/'summary.json',summary)
        raise SystemExit(code)
    try:
        result=run_validation(args.output_dir,args.probe_dir,args.full39_dir,args.binding_dir,
            r.decoding.constrained_loader(r.model_loader(online=args.online_model_downloads)))
    except Exception as exc:
        if args.output_dir.exists():
            summary=read(args.output_dir/'summary.json') if (args.output_dir/'summary.json').exists() else {}
            summary.update(experiment_completed=False,automated_gate_pass=False,status='failed',error_type=type(exc).__name__)
            r.write_summary(args.output_dir/'summary.json',summary)
        raise
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['automated_gate_pass'] else 1)


if __name__=='__main__':main()
