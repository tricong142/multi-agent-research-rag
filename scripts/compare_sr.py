import json
from pathlib import Path

downloads = Path(r"c:\Users\dellcuatri142\Downloads")

for idx in [2, 4, 5, 6]:
    p = downloads / f"semantic-review ({idx}).json"
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
        print(f"=== ({idx}) ===")
        print("Top keys:", list(data.keys()))
        print("criteria:", data.get("criteria_sha256"))
        print("pred:", data.get("predictions_sha256"))
        print("reviewer:", data.get("reviewer"))
        print("reviewer_kind:", data.get("reviewer_kind"))
        print("review_completed:", data.get("review_completed"))
        c0 = data["cases"][0]
        print("case 0 keys:", list(c0.keys()))
        print("case 0 judgments:", c0.get("judgments"))
