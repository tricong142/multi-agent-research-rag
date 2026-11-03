"""Paste as one cell in the existing Cellfix15 runtime. Preserve every attempt."""
import json
from pathlib import Path
from datetime import datetime, timezone
import uuid


def _validation30_read(path):
    if not path.exists():return {}
    try:
        value=json.loads(path.read_text())
        if isinstance(value,dict):return value
    except (json.JSONDecodeError,UnicodeDecodeError):
        pass
    print('Incomplete JSON preserved:',path)
    return {}


def _validation30_attempts():
    names = {n for n in statuses if n == 'validation30' or n.startswith('validation30-retry-')}
    names.update(p.name for p in out.glob('validation30*') if p.is_dir())
    for suffix in ('.stdout.log', '.stderr.log'):
        names.update(p.name[:-len(suffix)] for p in out.glob('validation30*'+suffix))
    disk = _validation30_read(out/'status.json')
    names.update(n for n in disk if n == 'validation30' or n.startswith('validation30-retry-'))
    completed, running = [], []
    for name in sorted(names):
        states = [s[name] for s in (statuses,disk) if name in s]
        if any(s.get('state') == 'running' for s in states):
            running.append(name)
        folder = out/name
        summary = _validation30_read(folder/'summary.json')
        metrics = _validation30_read(folder/'metrics.json')
        print('Previous attempt:', name, states, 'completed:', summary.get('experiment_completed',False))
        if metrics:
            print(json.dumps(metrics, indent=2))
        if summary.get('experiment_completed') is True and summary.get('prediction_count') == 30 and metrics.get('n') == 30:
            completed.append(folder)
    return sorted(names), completed, running


try:
    require_validation_binding()
    previous, completed, running = _validation30_attempts()
    if running:
        raise ValueError('Validation30 is marked running; do not start another worker: '+', '.join(running))
    if completed:
        print('Validation30 already finished. Metrics above include every completed attempt; no new inference started.')
        for folder in completed:
            for name in ('classification.json','summary.json'):
                if (folder/name).exists():
                    print(str(folder/name), (folder/name).read_text())
            if (folder/'HUMAN_REVIEW.html').exists():
                show_file(str(folder/'HUMAN_REVIEW.html'))
    else:
        # This helper was defined before the earlier cell7 stopped at the attempt guard.
        worker = _cell7_replay_worker()
        full39, probe = out/'reviewed-verifier39', out/'reviewed-probe'
        if not (full39/'semantic-review.json').is_file() or not (probe/'semantic-review.json').is_file():
            raise ValueError('The admitted full39/probe reviews are missing from this runtime. Preserve the ZIP.')

        stage = 'validation30-retry-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
        target = out/stage
        if target.exists() or stage in statuses or any((out/(stage+s)).exists() for s in ('.stdout.log','.stderr.log')):
            raise ValueError('Attempt name collision; preserve existing files.')

        # Replay/admission only: this command does not run model inference on full39.
        run(stage+'-admission', [python,worker,'--admit-full39',
            '--full39-dir',str(full39),'--probe-dir',str(probe)], timeout=300)

        record = out/(stage+'.retry.json')
        with record.open('x',encoding='utf-8') as stream:
            json.dump({'run_id':run_id,'stage':stage,'previous_attempts':previous,
                'reason':'user_requested_retry_after_existing_attempt_guard',
                'criteria_sha256':criteria_sha256,'evaluation_role':'development',
                'original_attempts_preserved':True,'model_and_budget_unchanged':True},stream,indent=2)
        bundle()
        print('Running only Validation30 in:', target, flush=True)
        code = run(stage,[python,'-u',worker,'--output-dir',str(target),
            '--probe-dir',str(probe),'--full39-dir',str(full39),
            '--binding-dir',str(root/'validation/cellfix15'),'--online-model-downloads'],
            timeout=5520,required=False)

        for name in ('metrics.json','classification.json','summary.json'):
            path=target/name
            print(str(path), path.read_text() if path.exists() else 'Incomplete; keep diagnostics.')
        if code != 0:
            stderr=out/(stage+'.stderr.log')
            if stderr.exists():print(stderr.read_text()[-12000:])
            print('Validation30 has not passed. Preserve all attempts and the ZIP.')
        if (target/'HUMAN_REVIEW.html').exists():
            show_file(str(target/'HUMAN_REVIEW.html'))
finally:
    download_archive()
