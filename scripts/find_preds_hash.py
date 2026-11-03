import hashlib
import json
from pathlib import Path

repo = Path(r"c:\Users\dellcuatri142\Downloads\AI ENGINEER")

for p in repo.glob("research-runs/**/decomposition-probe/predictions.jsonl"):
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    print(sha[:16], p.relative_to(repo))
