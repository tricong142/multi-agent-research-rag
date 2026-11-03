"""Narrow compatibility for the frozen full39 producer's metrics schema."""
import hashlib

ORIGINAL_SHA256 = '64a838b28d187c795a16edfa525786680539e729e6255f5d45c74546f450f9ee'
BEFORE = "    if score!=read(directory/'metrics.json') or not score['automated_gate_pass']:\n"
AFTER = """    stored=read(directory/'metrics.json')
    # Full39 producer omits this diagnostic; only verified complete usage may omit it.
    if 'usage_complete' not in stored and score.get('usage_complete') is True:
        score={k:v for k,v in score.items() if k!='usage_complete'}
    if score!=stored or not score['automated_gate_pass']:
"""


def patch_workflow(raw):
    if hashlib.sha256(raw).hexdigest() != ORIGINAL_SHA256:
        raise ValueError('Expected the original frozen Cellfix15 workflow')
    text = raw.decode('utf-8')
    newline = '\r\n' if b'\r\n' in raw else '\n'
    before,after = (v.replace('\n',newline) for v in (BEFORE,AFTER))
    if text.count(before) != 1:
        raise ValueError('Replay comparison anchor changed')
    return text.replace(before,after,1).encode('utf-8')
