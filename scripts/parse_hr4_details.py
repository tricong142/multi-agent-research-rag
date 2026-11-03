import html
import json
import re
from pathlib import Path

p = Path(r"c:\Users\dellcuatri142\Downloads\HUMAN_REVIEW (4).html")
text = p.read_text(encoding="utf-8")

articles = text.split('<article data-id="')[1:]
print("Total articles:", len(articles))

for i, a in enumerate(articles):
    cid = a.split('"')[0]
    m_pred = re.search(r'<details><summary>Prediction và evidence</summary><pre>(.*?)</pre>', a, re.DOTALL)
    if m_pred:
        raw_json = html.unescape(m_pred.group(1))
        pred_data = json.loads(raw_json)
        assessed_label = pred_data.get("assessed_label")
        status = pred_data.get("status")
        stop = pred_data.get("stop_reason")
        print(f"{i+1:02d}. {cid}: assessed_label={assessed_label}, status={status}, stop={stop}")
    else:
        print(f"{i+1:02d}. {cid}: No pred details found")
