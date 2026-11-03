import json
from pathlib import Path

downloads = Path(r"c:\Users\dellcuatri142\Downloads")
sr_path = downloads / "semantic-review.json"
data = json.loads(sr_path.read_text(encoding="utf-8"))

print("Reviewer:", data.get("reviewer"))
print("Reviewer kind:", data.get("reviewer_kind"))
print("Review completed:", data.get("review_completed"))
print("Criteria SHA256:", data.get("criteria_sha256"))
print("Predictions SHA256:", data.get("predictions_sha256"))
print("Cases count:", len(data.get("cases", [])))

true_count = sum(sum(1 for v in c["judgments"].values() if v is True) for c in data["cases"])
false_count = sum(sum(1 for v in c["judgments"].values() if v is False) for c in data["cases"])
print(f"Judgments: {true_count} True, {false_count} False, total = {true_count + false_count}")

failed_cases = {}
for c in data["cases"]:
    f = [k for k, v in c["judgments"].items() if not v]
    if f:
        failed_cases[c["example_id"]] = f

print("Failed cases:", json.dumps(failed_cases, indent=2))
print("All notes filled:", all(bool(c["notes"].strip()) for c in data["cases"]))
