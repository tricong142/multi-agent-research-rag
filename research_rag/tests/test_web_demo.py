import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from web_demo import server


@pytest.fixture(scope="module")
def library():
    return server.PdfLibrary()


def test_demo_questions_use_real_pdf_lookup(library):
    for example in library.examples:
        assert library.select(example["question"]) == example["paper"]
    assert library.select("Who won the 2024 Copa America?") is None


@pytest.mark.parametrize(("example_number", "with_upload"), [(0, False), (2, False), (0, True)])
def test_web_worker_preserves_graph_report_and_source(monkeypatch, library, example_number, with_upload):
    example = library.examples[example_number]
    claim = {"claim_id": "claim:1", "source_id": "source-1", "evidence": "Fires | 17.33%",
             "text": "Without fine-tuning, RAT-SQL achieved 17.33% exact-match accuracy on Fires."}
    answerable = example_number == 0
    engine = server.DemoEngine(library, {}, [])
    pdf = library.papers[example["paper"]]["path"]
    uploaded = {"title": "My paper.pdf", "pages": 13, "bytes": pdf.read_bytes(),
                "url": "/api/run/test/pdf"} if with_upload else None

    def worker(command, **kwargs):
        assert command[command.index("--verifier") + 1] == "r8-v12"
        reader_input = Path(command[command.index("--pdf") + 1])
        if with_upload:
            assert reader_input.name == "input.pdf" and reader_input.read_bytes() == uploaded["bytes"]
        else:
            assert reader_input == pdf
        assert f"--question={example['question']}" in command
        state = {
            "question": example["question"],
            "verified_claims": [claim] if answerable else [],
            "pdf_chunks": [{"source_id": "source-1", "metadata": {"page_no": 6}, "text": "Fires | 17.33%"}],
            "factcheck_calls_used": int(answerable),
            "status": "partial" if answerable else "insufficient_evidence",
            "final_report": {
                "title": "Research report",
                "sentences": [{"text": claim["text"], "claim_ids": ["claim:1"]}] if answerable else [],
                "limitations": [] if answerable else ["Insufficient evidence."],
            },
        }
        if answerable:
            events = [{"event": "agent_result", "action": name, "status": "ok", "step": i}
                      for i, name in enumerate(sorted(server.ACTIONS), 1)]
        else:
            events = [{"event": "agent_result", "action": "read", "status": "read_ready", "step": 1}]
        for flag, rows in (
            ("--events-output", events),
            ("--trace-output", [{"event": "graph_result", "state": state}]),
        ):
            Path(command[command.index(flag) + 1]).write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(server.subprocess, "run", worker)
    job = {"question": example["question"], "status": "running", "id": "test"}
    if with_upload:
        job["uploaded"] = uploaded
    engine.job = job
    engine.run(job)
    assert job["status"] == "done"
    result = job["result"]
    assert result["mode"] == "live_local"
    if answerable:
        assert {row["action"] for row in result["events"]} == server.ACTIONS
        assert result["claims"]["claim:1"]["page"] == 7
        assert result["claims"]["claim:1"]["url"] == (
            "/api/run/test/pdf#page=7" if with_upload else "/pdf/kaggledbqa#page=7")
        assert result["graph_status"] == "partial"
        if with_upload:
            assert engine.uploaded_pdf("test") == uploaded["bytes"]
            assert engine.uploaded_pdf("other") is None and "uploaded" not in engine.status("test")
    else:
        assert result["report"]["sentences"] == []
        assert result["report"]["limitations"] and result["factcheck_calls"] == 0
        assert not result["claims"] and not any(row["action"] == "write" for row in result["events"])


def test_missing_cuda_never_substitutes_simulated_answers(library):
    engine = server.DemoEngine(library, {}, ["CUDA unavailable"])
    assert engine.start(library.examples[0]["question"]) == (503, {"error": "CUDA unavailable"})
    assert engine.job is None


def test_multipart_pdf_validation(library):
    name = "Thử PDF".encode("utf-8")
    question = "Tài liệu có câu trả lời không?".encode("utf-8")
    pdf = library.papers["kaggledbqa"]["path"].read_bytes()
    content_type = "multipart/form-data; boundary=demo-boundary"
    body = (
        b'--demo-boundary\r\nContent-Disposition: form-data; name="question"\r\n\r\n'
        + question
        + b'\r\n--demo-boundary\r\nContent-Disposition: form-data; name="pdf"; filename="'
        + name
        + b'.pdf"\r\nContent-Type: application/pdf\r\n\r\n'
    )
    footer = b"\r\n--demo-boundary--\r\n"
    text, uploaded = server.read_submission(content_type, body + pdf + footer)
    assert text == question.decode("utf-8")
    assert uploaded == {"title": "Thử PDF.pdf", "pages": 13, "bytes": pdf}
    for broken in (b"plain text", b"%PDF-false"):
        with pytest.raises(ValueError):
            server.read_submission(content_type, body + broken + footer)


def test_missing_pdf_source_fails_closed(library):
    state = {
        "verified_claims": [{"claim_id": "claim:1", "source_id": "missing", "evidence": "unbound"}],
        "pdf_chunks": [],
    }
    with pytest.raises(ValueError, match="thiếu đoạn nguồn"):
        library.result(state, "kaggledbqa", [], mode="live_local")
