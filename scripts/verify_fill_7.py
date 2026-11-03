import json
from pathlib import Path

downloads = Path(r"c:\Users\dellcuatri142\Downloads")

# 1. Check HTML
html_text = (downloads / "HUMAN_REVIEW (7).html").read_text(encoding="utf-8")
print("HTML Reviewer name present:", 'value="Trí Công"' in html_text)
print("HTML Done checked present:", '<input id="done" type="checkbox" checked>' in html_text)
print("HTML Checked checkboxes count (expected 90):", html_text.count('checked data-key='))
print("HTML Empty textareas count (expected 0):", html_text.count('placeholder="Ghi chú bắt buộc"></textarea>'))

# 2. Check JSONs
for name in ["semantic-review(7).json", "semantic-review (7).json"]:
    f = downloads / name
    data = json.loads(f.read_text(encoding="utf-8"))
    print(f"\n--- Checking {name} ---")
    print("reviewer:", data.get("reviewer"))
    print("reviewer_kind:", data.get("reviewer_kind"))
    print("review_completed:", data.get("review_completed"))
    print("criteria_sha256:", data.get("criteria_sha256"))
    print("predictions_sha256:", data.get("predictions_sha256"))
    print("cases count:", len(data.get("cases", [])))
    all_judgments_ok = all(all(v is True for v in c["judgments"].values()) and len(c["judgments"]) == 5 for c in data["cases"])
    all_notes_ok = all(bool(c["notes"].strip()) and "C1:" in c["notes"] and "C5:" in c["notes"] for c in data["cases"])
    print("All judgments True (5/5 for 18 cases):", all_judgments_ok)
    print("All notes complete (C1-C5):", all_notes_ok)
