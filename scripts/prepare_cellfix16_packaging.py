"""Inherit launchers and gates; retain development data and original reviews."""
from pathlib import Path
from scripts.atomic_cellfix15_replay_compat import patch_workflow

ROOT=Path(__file__).resolve().parents[1]


def prepare():
    if (ROOT/'docs/atomic-verifier-cellfix16-release.json').exists():
        raise ValueError('Release is immutable')
    names=['atomic_cellfix15_binding.py','atomic_cellfix15_workflow.py','colab_cellfix15_cell6.py',
           'build_colab_cellfix15.py','build_kaggle_cellfix15.py','test_colab_cellfix15.py',
           'test_atomic_cellfix15_workflow.py','test_cellfix15_cell6.py','test_cellfix15_cell7.py',
           'test_cellfix15_packaging.py','check_cellfix15_packaging.py','check_kaggle_cellfix15.py',
           'check_atomic_cellfix15_tokenizer.py']
    for name in names:
        raw=(ROOT/'scripts'/name).read_bytes()
        if name=='atomic_cellfix15_workflow.py':raw=patch_workflow(raw)
        text=raw.decode('utf-8').replace('\r\n','\n').replace('cellfix15','cellfix16').replace('Cellfix15','Cellfix16')
        if name=='check_atomic_cellfix15_tokenizer.py':
            text=text.replace('research_rag.tests.test_atomic_cellfix16 import token_paths as absence_paths',
                              'research_rag.tests.test_atomic_cellfix15 import token_paths as absence_paths')
            anchor="    if '--new-only' in sys.argv:paths=[v for v in paths if v[0].startswith('cf15_')]"
            addition='''    from research_rag.tests.test_atomic_cellfix16 import cases,received
    for cid in ('005','008','026','029'):
        c,p,raw=received(cid)
        paths.append(('cf16_'+cid+'_received_blocked',c['claim'],p,c['context'],deepcopy(raw),False))
        witness=r.atomic.assessment_issue.__globals__['decision_evidence'](p,c['context'])
        passage=next(q for q in sorted(r.decoding.evidence_passages(c['context']),key=len) if witness['quotes'][0] in q)
        raw['observations'][0].update(member=witness['members'][0],truth='false',quotes=[passage])
        paths.append(('cf16_'+cid+'_counterevidence',c['claim'],p,c['context'],raw,True))
    for cid in ('013','014'):
        c,p,raw=received(cid)
        if cid=='014':
            paths.append(('cf16_014_old_true_blocked',c['claim'],p,c['context'],deepcopy(raw),False))
            raw['observations'][0]['truth']='false'
        paths.append(('cf16_'+cid+'_reported_accuracy',c['claim'],p,c['context'],raw,True))
    c,p,raw=received('007');raw['observations'][0]['numeric']['right']=deepcopy(raw['observations'][0]['numeric']['left'])
    paths.append(('cf16_sari_operand',c['claim'],p,c['context'],raw,True))
    c,p,raw=received('019')
    witness=__import__('importlib').import_module('04_factchecker.inference.cellfix16_rules').population_witness(p,c['context'])
    raw['coverage']=dict(complete=True,members=witness['members'],quotes=witness['quotes'])
    raw['observations'][0].update(member=witness['members'][0],truth='true',quotes=witness['quotes'])
    paths.append(('cf16_collective_closure',c['claim'],p,c['context'],raw,True))
    paths.append(('cf16_collective_unknown_retry',c['claim'],p,c['context'],cases()['019']['traces'][-1]['raw_output'],False))
    c,p,raw=received('011')
    paths.append(('cf16_unbound_count',c['claim'],p,c['context'],deepcopy(raw),False))
    raw['observations'][0].update(member='14,769 actions',truth='false')
    paths.append(('cf16_count_counterexample',c['claim'],p,c['context'],raw,True))
    c,p,raw=received('022')
    source=next(s for s in r.decoding.evidence_passages(c['context']) if 'However, in this study' in s and '980 annotations in 670 tweets in Turkish.' in s)
    numeric=__import__('importlib').import_module('04_factchecker.inference.numeric_verifier')
    records={}
    for i,left in enumerate(numeric.numeric_requirements(p['quote'])):
        right=next(v for v in numeric.numeric_requirements(source) if v['value']==left['value'])
        records['q'+str(i)]=dict(kind='value',source_quote=source,left={k:left[k] for k in ('value','unit','quote')},right={k:right[k] for k in ('value','unit','quote')})
    raw['observations'][0].update(truth='true',quotes=[source],numeric=records)
    paths.append(('cf16_modified_count_units',c['claim'],p,c['context'],raw,True))
    for cid,entity in {'009':'sentence','015':'prediction','020':'80 events','021':'news articles','023':'eight named-entity categories','025':'proposed model'}.items():
        c=cases()[cid];raw=deepcopy(c['traces'][0]['raw_output'])
        paths.append(('cf16_decompose_'+cid+'_received',c['claim'],None,'',deepcopy(raw),cid in ('015','021')))
        raw['parts'][-1]['scope']['entity']=entity
        paths.append(('cf16_decompose_'+cid+'_repaired',c['claim'],None,'',raw,True))
    if '--new-only' in sys.argv:paths=[v for v in paths if v[0].startswith('cf16_')]
'''
            assert text.count(anchor)==1
            text=text.replace(anchor,addition)
            text=text.replace("callback=backend.generation_options(request(claim,p,ctx))['prefix_allowed_tokens_fn']",
                "messages=request(claim,p,ctx) if p is not None else [{'role':'system','content':r.atomic.DECOMPOSE_PROMPT},{'role':'user','content':json.dumps({'claim':claim})}]\n        callback=backend.generation_options(messages)['prefix_allowed_tokens_fn']")
            text=text.replace("text=json.dumps(json.loads(h.AssessmentTokenFilterTests().ordered(raw)),separators=(',',':'))",
                "text=json.dumps(json.loads(h.AssessmentTokenFilterTests().ordered(raw)) if p is not None else raw,separators=(',',':'))")
        if name=='build_colab_cellfix15.py':
            text=text.replace("'fixtures/atomic_cellfix14_member_absence.json'", "'fixtures/atomic_cellfix14_member_absence.json', 'fixtures/cellfix15_validation30.json', 'atomic_cellfix16_rules.py'")
            text=text.replace('Đồng bộ member-local absence guard trong decoder và validator assessment.',
                              'Sửa explicit relations, decomposition, numeric binding và collective evidence; giữ member-local absence guard.')
        if name=='build_kaggle_cellfix15.py':
            text=text.replace('đồng bộ member-local absence guard trong decoder và validator assessment',
                              'sửa explicit relations, decomposition, numeric binding và collective evidence')
        if name=='check_cellfix15_packaging.py':
            text=text.replace("atomic-verifier-cellfix14-candidate.json", "atomic-verifier-cellfix15-candidate.json").replace("atomic-verifier-cellfix14-release.json", "atomic-verifier-cellfix15-release.json")
            text=text.replace("old = (ROOT/'scripts/atomic_cellfix14_workflow.py').read_text(encoding='utf-8')",
                              "from scripts.atomic_cellfix15_replay_compat import patch_workflow\n    old = patch_workflow((ROOT/'scripts/atomic_cellfix15_workflow.py').read_bytes()).decode('utf-8').replace('\\r\\n','\\n')")
            text=text.replace("new.replace('cellfix16','cellfix14')", "new.replace('cellfix16','cellfix15')")
        (ROOT/'scripts'/name.replace('cellfix15','cellfix16')).write_text(text,encoding='utf-8')


if __name__=='__main__':prepare()
