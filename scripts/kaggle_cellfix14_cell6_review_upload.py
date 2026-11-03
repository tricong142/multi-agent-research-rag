PROBE_REVIEW_PATH = ""  # Absolute path to the new probe human review JSON.
# Kaggle: review the current probe before enabling full39.
RUN_FULL39 = False
full39_passed = False


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


if not RUN_FULL39:
    print('FULL39 CHUA CHAY. Hoan tat human review cua probe hien tai truoc.')
else:
    try:
        import hashlib
        import json
        import shutil
        import tempfile
        from pathlib import Path

        require_validation_binding()
        probe = out / 'decomposition-probe'
        reviewed_probe = out / 'reviewed-probe'
        full_dir = out / 'verifier39'
        if (full_dir.exists() or 'verifier39' in statuses
                or any((out / ('verifier39' + suffix)).exists()
                       for suffix in ('.stdout.log', '.stderr.log'))):
            raise ValueError(
                'A verifier39 attempt already exists in files/statuses. Preserve its ZIP/results; this cell '
                'does not overwrite or automatically rerun a full39 attempt.')
        if not (probe / 'metrics.json').exists():
            raise ValueError('Probe18 must pass before full39.')
        metrics = json.loads((probe / 'metrics.json').read_text(encoding='utf-8'))
        if (statuses.get('decomposition-probe', {}).get('exit_code') != 0
                or metrics.get('automated_gate_pass') is not True
                or metrics.get('n') != 18 or metrics.get('valid_decompositions') != 18):
            raise ValueError('Probe18 must pass before full39.')

        expected_criteria = hashlib.sha256((probe / 'criteria.json').read_bytes()).hexdigest()
        expected_predictions = hashlib.sha256((probe / 'predictions.jsonl').read_bytes()).hexdigest()
        print('Current runtime run_id:', run_id)
        print('Expected criteria_sha256:', expected_criteria)
        print('Expected predictions_sha256:', expected_predictions)
        uploaded = _cell6_probe_review_input(probe, (run_id, expected_criteria, expected_predictions))
        if uploaded is not None:
            if len(uploaded) != 1:
                raise ValueError('Upload exactly one human semantic-review.json.')
            review_bytes = next(iter(uploaded.values()))
            review = json.loads(review_bytes)
            if not isinstance(review, dict):
                raise ValueError('Human review must be a JSON object.')
            print('Review run_id (informational):', review.get('run_id', '(not recorded)'))
            print('Review predictions_sha256:', review.get('predictions_sha256'))
            if (review.get('criteria_sha256') != expected_criteria
                    or review.get('predictions_sha256') != expected_predictions):
                show_file(str(probe / 'HUMAN_REVIEW.html'))
                raise ValueError(
                    'Review does not match this candidate/probe. The current runtime '
                    'HUMAN_REVIEW.html was downloaded. Read that form and export a new '
                    'human review; do not edit hashes/run_id in an old review.')

            # Keep each uploaded review by its digest, including a failed admission.
            attempts = out / 'review-attempts'
            attempts.mkdir(exist_ok=True)

            def preserve_review(raw):
                path = attempts / (hashlib.sha256(raw).hexdigest() + '.json')
                if path.exists() and path.read_bytes() != raw:
                    raise ValueError('Preserved review digest collision.')
                if not path.exists():
                    path.write_bytes(raw)

            def probe_files(directory):
                return {p.relative_to(directory).as_posix(): p.read_bytes()
                        for p in directory.rglob('*') if p.is_file()
                        and p.relative_to(directory).as_posix() != 'semantic-review.json'}

            if reviewed_probe.exists() and probe_files(reviewed_probe) != probe_files(probe):
                raise ValueError(
                    'Existing reviewed-probe differs from the current probe beyond '
                    'semantic-review.json. Preserve the diagnostic ZIP for inspection.')
            preserve_review(review_bytes)

            def unused_stage(stem):
                # Admission can be retried; each attempt keeps its own status/logs.
                name, attempt = stem, 0
                while (name in statuses or any((out / (name + suffix)).exists()
                        for suffix in ('.stdout.log', '.stderr.log'))):
                    attempt += 1
                    name = stem + '-retry-' + str(attempt)
                return name

            def admit(directory, stage):
                command = (
                    'import json; from pathlib import Path; '
                    'from research_rag.evaluation.evaluate_atomic_verifier import require_probe_review; '
                    'print(json.dumps(require_probe_review(Path(' + repr(str(directory)) + '))))')
                run(unused_stage(stage), [python, '-c', command], timeout=300)

            # Check the original frozen human gate before changing canonical review.
            with tempfile.TemporaryDirectory(prefix='probe-review-preflight-', dir=str(out)) as temp:
                staged = Path(temp) / 'probe'
                shutil.copytree(probe, staged)
                (staged / 'semantic-review.json').write_bytes(review_bytes)
                admit(staged, 'probe-admission-preflight')

            if not reviewed_probe.exists():
                shutil.copytree(probe, reviewed_probe)
            review_path = reviewed_probe / 'semantic-review.json'
            if review_path.exists() and review_path.read_bytes() != review_bytes:
                preserve_review(review_path.read_bytes())
            if not review_path.exists() or review_path.read_bytes() != review_bytes:
                review_path.write_bytes(review_bytes)
            admit(reviewed_probe, 'probe-admission')

            code = run('verifier39', [
                python, '-u', '-m', 'research_rag.evaluation.evaluate_atomic_verifier',
                '--output-dir', str(full_dir), '--probe-dir', str(reviewed_probe),
                '--online-model-downloads'], timeout=5520, required=False)
            path = full_dir / 'metrics.json'
            metrics = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
            print(json.dumps(metrics, indent=2))
            full39_passed = (
                code == 0 and metrics.get('automated_gate_pass') is True
                and metrics.get('n') == 39 and metrics.get('correct_labels') == 39
                and metrics.get('false_support') == 0 and metrics.get('runtime_failed_rows') == 0)
            if full39_passed:
                run('full39-review-form', [
                    python, str(root / 'atomic_workflow_cellfix14.py'),
                    '--make-review', str(full_dir), '--review-mode', 'full39'], timeout=300)
                show_file(str(full_dir / 'HUMAN_REVIEW.html'))
                print('Full39 passed. Review all 39 cases before enabling validation30.')
            else:
                print('Full39 has not passed. Preserve the ZIP; keep RUN_VALIDATION30=False.')
    finally:
        download_archive()
