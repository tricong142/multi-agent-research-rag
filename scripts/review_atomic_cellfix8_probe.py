"""Record the requested AI review honestly; retain the frozen human admission gate."""
from copy import deepcopy
import hashlib
import html
import importlib.util
import json
from pathlib import Path
import sys

REPO=Path(__file__).resolve().parents[1]
RUN='20261020T061934Z-c87bce57'
BASE=REPO/'research-runs'/('audit-cellfix8-fresh-'+RUN)
OUT=BASE/'artifact'
DELIVERY=REPO/'docs/reviews'/('cellfix8-'+RUN)
SHA=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
LABELS=['Part là factual predicate đầy đủ','Giữ đủ yêu cầu, số liệu, đơn vị và quan hệ',
        'Đúng lượng từ và population','Đúng chủ thể và metric','Đúng scope thời gian và điều kiện']

# These are reviewer findings about this run, not model prompts or gold labels.
NOTES=[
 ['Tách đúng hai predicate uses less memory và retains accuracy; vế sau kế thừa chủ thể.',
  'Giữ 25%, 94%, quan hệ less và retains trong hai quote tương ứng.',
  'Cả hai part atomic; không thêm lượng từ ALL/SOME.',
  'Cùng Model Juniper; memory và accuracy tách riêng, không hoán đổi số liệu.',
  'Claim không nêu time/condition; các trường này rỗng, không tự bổ sung.'],
 ['Một part retains 94% accuracy đầy đủ.', 'Giữ nguyên retains và requirement 94%.',
  'Atomic, không có population lượng hóa.', 'Entity Model Juniper; metric accuracy.', 'Không có restriction thời gian/điều kiện được thêm.'],
 ['Một part used human labels giữ cả động từ và đối tượng.', 'Không bỏ used hoặc human labels; không thêm số liệu.',
  'Atomic đúng với một study.', 'study là chủ thể; used human labels là metric dạng predicate đầy đủ vì không có named property.',
  'Không gán thêm time/condition.'],
 ['Giữ nguyên causal predicate caused the latency improvement.', 'Quan hệ caused nằm trong quote, không bị đổi thành đồng xuất hiện/correlation.',
  'Atomic đúng; không tạo population.', 'new index và metric latency đúng, modifier new được giữ.',
  'Không có restriction được tự thêm. Decomposition không chứng minh quan hệ causal là thật.'],
 ['Predicate improved đầy đủ với population tasks.', 'Không bịa improved accuracy khi claim chỉ nói improved.',
  'All ánh xạ all trên tasks.', 'Entity tasks; improved là predicate source cung cấp, không suy đoán property.',
  'after compression nằm đúng time và vẫn trong quote.'],
 ['Một event evaluated four models on two datasets, không tách count thành fragment.',
  'Có đủ hai requirement: 4 models và 2 datasets, giữ object/unit riêng.',
  'Atomic; four/two là số lượng đối tượng, không phải ALL/SOME.',
  'report là entity; evaluated four models giữ quan hệ đánh giá; on two datasets là condition.',
  'Không biến dataset condition thành time hoặc bỏ dataset requirement.'],
 ['Training took 12 seconds là một factual predicate đầy đủ.', 'Giữ số 12 và unit seconds cùng quan hệ took.',
  'Atomic, không có lượng từ population.', 'Training là entity; metric took 12 seconds đầy đủ, không phải took hoặc 12 seconds riêng.',
  '12 seconds là thời lượng được đo, không phải mốc time; time rỗng hợp lý.'],
 ['contained 240 documents giữ hành động và đối tượng trong một part.', 'Giữ requirement 240 documents, không bỏ count hoặc object.',
  'Atomic; 240 không bị hiểu thành population quantifier.', 'Entity sample; metric contained 240 documents đầy đủ.', 'Không tự thêm điều kiện hay thời gian.'],
 ['improved recall là predicate của method, giữ nguyên leading restriction.', 'Giữ hướng improved và property recall.',
  'Atomic, không suy rộng sang mọi dataset.', 'Entity method, metric recall đúng.',
  'On the tested dataset là condition; không đòi kết quả của dataset khác.'],
 ['Mỗi validation shard improved recall là một predicate đầy đủ.', 'Giữ hướng improved và restriction after the revision.',
  'Every ánh xạ all; population validation shard giữ modifier validation.',
  'Entity validation shard; metric recall không kèm improved.', 'after the revision nằm trong time của đúng predicate.'],
 ['reduced response time đầy đủ trên audited cache node.', 'Giữ at least one, reduced, response time và after the patch.',
  'At least one ánh xạ some; giữ đủ audited cache node.', 'Entity audited cache node; metric response time giữ cả cụm.',
  'after the patch là time; không thêm điều kiện khác.'],
 ['Predicate leaked được giữ, quantifier none mang phủ định.', 'Giữ monitored và during the overnight test; không tạo số liệu.',
  'None of ánh xạ none trên monitored pumps.', 'Entity monitored pumps; metric leaked là predicate dương trước áp lượng từ none.',
  'during the overnight test là restriction thời gian.'],
 ['North gateway reduced its error rate là factual predicate đầy đủ.', 'Giữ quan hệ reduced, định danh North và after calibration.',
  'Atomic, không mở rộng sang gateway khác.', 'Entity North gateway; metric error rate không lẫn its/reduced.',
  'after calibration là time của predicate reduced.'],
 ['weekly trial conducted in May improved throughput là một predicate, không tách modifier thành part riêng.',
  'Giữ nguyên conducted in May trong quote, cùng hướng improved và property throughput.',
  'Every ánh xạ all; population là weekly trial được lọc bởi conducted in May.',
  'Entity weekly trial; metric throughput đúng, không còn improved throughput.',
  'condition=in May lọc trial được tiến hành trong May; time rỗng không khẳng định improvement xảy ra trong May. Phải đọc cùng quote; schema chưa có restriction-owner riêng.'],
 ['patch reduced median request latency là predicate đầy đủ.', 'Giữ cả median, request và hướng reduced.',
  'Atomic, không tạo population.', 'Entity patch; metric median request latency không bị rút thành latency.', 'Không tự thêm time/condition.'],
 ['configuration change increased precision là predicate đầy đủ.', 'Giữ quan hệ increased trong quote.',
  'Atomic, không thêm lượng từ.', 'Entity configuration change giữ đủ định danh; metric precision không lẫn change trong subject.',
  'Không tự thêm time/condition.'],
 ['Tách decreased memory use và increased token recall; part sau kế thừa extractor.',
  'Giữ hai hướng đối nhau và đầy đủ memory use/token recall.', 'Hai part atomic; không thêm lượng từ population.',
  'Cả hai entity extractor, hai metric riêng đúng vế.', 'After tuning là prefix chung trước dấu phẩy, nên kế thừa time cho cả hai part là đúng.'],
 ['batch gained yield là predicate đầy đủ kèm restriction population và time.', 'Giữ gained, yield, low-temperature group và after the update.',
  'Every ánh xạ all; entity batch kết hợp condition in the low-temperature group giới hạn đúng population.',
  'Entity batch; metric yield không kèm gained.', 'after the update là time; low-temperature group là condition, không tráo hai loại restriction.']
]


def main():
    audit=json.loads((REPO/'docs'/('atomic-verifier-cellfix8-smoke-probe-audit-'+RUN+'.json')).read_bytes())
    assert audit['all_output_hashes_valid'] and audit['all_predictions_replayed']
    probe=OUT/'decomposition-probe'
    cases=json.loads((probe/'cases.json').read_bytes())
    rows=[json.loads(s) for s in (probe/'predictions.jsonl').read_bytes().splitlines()]
    criteria=json.loads((probe/'criteria.json').read_bytes())
    rubric=criteria['decomposition_probe']['human_review_rubric']
    assert len(cases)==len(rows)==len(NOTES)==18 and len(rubric)==5
    reviews=[]
    for i,(case,row,notes) in enumerate(zip(cases,rows,NOTES),1):
        assert case['example_id']==row['example_id']==f'decompose:{i:03d}' and len(notes)==5
        plan=row['result']['decomposition'];assert plan['unresolved']==[]
        for p in plan['parts']:
            assert case['claim'][p['start']:p['end']]==p['quote']
            for n in p['numeric_requirements']:assert p['quote'][n['start']:n['end']]==n['quote']
        reviews.append({'example_id':case['example_id'],'claim':case['claim'],'decomposition':plan,
            'judgments':dict.fromkeys(rubric,True),'criterion_notes':dict(zip(rubric,notes)),
            'notes':' '.join(f'C{j}: {note}' for j,note in enumerate(notes,1))})
    assert sum(len(v['decomposition']['parts']) for v in reviews)==20
    for i,metric in ((7,'took 12 seconds'),(8,'contained 240 documents'),(10,'recall'),(14,'throughput'),(18,'yield')):
        assert reviews[i-1]['decomposition']['parts'][0]['scope']['metric']==metric
    p=reviews[13]['decomposition']['parts'][0]
    assert p['scope']['condition']=='in May' and p['scope']['time']==''
    assert [(n['value'],n['unit']) for n in reviews[5]['decomposition']['parts'][0]['numeric_requirements']]==[('4','models'),('2','datasets')]
    DELIVERY.mkdir(parents=True,exist_ok=True)
    review={'run_id':RUN,'candidate':audit['candidate'],'criteria_sha256':audit['criteria_sha256'],
        'predictions_sha256':SHA(probe/'predictions.jsonl'),'reviewer':'Codex (AI reviewer)',
        'reviewer_kind':'assistant','review_completed':True,'human_review_completed':False,
        'review_scope':'decomposition rubric only; not claim truth or model label accuracy',
        'reviewed_on':'2026-10-20','cases':reviews}
    review_path=DELIVERY/'semantic-review.json'
    review_path.write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    seed=deepcopy(review)
    seed.update(reviewer='',reviewer_kind='human',review_completed=False,human_review_completed=False,
        ai_review_sha256=SHA(review_path))
    for row in seed['cases']:
        row['judgments']=dict.fromkeys(rubric,None)
        row['notes']='[Gợi ý AI; người review cần đọc/chỉnh trước khi xác nhận.] '+row['notes']
    cards=[]
    for row in reviews:
        checks=''.join('<label><input type="checkbox" data-key="'+key+'"> '+html.escape(label)
            +'<br><small>AI: đạt — '+html.escape(row['criterion_notes'][key])+'</small></label><br>' for key,label in zip(rubric,LABELS))
        cards.append('<article data-id="'+row['example_id']+'"><h2>'+row['example_id']+'</h2><p>'+html.escape(row['claim'])
            +'</p><pre>'+html.escape(json.dumps(row['decomposition'],ensure_ascii=False,indent=2))+'</pre>'+checks
            +'<label>Ghi chú người review (có gợi ý AI)<textarea>'+html.escape(next(v['notes'] for v in seed['cases'] if v['example_id']==row['example_id']))+'</textarea></label></article>')
    script='''const seed=SEED;
document.querySelector('#save').onclick=()=>{
 const data=JSON.parse(JSON.stringify(seed));data.reviewer=document.querySelector('#name').value.trim();
 if(!data.reviewer||!document.querySelector('#done').checked){alert('Cần tên và xác nhận đã trực tiếp review đủ 18 ca.');return;}
 const cards=[...document.querySelectorAll('article')];
 data.cases=data.cases.map((row,i)=>{const card=cards[i];row.judgments=Object.fromEntries([...card.querySelectorAll('[data-key]')].map(x=>[x.dataset.key,x.checked]));row.notes=card.querySelector('textarea').value.trim();return row;});
 if(data.cases.some(row=>Object.values(row.judgments).some(v=>v!==true)||!row.notes)){alert('Cần đủ 90 xác nhận và notes từng ca; ca chưa đạt phải dừng.');return;}
 data.review_completed=true;data.human_review_completed=true;data.reviewer_kind='human';data.reviewed_on=new Date().toISOString();
 const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)+'\\n'],{type:'application/json'}));
 const link=document.createElement('a');link.href=url;link.download='semantic-review.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};'''.replace('SEED',json.dumps(seed,ensure_ascii=False).replace('<','\\u003c'))
    page='<!doctype html><html lang="vi"><meta charset="utf-8"><title>Cellfix8 — human confirmation after AI review</title><style>body{max-width:1050px;margin:30px auto;font:16px/1.6 system-ui;padding:12px}article{border:1px solid #bbb;padding:20px;margin:20px 0}pre{white-space:pre-wrap}textarea{width:95%;min-height:130px}small{display:inline-block;margin-left:25px;color:#333}</style><h1>Cellfix8 — xác nhận human sau AI review</h1><p>Run '+RUN+'. Đây là review đề xuất của AI, chưa có chữ ký human. Đọc từng claim/part và năm nhận xét, chỉ tích khi chính bạn thấy đạt. Không chuyển chữ ký candidate cũ.</p><p>014: May lọc thời điểm trial được tiến hành, không phải thời điểm improvement. 018: population được giới hạn bởi low-temperature group.</p><pre>criteria_sha256: '+review['criteria_sha256']+'\npredictions_sha256: '+review['predictions_sha256']+'</pre><label>Tên người trực tiếp review <input id="name"></label><br><label><input id="done" type="checkbox"> Tôi đã trực tiếp đọc đủ 18 claim/20 part, xác nhận từng tiêu chí và ghi chú.</label>'+''.join(cards)+'<button id="save">Xuất semantic-review.json sau xác nhận human</button><script>'+script+'</script></html>'
    assert page.count('data-key=')==90 and page.count('<article ')==18 and ' checked' not in page
    (DELIVERY/'HUMAN_REVIEW_WITH_AI_NOTES.html').write_text(page,encoding='utf-8')
    (DELIVERY/'review-form.js').write_text(script,encoding='utf-8')
    table=['# AI review probe18 — cellfix8',f'Run `{RUN}`. AI review hoàn tất: 18/18 claim, 20 part, 90/90 tiêu chí đạt. Human review chưa hoàn tất.',
        'C1 predicate đầy đủ; C2 yêu cầu/số liệu/quan hệ; C3 lượng từ/population; C4 chủ thể/metric; C5 time/condition.',
        '| ID | C1 | C2 | C3 | C4 | C5 | Ghi chú đối chiếu |','|---|---|---|---|---|---|---|']
    for row in reviews:table.append('| '+row['example_id']+' | ✓ | ✓ | ✓ | ✓ | ✓ | '+row['notes']+' |')
    table+=['014: in May là restriction của population trial conducted in May; không suy ra improvement diễn ra trong May. Scope phải được đọc cùng quote đầy đủ, không lấy riêng condition làm event time.',
        '018: entity batch kết hợp condition in the low-temperature group giữ đúng population; after the update mới là time.',
        'Đây là review của AI, không phải independent human review và không đo label accuracy của 18 claim. Không copy chữ ký Trí Công từ run cũ.']
    (DELIVERY/'DECOMPOSITION_REVIEW.md').write_text('\n\n'.join(table[:3])+'\n\n'+'\n'.join(table[3:]),encoding='utf-8')
    # Ready-to-run cell for the still-live Colab run. Human admission remains intact.
    book=json.loads((REPO/'scripts/colab_atomic_verifier_cellfix8.ipynb').read_bytes())
    cells=[v['source'] for v in book['cells'] if v['cell_type']=='code']
    cell="assert globals().get('run_id') == "+repr(RUN)+", 'Runtime does not contain the audited run; restore audited artifacts first.'\n"
    cell+=cells[5].replace('RUN_FULL39 = False','RUN_FULL39 = True',1)
    compile(cell,'RUN_FULL39_AFTER_HUMAN_REVIEW','exec')
    (DELIVERY/'RUN_FULL39_AFTER_HUMAN_REVIEW.py').write_text(cell,encoding='utf-8')
    # Verify the AI review cannot pass the human gate, without editing original outputs.
    sys.path.insert(0,str(BASE/'workspace'))
    spec=importlib.util.spec_from_file_location('review_workflow',BASE/'workspace/atomic_workflow_cellfix8.py')
    w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
    import tempfile,shutil
    with tempfile.TemporaryDirectory(dir=REPO/'research-runs',prefix='cf8-ai-admission-') as temp:
        test=Path(temp)/'probe';shutil.copytree(probe,test)
        (test/'semantic-review.json').write_bytes(review_path.read_bytes())
        try:w.r.require_probe_review(test)
        except ValueError as exc:assert 'Completed human review' in str(exc);blocked=str(exc)
        else:raise AssertionError('AI review must not be mislabeled as human')
    assert SHA(probe/'predictions.jsonl')==review['predictions_sha256']
    result={'run_id':RUN,'claims':18,'parts':20,'criteria_checked':90,'ai_passed_claims':18,
        'reviewer_kind':'assistant','human_review_completed':False,'ai_review_does_not_admit_full39':True,
        'admission_block':blocked,'full39_cell_prepared_with_run_flag_true':True,'full39_executed':False,
        'original_predictions_unchanged':True,'files_sha256':{p.name:SHA(p) for p in sorted(DELIVERY.iterdir()) if p.is_file() and p.name!='review-validation.json'}}
    (DELIVERY/'review-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='files_sha256'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
