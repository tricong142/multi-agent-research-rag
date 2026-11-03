import html
import json
import re
from pathlib import Path

p = Path(r"c:\Users\dellcuatri142\Downloads\HUMAN_REVIEW (4).html")
text = p.read_text(encoding="utf-8")

m_seed = re.search(r"const seed=({.*?});", text)
seed = json.loads(m_seed.group(1))

articles = text.split('<article data-id="')[1:]

print(f"Seed cases: {len(seed['cases'])}, Articles: {len(articles)}")
print("Criteria sha256:", seed["criteria_sha256"])
print("Predictions sha256:", seed["predictions_sha256"])

for i, a in enumerate(articles):
    cid = a.split('"')[0]
    claim = re.search(r'<h3>(.*?)</h3>', a).group(1)
    context = re.search(r'<pre>(.*?)</pre>', a, re.DOTALL).group(1)
    m_pred = re.search(r'<details><summary>Prediction và evidence</summary><pre>(.*?)</pre>', a, re.DOTALL)
    pred_data = json.loads(html.unescape(m_pred.group(1)))
    label = pred_data.get("assessed_label")
    status = pred_data.get("status")
    stop = pred_data.get("stop_reason")
    assert status == "completed", f"Status not completed for {cid}"
    assert stop == "completed", f"Stop not completed for {cid}"
    assert label in ("support", "contradict", "not_enough_info"), f"Invalid label {label} for {cid}"

print("All 39 cases in HUMAN_REVIEW (4).html are completed and have valid labels!")

