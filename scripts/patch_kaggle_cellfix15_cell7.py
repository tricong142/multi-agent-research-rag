"""Change only cell7 I/O orchestration; preserve frozen payload and producer metrics."""
import copy
import hashlib
import json
from pathlib import Path

from scripts.atomic_cellfix15_replay_compat import ORIGINAL_SHA256,BEFORE,AFTER,patch_workflow

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'scripts/kaggle_atomic_verifier_cellfix15.ipynb'
CELL=ROOT/'scripts/kaggle_cellfix15_cell7_replay_compat.py'
TARGET=ROOT/'scripts/kaggle_atomic_verifier_cellfix15_cell7_fix.ipynb'


def helper():
    raw=(ROOT/'scripts/atomic_cellfix15_workflow.py').read_bytes()
    expected=hashlib.sha256(patch_workflow(raw)).hexdigest()
    return '''
def _cell7_replay_worker():
    import hashlib
    import json
    from pathlib import Path
    original=root/'atomic_workflow_cellfix15.py'
    raw=original.read_bytes()
    original_sha=hashlib.sha256(raw).hexdigest()
    if original_sha != '''+repr(ORIGINAL_SHA256)+''':
        raise ValueError('Expected the original frozen Cellfix15 workflow')
    if manifest['atomic_workflow_cellfix15.py']['sha256'] != original_sha:
        raise ValueError('Workflow differs from the frozen input manifest')
    newline='\\r\\n' if b'\\r\\n' in raw else '\\n'
    before='''+repr(BEFORE)+'''.replace('\\n',newline)
    after='''+repr(AFTER)+'''.replace('\\n',newline)
    text=raw.decode('utf-8')
    if text.count(before)!=1:
        raise ValueError('Replay comparison anchor changed')
    patched=text.replace(before,after,1).encode('utf-8')
    patched_sha=hashlib.sha256(patched).hexdigest()
    if patched_sha != '''+repr(expected)+''':
        raise ValueError('Unexpected compatibility worker bytes')
    folder=out/'compatibility/cellfix15-full39-replay-v1'
    worker=folder/'atomic_workflow_cellfix15.py'
    compile(patched,str(worker),'exec')
    record={'version':'cellfix15-full39-replay-compat-v1',
            'criteria_sha256':criteria_sha256,'original_workflow_sha256':original_sha,
            'compatibility_workflow_sha256':patched_sha,
            'change':'omit replay-only usage_complete only when recomputed True and absent from producer metrics',
            'producer_metrics_modified':False,'frozen_inputs_modified':False}
    metadata=(json.dumps(record,indent=2)+'\\n').encode('utf-8')
    # Preserve previous attempts and the original frozen workflow.
    for path,data in ((worker,patched),(folder/'compatibility.json',metadata)):
        if path.exists() and path.read_bytes()!=data:
            raise ValueError('Preserve existing compatibility artifact: '+str(path))
    folder.mkdir(parents=True,exist_ok=True)
    for path,data in ((worker,patched),(folder/'compatibility.json',metadata)):
        if not path.exists():path.write_bytes(data)
    print('Using recorded full39 replay compatibility:',patched_sha)
    return str(worker)

'''


def build():
    original=SOURCE.read_bytes()
    assert hashlib.sha256(original).hexdigest()=='2a8ee31ff7fe7558f0ad63caa4a9ba60789d189214fdd438afe75b4a47f1ee6a'
    book=json.loads(original);indices=[i for i,c in enumerate(book['cells']) if c['cell_type']=='code']
    assert len(indices)==7
    index=indices[6];code=''.join(book['cells'][index]['source'])
    anchor="        worker=str(root/'atomic_workflow_cellfix15.py')\n"
    assert code.count(anchor)==1
    code=code.replace(anchor,'        worker=_cell7_replay_worker()\n',1)
    # Preserve explicit review input, default-off flag, admission retries and inference guards.
    code=helper()+code
    compile(code,'kaggle-cell7-replay-compat','exec')
    CELL.write_text(code,encoding='utf-8')
    patched=copy.deepcopy(book);patched['cells'][index]['source']=code
    assert all(a==b for i,(a,b) in enumerate(zip(book['cells'],patched['cells'])) if i!=index)
    assert patched['metadata']==book['metadata']
    TARGET.write_text(json.dumps(patched,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    assert SOURCE.read_bytes()==original
    print(json.dumps({'cell':str(CELL),'notebook':str(TARGET),'changed_code_cells':[7],
        'original_notebook_sha256':hashlib.sha256(original).hexdigest(),
        'frozen_payload_unchanged':True,'validation_default_disabled':True}))


if __name__=='__main__':build()
