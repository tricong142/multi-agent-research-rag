import html
import json
import re
from pathlib import Path

p = Path(r"c:\Users\dellcuatri142\Downloads\HUMAN_REVIEW (4).html")
text = p.read_text(encoding="utf-8")

articles = text.split('<article data-id="')[1:]
for a in articles:
    cid = a.split('"')[0]
    if cid == "scope:none:not_enough_info":
        m_pred = re.search(r'<details><summary>Prediction và evidence</summary><pre>(.*?)</pre>', a, re.DOTALL)
        raw_json = html.unescape(m_pred.group(1))
        pred_data = json.loads(raw_json)
        print("scope:none:not_enough_info prediction details:")
        print(json.dumps(pred_data, indent=2, ensure_ascii=False))

