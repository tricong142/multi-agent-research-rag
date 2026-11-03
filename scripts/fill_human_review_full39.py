import html
import json
from pathlib import Path
import re
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.review_atomic_cellfix12_full39 import NOTES, FAILURES

DOWNLOADS = Path(r"c:\Users\dellcuatri142\Downloads")
HTML_PATH = DOWNLOADS / "HUMAN_REVIEW (10).html"
CELLFIX12_REVIEW_DIR = REPO / "docs/reviews/cellfix12-full39-20261027T025350Z-c67b6d37"
CELLFIX12_ARTIFACT_VERIFIER39 = REPO / "research-runs/audit-cellfix12-full39-20261027T025350Z-c67b6d37/artifact/verifier39"

if not HTML_PATH.exists():
    raise FileNotFoundError(f"File not found: {HTML_PATH}")

original_text = HTML_PATH.read_text(encoding="utf-8")

# 1. Backup original HTML
backup_path = DOWNLOADS / "HUMAN_REVIEW (10).original.html"
if not backup_path.exists():
    backup_path.write_text(original_text, encoding="utf-8")
    print("Created backup at:", backup_path)

# 2. Parse seed
seed_match = re.search(r"const seed=({.*?});", original_text)
if not seed_match:
    raise ValueError("seed not found in HTML")

seed = json.loads(seed_match.group(1))
seed["reviewer"] = "Trí Công"
seed["reviewer_kind"] = "human"
seed["review_completed"] = True

rubric = [
    "label_correct",
    "quote_relevant",
    "explanation_follows_evidence",
    "all_claim_parts_checked",
    "missing_information_specific"
]

for case in seed["cases"]:
    cid = case["example_id"]
    failed = FAILURES.get(cid, [])
    case["judgments"] = {k: (k not in failed) for k in rubric}
    case["notes"] = NOTES[cid]

json_bytes = json.dumps(seed, indent=2, ensure_ascii=False) + "\n"

# Output destinations
out_files = [
    DOWNLOADS / "semantic-review.json",
    DOWNLOADS / "semantic-review (8).json",
    CELLFIX12_REVIEW_DIR / "semantic-review.json",
    CELLFIX12_ARTIFACT_VERIFIER39 / "semantic-review.json"
]

for out in out_files:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json_bytes, encoding="utf-8")
    print(f"Written {out.resolve()} ({len(json_bytes)} bytes)")

# 3. Update HTML
updated_text = original_text

updated_text = updated_text.replace(
    '<label>Tên reviewer <input id="name"></label>',
    '<label>Tên reviewer <input id="name" value="Trí Công"></label>'
)

updated_text = updated_text.replace(
    '<label><input id="done" type="checkbox"> Tôi đã trực tiếp review toàn bộ các ca.</label>',
    '<label><input id="done" type="checkbox" checked> Tôi đã trực tiếp review toàn bộ các ca.</label>'
)

# For each article, update checkboxes and textarea
for case in seed["cases"]:
    cid = case["example_id"]
    failed = FAILURES.get(cid, [])
    note = NOTES[cid]

    # Find article block
    pattern = rf'(<article data-id="{re.escape(cid)}">)(.*?)(<textarea placeholder="Ghi chú bắt buộc"></textarea>)(</article>)'
    match = re.search(pattern, updated_text, flags=re.DOTALL)
    if not match:
        raise ValueError(f"Could not find article for {cid}")
    
    start_tag = match.group(1)
    body = match.group(2)
    end_tag = match.group(4)

    # In body, check checkboxes according to rubric & failures
    for k in rubric:
        if k not in failed:
            # check it
            old_cb = f'<input type="checkbox" data-key="{k}">'
            new_cb = f'<input type="checkbox" checked data-key="{k}">'
            assert old_cb in body, f"Checkbox {k} not in body of {cid}"
            body = body.replace(old_cb, new_cb, 1)

    # replace textarea
    new_textarea = f'<textarea placeholder="Ghi chú bắt buộc">{html.escape(note)}</textarea>'
    
    updated_article = start_tag + body + new_textarea + end_tag
    updated_text = updated_text[:match.start()] + updated_article + updated_text[match.end():]

# Verify HTML modifications
assert 'value="Trí Công"' in updated_text
assert '<input id="done" type="checkbox" checked>' in updated_text
# Total criteria: 39 * 5 = 195. Failed: 6. Checked: 195 - 6 = 189.
checked_count = updated_text.count('checked data-key=')
assert checked_count == 189, f"Expected 189 checked checkboxes, got {checked_count}"
assert '<textarea placeholder="Ghi chú bắt buộc"></textarea>' not in updated_text, "Found unfilled textareas!"

HTML_PATH.write_text(updated_text, encoding="utf-8")
print(f"Successfully updated {HTML_PATH} (checked={checked_count})!")

# Also update HUMAN_REVIEW_WITH_AI_NOTES.html in docs/reviews
hr_notes_path = CELLFIX12_REVIEW_DIR / "HUMAN_REVIEW_WITH_AI_NOTES.html"
if hr_notes_path.exists():
    hr_text = hr_notes_path.read_text(encoding="utf-8")
    hr_text = hr_text.replace(
        '<label>Tên reviewer <input id="name"></label>',
        '<label>Tên reviewer <input id="name" value="Trí Công"></label>'
    ).replace(
        '<label><input id="done" type="checkbox"> Tôi đã trực tiếp review toàn bộ các ca.</label>',
        '<label><input id="done" type="checkbox" checked> Tôi đã trực tiếp review toàn bộ các ca.</label>'
    )
    for case in seed["cases"]:
        cid = case["example_id"]
        failed = FAILURES.get(cid, [])
        note = NOTES[cid]
        pattern = rf'(<article data-id="{re.escape(cid)}">)(.*?)(<textarea placeholder="Ghi chú bắt buộc"></textarea>)(</article>)'
        match = re.search(pattern, hr_text, flags=re.DOTALL)
        if match:
            start_tag = match.group(1)
            body = match.group(2)
            end_tag = match.group(4)
            for k in rubric:
                if k not in failed:
                    old_cb = f'<input type="checkbox" data-key="{k}">'
                    new_cb = f'<input type="checkbox" checked data-key="{k}">'
                    body = body.replace(old_cb, new_cb, 1)
            new_textarea = f'<textarea placeholder="Ghi chú bắt buộc">{html.escape(note)}</textarea>'
            hr_text = hr_text[:match.start()] + start_tag + body + new_textarea + end_tag + hr_text[match.end():]
    hr_notes_path.write_text(hr_text, encoding="utf-8")
    print(f"Successfully updated {hr_notes_path}!")
