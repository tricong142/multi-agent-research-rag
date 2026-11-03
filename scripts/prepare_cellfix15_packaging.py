"""Inherit frozen launchers; only candidate identity and documentation change."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def prepare():
    if (ROOT/'docs/atomic-verifier-cellfix15-release.json').exists():
        raise ValueError('Released launchers are immutable')
    scripts = ROOT/'scripts'
    names = ['check_atomic_cellfix14.py','check_atomic_cellfix14_tokenizer.py',
        'atomic_cellfix14_binding.py','atomic_cellfix14_workflow.py','colab_cellfix14_cell6.py',
        'build_colab_cellfix14.py','build_kaggle_cellfix14.py','test_colab_cellfix14.py',
        'test_atomic_cellfix14_workflow.py','test_cellfix14_cell6.py','test_cellfix14_cell7.py',
        'test_cellfix14_packaging.py']
    for name in names:
        text = (scripts/name).read_text(encoding='utf-8')
        text = text.replace('cellfix14','cellfix15').replace('Cellfix14','Cellfix15')
        if name == 'atomic_cellfix14_workflow.py':
            # Runtime watchdog implementation is inherited byte-for-byte.
            text = text.replace('inference.cellfix15_runtime','inference.cellfix14_runtime')
        if name == 'check_atomic_cellfix14_tokenizer.py':
            text = text.replace('from research_rag.tests.test_atomic_cellfix15 import duration_case',
                                'from research_rag.tests.test_atomic_cellfix14 import duration_case')
            text = text.replace("    if '--new-only' in sys.argv:paths=[v for v in paths if v[0].startswith('cf14_')]",
                "    from research_rag.tests.test_atomic_cellfix15 import token_paths as absence_paths\n"
                "    paths += [('cf15_'+name,claim,p,ctx,raw,expected) for name,claim,p,ctx,raw,expected in absence_paths()]\n"
                "    if '--new-only' in sys.argv:paths=[v for v in paths if v[0].startswith('cf15_')]")
        if name == 'build_colab_cellfix14.py':
            start = text.index('    files=[TARGET');end = text.index('\n    record=',start)
            files = ['build_atomic_cellfix15_candidate.py','check_atomic_cellfix15.py','check_atomic_cellfix15_tokenizer.py',
                'atomic_cellfix15_binding.py','atomic_cellfix15_workflow.py','colab_cellfix15_cell6.py','test_atomic_cellfix15.py',
                'fixtures/atomic_cellfix14_member_absence.json','prepare_cellfix15_packaging.py','test_cellfix15_packaging.py',
                'test_colab_cellfix15.py','test_atomic_cellfix15_workflow.py','test_cellfix15_cell6.py','test_cellfix15_cell7.py','check_cellfix15_packaging.py','check_kaggle_cellfix15.py','build_kaggle_cellfix15.py',
                'build_atomic_cellfix14_candidate.py','build_colab_cellfix3_fresh.py']
            text = text[:start]+"    files=[TARGET,Path(__file__)]+[ROOT/'scripts'/n for n in "+repr(files)+']'+text[end:]
            text = text.replace('Sửa quantity/binding, schema lượng từ theo part, deadline/filter và trace lỗi.',
                                'Đồng bộ member-local absence guard trong decoder và validator assessment.')
        if name == 'build_kaggle_cellfix14.py':
            text = text.replace('Candidate mới sửa deadline/trace, decoder–validator, quantity và binding.',
                                'Candidate mới đồng bộ member-local absence guard trong decoder và validator assessment.')
        (scripts/name.replace('cellfix14','cellfix15')).write_text(text,encoding='utf-8')
    text = (scripts/'check_kaggle_cellfix13.py').read_text(encoding='utf-8').replace('cellfix13','cellfix15')
    text = text.replace("    release = json.loads((ROOT / 'docs/atomic-verifier-cellfix15-release.json').read_bytes())",
        "    catalog=ROOT/'docs/atomic-verifier-cellfix15-release.json'\n"
        "    if not catalog.exists():catalog=ROOT/'research-runs/cellfix15-notebook-draft.json'\n"
        "    release=json.loads(catalog.read_bytes())")
    (scripts/'check_kaggle_cellfix15.py').write_text(text,encoding='utf-8')


if __name__ == '__main__':
    prepare()
