import json
from pathlib import Path

p = Path(r"c:\Users\dellcuatri142\Downloads\semantic-review (3).json")
d = json.loads(p.read_text(encoding="utf-8"))
print("Reviewer:", d.get("reviewer"))
print("Reviewer kind:", d.get("reviewer_kind"))
print("Criteria sha:", d.get("criteria_sha256"))
print("Predictions sha:", d.get("predictions_sha256"))
print("Cases count:", len(d.get("cases", [])))

