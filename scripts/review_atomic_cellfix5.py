"""Record an assistant review of actual cellfix5 outputs; leave human admission unsigned."""
from copy import deepcopy
import hashlib
import html
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
RUN = '20261017T173345Z-905edcb5'
OUT = ROOT/'research-runs'/('audit-cellfix5-fresh-'+RUN)/'artifact'
DOCS = ROOT/'docs'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
read = lambda p: json.loads(p.read_text(encoding='utf-8'))
lines = lambda p: [json.loads(s) for s in p.read_text(encoding='utf-8').splitlines()]
LABELS = [
    'Part là factual predicate đầy đủ',
    'Giữ đủ yêu cầu, số liệu, đơn vị, quan hệ',
    'Đúng lượng từ và population',
    'Đúng chủ thể và metric',
    'Đúng scope thời gian và điều kiện',
]

# These notes describe the received outputs after reading every claim and part.
# They are assistant judgments, not evidence of a human review or model accuracy.
NOTES = [
    'Hai predicate uses 25% less memory và retains 94% accuracy được tách đúng; part sau kế thừa Model Juniper. Hai metric memory/accuracy và hai requirement 25%/94% không trộn nhau; quan hệ less/retains vẫn nằm trong quote.',
    'Một predicate giữ nguyên retains 94% accuracy; entity Model Juniper, metric accuracy, requirement 94%. Không tự thêm population hoặc restriction.',
    'Một predicate used human labels đầy đủ cả hành động và đối tượng. Metric used human labels hợp lệ vì source không nêu một named measurement riêng.',
    'Giữ nguyên causal predicate caused the latency improvement trong quote, không biến causation thành correlation. Entity new index và metric latency đúng; assessment vẫn phải kiểm quan hệ caused từ toàn bộ quote.',
    'All được ánh xạ all trên population tasks; improved là predicate duy nhất source cung cấp, không tự đoán accuracy/latency. after compression giữ đúng thời gian.',
    'Giữ evaluated four models và condition on two datasets. Numeric requirements gồm 4 models và 2 datasets, mỗi số có object riêng; không chỉ kiểm số 4.',
    'Metric took 12 seconds giữ quan hệ thời lượng và quantity, không còn took đơn lẻ hoặc 12 seconds thiếu quan hệ. Entity Training, unit seconds đúng.',
    'Metric contained 240 documents giữ quan hệ chứa và count object, không còn contained đơn lẻ. Requirement 240 documents đầy đủ.',
    'Entity method, metric recall; On the tested dataset nằm ở condition, time rỗng. Không mở rộng kết luận sang dataset khác.',
    'Every ánh xạ all trên validation shard; metric hiện là recall, không còn improved recall. after the revision nằm đúng time; hướng improved vẫn giữ nguyên trong quote.',
    'At least one ánh xạ some; population audited cache node giữ audited. Metric response time giữ cả cụm; after the patch là time của predicate reduced.',
    'None ánh xạ none trên monitored pumps; metric leaked giữ dạng dương để quantifier none mang phủ định. during the overnight test và modifier monitored được giữ.',
    'Entity North gateway giữ định danh North; metric error rate không kèm reduced/its. Quan hệ reduced và time after calibration vẫn nguyên trong quote.',
    'Every ánh xạ all trên weekly trial; metric throughput không còn improved throughput. condition in May lọc các trial conducted in May, không khẳng định việc cải thiện diễn ra trong May. Quote đầy đủ giữ attachment conducted in May; schema scope chưa có trường restriction-owner riêng.',
    'Metric median request latency giữ cả median và request; không rút còn latency. Entity patch và hướng reduced trong quote đúng.',
    'Entity configuration change đầy đủ; metric precision không lẫn với change trong subject. Hướng increased giữ trong quote.',
    'Hai predicate decreased memory use và increased token recall tách đúng; part sau kế thừa extractor. After tuning là prefix chung có dấu phẩy, nên time của cả hai part đúng. Không trộn hai hướng thay đổi hoặc hai metric.',
    'Every ánh xạ all; entity batch kết hợp condition in the low-temperature group giữ đúng population. Metric yield không còn gained yield; after the update là time, gained giữ nguyên trong quote.',
]


def main():
    audit_path = DOCS/('atomic-verifier-cellfix5-smoke-probe-audit-'+RUN+'.json')
    audit = read(audit_path)
    assert audit['all_output_hashes_valid'] and audit['all_input_bytes_match_released_payload']
    probe = OUT/'decomposition-probe'
    original_review = (probe/'semantic-review.json').read_bytes()
    template = read(probe/'semantic-review.json')
    assert template['reviewer'] == template['reviewer_kind'] == '' and template['review_completed'] is False
    assert template['criteria_sha256'] == audit['criteria_sha256']
    assert template['predictions_sha256'] == sha(probe/'predictions.jsonl')
    cases, rows = read(probe/'cases.json'), lines(probe/'predictions.jsonl')
    rubric = read(probe/'criteria.json')['decomposition_probe']['human_review_rubric']
    assert len(cases) == len(rows) == len(NOTES) == 18 and len(rubric) == len(LABELS) == 5
    reviews = []
    for i,(case,row,note) in enumerate(zip(cases,rows,NOTES),1):
        assert case['example_id'] == row['example_id'] == template['cases'][i-1]['example_id'] == f'decompose:{i:03d}'
        assert case['claim'] == template['cases'][i-1]['claim']
        result = row['result']; plan = result['decomposition']
        assert result['status'] == 'completed' and plan['unresolved'] == []
        for p in plan['parts']:
            assert case['claim'][p['start']:p['end']] == p['quote']
            for q in p['numeric_requirements']:
                assert p['quote'][q['start']:q['end']] == q['quote']
        reviews.append({'run_id':RUN,'example_id':case['example_id'],'claim':case['claim'],
            'decomposition':plan,'reviewer':'Codex','reviewer_kind':'assistant',
            'independent_human_review':False,'human_review_completed':False,
            'predictions_sha256':template['predictions_sha256'],'criteria_sha256':template['criteria_sha256'],
            'judgments':{key:True for key in rubric},'review_status':'assistant_rubric_pass',
            'notes':note,'review_basis':'Current received output read against the original claim, including every quote, scope and numeric requirement. No old human signature transferred.'})
    assert sum(len(r['decomposition']['parts']) for r in reviews) == 20
    expected_metrics = {10:'recall',14:'throughput',18:'yield'}
    assert all(reviews[i-1]['decomposition']['parts'][0]['scope']['metric'] == metric for i,metric in expected_metrics.items())
    semantic = DOCS/('decomposition-semantic-review-cellfix5-'+RUN+'.jsonl')
    semantic.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in reviews),encoding='utf-8')

    # Reuse only the offline form's styles and export controls. Render every
    # claim, part, note and hash from this run; never reuse old checked boxes.
    old = (DOCS/'HUMAN_REVIEW_CELLFIX4_20261017T111605Z-9505cc47.html').read_text(encoding='utf-8')
    header = old.split('<header>')[0].replace('cellfix4','cellfix5')
    controls = old[old.index('<script>'):]
    page = header + '<header><h1>Human review 18 claim — cellfix5</h1><p>Run: '+RUN+'</p>'
    page += '<p>Audit provenance/replay đạt; smoke đúng 12/12, probe 18/18 hợp lệ về cấu trúc. AI đã đọc 20 part và đánh giá 18 claim đạt năm tiêu chí. Đây là review của AI; human review của run mới chưa hoàn tất. Không chuyển chữ ký cũ sang run này.</p>'
    page += '<p>Đọc từng claim và toàn bộ part, đánh dấu riêng năm tiêu chí, đọc/chỉnh sửa ghi chú đề xuất đã điền sẵn và nhập tên người trực tiếp review. Ghi chú do AI soạn về chất lượng decomposition; không phải bằng chứng xác nhận claim là đúng. Nếu thấy ca chưa đạt, để ô tương ứng trống và phản hồi case ID. Form chạy offline, không gửi dữ liệu ra mạng.</p>'
    page += '<pre>predictions_sha256: '+template['predictions_sha256']+'\ncriteria_sha256: '+template['criteria_sha256']+'</pre>'
    page += '<label>Tên người trực tiếp review: <input type="text" id="reviewer" autocomplete="name"></label></header>'
    for i,r in enumerate(reviews):
        page += f'<section class="case" data-index="{i}"><h2>{r["example_id"]}</h2><p class="claim">{html.escape(r["claim"])}</p>'
        for part in r['decomposition']['parts']:
            page += '<pre>'+html.escape(json.dumps(part,ensure_ascii=False,indent=2))+'</pre>'
        page += '<p><strong>Nhận xét AI để đối chiếu:</strong> '+html.escape(r['notes'])+'</p>'
        draft='[Ghi chú đề xuất do AI soạn — người review cần đọc/chỉnh sửa trước khi xác nhận.]\n'+r['notes']
        page += '<label>Ghi chú của người review (bản đề xuất đã điền sẵn):<textarea class="notes" data-prefilled-by="assistant" rows="6">'+html.escape(draft)+'</textarea></label><fieldset><legend>Xác nhận riêng từng tiêu chí</legend>'
        for key,label in zip(rubric,LABELS):
            page += f'<label><input type="checkbox" class="judgment" data-key="{key}"> {label}</label>'
        page += '</fieldset></section>'
    page += '<footer><p id="status">Chưa ký.</p><button id="save" type="button">Tải semantic-review.json đã review</button><p>Chỉ xuất khi đủ 90 xác nhận, ghi chú cho từng ca và tên người review. Runner còn kiểm hash/provenance/replay. Không sửa predictions.</p></footer>'
    data = json.dumps(template,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    page += '<script id="template" type="application/json">'+data+'</script>\n'+controls
    assert page.count('type="checkbox"') == 90 and page.count('class="case"') == 18
    assert ' checked' not in page and 'https://' not in page and 'http://' not in page
    assert json.loads(re.search(r'<script id="template" type="application/json">(.*?)</script>',page,re.S)[1]) == template
    form = DOCS/('HUMAN_REVIEW_CELLFIX5_'+RUN+'.html')
    form.write_text(page,encoding='utf-8')

    smoke = []
    cases12 = read(OUT/'assessment-smoke/cases.json')
    for case,row in zip(cases12,lines(OUT/'assessment-smoke/predictions.jsonl')):
        result=row['result']
        assert result['status']=='completed' and result['assessed_label']==case['label']
        observations=[o for part in result['parts'] for o in part['observations']]
        assert all(q in case['context'] for o in observations for q in o['quotes'])
        item={'example_id':case['example_id'],'claim':case['claim'],'context':case['context'],
            'gold':case['label'],'code_label':result['assessed_label'],'reviewer_kind':'assistant',
            'label_matches_gold':True,'notes':[],
            'parts':deepcopy(result['parts'])}
        if case['example_id']=='contract:accuracy_conflict':
            assert observations[0]['model_truth']=='false' and observations[0]['truth']=='true'
            item['notes'].append('Model explanation confuses accuracy with the memory part, including the claim that no memory comparison is present. Evidence explicitly supports 25% less memory; numeric code derives true. Accuracy is explicitly 81%, not 94%, so aggregate contradict is correct. Keep model_truth, derived truth and the inconsistent explanations visible; do not present this as clean reasoning quality.')
        if case['example_id']=='contract:cross_sentence':
            assert len(observations[0]['numeric_result'])==2
            assert observations[0]['citation_additions']==['Evaluation used two datasets.']
            item['notes'].append('Two independent quantity checks, four models and two datasets, are both grounded and true. The second citation is merged from the model-provided numeric source_quote. Observation prose mentions only four models; model_explanation ends in 2/. Complete JSON/ledger and correct label do not imply complete natural-language explanation.')
        smoke.append(item)
    assert len(smoke)==12
    evidence=DOCS/('atomic-verifier-cellfix5-evidence-review-'+RUN+'.jsonl')
    evidence.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in smoke),encoding='utf-8')
    report=DOCS/('ATOMIC_VERIFIER_CELLFIX5_REVIEW_'+RUN+'.md')
    text=['# Rà soát ZIP cellfix5 — 18/10/2026 (Asia/Saigon)',
        f'Run: `{RUN}`. ZIP: `output-cellfix5-fresh-{RUN}.zip`.',
        f"SHA256 ZIP: `{audit['zip_sha256']}`.",
        'Kết quả audit/replay đạt. Smoke đúng 12/12; probe hợp lệ về cấu trúc 18/18. '
        'AI đã đọc 18 claim/20 part và đánh giá 90/90 tiêu chí đạt. Human review cho run này chưa ký. '
        'Không chạy inference full39 trong lượt rà soát này.',
        '## Artifact và kiểm tra tự động',
        '| Kiểm tra | Kết quả |','| --- | --- |',
        f"| Output manifest | {audit['output_files']} file khớp size/hash |",
        f"| Embedded payload | {audit['input_files']} file đầu vào, {audit['source_fixture_files']} source/fixture khớp release |",
        '| Colab regression | 181 test đạt theo log, stage exit 0 |',
        '| Validate-only | probe18, smoke12, verifier39 đều freeze_valid=true; không phải inference39 |',
        '| Model | Qwen/Qwen2.5-3B-Instruct, revision aa8e72537993ba99e69dfaafa59ed015b17504d1; Tesla T4 |',
        '| Smoke12 | 12 đúng; 0 false support; 0 runtime failure; 28 call; 3577 generated tokens |',
        '| Probe18 | 18 hợp lệ; 0 incomplete; 18 call; 972 generated tokens; label_accuracy=null |',
        '| Raw call/trace | 46 lượt gọi đối chiếu raw JSON, prompt, schema, deadline, citation và numeric sources |',
        '| Full39 gate | Chặn unsigned review trước model_loader; không tạo output full39 |',
        f"Criteria SHA256: `{audit['criteria_sha256']}`. Payload SHA256: `{audit['payload_sha256']}`.",
        'Hash/provenance xác nhận tính nhất quán với release đã đóng băng; không phải chữ ký xác thực độc lập máy Colab.',
        '## Review 18 claim theo từng tiêu chí',
        'C1: factual predicate đầy đủ. C2: đủ yêu cầu/số liệu/đơn vị/quan hệ. '
        'C3: lượng từ/population. C4: chủ thể/metric. C5: scope thời gian/điều kiện. '
        'Các dấu đạt dưới đây là nhận xét của AI, không thay chữ ký human.',
        '| Claim | C1 | C2 | C3 | C4 | C5 | Nhận xét đối chiếu output thực tế |',
        '| --- | --- | --- | --- | --- | --- | --- |']
    for r in reviews:
        text.append('| '+r['example_id']+' | ✓ | ✓ | ✓ | ✓ | ✓ | '+r['notes']+' |')
    text += ['Không còn lỗi metric kèm change verb ở 010/014/018: lần lượt là `recall`, `throughput`, `yield`. '
        '007 giữ `took 12 seconds`; 008 giữ `contained 240 documents`; 006 có đủ hai quantity requirement.',
        '**Lưu ý 014:** `in May` lọc population trial conducted in May; không suy ra improvement diễn ra trong May. '
        'Kết luận C5 đạt khi đọc scope cùng quote đầy đủ. Schema chưa có trường restriction-owner; '
        'downstream không được dùng riêng condition để biến thành event time.',
        '## Review nhãn và bằng chứng smoke12',
        '| Ca | Gold | Code | Đối chiếu bằng chứng |','| --- | --- | --- | --- |']
    evidence_notes={
        'partial_accuracy':'Memory 25% được chứng minh; accuracy 94% chưa có bằng chứng.',
        'partial_memory':'Accuracy 94% được chứng minh; memory reduction chưa có bằng chứng.',
        'both_supported':'Context xác nhận đồng thời memory giảm 25% và accuracy 94%.',
        'accuracy_conflict':'Memory giảm 25% đúng; accuracy 81%, explicitly not 94%. Explanation của model lẫn part; xem lưu ý.',
        'irrelevant':'Không có số accuracy của Model Juniper; mismatched/absent scope không thành support.',
        'negation':'Explicit did not use any human labels phủ định cùng predicate.',
        'causality_missing':'Cùng xuất hiện không chứng minh quan hệ caused; chưa đủ thông tin.',
        'scope':'Một task less accurate là counterexample bác bỏ ALL.',
        'cross_sentence':'Hai numeric checks riêng: four models và two datasets, nguồn ở hai câu cùng report.',
        'wrong_units':'12 hours, not 12 seconds: cùng số nhưng khác unit và có phủ định trực tiếp.',
        'atomic_support':'Exactly 240 documents cùng sample.',
        'bounded_scope':'Chỉ xác nhận recall trên tested dataset; không mở rộng sang dataset khác.'}
    for item in smoke:
        key=item['example_id'].split(':',1)[1]
        text.append('| '+item['example_id']+' | '+item['gold']+' | '+item['code_label']+' | '+evidence_notes[key]+' |')
    text += ['## Hạn chế còn thấy',
        '- `accuracy_conflict`: model_truth=false ở memory part và explanation nói về accuracy; '
        'code tính true cho memory 25% theo evidence. Aggregate contradict đúng, nhưng lời giải thích model chưa nhất quán. '
        'Không dùng prose này như lý do duy nhất cho quyết định; ledger tách rõ model_truth/truth.',
        '- `cross_sentence`: ledger có đủ hai số và citation; observation prose chỉ nhắc four models, '
        'model_explanation kết thúc ở `2/`. JSON không bị cắt và gate không hỏng, nhưng chất lượng explanation chưa hoàn chỉnh.',
        '- Smoke/probe là bộ phát triển đã dùng nhiều vòng sửa. Không chứng minh generalization hoặc zero false support trên full39. '
        'Số baseline 37/39 nằm trong ZIP là lịch sử, không phải kết quả cellfix5.',
        '- ZIP không kiểm E2E Reader/Summarizer với verifier mới; chưa đủ cơ sở ghi toàn dự án Ready.',
        '## Bước tiếp theo',
        f'1. Mở `docs/{form.name}`, đọc output, đọc/chỉnh sửa ghi chú đề xuất đã điền cho từng ca và xác nhận riêng 90 ô; '
        'xuất semantic-review.json nếu mọi tiêu chí thực sự đạt. Tên và ô xác nhận bắt đầu trống; ghi chú có nhãn AI soạn, không kế thừa xác nhận run cũ.',
        '2. Gửi JSON review mới để kiểm đúng predictions/criteria hash. Khi admission hợp lệ mới chuẩn bị chạy full39 trên đúng candidate này. '
        'Không cần vá tiếp ba metric 010/014/018 chỉ để chạy lại probe.',
        '3. Full39 phải đo đủ nhãn, false_support=0 và runtime_failed_rows=0. Sau đó còn đánh giá độc lập và tích hợp/E2E theo phạm vi dự án.']
    formatted=[]
    for line in text:
        if formatted and not (line.startswith('|') and formatted[-1].startswith('|')):
            formatted.append('')
        formatted.append(line)
    report.write_text('\n'.join(formatted)+'\n',encoding='utf-8')
    audit['assistant_review']={'probe_claims_inspected':18,'parts_inspected':20,'rubric_pass_count':18,
        'rubric_judgments_true':90,'prompt_metric_failures_010_014_018_resolved':True,
        'may_scope_note':NOTES[13],'smoke_labels_and_evidence_inspected':12,
        'explanation_quality_caveats':['contract:accuracy_conflict','contract:cross_sentence'],
        'human_review_completed':False,'historical_human_approval_transferred':False,
        'files':{p.relative_to(ROOT).as_posix():sha(p) for p in (semantic,evidence,form,report)}}
    assert (probe/'semantic-review.json').read_bytes()==original_review
    audit_path.write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'assistant_rubric_pass':18,'judgments_true':90,'human_review_completed':False,
        'review_file':str(semantic),'form':str(form)},ensure_ascii=False))


if __name__=='__main__':
    main()
