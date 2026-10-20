"""Historical v7 tests compare released bytes with the preserved checkout."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = Path(json.loads((ROOT / 'docs/atomic-verifier-v7-preserved-before-next-candidate.json').read_text())['snapshot'])


def v7_file(relative):
    preserved = SNAPSHOT / relative
    return preserved if preserved.is_file() else ROOT / relative
