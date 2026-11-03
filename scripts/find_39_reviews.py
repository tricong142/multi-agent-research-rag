import json
from pathlib import Path

repo = Path(r"c:\Users\dellcuatri142\Downloads\AI ENGINEER")
for p in repo.glob("**/*semantic-review*.json"):
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        cases = d.get("cases", [])
        if len(cases) == 39:
            print(f"{p.relative_to(repo)}: reviewer={d.get('reviewer')}, completed={d.get('review_completed')}")
    except Exception as e:
        pass
