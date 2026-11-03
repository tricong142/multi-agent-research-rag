import json
import re
from pathlib import Path

html_path = Path(r"c:\Users\dellcuatri142\Downloads\HUMAN_REVIEW (7).html")
text = html_path.read_text(encoding="utf-8")

m = re.search(r"const seed=({.*?});", text)
if m:
    seed = json.loads(m.group(1))
    print("Seed keys:", list(seed.keys()))
    print("criteria_sha256:", seed.get("criteria_sha256"))
    print("predictions_sha256:", seed.get("predictions_sha256"))
    print("num cases:", len(seed.get("cases", [])))
    print("sample case:", json.dumps(seed["cases"][0], ensure_ascii=False, indent=2))
else:
    print("No seed found in HUMAN_REVIEW (7).html")
