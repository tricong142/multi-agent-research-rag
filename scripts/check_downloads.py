import json
from pathlib import Path

downloads = Path(r"c:\Users\dellcuatri142\Downloads")

for f in sorted(downloads.glob("semantic-review*.json")):
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        print(f"{f.name}: reviewer={data.get('reviewer')}, criteria={str(data.get('criteria_sha256'))[:12]}, pred={str(data.get('predictions_sha256'))[:12]}, cases={len(data.get('cases', []))}")
    except Exception as e:
        print(f"{f.name}: error {e}")

for f in sorted(downloads.glob("HUMAN_REVIEW*.html")):
    try:
        t = f.read_text(encoding="utf-8")
        import re
        m = re.search(r"const seed=({.*?});", t)
        if m:
            s = json.loads(m.group(1))
            print(f"{f.name}: criteria={str(s.get('criteria_sha256'))[:12]}, pred={str(s.get('predictions_sha256'))[:12]}")
        else:
            print(f"{f.name}: no seed found")
    except Exception as e:
        print(f"{f.name}: error {e}")
