import html
import json
import re
import sys
from pathlib import Path

REPO = Path(r"c:\Users\dellcuatri142\Downloads\AI ENGINEER")
sys.path.insert(0, str(REPO))
from scripts.review_atomic_cellfix13_full39 import NOTES

p = Path(r"c:\Users\dellcuatri142\Downloads\HUMAN_REVIEW (4).html")
text = p.read_text(encoding="utf-8")
articles = text.split('<article data-id="')[1:]

print("Comparing 39 cases in HUMAN_REVIEW (4).html against NOTES:")
discrepancies = []
for a in articles:
    cid = a.split('"')[0]
    claim = re.search(r'<h3>(.*?)</h3>', a).group(1)
    context = re.search(r'<pre>(.*?)</pre>', a, re.DOTALL).group(1)
    m_pred = re.search(r'<details><summary>Prediction và evidence</summary><pre>(.*?)</pre>', a, re.DOTALL)
    pred = json.loads(html.unescape(m_pred.group(1)))
    
    note = NOTES.get(cid, "")
    if not note:
        discrepancies.append(f"Missing note for {cid}")
    
    # check label consistency
    assessed_label = pred["assessed_label"]
    parts = pred["parts"]
    status = pred["status"]
    
    print(f"[{cid}] label={assessed_label}, parts={len(parts)}, status={status}")

print("Total discrepancies:", len(discrepancies))

