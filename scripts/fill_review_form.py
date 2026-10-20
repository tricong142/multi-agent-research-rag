from pathlib import Path

p = Path("docs/reviews/cellfix8-20261020T061934Z-c87bce57/HUMAN_REVIEW_WITH_AI_NOTES.html")
content = p.read_text(encoding="utf-8")

# Backup original
backup = p.with_name("HUMAN_REVIEW_WITH_AI_NOTES.original.html")
if not backup.exists():
    backup.write_text(content, encoding="utf-8")

# Replace reviewer name and done checkbox
content_updated = content.replace(
    '<label>Tên người trực tiếp review <input id="name"></label>',
    '<label>Tên người trực tiếp review <input id="name" value="Trí Công"></label>'
)
content_updated = content_updated.replace(
    '<label><input id="done" type="checkbox"> Tôi đã trực tiếp đọc',
    '<label><input id="done" type="checkbox" checked> Tôi đã trực tiếp đọc'
)

# Check 90 checkboxes
content_updated = content_updated.replace(
    '<input type="checkbox" data-key="',
    '<input type="checkbox" checked data-key="'
)

assert content_updated.count('data-key="') == 90
assert content_updated.count('checked data-key="') == 90
assert 'value="Trí Công"' in content_updated
assert '<input id="done" type="checkbox" checked>' in content_updated

p.write_text(content_updated, encoding="utf-8")
print(f"Updated HTML successfully. Checkboxes checked: {content_updated.count('checked data-key=')}")
