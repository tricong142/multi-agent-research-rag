import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path.cwd()
RUN = "20261020T061934Z-c87bce57"
BASE = REPO / "research-runs" / ("audit-cellfix8-fresh-" + RUN)
DELIVERY = REPO / "docs/reviews/cellfix8-20261020T061934Z-c87bce57"

sys.path.insert(0, str(BASE / "workspace"))
spec = importlib.util.spec_from_file_location("review_workflow", BASE / "workspace/atomic_workflow_cellfix8.py")
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)

probe = BASE / "artifact/decomposition-probe"
signed_review_path = DELIVERY / "semantic-review-human.json"

with tempfile.TemporaryDirectory(dir=REPO / "research-runs", prefix="cf8-human-admission-") as temp:
    test = Path(temp) / "probe"
    shutil.copytree(probe, test)
    (test / "semantic-review.json").write_bytes(signed_review_path.read_bytes())
    result = w.r.require_probe_review(test)
    print("w.r.require_probe_review PASSED! Result:", result)
