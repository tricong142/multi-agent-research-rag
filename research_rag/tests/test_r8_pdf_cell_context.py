import hashlib
import importlib
import json
import re
from pathlib import Path
from types import SimpleNamespace

import fitz
import pytest

from research_rag.adapters import PdfReader
from research_rag.graph import build_graph
from research_rag.pdf_cell_context import relevant_coordinate_cells
from research_rag.r8_adapter import R8_POLICY_ID, R8FactCheckerNode, load_r8_runtime
from train_agent3_summarizer.node import SummarizerNode


ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "artifacts/r8-v12-e2e-real-pdf"
MANIFEST = json.loads((DEMO / "manifest.json").read_bytes())
COORDINATES = json.loads((DEMO / "table-coordinates.json").read_bytes())
CASES = json.loads((DEMO / "inputs.json").read_bytes())


class TextPageReader:
    def process_page(self, path, index):
        with fitz.open(path) as pdf:
            blocks = [SimpleNamespace(text=block[4], bbox=block[:4], label="text", source_tool="pymupdf")
                      for block in pdf[index].get_text("blocks")]
        return {"success": True, "blocks": blocks}


class ReplayRetriever:
    def search(self, query, *, pdf_chunks, top_k, **kwargs):
        assert all(c["metadata"]["source_tool"] != "pdf_coordinates" for c in pdf_chunks)
        return {"chunks": pdf_chunks[:top_k], "decision": "dense"}


class NoGeneration:
    def generation_deadline(self, deadline):
        raise AssertionError("Scoped table verification must run without model generation")


def pdf_for(case):
    entry = MANIFEST["pdfs"][case["paper"]]
    path = ROOT / entry["path"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
    return str(path)


def test_document_cap_and_page_batch_are_independent():
    case = CASES[1]
    path = pdf_for(case)
    with pytest.raises(ValueError, match="26 pages, above max_pages=20"):
        PdfReader(TextPageReader()).read_for_question(path, question=case["question"], excluded_pages=[])
    reader = PdfReader(TextPageReader(), max_pages=26, table_coordinates=COORDINATES)
    result = reader.read_for_question(path, question=case["question"], excluded_pages=[])
    assert len(result["read_pages"]) == 3 and 4 in result["read_pages"]
    cells = relevant_coordinate_cells(case["question"], result["chunks"])
    assert cells[0]["metadata"]["row_label"] == "Llama 2 7B / +TEMP"
    assert cells[0]["metadata"]["raw_value"] == "82.6"
    assert {cell["metadata"]["column"] for cell in cells} == {"SST2"}
    assert any("−TEMP | SST2 | 61.0%" in cell["text"] for cell in cells)
    subsequent = reader.read_for_question(path, question=case["question"], excluded_pages=result["read_pages"])
    assert len(subsequent["read_pages"]) == 3 and 4 not in subsequent["read_pages"]


def test_fires_competing_cells_have_distinct_groups_and_ids():
    case = CASES[0]
    result = PdfReader(TextPageReader(), table_coordinates=COORDINATES).read_for_question(
        pdf_for(case), question=case["question"], excluded_pages=[])
    cells = relevant_coordinate_cells(case["question"], result["chunks"])
    assert [(c["metadata"]["row_group"], c["metadata"]["raw_value"]) for c in cells] == [
        ("Without fine-tuning", "17.33"), ("With fine-tuning", "30.66"),
    ]
    assert len({c["source_id"] for c in cells}) == 2
    assert all(c["metadata"]["page_no"] == 6 for c in cells)
    assert relevant_coordinate_cells(CASES[2]["question"], result["chunks"]) == []
    unrelated = PdfReader(TextPageReader(), table_coordinates={"wrong-hash": next(iter(COORDINATES.values()))})
    other = unrelated.read_for_question(pdf_for(case), question=case["question"], excluded_pages=[])
    assert not relevant_coordinate_cells(case["question"], other["chunks"])


def test_coordinate_proof_rejects_wrong_scope_and_ambiguous_cells():
    case = CASES[0]
    result = PdfReader(TextPageReader(), table_coordinates=COORDINATES).read_for_question(
        pdf_for(case), question=case["question"], excluded_pages=[])
    cells = [c for c in result["chunks"] if c["metadata"]["source_tool"] == "pdf_coordinates"]
    target, other = relevant_coordinate_cells(case["question"], cells)
    claim = "Without fine-tuning, RAT-SQL achieved 17.33% exact-match accuracy on the Fires database."
    checker = R8FactCheckerNode(NoGeneration(), load_r8_runtime())

    def verify(text=claim, source=target, roster=cells, question=case["question"], context=None):
        verdict = checker({"claim": text, "context": source["text"] if context is None else context,
                           "source_id": source["source_id"], "question": question,
                           "pdf_coordinate_cells": roster})
        return verdict["fact_check_label"]

    assert verify() == "support"
    assert verify(text=claim.replace("17.33", "30.66")) == "contradict"
    assert verify(text=claim.replace("Without", "With").replace("17.33", "30.66"), source=other) == "not_enough_info"
    assert verify(text=claim.replace("Fires", "Crime")) == "not_enough_info"
    assert verify(text=claim.replace("17.33%", "17.33")) == "not_enough_info"
    assert verify(source=other) == "not_enough_info"
    assert verify(roster=[*cells, {**target, "source_id": "duplicate"}]) == "not_enough_info"
    assert verify(roster=[c for c in cells if c != target]) == "not_enough_info"
    assert verify(context="changed evidence") == "not_enough_info"
    assert verify(question=case["question"].replace("Table 4", "Table 7")) == "not_enough_info"


@pytest.mark.parametrize(("index", "line", "claim", "page"), [
    (0, "Without fine-tuning | (e) RAT-SQL | Fires | 17.33%",
     "Without fine-tuning, RAT-SQL achieved 17.33% exact-match accuracy on Fires.", 6),
    (1, "Llama 2 7B / +TEMP | SST2 | 82.6%",
     "The reported SST2 accuracy for Llama 2 7B with +TEMP is 82.6%.", 4),
    (2, None, None, None),
])
def test_three_case_cpu_replay_to_writer(index, line, claim, page):
    case = CASES[index]
    calls = {"generator": [], "critic": [], "factchecker": []}
    checker = R8FactCheckerNode(NoGeneration(), load_r8_runtime())

    class SimulatedSummarizer(SummarizerNode):
        def _call_generator(self, context, question, retry_instruction, *, id_mode=False):
            assert id_mode
            calls["generator"].append(context)
            if line is None:
                assert not re.search(r"\| Fires \| \d", context)
                return {"claims": []}
            sources = re.split(r"(?m)^\[(S\d+)\] ", context)
            chosen = [id_ for id_, text in zip(sources[1::2], sources[2::2]) if line in text]
            assert len(chosen) == 1
            return {"claims": [{"text": claim, "source_ids": chosen}]}

        def _call_critic(self, context, question, answer, evidence_spans):
            assert line in context and answer == claim and len(evidence_spans) == 1
            calls["critic"].append(context)
            return {"is_supported": True, "reason": "simulated acceptance", "action": "accept"}

    def verify(state):
        calls["factchecker"].append(state)
        return checker(state)

    graph = build_graph(reader=PdfReader(TextPageReader(), max_pages=26, table_coordinates=COORDINATES),
                        retriever=ReplayRetriever(), summarizer=SimulatedSummarizer(None, None, None, None),
                        factchecker=verify, writer=importlib.import_module("05_writer.node").WriterNode(),
                        verifier_policy=R8_POLICY_ID, max_graph_retries=0)
    state = graph.invoke({"pdf_path": pdf_for(case), "question": case["question"]})
    assert calls["generator"] and not state["errors"]
    report = state["final_report"]
    if line is None:
        assert not calls["critic"] and not calls["factchecker"]
        assert not state["verified_claims"] and report["limitations"]
        assert not re.search(r"\d", json.dumps(report.get("sentences", [])))
        return
    assert calls["critic"] and len(calls["factchecker"]) == 1
    assert line in calls["factchecker"][0]["context"]
    assert state["fact_check_results"][0]["verification_method"] == "pdf_coordinate_cell"
    verified, = state["verified_claims"]
    citation = next(c for c in state["pdf_chunks"] if c["source_id"] == verified["source_id"])
    assert citation["metadata"]["page_no"] == page
    assert verified["evidence"] == citation["text"] and line in verified["evidence"]
    assert claim in json.dumps(report) and verified["claim_id"] in json.dumps(report)
