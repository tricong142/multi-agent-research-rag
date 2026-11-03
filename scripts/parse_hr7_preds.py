import json
import re
from pathlib import Path

html_path = Path(r"c:\Users\dellcuatri142\Downloads\HUMAN_REVIEW (7).html")
text = html_path.read_text(encoding="utf-8")

# Parse each article
parts = text.split('<article data-id="')[1:]
print(f"Total articles: {len(parts)}")
for idx, part in enumerate(parts):
    ex_id = part.split('"')[0]
    claim_match = re.search(r"<h3>(.*?)</h3>", part)
    claim = claim_match.group(1) if claim_match else ""
    pred_match = re.search(r"<pre>(\{.*?\})</pre>", part, re.DOTALL)
    if pred_match:
        pred_json = json.loads(pred_match.group(1).replace("&quot;", '"'))
        decomp = pred_json.get("decomposition", {})
        policy = pred_json.get("policy", "")
        print(f"[{idx+1}] {ex_id}: {claim}")
        print(f"    policy: {policy}, decomp parts: {len(decomp.get('parts', []))}")
