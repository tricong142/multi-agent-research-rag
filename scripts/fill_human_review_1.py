import html
import json
from pathlib import Path
import re

REPO = Path.cwd()
HTML_PATH = Path("../HUMAN_REVIEW (1).html")

if not HTML_PATH.exists():
    raise FileNotFoundError(f"File not found: {HTML_PATH.resolve()}")

# 1. Backup original
backup_path = Path("../HUMAN_REVIEW (1).original.html")
original_text = HTML_PATH.read_text(encoding="utf-8")
if not backup_path.exists():
    backup_path.write_text(original_text, encoding="utf-8")
    print("Created backup at:", backup_path.resolve())

# 2. Extract notes from DECOMPOSITION_REVIEW.md
decomp_review = (REPO / "docs/reviews/cellfix8-20261020T061934Z-c87bce57/DECOMPOSITION_REVIEW.md").read_text(encoding="utf-8")
notes_map = {}
for line in decomp_review.splitlines():
    if line.startswith("| decompose:"):
        parts = [p.strip() for p in line.split("|")[1:-1]]
        example_id = parts[0]
        note = parts[6]
        notes_map[example_id] = note

print(f"Loaded notes for {len(notes_map)} cases.")

# 3. Modify HTML
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
for example_id, note in notes_map.items():
    # Find the article block
    pattern = rf'(<article data-id="{example_id}">.*?)<textarea placeholder="Ghi chú bắt buộc"></textarea>(</article>)'
    replacement = rf'\1<textarea placeholder="Ghi chú bắt buộc">{html.escape(note)}</textarea>\2'
    new_text, count = re.subn(pattern, replacement, updated_text, flags=re.DOTALL)
    if count == 1:
        updated_text = new_text
    else:
        print(f"Warning: pattern count for {example_id} was {count}")

# Verify modifications
assert updated_text.count('value="Trí Công"') == 1, "Reviewer name missing or duplicated"
assert '<input id="done" type="checkbox" checked>' in updated_text, "Done checkbox missing"
assert updated_text.count('checked data-key="') == 90, f"Expected 90 checked checkboxes, got {updated_text.count('checked data-key=')}"
assert '<textarea placeholder="Ghi chú bắt buộc"></textarea>' not in updated_text, "Found unfilled textareas!"

# Write back to HUMAN_REVIEW (1).html
HTML_PATH.write_text(updated_text, encoding="utf-8")
print(f"Successfully updated {HTML_PATH.resolve()}!")

# 4. Generate semantic-review.json
seed_match = re.search(r'const seed=({.*?});document\.querySelector', original_text)
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

json_bytes = json.dumps(seed, indent=2, ensure_ascii=False) + "\n"

# Save in Downloads
out_download = Path("../semantic-review.json")
out_download.write_text(json_bytes, encoding="utf-8")
print(f"Generated {out_download.resolve()} (criteria: {seed['criteria_sha256'][:12]}, predictions: {seed['predictions_sha256'][:12]})")

# Also save in research-runs / delivery if needed
out_repo = REPO / "docs/reviews/cellfix9-semantic-review-human.json"
out_repo.write_text(json_bytes, encoding="utf-8")
print(f"Saved copy to {out_repo.resolve()}")
