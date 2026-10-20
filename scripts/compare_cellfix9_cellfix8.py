from pathlib import Path
import json, re

html8 = Path("docs/reviews/cellfix8-20261020T061934Z-c87bce57/HUMAN_REVIEW_WITH_AI_NOTES.html").read_text(encoding="utf-8")
html9 = Path("../HUMAN_REVIEW (1).html").read_text(encoding="utf-8")

# Extract predictions from html9
articles9 = re.findall(r'<article data-id="(decompose:\d{3})">.*?<details><summary>.*?</summary><pre>(.*?)</pre>', html9, re.DOTALL)
print("Articles found in html9:", len(articles9))

seed8_match = re.search(r'const seed\s*=\s*({.*?});\s*(?:document|<)', html8, re.DOTALL)
seed8 = json.loads(seed8_match.group(1))
seed8_cases = {c["example_id"]: c for c in seed8["cases"]}

mismatches = []
import html
for aid, json_str in articles9:
    pred9 = json.loads(html.unescape(json_str))
    decomp9 = pred9["decomposition"]
    decomp8 = seed8_cases[aid]["decomposition"]
    if decomp9 != decomp8:
        print(f"Mismatch in {aid}!")
        mismatches.append(aid)

if not mismatches:
    print("ALL 18 decompositions in cellfix9 are 100% IDENTICAL to cellfix8!")
else:
    print("Mismatched cases:", mismatches)
