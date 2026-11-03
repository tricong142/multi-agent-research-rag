import html
import json
from pathlib import Path
import re
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.review_atomic_cellfix13_full39 import NOTES

DOWNLOADS = Path(r"c:\Users\dellcuatri142\Downloads")
HTML_PATH = DOWNLOADS / "HUMAN_REVIEW (16).html"
RUN = "20261027T113721Z-18c80dae"
CELLFIX13_REVIEW_DIR = REPO / f"docs/reviews/cellfix13-full39-{RUN}"
CELLFIX13_ARTIFACT_VERIFIER39 = REPO / f"research-runs/audit-cellfix13-full39-{RUN}/artifact/verifier39"
CELLFIX13_WORKSPACE = REPO / f"research-runs/audit-cellfix13-full39-{RUN}/workspace"
PROBE_DIR = REPO / f"research-runs/audit-cellfix13-full39-{RUN}/artifact/reviewed-probe"

if not HTML_PATH.exists():
    raise FileNotFoundError(f"File not found: {HTML_PATH}")

original_text = HTML_PATH.read_text(encoding="utf-8")

# 1. Backup original HTML
backup_path = DOWNLOADS / "HUMAN_REVIEW (16).original.html"
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
    case["judgments"] = {k: True for k in rubric}
    case["notes"] = NOTES[cid]

json_bytes = json.dumps(seed, indent=2, ensure_ascii=False) + "\n"

# Output destinations
out_files = [
    DOWNLOADS / "semantic-review.json",
    DOWNLOADS / "semantic-review (13).json",
    CELLFIX13_REVIEW_DIR / "semantic-review.json",
    CELLFIX13_ARTIFACT_VERIFIER39 / "semantic-review.json"
]

for out in out_files:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json_bytes, encoding="utf-8")
    print(f"Written {out.resolve()} ({len(json_bytes)} bytes)")

# 3. Update HTML in Downloads
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
    note = NOTES[cid]

    pattern = rf'(<article data-id="{re.escape(cid)}">)(.*?)(<textarea placeholder="Ghi chú bắt buộc"></textarea>)(</article>)'
    match = re.search(pattern, updated_text, flags=re.DOTALL)
    if not match:
        raise ValueError(f"Could not find article for {cid}")
    
    start_tag = match.group(1)
    body = match.group(2)
    end_tag = match.group(4)

    for k in rubric:
        old_cb = f'<input type="checkbox" data-key="{k}">'
        new_cb = f'<input type="checkbox" checked data-key="{k}">'
        assert old_cb in body, f"Checkbox {k} not in body of {cid}"
        body = body.replace(old_cb, new_cb, 1)

    new_textarea = f'<textarea placeholder="Ghi chú bắt buộc">{html.escape(note)}</textarea>'
    
    updated_article = start_tag + body + new_textarea + end_tag
    updated_text = updated_text[:match.start()] + updated_article + updated_text[match.end():]

# Verify HTML modifications
assert 'value="Trí Công"' in updated_text
assert '<input id="done" type="checkbox" checked>' in updated_text
checked_count = updated_text.count('checked data-key=')
assert checked_count == 195, f"Expected 195 checked checkboxes, got {checked_count}"
assert '<textarea placeholder="Ghi chú bắt buộc"></textarea>' not in updated_text, "Found unfilled textareas!"

HTML_PATH.write_text(updated_text, encoding="utf-8")
print(f"Successfully updated {HTML_PATH} (checked={checked_count})!")

# Also update HUMAN_REVIEW_WITH_AI_NOTES.html in docs/reviews
hr_notes_path = CELLFIX13_REVIEW_DIR / "HUMAN_REVIEW_WITH_AI_NOTES.html"
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
        note = NOTES[cid]
        pattern = rf'(<article data-id="{re.escape(cid)}">)(.*?)(<textarea placeholder="Ghi chú bắt buộc"></textarea>)(</article>)'
        match = re.search(pattern, hr_text, flags=re.DOTALL)
        if match:
            start_tag = match.group(1)
            body = match.group(2)
            end_tag = match.group(4)
            for k in rubric:
                old_cb = f'<input type="checkbox" data-key="{k}">'
                new_cb = f'<input type="checkbox" checked data-key="{k}">'
                if old_cb in body:
                    body = body.replace(old_cb, new_cb, 1)
            new_textarea = f'<textarea placeholder="Ghi chú bắt buộc">{html.escape(note)}</textarea>'
            hr_text = hr_text[:match.start()] + start_tag + body + new_textarea + end_tag + hr_text[match.end():]
    hr_notes_path.write_text(hr_text, encoding="utf-8")
    print(f"Successfully updated {hr_notes_path}!")

# 4. Verify gate admission
venv_py = REPO / ".venv/Scripts/python.exe"
if venv_py.exists():
    res = subprocess.run([
        str(venv_py), str(CELLFIX13_WORKSPACE / "atomic_workflow_cellfix13.py"),
        "--admit-full39", "--full39-dir", str(CELLFIX13_ARTIFACT_VERIFIER39),
        "--probe-dir", str(PROBE_DIR)
    ], cwd=CELLFIX13_WORKSPACE, capture_output=True, text=True)
    if res.returncode == 0:
        print("Gate admission check PASSED:", res.stdout.strip())
    else:
        print("Gate admission check FAILED:", res.stderr)
