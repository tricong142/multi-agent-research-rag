import json
import re
from pathlib import Path

p = Path(r"c:\Users\dellcuatri142\Downloads\HUMAN_REVIEW (4).html")
text = p.read_text(encoding="utf-8")
m = re.search(r"const seed=({.*?});", text)
seed = json.loads(m.group(1))

print("Total cases:", len(seed["cases"]))
for i, c in enumerate(seed["cases"]):
    print(f"{i+1:02d}. {c['example_id']}")

