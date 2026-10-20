from pathlib import Path

t = Path("../HUMAN_REVIEW (1).html").read_text(encoding="utf-8")
print("Reviewer name present:", 'value="Trí Công"' in t)
print("Done checked present:", '<input id="done" type="checkbox" checked>' in t)
print("Checked checkboxes count:", t.count('checked data-key='))
print("Empty textareas count:", t.count('placeholder="Ghi chú bắt buộc"></textarea>'))

# Check semantic-review.json
sr = Path("../semantic-review.json").read_text(encoding="utf-8")
import json
data = json.loads(sr)
print("semantic-review.json reviewer:", data.get("reviewer"))
print("semantic-review.json reviewer_kind:", data.get("reviewer_kind"))
print("semantic-review.json review_completed:", data.get("review_completed"))
print("semantic-review.json cases count:", len(data.get("cases", [])))
print("semantic-review.json all judgments true:", all(all(v is True for v in c["judgments"].values()) for c in data["cases"]))
print("semantic-review.json all notes non-empty:", all(bool(c["notes"].strip()) for c in data["cases"]))
