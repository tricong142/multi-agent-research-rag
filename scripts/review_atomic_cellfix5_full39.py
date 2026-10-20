"""Review all39 received decisions and diagnose frozen code, without modifying outputs."""
from collections import Counter,defaultdict
import hashlib
import importlib
import json
from pathlib import Path
import statistics
import sys

REPO=Path(__file__).resolve().parents[1]
RUN='20261018T153854Z-2c3e0bd6'
BASE=REPO/'research-runs'/('audit-cellfix5-full39-'+RUN)
ROOT,OUT=BASE/'workspace',BASE/'artifact'
DOCS=REPO/'docs'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
lines=lambda p:[json.loads(s) for s in p.read_text(encoding='utf-8').splitlines()]

# Source-specific review of every supplied claim/context pair, not new evidence.
NOTES={
 'contract:partial_accuracy':'Context chỉ có memory giảm 25%; part memory support, accuracy 94% thiếu evidence, nên AND là NEI.',
 'contract:partial_memory':'Context chỉ có accuracy 94%; part memory thiếu evidence, nên AND là NEI.',
 'contract:both_supported':'Context xác nhận cả memory giảm 25% so baseline và accuracy 94%; cả hai numeric checks đúng.',
 'contract:accuracy_conflict':'Memory giảm 25% được chứng minh; accuracy thực tế 81%, not 94%. Nhãn contradict đúng, nhưng model_truth/explanation ở memory part lẫn accuracy; code numeric sửa truth về true.',
 'contract:irrelevant':'Không có accuracy của Model Juniper; scope mismatched và accuracy không được báo cáo nên NEI, không phải phủ định 94%.',
 'contract:negation':'did not use any human labels phủ định trực tiếp cùng predicate; contradict đúng.',
 'contract:causality_missing':'Không thiết lập causal relationship; co-occurrence không chứng minh caused. NEI đúng.',
 'contract:scope':'Một fourth task less accurate là counterexample đủ bác bỏ All tasks improved.',
 'contract:cross_sentence':'Bốn models và hai datasets được chứng minh ở hai câu cùng report. Ledger có cả hai check/citation; observation prose chỉ nhắc four models, model_explanation kết thúc ở 2/.',
 'contract:wrong_units':'12 hours, not 12 seconds là phản bác trực tiếp; không nhầm cùng số 12 thành cùng duration.',
 'contract:atomic_support':'Exactly 240 documents cùng sample chứng minh claim.',
 'contract:bounded_scope':'Cùng tested dataset có recall improved; kết quả ở dataset khác không làm thiếu evidence cho claim đã giới hạn.',
 'scope:universal:support':'Context đóng population Cedar/Maple/Pine và xác nhận each improved. Model chỉ ghi Maple, coverage.complete=false; code giữ NEI. Thiếu ledger toàn population, không phải thiếu evidence trong context.',
 'scope:universal:contradict':'Third shard became worse là counterexample đúng scope. Nhãn đúng; member validation set là tập hợp, chưa định danh đúng counterexample theo contract one-record-per-member.',
 'scope:universal:not_enough_info':'Chỉ biết hai shard improved, các shard còn lại chưa báo cáo. Không có counterexample; model gán false vì chưa đủ coverage nên code trả contradict sai.',
 'scope:existential:support':'Birch became faster là positive witness đủ cho SOME. Model chọn Elm became slower và bỏ Birch nên trả NEI sai.',
 'scope:existential:contradict':'Population complete Birch/Elm/Fir, không node nào giảm response time. Model chỉ ghi Fir false, không complete coverage nên NEI sai.',
 'scope:existential:not_enough_info':'Elm không giảm, các node khác chưa biết; SOME chưa chứng minh hay bác bỏ. Nhãn NEI đúng, nhưng member audited cache nodes là collective và explanation không phân biệt riêng witness đã biết với phần chưa báo cáo.',
 'scope:none:support':'Population ba pumps đóng, context explicitly no leaks for any. Cần positive predicate leaked=false cho từng member cùng closure. Model ghi Blue unknown, bỏ closure nên NEI sai.',
 'scope:none:contradict':'Silver leaked là leaked=true trước khi áp NONE, đủ refute NONE. Model lại ghi truth=false, đảo polarity của positive predicate nên NEI sai.',
 'scope:none:not_enough_info':'Blue/Green không leak, Silver chưa báo cáo; NONE là NEI. Nhãn cuối đúng nhưng observation Silver=false là sai; phải unknown, nên ledger chưa đạt.',
 'scope:entity:support':'North giảm error rate sau calibration; South tăng không liên quan. Quote chọn đúng North, support đúng.',
 'scope:entity:contradict':'North tăng error rate sau calibration là counterevidence; không mượn kết quả giảm của South.',
 'scope:entity:not_enough_info':'North không có calibration results; South giảm không bác bỏ North. Missing evidence bị model biến thành false, dẫn tới contradict sai.',
 'scope:time:support':'Mọi May trial đều improved; April trial reduced nằm ngoài population. Model dùng April để refute May, scope_match vẫn matched nên false contradiction.',
 'scope:time:contradict':'Trong bốn May trials, một reduced throughput là counterexample đúng population. Nhãn đúng; ledger dùng member weekly trials chung thay cho member counterexample riêng.',
 'scope:time:not_enough_info':'Chỉ có April results, May không có throughput results. Đây là NEI, không phải bằng chứng May trial không cải thiện.',
 'scope:direction:support':'42 ms before xuống 31 ms after chứng minh decrease. Arithmetic đúng nhưng metric binding đòi nguyên chuỗi median request latency trong proof chỉ ghi median latency, nên code hạ xuống unknown.',
 'scope:direction:contradict':'42 ms before lên 55 ms after bác bỏ reduced. Numeric observed_direction=increase, model vẫn nói giảm; code còn hạ về unknown do metric binding nên nhãn NEI sai.',
 'scope:direction:not_enough_info':'Chỉ có giá trị after-patch 31 ms, không baseline/change. Không thể kết luận giảm hay không giảm; model gán false nên contradict sai.',
 'scope:metric:support':'Precision 0.81 lên 0.86 đúng claim. Parser/decoder ghi unit afterward cho 0.86 afterward; unit_mismatch_no_conversion làm observation unknown.',
 'scope:metric:contradict':'Precision 0.81 xuống 0.74, recall tăng là metric khác. Pair precision đúng nhưng change checker nhìn toàn passage bốn số nên ambiguous_numeric_passage, NEI sai.',
 'scope:metric:not_enough_info':'Chỉ đo recall, precision was not measured, nên NEI đúng. Quote/model prose về recall không phải bằng chứng phủ định precision; explanation denies increase chưa chính xác.',
 'scope:conjunction:support':'Context nêu memory 5.4 xuống 4.6 GB và recall 0.72 lên 0.81. Gold support giả định cùng extraction workload gắn với extractor trong claim, nhưng không có literal target extractor; decoder khóa cả hai part ở unknown. Cần chốt contract alias/coreference và annotation, không tự xóa entity guard để khớp gold.',
 'scope:conjunction:contradict':'Context nêu memory giảm, recall 0.72 xuống 0.68; gold contradict dựa trên binding cùng workload với extractor. Literal target extractor vắng, decoder chỉ cho unknown. Đây là xung đột giữa gold có binding ngầm và contract exact target; phải làm rõ annotation/binding trước khi sửa.',
 'scope:conjunction:not_enough_info':'Recall không được đánh giá nên AND là NEI như gold. Memory part cũng unknown vì exact target extractor vắng dù workload có số giảm. Nhãn cuối đúng không xác nhận binding ngầm của extractor hoặc chất lượng giải thích từng part.',
 'scope:condition:support':'Mọi low-temperature batch gained; separate high-temperature batch lost nằm ngoài population. Model dùng high-temperature counterexample để refute low-temperature sai scope.',
 'scope:condition:contradict':'Trong low-temperature group có one lost yield; đủ bác bỏ ALL. Nhãn đúng, member one còn phụ thuộc context group ở câu trước.',
 'scope:condition:not_enough_info':'Low-temperature chưa đo changes; high-temperature gained không chứng minh hoặc bác bỏ low-temperature. Quote out-of-group và false verdict sai.',
}


def main():
    audit_path=DOCS/('atomic-verifier-cellfix5-full39-audit-'+RUN+'.json')
    audit=read(audit_path);assert audit['all_39_predictions_replayed'] and audit['metrics_recomputed_exactly']
    cases=read(OUT/'verifier39/cases.json');rows=lines(OUT/'verifier39/predictions.jsonl')
    assert set(NOTES)=={c['example_id'] for c in cases} and len(cases)==len(rows)==39
    frozen=read(ROOT/'research_rag/evaluation/atomic_verifier_criteria_v8.json')
    for name,digest in frozen['source_sha256'].items():assert sha(ROOT/name)==digest
    sys.path.insert(0,str(ROOT))
    a=importlib.import_module('04_factchecker.inference.atomic_verifier')
    d=importlib.import_module('04_factchecker.inference.atomic_decoding')
    n=importlib.import_module('04_factchecker.inference.numeric_verifier')
    pcases=read(OUT/'reviewed-probe/cases.json');prows=lines(OUT/'reviewed-probe/predictions.jsonl')
    previous={c['claim']:r['result']['decomposition'] for c,r in zip(pcases,prows)}
    unchanged=sum(r['result']['decomposition']==previous[c['claim']] for c,r in zip(cases,rows))
    assert unchanged==39
    lookup={c['example_id']:(c,r) for c,r in zip(cases,rows)}
    diagnostics={}
    for cid in ('scope:universal:support','scope:conjunction:support','scope:conjunction:contradict'):
        c,r=lookup[cid];parts=[]
        for part in r['result']['parts']:
            schema=d.assessment_schema(c['claim'],part['part'],c['context'])
            allowed=[b['properties']['truth']['enum'][0] for b in schema['properties']['observations']['items']['anyOf']]
            cov=schema['properties']['coverage']
            can_complete=any(b['properties']['complete'].get('const') is True for b in cov.get('anyOf',[]))
            parts.append({'quote':part['part']['quote'],'literal_targets':a.target_members(part['part'],c['context']),
                'allowed_truths':allowed,'complete_coverage_representable':can_complete})
        diagnostics[cid]=parts
    assert diagnostics['scope:universal:support'][0]['complete_coverage_representable'] is True
    assert all(p['allowed_truths']==['unknown'] for cid in ('scope:conjunction:support','scope:conjunction:contradict') for p in diagnostics[cid])
    c,r=lookup['scope:metric:support'];requirements=n.numeric_requirements(c['context'])
    assert any(q['value']=='0.86' and q['unit']=='afterward' for q in requirements)
    try:n._operand({'value':'0.86','unit':'','quote':'0.86'},c['context'])
    except ValueError as exc:bare_error=str(exc)
    else:raise AssertionError('Expected frozen bare-number unit guard')
    assert bare_error=='numeric_unit_required'
    diagnostics['afterward_unit']={'parsed_requirements':requirements,'bare_dimensionless_operand_error':bare_error}
    for cid in ('scope:direction:support','scope:metric:contradict'):
        c,r=lookup[cid];part=r['result']['parts'][0];record=part['observations'][0]['numeric']
        if isinstance(record,list):record=record[0]
        diagnostics[cid]={'numeric_metric_bound':a.numeric_metric_matches(part['part'],record,part['numeric_requirements']),
            'numeric_tool_result':n.check_numeric(record,part['part']['quote'],c['context'],metric=part['part']['scope']['metric'])}
    assert diagnostics['scope:direction:support']['numeric_metric_bound'] is False
    assert diagnostics['scope:metric:contradict']['numeric_tool_result']['reason']=='ambiguous_numeric_passage'
    categories={
        'quantifier_population_or_positive_predicate':[
            'scope:universal:support','scope:existential:support','scope:existential:contradict','scope:none:support','scope:none:contradict'],
        'missing_information_mistaken_for_false':[
            'scope:universal:not_enough_info','scope:entity:not_enough_info','scope:time:not_enough_info','scope:direction:not_enough_info','scope:condition:not_enough_info'],
        'outside_population_counterevidence':['scope:time:support','scope:condition:support'],
        'numeric_parser_or_binding':['scope:direction:support','scope:direction:contradict','scope:metric:support','scope:metric:contradict'],
        'literal_target_forces_unknown':['scope:conjunction:support','scope:conjunction:contradict']}
    assert sorted(cid for ids in categories.values() for cid in ids)==sorted(audit['wrong_case_ids'])
    caveats={'contract:accuracy_conflict','contract:cross_sentence','scope:universal:contradict',
        'scope:existential:not_enough_info','scope:none:not_enough_info','scope:time:contradict',
        'scope:metric:not_enough_info','scope:conjunction:not_enough_info','scope:condition:contradict'}
    reviewed=[]
    for case,row in zip(cases,rows):
        result=row['result'];correct=case['label']==result['assessed_label']
        reviewed.append({'run_id':RUN,'example_id':case['example_id'],'claim':case['claim'],'context':case['context'],
            'gold_label':case['label'],'code_label':result['assessed_label'],'label_matches_gold':correct,
            'reviewer':'Codex','reviewer_kind':'assistant','independent_human_review':False,
            'evidence_review_status':'incorrect_decision' if not correct else 'label_correct_with_ledger_or_prose_caveat' if case['example_id'] in caveats else 'label_and_evidence_consistent',
            'notes':NOTES[case['example_id']],'parts':result['parts']})
    review_path=DOCS/('atomic-verifier-cellfix5-full39-evidence-review-'+RUN+'.jsonl')
    review_path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in reviewed),encoding='utf-8')
    diag_path=DOCS/('atomic-verifier-cellfix5-full39-diagnostics-'+RUN+'.json')
    diag_path.write_text(json.dumps({'diagnostic_only_no_new_model_inference':True,
        'source_sha256':frozen['source_sha256'],'all39_decompositions_match_reviewed_probe':True,
        'failed_case_categories':categories,'frozen_schema_and_numeric_checks':diagnostics},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    latencies=sorted(row['result']['elapsed_ms'] for row in rows)
    audit['assistant_evidence_review']={'cases_read':39,'parts_read':sum(len(r['result']['parts']) for r in rows),
        'all_decompositions_equal_reviewed_probe':True,'label_correct':21,'label_incorrect':18,
        'correct_label_cases_with_ledger_or_explanation_caveat':sorted(caveats),
        'diagnostic_categories':{k:len(v) for k,v in categories.items()},
        'human_full39_review_completed':False,'synthetic_diagnostics_are_not_model_predictions':True,
        'latency_ms':{'mean':statistics.mean(latencies),'p95_nearest_rank':latencies[37],'max':max(latencies)},
        'files':{p.relative_to(REPO).as_posix():sha(p) for p in (review_path,diag_path)}}
    audit_path.write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'cases_reviewed':39,'parts_reviewed':sum(len(r['result']['parts']) for r in rows),
        'all39_decompositions_match_probe':unchanged,'failed_case_categories':{k:len(v) for k,v in categories.items()},
        'diagnostics':str(diag_path)},ensure_ascii=False))


if __name__=='__main__':main()
