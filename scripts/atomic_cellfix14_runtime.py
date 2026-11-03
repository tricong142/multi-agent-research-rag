"""Request-local memoization and deadlines for expensive constrained decoding."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import json
import signal
import threading
import time

_request=ContextVar('decode_request',default=None)


def check_deadline():
    state=_request.get()
    if state and state['deadline'] is not None and time.monotonic()>=state['deadline']:
        from .atomic_verifier import CaseDeadlineExceeded
        raise CaseDeadlineExceeded()


def cached(function):
    @wraps(function)
    def call(*args,**kwargs):
        check_deadline()
        state=_request.get()
        if state is None:return function(*args,**kwargs)
        key=(function.__module__,function.__qualname__,json.dumps([args,kwargs],sort_keys=True))
        if key not in state['cache']:state['cache'][key]=function(*args,**kwargs)
        check_deadline()
        return state['cache'][key]
    return call


@contextmanager
def decode_request(deadline):
    token=_request.set({'deadline':deadline,'cache':{}})
    # POSIX alarm interrupts Python schema/filter work; the outer worker watchdog
    # remains responsible for native code that does not return to Python.
    armed=(deadline is not None and hasattr(signal,'setitimer') and threading.current_thread() is threading.main_thread()
           and signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0))
    previous=None
    if armed:
        previous=signal.getsignal(signal.SIGALRM)
        def expired(*_):
            from .atomic_verifier import CaseDeadlineExceeded
            raise CaseDeadlineExceeded()
        signal.signal(signal.SIGALRM,expired)
        signal.setitimer(signal.ITIMER_REAL,max(.001,deadline-time.monotonic()))
    try:
        check_deadline()
        yield
    finally:
        if armed:
            signal.setitimer(signal.ITIMER_REAL,0)
            signal.signal(signal.SIGALRM,previous)
        _request.reset(token)


def run_worker(command,timeout_seconds):
    """Supervise only our own child; an unresponsive native call cannot hold the GPU forever."""
    import subprocess
    from pathlib import Path
    import psutil
    if '--output-dir' in command:
        output=Path(command[command.index('--output-dir')+1])
    else:
        output=next((Path(arg.split('=',1)[1]) for arg in command if arg.startswith('--output-dir=')),None)
    worker=subprocess.Popen(command)
    deadline=time.monotonic()+timeout_seconds
    offset=0;pending=b'';case_deadline=None;case_id=None;reason=None
    try:
        while worker.poll() is None:
            trace=output/'calls.jsonl' if output else None
            if trace is not None and trace.exists():
                with trace.open('rb') as handle:
                    handle.seek(offset);pending+=handle.read();offset=handle.tell()
                lines=pending.split(b'\n');pending=lines.pop()
                for line in lines:
                    if not line:continue
                    event=json.loads(line)
                    if event.get('event')=='call_started':
                        case_deadline=event.get('case_deadline_monotonic')
                        if case_deadline is None and event.get('case_deadline_unix') is not None:
                            case_deadline=time.monotonic()+max(0,event['case_deadline_unix']-time.time())
                        case_id=event.get('example_id')
                    elif event.get('event')=='case_finished' and event.get('example_id')==case_id:
                        case_deadline=None
            if time.monotonic()>=deadline:reason='process_timeout';break
            if case_deadline is not None and time.monotonic()>=case_deadline:
                reason='case_watchdog_timeout';break
            time.sleep(.05)
        if reason is None:return worker.wait()
    except BaseException:
        reason='supervisor_interrupted'
        raise
    finally:
        if reason is not None and worker.poll() is None:
            try:children=psutil.Process(worker.pid).children(recursive=True)
            except psutil.NoSuchProcess:children=[]
            worker.kill()
            for child in children:
                try:child.kill()
                except psutil.NoSuchProcess:pass
            worker.wait();psutil.wait_procs(children,timeout=5)
            if output and output.exists():
                record={'stop_reason':reason,'example_id':case_id,'usage_complete':False,
                        'note':'Worker terminated; unfinished output/usage remains unknown, never zero.'}
                (output/'watchdog.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    return 124
