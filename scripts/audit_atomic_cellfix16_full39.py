"""Audit the received Cellfix16 run without inference or changing frozen outcomes."""
from collections import Counter
import hashlib
import importlib
import importlib.util
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import sys
import zipfile

from scripts.atomic_validation_review import digest, json_bytes, write_once

ROOT = Path(__file__).resolve().parents[1]
RUN = "20261103T091648Z-c8c48869"
BASE = ROOT / "research-runs" / ("audit-cellfix16-full39-" + RUN)
ARCHIVE = ROOT.parent / ("output-cellfix16-kaggle-" + RUN + " (1).zip")


def file_sha(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            result.update(chunk)
    return result.hexdigest()


def checked_extract(z, target, files):
    assert len(z.namelist()) == len(set(z.namelist()))
    for name, item in files.items():
        relative = PurePosixPath(name)
        destination = (target / name).resolve()
        assert not relative.is_absolute() and ".." not in relative.parts and "\\" not in name
        assert destination.is_relative_to(target.resolve())
        destination.parent.mkdir(parents=True, exist_ok=True)
        existing = destination.exists()
        result, size = hashlib.sha256(), 0
        output = None if existing else destination.open("xb")
        try:
            with z.open(name) as stream:
                for chunk in iter(lambda: stream.read(65536), b""):
                    result.update(chunk)
                    size += len(chunk)
                    if output is not None:
                        output.write(chunk)
        finally:
            if output is not None:
                output.close()
        assert size == item["size"] and result.hexdigest() == item["sha256"], name
        assert file_sha(destination) == item["sha256"], name


def receive():
    release = json.loads((ROOT / "docs/atomic-verifier-cellfix16-release.json").read_bytes())
    for name, expected in release["files"].items():
        assert file_sha(ROOT / name) == expected, name
    raw = file_sha(ARCHIVE)
    BASE.mkdir(parents=True, exist_ok=True)
    preserved = BASE / "original-output.zip"
    if not preserved.exists():
        shutil.copyfile(ARCHIVE, preserved)
    assert file_sha(preserved) == raw
    out, source = BASE / "artifact", BASE / "workspace"
    with zipfile.ZipFile(ARCHIVE) as z:
        assert len(z.infolist()) < 1000 and sum(i.file_size for i in z.infolist()) < 256 * 1024**2
        manifest = json.loads(z.read("output-manifest.json"))
        assert manifest["run_id"] == RUN
        assert set(z.namelist()) == {v["path"] for v in manifest["files"]} | {"output-manifest.json"}
        checked_extract(z, out, {item["path"]: item for item in manifest["files"]})
        write_once(out / "output-manifest.json", z.read("output-manifest.json"))
        inputs = json.loads(z.read("input-manifest.json"))
        assert inputs == release["payload_files"] and file_sha(out / "frozen-inputs.zip") == release["payload_sha256"]
    with zipfile.ZipFile(out / "frozen-inputs.zip") as z:
        assert set(z.namelist()) == set(inputs)
        checked_extract(z, source, inputs)
    provenance = json.loads((out / "notebook-provenance.json").read_bytes())
    for key in ("candidate", "criteria_sha256", "payload_sha256"):
        assert provenance[key] == release[key], key
    return out, source, manifest, release, raw


def main():
    if "--no-torch" in sys.argv:
        # LMFE supports ordinary token lists without its optional torch bitmasks.
        sys.modules["torch"] = None
    out, source, manifest, release, raw = receive()
    rows = lambda p: [json.loads(s) for s in p.read_bytes().splitlines()]
    cases = json.loads((out / "verifier39/cases.json").read_bytes())
    predictions = rows(out / "verifier39/predictions.jsonl")
    failures = [{"case": case, "prediction": pred} for case, pred in zip(cases, predictions)
                if pred["result"]["status"] != "completed" or pred["result"]["assessed_label"] != case["label"]]
    write_once(BASE / "failed-cases.json", json_bytes(failures))
    if "--receive-only" in sys.argv:
        print(json.dumps({"run_id": RUN, "candidate": release["candidate"], "outputs": len(manifest["files"]),
                      "inputs": len(release["payload_files"]), "archive_sha256": raw,
                      "failed_cases": failures}, indent=2), flush=True)
        return
    sys.path.insert(0, str(source))
    spec = importlib.util.spec_from_file_location("received_cf16_workflow", source / "atomic_workflow_cellfix16.py")
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    r = worker.r
    assert Path(r.__file__).resolve().is_relative_to(source)
    # Same SHA256 bytes, smaller temporary allocation on this low-memory Windows host.
    original_sha = r.sha256
    for module in list(sys.modules.values()):
        if getattr(module, "sha256", None) is original_sha:
            module.sha256 = file_sha
    frozen, all_cases, _, _, _, baseline, baseline_metrics = r.load_frozen(r.CRITERIA)
    assert r.sha256(r.CRITERIA) == release["criteria_sha256"]
    cache = importlib.import_module("04_factchecker.inference.cellfix14_runtime").decode_request
    stages = {}
    for folder in ("assessment-smoke", "decomposition-probe", "verifier39"):
        if folder == "decomposition-probe":
            effective, selected, _ = r.probe_configuration(frozen, all_cases, r.CRITERIA)
        elif folder == "assessment-smoke":
            effective, selected = r.smoke_configuration(frozen, all_cases)
        else:
            effective, selected = frozen, all_cases
        read = lambda name: json.loads((out / folder / name).read_bytes())
        assert read("cases.json") == selected
        assert (out / folder / "criteria.json").read_bytes() == r.CRITERIA.read_bytes()
        assert read("baseline.json") == baseline and read("baseline-metrics.json") == baseline_metrics
        provenance = read("provenance.json")
        assert provenance["source_sha256"] == frozen["source_sha256"]
        assert provenance["prompt_sha256"] == frozen["prompt_sha256"]
        assert provenance["criteria_sha256"] == release["criteria_sha256"]
        for key in ("model_files", "shared_tokenizer_files", "repo_id", "revision", "dtype", "quantization", "seed", "do_sample"):
            assert provenance["model"][key] == baseline["model_metadata"][key], key
        assert provenance["model"]["structured_decoder"] == frozen["structured_decoder"]
        assert provenance["model"]["max_new_tokens"] == frozen["max_new_tokens"]
        predicted, events = rows(out / folder / "predictions.jsonl"), rows(out / folder / "calls.jsonl")
        assert [p["example_id"] for p in predicted] == [c["example_id"] for c in selected]
        with cache(None):
            for case, row in zip(selected, predicted):
                r.replay_result(row["result"], case["claim"], case.get("context", ""), effective)
            if folder == "decomposition-probe":
                score = r.score_probe(predicted, selected, effective)
                generations = [e for e in events if e["event"] == "generation"]
                traces = [t for p in predicted for t in p["result"]["trace"]]
                assert len(generations) == len(traces) and all(g.get("usage_complete", True) for g in generations)
                score["generated_tokens"] = sum(g["generated_tokens"] for g in generations)
                score["prompt_tokens"] = sum(g["prompt_tokens"] for g in generations)
                score["checks"]["within_measured_token_budget"] = (score["generated_tokens"] <= effective["maximum_generated_tokens"]
                    and all(g["generated_tokens"] <= effective["max_new_tokens"] for g in generations))
                score["checks"]["structured_decoding_trace_complete"] = r.decoding_trace_complete(
                    generations, [t["messages"] for t in traces], effective)
                score["checks"]["cooperative_deadline_trace_complete"] = all(t.get("cooperative_deadline") is True for t in traces)
                score["automated_gate_pass"] = all(score["checks"].values())
            else:
                score = worker.measured_score(predicted, selected, effective, events)
                assert score.pop("usage_complete") is True
        assert score == read("metrics.json"), folder
        stages[folder] = {"metrics": score, "event_counts": dict(Counter(e["event"] for e in events))}
        print("Verified " + folder, flush=True)
    with cache(None):
        admission = r.require_probe_review(out / "reviewed-probe")
    assert admission == json.loads((out / "verifier39/probe-admission.json").read_bytes())
    failed = failures[0]
    assert len(failures) == 1 and failed["case"]["example_id"] == "scope:existential:contradict"
    part = failed["prediction"]["result"]["decomposition"]["parts"][0]
    from lmformatenforcer import JsonSchemaParser, CharacterLevelParserConfig
    CheckedParser = importlib.import_module("04_factchecker.inference.decoder_parser").CheckedParser
    evidence = importlib.import_module("04_factchecker.inference.assessment_evidence")
    with cache(None):
        schema = r.decoding.assessment_schema(failed["case"]["claim"], part, failed["case"]["context"])
        witness = evidence.population_witness(part, failed["case"]["context"])
    member_schema = schema["properties"]["coverage"]["properties"]["members"]["items"]
    assert member_schema["enum"] == []
    checks = []
    generation = [e for e in rows(out / "verifier39/calls.jsonl")
                  if e.get("example_id") == failed["case"]["example_id"] and e["event"] == "generation"]
    for trace, event in zip(failed["prediction"]["result"]["trace"][1:], generation[1:]):
        text = event["raw_output"]
        config = CharacterLevelParserConfig()
        config.force_json_field_order = True
        config.alphabet += "".join(sorted(set(text) - set(config.alphabet)))
        parser = CheckedParser(JsonSchemaParser(schema, config=config))
        for char in text:
            parser = parser.add_character(char)
        assert parser.can_end()
        with cache(None):
            try:
                r.atomic.assess_part(trace["output"], part, failed["case"]["context"])
            except ValueError as exc:
                issue = str(exc)
            else:
                raise AssertionError("Invalid source member accepted")
        assert issue == trace["validation_issue"] == "quote_membership"
        checks.append({"attempt": trace["attempt"], "decoder_accepts_actual_output": True,
                       "validator_rejection": issue, "coverage_members": trace["output"]["coverage"]["members"]})
    assert len(checks) == 2 and witness["members"] == ["Birch, Elm and Fir"]
    assert not (out / "validation30").exists()
    for item in manifest["files"]:
        assert digest((out / item["path"]).read_bytes()) == item["sha256"], item["path"]
    report = {"run_id": RUN, "candidate": release["candidate"], "archive_sha256": raw,
              "verified_outputs": len(manifest["files"]), "verified_inputs": len(release["payload_files"]),
              "criteria_sha256": release["criteria_sha256"], "stages": stages, "probe_admission": admission,
              "failed_case": failed, "population_witness": witness, "coverage_member_schema": member_schema,
              "decoder_validator_checks": checks, "validation30_started": False,
              "new_model_inference": False, "original_outputs_unchanged": True,
              "audit_hash_read_chunk_bytes": 65536,
              "torch_disabled_for_offline_schema_checks": "--no-torch" in sys.argv}
    target = ROOT / "docs" / ("atomic-verifier-cellfix16-full39-audit-" + RUN + ".json")
    target.write_bytes(json_bytes(report))
    print(json.dumps({"report": str(target), "root_cause": "empty coverage enum after punctuation filter",
                      "decoder_validator_checks": checks}, indent=2), flush=True)


if __name__ == "__main__":
    main()
