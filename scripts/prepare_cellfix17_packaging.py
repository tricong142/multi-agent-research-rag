"""Derive new launchers from frozen Cellfix16, without changing its release."""
import json
from pathlib import Path
from scripts.atomic_validation_review import json_bytes, write_once

ROOT = Path(__file__).resolve().parents[1]


def prepare():
    if (ROOT / "docs/atomic-verifier-cellfix17-release.json").exists():
        raise ValueError("Released candidate is immutable")
    base = ROOT / "research-runs/audit-cellfix16-full39-20261103T091648Z-c8c48869"
    received = json.loads((base / "failed-cases.json").read_bytes())[0]
    cid = received["case"]["example_id"]
    texts = [e["raw_output"] for e in (json.loads(s) for s in
             (base / "artifact/verifier39/calls.jsonl").read_text(encoding="utf-8").splitlines())
             if e.get("example_id") == cid and e["event"] == "generation"][1:]
    fixture = {"source_run_id": "20261103T091648Z-c8c48869", "case": received["case"],
               "part": received["prediction"]["result"]["decomposition"]["parts"][0],
               "raw_outputs": [t["output"] for t in received["prediction"]["result"]["trace"][1:]],
               "received_texts": texts}
    assert len(texts) == len(fixture["raw_outputs"]) == 2
    write_once(ROOT / "scripts/fixtures/cellfix16_full39_failure.json", json_bytes(fixture))
    names = ["atomic_cellfix16_binding.py", "atomic_cellfix16_workflow.py", "colab_cellfix16_cell6.py",
             "build_colab_cellfix16.py", "build_kaggle_cellfix16.py", "test_colab_cellfix16.py",
             "test_atomic_cellfix16_workflow.py", "test_cellfix16_cell6.py", "test_cellfix16_cell7.py",
             "test_cellfix16_packaging.py", "check_cellfix16_packaging.py", "check_kaggle_cellfix16.py",
             "check_atomic_cellfix16.py", "check_atomic_cellfix16_tokenizer.py"]
    for name in names:
        text = (ROOT / "scripts" / name).read_text(encoding="utf-8").replace("cellfix16", "cellfix17").replace("Cellfix16", "Cellfix17")
        if name == "check_atomic_cellfix16_tokenizer.py":
            text = text.replace("    from research_rag.evaluation import evaluate_atomic_verifier as r\n",
                "    from research_rag.evaluation import evaluate_atomic_verifier as r\n    from scripts.atomic_offline_memory import use_streaming_hashes\n    use_streaming_hashes(r)\n")
            text = text.replace("04_factchecker.inference.cellfix17_rules", "04_factchecker.inference.cellfix16_rules")
            text = text.replace("from research_rag.tests.test_atomic_cellfix17 import cases,received",
                                "from research_rag.tests.test_atomic_cellfix16 import cases,received")
            marker = "    prepared=[]"
            assert text.count(marker) == 1
            text = text.replace(marker, "    from research_rag.tests.test_atomic_cellfix17 import token_paths17\n    paths.extend(token_paths17())\n" + marker)
            marker = "    output={'candidate':criteria['policy']"
            addition = '''    from research_rag.tests.test_atomic_cellfix17 import fixture17
    sample17=fixture17();messages17=request(sample17['case']['claim'],sample17['part'],sample17['case']['context'])
    exact_received=[]
    for attempt,text17 in enumerate(sample17['received_texts'],1):
        callback17=backend.generation_options(messages17)['prefix_allowed_tokens_fn']
        ids17=Sequence([tokenizer.eos_token_id]);rejected17=None
        for index,token in enumerate(tokenizer.encode(text17,add_special_tokens=False)):
            if token not in callback17(0,ids17):rejected17=index;break
            ids17.append(token)
        assert rejected17 is not None,'Received invalid coverage reached EOS'
        exact_received.append(dict(attempt=attempt,rejected_at_bpe_token=rejected17,no_character_fallback=True))
'''
            assert text.count(marker) == 1
            text = text.replace(marker, addition + marker)
            text = text.replace("'exact_malformed_prefix_replay':prefix_check,", "'exact_malformed_prefix_replay':prefix_check,'received_full39_bpe_replay':exact_received,")
        if name == "build_colab_cellfix16.py":
            text = text.replace("'atomic_cellfix17_rules.py'", "'atomic_cellfix17_coverage.py', 'fixtures/cellfix16_full39_failure.json'")
            text = text.replace("'prepare_cellfix17_packaging.py'", "'prepare_cellfix17_packaging.py', 'atomic_offline_memory.py'")
            text = text.replace("Sửa explicit relations, decomposition, numeric binding và collective evidence; giữ member-local absence guard.",
                                "Sửa coverage member enum rỗng do lọc mất dấu câu; giữ source span và validator.")
            text = text.replace("Candidate mới sửa explicit relations, decomposition, numeric binding và collective evidence.",
                                "Candidate mới sửa coverage source-member enums; validator và budgets giữ nguyên.")
        if name == "build_kaggle_cellfix16.py":
            text = text.replace("Candidate mới sửa explicit relations, decomposition, numeric binding và collective evidence.",
                                "Candidate mới sửa coverage enum rỗng do loại dấu câu khỏi member hợp lệ.")
        if name == "check_cellfix16_packaging.py":
            text = text.replace("atomic-verifier-cellfix15-candidate.json", "atomic-verifier-cellfix16-candidate.json")
            text = text.replace("atomic-verifier-cellfix15-release.json", "atomic-verifier-cellfix16-release.json")
            start = "    from scripts.atomic_cellfix15_replay_compat import patch_workflow\n"
            old = "    old = patch_workflow((ROOT/'scripts/atomic_cellfix15_workflow.py').read_bytes()).decode('utf-8').replace('\\r\\n','\\n')"
            assert start in text and old in text
            text = text.replace(start, "").replace(old, "    old = (ROOT/'scripts/atomic_cellfix16_workflow.py').read_text(encoding='utf-8')")
            text = text.replace("new.replace('cellfix17','cellfix15')", "new.replace('cellfix17','cellfix16')")
        if name == "check_atomic_cellfix16.py":
            text = text.replace("    from research_rag.evaluation import evaluate_atomic_verifier as r\n",
                "    from research_rag.evaluation import evaluate_atomic_verifier as r\n    from scripts.atomic_offline_memory import use_streaming_hashes\n    use_streaming_hashes(r)\n")
            text = text.replace("errors=len(result.errors),", "errors=len(result.errors),hash_io_chunk_bytes=65536,")
        (ROOT / "scripts" / name.replace("cellfix16", "cellfix17")).write_text(text, encoding="utf-8")
    print("Prepared Cellfix17 launchers and received-trace fixture", flush=True)


if __name__ == "__main__":
    prepare()
