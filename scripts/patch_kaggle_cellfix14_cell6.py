"""Change only code cell 6; preserve the released notebook and embedded payload."""
import copy
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'scripts/kaggle_atomic_verifier_cellfix14.ipynb'
CELL=ROOT/'scripts/kaggle_cellfix14_cell6_review_upload.py'
TARGET=ROOT/'scripts/kaggle_atomic_verifier_cellfix14_cell6_fix.ipynb'

HELPER='''
def _cell6_probe_review_input(probe, binding_key):
    # An explicit path remains supported; never search for or select an old review.
    if PROBE_REVIEW_PATH and str(PROBE_REVIEW_PATH).strip():
        return read_review(PROBE_REVIEW_PATH)

    state = globals().get('_cellfix14_probe_review_upload')
    if not isinstance(state, dict) or state.get('binding_key') != binding_key:
        state = None
    if state is not None and state['widget'].value:
        value = state['widget'].value
        # ipywidgets 7 maps names to records; version 8 returns a tuple of records.
        if len(value) != 1:
            raise ValueError('Select exactly one exported probe semantic-review.json.')
        if isinstance(value, dict):
            name, item = next(iter(value.items()))
        else:
            item = value[0]
            name = item.get('name', 'semantic-review.json')
        content = item.get('content')
        if not isinstance(content, (bytes, bytearray, memoryview)):
            raise ValueError('The uploaded review has no binary content. Select the JSON file again.')
        return {str(name): bytes(content)}

    form = probe / 'HUMAN_REVIEW.html'
    print('CHUA CO REVIEW: full39 chua chay; khong co model call nao duoc gui.')
    if form.is_file():
        print('Tai form cua dung probe hien tai, review truc tiep va xuat semantic-review.json:')
        show_file(str(form))
    try:
        import ipywidgets as widgets
        from IPython.display import display
    except ImportError:
        print('Runtime khong co upload widget. Dua JSON len Kaggle Input hoac /kaggle/working,')
        print('dien duong dan tuyet doi vao PROBE_REVIEW_PATH, roi chay lai RIENG cell 6.')
        return None
    if state is None:
        state = {'binding_key': binding_key,
                 'widget': widgets.FileUpload(accept='.json', multiple=False, description='Upload review')}
        globals()['_cellfix14_probe_review_upload'] = state
    display(state['widget'])
    print('Chon JSON review bang nut Upload review. Doi upload xong, roi chay lai RIENG cell 6.')
    print('Neu nut khong hien thi, dung PROBE_REVIEW_PATH. Khong chay lai cell 1 de tiep tuc run nay.')
    return None

'''


def build():
    original=SOURCE.read_bytes();book=json.loads(original)
    indices=[i for i,c in enumerate(book['cells']) if c['cell_type']=='code']
    assert len(indices)==7
    index=indices[5];code=''.join(book['cells'][index]['source'])
    anchor='        uploaded = read_review(PROBE_REVIEW_PATH)\n'
    assert code.count(anchor)==1
    start=code.index(anchor);end=code.rindex('    finally:\n')
    remaining=code[start+len(anchor):end]
    replacement=("        uploaded = _cell6_probe_review_input(probe, (run_id, expected_criteria, expected_predictions))\n"
                 "        if uploaded is not None:\n"+
                 ''.join('    '+line if line.strip() else line for line in remaining.splitlines(keepends=True)))
    code=code[:start]+replacement+code[end:]
    marker='full39_passed = False\n'
    assert code.count(marker)==1
    code=code.replace(marker,marker+'\n'+HELPER,1)
    compile(code,'kaggle-cell6-review-fix','exec')
    CELL.write_text(code,encoding='utf-8')
    patched=copy.deepcopy(book);patched['cells'][index]['source']=code
    assert all(a==b for i,(a,b) in enumerate(zip(book['cells'],patched['cells'])) if i!=index)
    assert patched['metadata']==book['metadata']
    TARGET.write_text(json.dumps(patched,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    assert SOURCE.read_bytes()==original
    print(json.dumps({'cell':str(CELL),'notebook':str(TARGET),'changed_code_cells':[6],
        'original_notebook_sha256':hashlib.sha256(original).hexdigest(),'payload_unchanged':True}))


if __name__=='__main__':build()
