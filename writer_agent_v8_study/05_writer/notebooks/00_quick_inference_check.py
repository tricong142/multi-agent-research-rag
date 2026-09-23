# %% CPU-only plumbing check; synthetic fixture, NOT QASPER benchmark data.
from __future__ import annotations
import importlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

WriterNode = importlib.import_module("05_writer.node").WriterNode


def main():
    evidence = "This synthetic experiment used 100 training examples."
    state = {
        "intent": "State the training set size in this synthetic fixture.",
        "verified_claims": [{"claim_id": "demo:c1", "text": evidence, "evidence": evidence,
                             "source_id": "synthetic:smoke-test", "confidence": 1.0,
                             "verification_status": "verified"}],
    }
    node = WriterNode()
    output = node(state)
    assert output["final_report"]["sentences"][0]["claim_ids"] == ["demo:c1"]
    assert output["low_confidence_warning"] is True  # offline intent coverage is unassessed
    assert node({"intent": "Missing evidence", "verified_claims": []})["low_confidence_warning"] is True
    assert "needs_escalation" not in output and "next_node" not in output
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
