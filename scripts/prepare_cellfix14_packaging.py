"""Derive new launchers without editing or executing a previous release."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def prepare():
    if (ROOT/'docs/atomic-verifier-cellfix14-release.json').exists():raise ValueError('Released launchers are immutable')
    scripts=ROOT/'scripts'
    # Pure launchers are inherited; historical fixtures and test modules retain their names.
    for old,new in [('colab_cellfix13_cell6.py','colab_cellfix14_cell6.py'),
                    ('build_colab_cellfix13.py','build_colab_cellfix14.py')]:
        text=(scripts/old).read_text(encoding='utf-8').replace('cellfix13','cellfix14').replace('Cellfix13','Cellfix14')
        if old.startswith('build_'):
            start=text.index("    intro='''");end=text.index("'''",start+13)+3
            intro="""# Cellfix14 — candidate mới, dev30-v1 đã lộ kết quả

Sửa quantity/binding, schema lượng từ theo part, deadline/filter và trace lỗi.
Giữ model/revision, gold, ngân sách call/token/thời gian và gate full39.
Bộ30 đã dùng để sửa là DEVELOPMENT, không phải holdout độc lập. Kết quả model
chưa được đo cho candidate này. Cần holdout mới disjoint theo paper trước nghiệm thu.
Chạy cells1–5; review probe mới trước cell6; review full39 mới trước cell7 dev30.
Không tự ký review hoặc đổi gold. Cells6/7 mặc định tắt. Lưu ZIP kể cả thất bại.
"""
            text=text[:start]+"    intro="+repr(intro)+text[end:]
            start=text.index('    files=[TARGET');end=text.index('\n    record=',start)
            names=['build_atomic_cellfix14_candidate.py','check_atomic_cellfix14.py','check_atomic_cellfix14_tokenizer.py',
                   'atomic_cellfix14_binding.py','atomic_cellfix14_workflow.py','colab_cellfix14_cell6.py',
                   'atomic_cellfix14_quantities.py','atomic_cellfix14_binding_rules.py','atomic_cellfix14_runtime.py',
                   'atomic_cellfix14_generation.py','atomic_cellfix14_decomposition.py','test_atomic_cellfix14.py',
                   'prepare_cellfix14_packaging.py','test_cellfix14_packaging.py','test_colab_cellfix14.py',
                   'test_atomic_cellfix14_workflow.py','test_cellfix14_cell6.py','test_cellfix14_cell7.py','build_colab_cellfix3_fresh.py']
            text=text[:start]+"    files=[TARGET,Path(__file__)]+[ROOT/'scripts'/n for n in "+repr(names)+']'+text[end:]
            text=text.replace("'independent_validation_completed':False,","'independent_validation_completed':False,'validation30_used_for_tuning':True,'evaluation_role':'development',")
            text=text.replace('Chưa dùng bộ này để tune.','Bộ này đã dùng để sửa; chỉ đo development.')
            text=text.replace('Validation gold reused unchanged; new candidate binding verified.','Exposed dev30 gold unchanged; development binding verified.')
        (scripts/new).write_text(text,encoding='utf-8')
    text=(scripts/'atomic_cellfix13_workflow.py').read_text(encoding='utf-8').replace('cellfix13','cellfix14').replace('cf13','cf14')
    text=text.replace('independent_verifier_validation','development_verifier_regression')
    text=text.replace("'evaluation_mode':'development_verifier_regression',","'evaluation_mode':'development_verifier_regression','independent_validation_completed':False,'validation30_used_for_tuning':True,")
    text=text.replace("    score['generated_tokens']=sum(g['generated_tokens'] for g in generations)",
        "    complete_usage=len(generations)==len(traces) and all(g.get('usage_complete',True) and type(g.get('generated_tokens')) is int and type(g.get('prompt_tokens')) is int for g in generations)\n    score['usage_complete']=complete_usage\n    score['generated_tokens']=sum(g['generated_tokens'] for g in generations if type(g.get('generated_tokens')) is int) if complete_usage else None")
    text=text.replace("sum(g['prompt_tokens'] for g in generations)","sum(g['prompt_tokens'] for g in generations if type(g.get('prompt_tokens')) is int) if complete_usage else None")
    text=text.replace("(len(generations)==len(traces) and score['generated_tokens']", "(complete_usage and score['generated_tokens']")
    text=text.replace("elif gen['raw_output']!=trace.get('raw_output') or gen['json_valid'] is not False:",
        "elif gen.get('usage_complete',True) and (gen['raw_output']!=trace.get('raw_output') or gen['json_valid'] is not False):")
    text=text.replace("                r.replay_result(result,case['claim'],case['context'],criteria)",
        "                calls.write(json.dumps({'event':'case_finished','example_id':case['example_id']})+'\\n');calls.flush()\n                r.replay_result(result,case['claim'],case['context'],criteria)")
    text=text.replace('        from research_rag.local import run_worker',
        "        from importlib import import_module\n        run_worker=import_module('04_factchecker.inference.cellfix14_runtime').run_worker")
    (scripts/'atomic_cellfix14_workflow.py').write_text(text,encoding='utf-8')
    text=(scripts/'check_atomic_cellfix13_tokenizer.py').read_text(encoding='utf-8')
    text=text.replace('atomic-cellfix13-candidate','atomic-cellfix14-candidate').replace('atomic-verifier-cellfix13-tokenizer-check','atomic-verifier-cellfix14-tokenizer-check')
    text=text.replace('    from transformers import AutoTokenizer','    from transformers import PreTrainedTokenizerFast')
    text=text.replace('    tokenizer=AutoTokenizer.from_pretrained(folder,local_files_only=True)',
        "    config=json.loads((folder/'tokenizer_config.json').read_bytes())\n    tokenizer=PreTrainedTokenizerFast(tokenizer_file=str(folder/'tokenizer.json'),eos_token=config['eos_token'],pad_token=config['pad_token'],extra_special_tokens=config['extra_special_tokens'],clean_up_tokenization_spaces=False)\n    assert tokenizer.eos_token_id==tokenizer.convert_tokens_to_ids(config['eos_token'])\n    assert all(tokenizer.convert_tokens_to_ids(v) in tokenizer.all_special_ids for v in config['extra_special_tokens'])")
    text=text.replace('    results=[]',
        "    from research_rag.tests.test_atomic_cellfix14 import duration_case\n    for duration in ('half-hour','two-hour'):\n        claim,p,ctx,raw=duration_case(duration)\n        paths.append(('cf14_duration_'+duration,claim,p,ctx,raw,True))\n        bad=deepcopy(raw);bad['observations'][0]['numeric']['q1']=bad['observations'][0]['numeric']['q0']\n        paths.append(('cf14_duration_wrong_slot_'+duration,claim,p,ctx,bad,False))\n    if '--new-only' in sys.argv:paths=[v for v in paths if v[0].startswith('cf14_')]\n    results=[]")
    text=text.replace('assert accepted==expected,(name,accepted,expected)',"assert accepted==expected,(name,accepted,expected,tokenizer.decode(ids[1:])[-200:])")
    text=text.replace("(ROOT/'docs/atomic-verifier-cellfix14-tokenizer-check.json').write_text", "(ROOT/('docs/atomic-verifier-cellfix14-tokenizer-check-focused.json' if '--new-only' in sys.argv else 'docs/atomic-verifier-cellfix14-tokenizer-check.json')).write_text")
    (scripts/'check_atomic_cellfix14_tokenizer.py').write_text(text,encoding='utf-8')
    # Port only notebook I/O. New source/gates remain byte-identical in the payload.
    text=(scripts/'build_kaggle_cellfix13.py').read_text(encoding='utf-8').replace('cellfix13','cellfix14').replace('Cellfix13','Cellfix14')
    text=text.replace("    release = json.loads((ROOT / 'docs/atomic-verifier-cellfix14-release.json').read_bytes())",
        "    catalog=ROOT/'docs/atomic-verifier-cellfix14-release.json'\n    if not catalog.exists():catalog=ROOT/'research-runs/cellfix14-notebook-draft.json'\n    release=json.loads(catalog.read_bytes())")
    start=text.index("INTRO = '''");end=text.index("'''",start+11)+3
    intro="""# Cellfix14 — Kaggle, development30-v1

Candidate mới sửa deadline/trace, decoder–validator, quantity và binding.
Chưa có inference GPU hoặc kết quả 30/30 cho Cellfix14. Bộ30-v1 đã dùng để sửa,
chỉ được ghi là development. Cần holdout khác paper để đo độc lập.
Import notebook private, bật GPU T4 và Internet. Chạy cells1–5, trực tiếp review
probe mới trước cell6, rồi review full39 mới trước cell7. Đặt PROBE_REVIEW_PATH
và FULL39_REVIEW_PATH bằng đường dẫn JSON review thực tế của run mới trên Kaggle.
Cells6/7 mặc định tắt. Không sửa hash, tự ký human review hoặc bỏ ca lỗi.
Lưu ZIP trong /kaggle/working trước khi dừng runtime. Không chạy lại cell1 để resume.
"""
    text=text[:start]+'INTRO = '+repr(intro)+text[end:]
    (scripts/'build_kaggle_cellfix14.py').write_text(text,encoding='utf-8')
    for name in ('test_colab_cellfix13.py','test_atomic_cellfix13_workflow.py','test_cellfix13_cell6.py','test_cellfix13_cell7.py'):
        text=(scripts/name).read_text(encoding='utf-8').replace('cellfix13','cellfix14').replace('Cellfix13','Cellfix14')
        text=text.replace('docs/validation/atomic-cellfix14-v1','docs/validation/atomic-cellfix14-dev30-v1')
        (scripts/name.replace('cellfix13','cellfix14')).write_text(text,encoding='utf-8')


if __name__=='__main__':prepare()
