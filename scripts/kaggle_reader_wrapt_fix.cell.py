# Paste into ONE cell after the successful endpoint setup, before cell 2.
# No Gemini requests; preserves the original setup record and logs this repair.
assert all(name in globals() for name in ('out', 'python', 'setup_status', 'find_bootstrap_pip', 'bundle_endpoint')), 'Use the existing endpoint notebook session after cell 1'
assert not (out / 'status.json').exists() and not (out / 'probe').exists(), 'Preserve the attempted probe; do not change its environment'
assert not (out / 'setup-before-wrapt.json').exists(), 'This repair was already attempted; preserve the ZIP'
with (out / 'setup-before-wrapt.json').open('x') as handle:
    handle.write((out / 'setup-status.json').read_text())
setup_status.update(state='running', stage='install_wrapt')
(out / 'setup-status.json').write_text(json.dumps(setup_status, indent=2))
try:
    with (out / 'wrapt.stdout.log').open('x') as stdout, (out / 'wrapt.stderr.log').open('x') as stderr:
        subprocess.run(find_bootstrap_pip() + ['--python', python, 'install', '--disable-pip-version-check', 'wrapt==2.1.2'],
                       stdout=stdout, stderr=stderr, check=True, timeout=180)
    setup_status['stage'] = 'validate_wrapt'
    smoke = subprocess.run([python, '-c', "from importlib.metadata import version; import wrapt, httpx, pydantic; from google import genai; assert version('wrapt') == '2.1.2'"],
                           capture_output=True, text=True, timeout=60)
    with (out / 'wrapt.stdout.log').open('a') as stdout, (out / 'wrapt.stderr.log').open('a') as stderr:
        stdout.write(smoke.stdout)
        stderr.write(smoke.stderr)
    smoke.check_returncode()
    if 'Error in sitecustomize' in smoke.stderr:
        raise RuntimeError('sitecustomize still fails; preserve wrapt.stderr.log in the ZIP')
    setup_status['stage'] = 'freeze_after_wrapt'
    with (out / 'freeze-after-wrapt.stdout.log').open('x') as handle:
        subprocess.run([python, '-m', 'pip', 'freeze'], stdout=handle, check=True, timeout=30)
    setup_status.update(state='completed', stage='complete', wrapt='2.1.2')
except BaseException as exc:
    setup_status.update(state='failed', error_type=type(exc).__name__)
    if isinstance(exc, subprocess.CalledProcessError): setup_status['exit_code'] = exc.returncode
    raise
finally:
    (out / 'setup-status.json').write_text(json.dumps(setup_status, indent=2))
    bundle_endpoint()
print('ENV_OK: wrapt and SDK imports passed without sitecustomize errors. Run original cell 2 once.')
