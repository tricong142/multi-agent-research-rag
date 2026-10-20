"""Prepare a review-pending, source-separated verifier pilot without calling a model."""
import ast
from collections import Counter
import hashlib
import html
import json
from pathlib import Path
import re
import unicodedata

from scripts.atomic_validation_review import CHECKS, digest, json_bytes, write_once

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'docs/validation/atomic-cellfix6-v1'
QASPER = ROOT / 'kb_indexing/data/qasper_eval_20260926'
TRACE = ROOT / 'research-runs/colab-qasper-benchmark/20261017T053445Z-0d2b6961/output/benchmark'


def lines(path):
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def tokens(text):
    return re.findall(r'[a-z0-9]+', unicodedata.normalize('NFKC', text).lower())


def grams(words, n=8):
    return {tuple(words[i:i+n]) for i in range(max(0, len(words)-n+1))}


def near(a, b):
    aa, bb = set(a), set(b)
    jaccard = len(aa & bb) / max(1, len(aa | bb))
    shared = grams(a) & grams(b)
    return a == b or (min(len(a), len(b)) >= 6 and jaccard >= .8) or bool(shared), jaccard, shared


def overlap(rows, source, candidate, dev, test, retrieved):
    scan = [source/n for n in candidate['input_manifest']
            if (n.startswith('research_rag/tests/') or n.startswith('research_rag/evaluation/'))
            and n.endswith(('.py', '.json', '.jsonl'))]
    names = ['04_factchecker/data/scifact_train.jsonl', '04_factchecker/data/scifact_dev.jsonl',
             '05_writer/data/writer_sft_validated.jsonl', '05_writer/data/writer_eval_candidates.jsonl',
             '05_writer/data/writer_eval_manual.jsonl',
             'train_agent3_summarizer/data/summarizer_sft_validated.jsonl',
             'train_agent3_summarizer/data/summarizer_eval_manual.jsonl']
    scan += [ROOT/n for n in names]
    targets = {(r['id'], 'claim'): tokens(r['claim']) for r in rows}
    targets.update({(r['source']['doc_id'], 'context'): tokens(r['context']) for r in rows})
    # Only selected eight-token phrases are indexed; no huge all-corpus shingle table.
    index = {}
    for key, words in targets.items():
        for gram in grams(words):
            index.setdefault(gram, set()).add(key)
    target_sets = {key: set(words) for key, words in targets.items()}
    flags, hashes, count = [], {}, 0
    for path in scan:
        raw = path.read_bytes()
        name = path.relative_to(ROOT).as_posix()
        hashes[name] = digest(raw)
        if path.suffix == '.py':
            values = (n.value for n in ast.walk(ast.parse(raw.decode('utf-8-sig')))
                      if isinstance(n, ast.Constant) and isinstance(n.value, str))
        elif path.suffix == '.jsonl':
            values = (s for value in lines(path) for s in strings(value))
        else:
            values = strings(json.loads(raw))
        seen = set()
        for value in values:
            words = tokens(value)
            if len(words) < 6:
                continue
            normalized = ' '.join(words)
            if normalized in seen:
                continue
            seen.add(normalized)
            count += 1
            ws = set(words)
            hits = set()
            for gram in grams(words):
                hits.update(index.get(gram, ()))
            for key, ts in target_sets.items():
                if len(ts & ws) / max(1, len(ts | ws)) >= .8:
                    hits.add(key)
            for key in sorted(hits):
                found, score, shared = near(targets[key], words)
                if found:
                    flags.append({'target': list(key), 'against_file': name,
                                  'against_text_sha256': digest(value.encode()),
                                  'token_jaccard': round(score, 6),
                                  'shared_eight_tokens': [' '.join(g) for g in sorted(shared)[:3]]})
    papers = {r['source']['paper_id'] for r in rows}
    writer_papers = {str(r['paper_id']) for n in names if n.startswith('05_writer/') for r in lines(ROOT/n)}
    document_overlap = sorted(papers & (dev | retrieved | writer_papers))
    # Cross-paper overlap is unexpected; sibling contexts are intentionally shared.
    for i, a in enumerate(rows):
        for b in rows[i+1:]:
            if a['source']['paper_id'] == b['source']['paper_id']:
                continue
            for field in ('claim', 'context'):
                found, score, shared = near(tokens(a[field]), tokens(b[field]))
                if found:
                    flags.append({'target': [a['id'], field], 'against_case': b['id'],
                                  'token_jaccard': score, 'shared_eight_tokens': len(shared)})
    return {'normalization': 'NFKC; lowercase alphanumeric tokenization',
            'flag_rules': ['exact normalized text', 'token-set Jaccard >= 0.8 with at least 6 tokens',
                           'any shared contiguous 8-token phrase'],
            'scanned_files_sha256': hashes, 'scanned_unique_strings_per_file_total': count,
            'flags': flags, 'document_overlap': document_overlap,
            'selected_papers': sorted(papers), 'test_candidate_papers': len(test),
            'eligible_after_dev_retrieval_exclusion': len(test-retrieved),
            'selected_in_test_candidate': papers <= test,
            'retrieved_dev_papers_excluded': sorted(retrieved),
            'within_paper_contrast_siblings': 'Three cases share a paragraph by design; report grouped results.',
            'limitations': ['Lexical screening does not prove semantic independence.',
                           'Summarizer paper identities are unresolved; text checks only.',
                           'QASPER corpus was indexed for retrieval; selected papers were not returned in saved dev top-k traces.',
                           'Base-model pretraining exposure is unknown.']}


def review_html(rows, template):
    labels = {'gold_label': 'Nhãn đúng theo context', 'exact_evidence': 'Evidence nguyên văn và đủ vai trò',
              'missing_information': 'Thông tin thiếu ghi đúng; không suy diễn từ sự vắng mặt',
              'identity_metric_quantity': 'Đúng chủ thể, metric, từng số và đơn vị',
              'scope_population_relation': 'Đúng scope, population, lượng từ và quan hệ'}
    cards = []
    for row in rows:
        esc = html.escape
        checks = ''.join(f'<label><input type="checkbox" data-check="{key}"> {esc(label)}</label>'
                         for key, label in labels.items())
        quotes = ''.join('<blockquote>'+esc(s['quote'])+'</blockquote>' for s in row['evidence'])
        cards.append(f'''<article data-id="{row['id']}"><h2>{row['id']} · {esc(row['proposed_gold'])} (đề xuất)</h2>
<h3>{esc(row['claim'])}</h3><p>Nguồn: {esc(row['source']['title'])} · {row['source']['doc_id']}</p>
<details><summary>Đọc toàn bộ context nguyên văn</summary><pre>{esc(row['context'])}</pre></details>
<p>Vai trò evidence: {row['evidence_role']}</p>{quotes}<p><b>Thông tin thiếu:</b> {esc(row['missing_information'] or 'Không có theo annotation đề xuất.')}</p>
<p><b>Lý do đề xuất:</b> {esc(row['rationale'])}</p>{checks}
<label>Kết luận nhãn <select data-label><option value="">Chưa kết luận</option>
<option>support</option><option>contradict</option><option>not_enough_info</option></select></label>
<label>Ghi chú của người review (bắt buộc)<textarea data-note rows="2"></textarea></label></article>''')
    data = json.dumps(template, ensure_ascii=False).replace('<', '\\u003c')
    return ('''<!doctype html><meta charset="utf-8"><title>Review validation cellfix6 v1</title>
<style>body{max-width:1000px;margin:30px auto;padding:0 20px;font:16px/1.6 system-ui;background:#f5f7fa;color:#17202b}article{background:white;border:1px solid #cbd3dc;padding:24px;margin:24px 0}label{display:block;margin:10px 0}textarea{display:block;width:95%}pre{white-space:pre-wrap;font:inherit}blockquote{border-left:4px solid #668;padding-left:15px}button,input,select{font:inherit}button{padding:12px}#status{white-space:pre-wrap}</style>
<h1>Review annotation: 30 ca / 10 paper</h1>
<p>Đây là nhãn mới do AI đề xuất, chưa được người review chấp thuận. Chỉ đánh giá theo context được cung cấp. Với NEI, trích dẫn chỉ là thông tin liên quan; đọc toàn bộ đoạn để kiểm thông tin còn thiếu. Không biến “không đề cập” thành contradict.</p>
<p>Không có kết quả model của bộ này. Bộ là pilot kiểm verifier, chưa chứng minh dữ liệu chưa từng nằm trong pretraining. Nguồn QASPER đã được lập chỉ mục retrieval; paper được chọn không xuất hiện trong top-k dev đã lưu. Paper ID của dữ liệu Summarizer chưa xác định hoàn toàn; kiểm lexical không chứng minh không trùng về nghĩa.</p>
<p>Protocol đề xuất: đủ 30 ca, đúng 30/30, false support=0, runtime failure=0, đúng budget. Báo cả support recall, confusion và kết quả theo 10 paper. Nếu dùng kết quả để sửa candidate thì chuyển bộ thành development và tạo bộ mới.</p>
<label>Tên người review <input id="reviewer"></label><label>Ngày review <input id="day" type="date"></label>
<label><input id="attest" type="checkbox"> Tôi là người trực tiếp đọc context và xác nhận từng tiêu chí.</label>
<label><input id="limits" type="checkbox"> Tôi đã đọc các giới hạn provenance nêu trên.</label>
<label><input id="unseen" type="checkbox"> Tôi chưa xem kết quả candidate trên bộ validation này.</label>
<label><input id="protocol" type="checkbox"> Tôi chấp nhận protocol trước inference và không dùng kết quả để tune rồi vẫn gọi bộ này độc lập.</label>
''' + ''.join(cards) + '''<button id="export">Xuất annotation-review.json (có thể lưu bản chưa hoàn tất)</button><p id="status"></p>
<script>
const seed=''' + data + ''';
document.getElementById('export').onclick=()=>{
 const result=JSON.parse(JSON.stringify(seed));
 result.reviewer=document.getElementById('reviewer').value.trim();
 result.reviewed_on=document.getElementById('day').value;
 result.human_attestation=document.getElementById('attest').checked;
 result.provenance_limits_acknowledged=document.getElementById('limits').checked;
 result.no_candidate_outcomes_seen=document.getElementById('unseen').checked;
 result.protocol_accepted=document.getElementById('protocol').checked;
 result.decisions=[...document.querySelectorAll('article')].map(card=>({id:card.dataset.id,
  accepted_label:card.querySelector('[data-label]').value||null,
  checks:Object.fromEntries([...card.querySelectorAll('[data-check]')].map(c=>[c.dataset.check,c.checked])),
  note:card.querySelector('[data-note]').value.trim()}));
 const complete=result.decisions.filter(d=>d.accepted_label&&d.note&&Object.values(d.checks).every(Boolean)).length;
 document.getElementById('status').textContent=`Đã điền ${complete}/30 ca. File xuất chưa phải admission; script sẽ kiểm hash, nhãn và đủ xác nhận trước khi khóa.`;
 const url=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)+'\\n'],{type:'application/json'}));
 const a=document.createElement('a');a.href=url;a.download='annotation-review-cellfix6-v1.json';a.click();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
};
</script>''').encode('utf-8')


def main():
    candidate = json.loads((ROOT/'docs/atomic-verifier-cellfix6-candidate.json').read_text())
    source = Path(candidate['source_root'])
    for name, item in candidate['input_manifest'].items():
        raw = (source/name).read_bytes()
        assert len(raw) == item['size'] and digest(raw) == item['sha256'], name
    upstream = json.loads((QASPER/'manifest.json').read_text())
    for name, expected in upstream['output_hashes'].items():
        assert digest((QASPER/name).read_bytes()) == expected, name
    for name, expected in upstream['input_hashes'].items():
        if '/' in name or '\\' in name:
            assert digest((ROOT/name).read_bytes()) == expected, name
    dev = {r['paper_id'] for r in lines(QASPER/'qrels_dev.jsonl')}
    test_rows = list(lines(QASPER/'qrels_test_candidate.jsonl'))
    test = {r['paper_id'] for r in test_rows}
    qrel_docs = {doc for r in test_rows for doc in r['relevant_doc_ids']}
    retrieved, trace_hashes = set(), {}
    for path in (TRACE/'bm25-traces.jsonl', TRACE/'dense-traces.jsonl'):
        trace_hashes[path.relative_to(ROOT).as_posix()] = digest(path.read_bytes())
        retrieved.update(doc.split(':')[1] for r in lines(path) for doc in r['doc_ids'])
    corpus = {r['doc_id']: r for r in lines(QASPER/'corpus.jsonl')}
    rows = []
    for paper, index, specs in json.loads((DEST/'authoring.json').read_text(encoding='utf-8')):
        doc_id = f'qasper:{paper}:paragraph:{index}'
        assert paper in test-dev-retrieved and doc_id in qrel_docs
        doc = corpus[doc_id]
        for label, claim, quote, missing, tags, rationale in specs:
            start = doc['text'].index(quote)
            rows.append({'id': f'validation-v1:{len(rows)+1:03d}', 'group_id': paper,
                         'claim': claim, 'context': doc['text'], 'proposed_gold': label,
                         'evidence': [{'quote': quote, 'start': start, 'end': start+len(quote)}],
                         'evidence_role': 'related_not_proof_of_absence' if label=='not_enough_info' else 'label_evidence',
                         'missing_information': missing, 'rationale': rationale, 'tags': tags,
                         'source': {**doc['metadata'], 'doc_id': doc_id, 'context_sha256': digest(doc['text'].encode()),
                                    'paper_url': 'https://arxiv.org/abs/'+paper}})
    assert len(rows) == 30 and len({r['group_id'] for r in rows}) == 10
    report = overlap(rows, source, candidate, dev, test, retrieved)
    frozen = json.loads((source/'research_rag/evaluation/atomic_verifier_criteria_v8.json').read_text())
    protocol = {'version': 'verifier-validation-protocol-v1', 'scope': 'supplied-context verifier pilot',
                'gate': {'cases': 30, 'correct_labels': 30, 'false_support': 0, 'runtime_failed_rows': 0,
                         'every_paper_complete_and_correct': True, 'measured_token_budget_required': True,
                         'decode_and_deadline_trace_required': True},
                'model': frozen['base_model'], 'revision': frozen['base_revision'],
                'seed': 42, 'quantization': 'NF4', 'dtype': 'float16', 'do_sample': False,
                'budget': {'calls_per_case': 8, 'attempts_per_stage': 2, 'new_tokens_per_call': 1536,
                           'seconds_per_case': 180, 'maximum_calls': 240, 'maximum_generated_tokens': 368640},
                'report': ['confusion', 'per_label_precision_recall', 'support_recall', 'false_support_count_and_denominator',
                           'runtime_failures', 'per_paper_results', 'latency', 'calls', 'prompt_tokens', 'generated_tokens'],
                'prerequisites': ['human annotation admission and immutable lock', 'same candidate smoke12 gate',
                                  'same candidate probe18 and human review', 'same candidate full39 gate under strict-identity-v1'],
                'outcome_policy': 'One preregistered quality run. Preserve all failures. Technical reruns must retain failed traces and declare why. If outcomes inform a fix or selection, retire this set to development; never continue calling it independent.',
                'claims': 'New assistant-authored claims; labels proposed from exact QASPER paragraphs, not QASPER entailment labels.',
                'interpretation': 'Zero observed false support on this small correlated pilot is not a population guarantee or E2E acceptance.'}
    source_meta = {k: upstream[k] for k in ('source','native_split','source_revision','source_card','license_url','attribution','remaining_review')}
    source_meta.update(output_hashes=upstream['output_hashes'], retrieval_trace_sha256=trace_hashes,
                       selection='Human-readable textual paragraphs from test-candidate qrels, excluding every paper in saved dev BM25/Dense returned results. Ten papers selected before candidate inference to cover numbers, scope, relation and absence; not a random representative sample.',
                       label_author='AI proposed; pending human adjudication', candidate_results_used_for_selection=False)
    payloads = {
        'cases.jsonl': b''.join((json.dumps(r,ensure_ascii=False)+'\n').encode() for r in rows),
        'inputs.jsonl': b''.join((json.dumps({k:r[k] for k in ('id','claim','context')},ensure_ascii=False)+'\n').encode() for r in rows),
        'criteria.json': json_bytes(protocol), 'overlap-report.json': json_bytes(report),
        'source-provenance.json': json_bytes(source_meta),
        'review_gate.py': (ROOT/'scripts/atomic_validation_review.py').read_bytes(),
        'authoring.json': (DEST/'authoring.json').read_bytes()}
    for name, raw in payloads.items():
        write_once(DEST/name, raw)
    manifest = {'version': 'atomic-cellfix6-validation-v1', 'status': 'draft_pending_human_annotation',
                'candidate': candidate['candidate'], 'candidate_criteria_sha256': candidate['criteria_sha256'],
                'candidate_manifest_sha256': digest((ROOT/'docs/atomic-verifier-cellfix6-candidate.json').read_bytes()),
                'cases': len(rows), 'papers': 10, 'proposed_label_counts': dict(Counter(r['proposed_gold'] for r in rows)),
                'files': {name: {'size':len(raw),'sha256':digest(raw)} for name,raw in sorted(payloads.items())},
                'inference_completed': False, 'human_adjudication_complete': False}
    write_once(DEST/'manifest.json', json_bytes(manifest))
    template = {'review_type': 'human', 'reviewer': '', 'reviewed_on': '', 'human_attestation': False,
                'provenance_limits_acknowledged': False, 'no_candidate_outcomes_seen': False, 'protocol_accepted': False,
                'manifest_sha256': digest(json_bytes(manifest)), 'candidate_criteria_sha256': candidate['criteria_sha256'],
                'decisions': [{'id':r['id'], 'accepted_label':None, 'checks':dict.fromkeys(CHECKS), 'note':''} for r in rows]}
    write_once(DEST/'annotation-review.template.json', json_bytes(template))
    write_once(DEST/'REVIEW.html', review_html(rows,template))
    print(json.dumps({'cases':len(rows),'papers':10,'overlap_flags':len(report['flags']),
                      'document_overlap':report['document_overlap'],'human_review':'pending'}))


if __name__ == '__main__':
    main()
