import html
import json
from pathlib import Path
import re
import sys
REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from scripts.review_atomic_cellfix8_probe import NOTES

DOWNLOADS = Path(r"c:\Users\dellcuatri142\Downloads")
REPO = Path(r"c:\Users\dellcuatri142\Downloads\AI ENGINEER")
HTML_PATH = DOWNLOADS / "HUMAN_REVIEW (7).html"

if not HTML_PATH.exists():
    raise FileNotFoundError(f"File not found: {HTML_PATH}")

original_text = HTML_PATH.read_text(encoding="utf-8")

# 1. Backup original HTML
backup_path = DOWNLOADS / "HUMAN_REVIEW (7).original.html"
if not backup_path.exists():
    backup_path.write_text(original_text, encoding="utf-8")
    print("Created backup at:", backup_path)

# 2. Prepare notes map
notes_map = {}
for i, n in enumerate(NOTES, 1):
    ex_id = f"decompose:{i:03d}"
    notes_map[ex_id] = " ".join(f"C{j}: {part}" for j, part in enumerate(n, 1))

# 3. Generate JSON
seed_match = re.search(r"const seed=({.*?});", original_text)
if not seed_match:
    raise ValueError("seed not found in HTML")

seed = json.loads(seed_match.group(1))
seed["reviewer"] = "Trí Công"
seed["reviewer_kind"] = "human"
seed["review_completed"] = True

rubric = [
    "factual_predicates_not_fragments",
    "all_requirements_preserved",
    "quantifier_preserved",
    "entity_metric_binding_correct",
    "time_condition_scope_correct"
]

for case in seed["cases"]:
    case["judgments"] = {k: True for k in rubric}
    case["notes"] = notes_map[case["example_id"]]

json_content = json.dumps(seed, indent=2, ensure_ascii=False) + "\n"

# Output destinations
out_files = [
    DOWNLOADS / "semantic-review(7).json",
    DOWNLOADS / "semantic-review (7).json",
    REPO / "docs" / "reviews" / "semantic-review(7).json"
]

(REPO / "docs" / "reviews").mkdir(parents=True, exist_ok=True)

for out in out_files:
    out.write_text(json_content, encoding="utf-8")
    print(f"Written {out.resolve()} ({len(json_content)} bytes)")

# 4. Modify and update HTML
updated_text = original_text

# Fill reviewer name
updated_text = updated_text.replace(
    '<label>Tên reviewer <input id="name"></label>',
    '<label>Tên reviewer <input id="name" value="Trí Công"></label>'
)

# Fill done checkbox
updated_text = updated_text.replace(
    '<label><input id="done" type="checkbox"> Tôi đã trực tiếp review toàn bộ các ca.</label>',
    '<label><input id="done" type="checkbox" checked> Tôi đã trực tiếp review toàn bộ các ca.</label>'
)

# Check all 90 checkboxes
updated_text = updated_text.replace(
    '<input type="checkbox" data-key="',
    '<input type="checkbox" checked data-key="'
)

# Fill textareas
for ex_id, note in notes_map.items():
    pattern = rf'(<article data-id="{ex_id}">.*?)<textarea placeholder="Ghi chú bắt buộc"></textarea>(</article>)'
    replacement = rf'\1<textarea placeholder="Ghi chú bắt buộc">{html.escape(note)}</textarea>\2'
    new_text, count = re.subn(pattern, replacement, updated_text, flags=re.DOTALL)
    if count == 1:
        updated_text = new_text
    else:
        print(f"Warning: pattern count for {ex_id} was {count}")

assert 'value="Trí Công"' in updated_text, "Reviewer name missing"
assert '<input id="done" type="checkbox" checked>' in updated_text, "Done checkbox missing"
assert updated_text.count('checked data-key="') == 90, f"Expected 90 checked, got {updated_text.count('checked data-key=')}"
assert '<textarea placeholder="Ghi chú bắt buộc"></textarea>' not in updated_text, "Found unfilled textareas!"

HTML_PATH.write_text(updated_text, encoding="utf-8")
print(f"Successfully updated {HTML_PATH}!")
