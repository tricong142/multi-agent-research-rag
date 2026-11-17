"""Local web entry point for the locked R8 v12 PDF workflow and its saved GPU demo."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import threading
import uuid
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from research_rag.retrieval import RetrievalService, tokenize

DATA = ROOT / "artifacts/r8-v12-e2e-real-pdf"
ARCHIVE_NAME = "r8-v12-e2e-real-pdf-table-proof-w3dquqnw.zip"
ARCHIVE_SHA = "d12dff01150ca1d83f9b5479a5fe75ffd186f0415d1bac03401bb14fd8b4ef8d"
ACTIONS = {"search", "read", "summarize", "factcheck", "write"}
LOG = logging.getLogger("web_demo")
MAX_PDF_BYTES = 25 * 1024 * 1024
MAX_PAGES = 26
STATIC_FILES = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
                "/styles.css": ("styles.css", "text/css")}
CHECKPOINT_FILES = (
    "train_agent2_reader/layoutlmv3_doclaynet_model/config.json",
    "train_agent2_reader/layoutlmv3_doclaynet_model/model.safetensors",
    "train_agent3_summarizer/checkpoints/generator_qlora/final/adapter_config.json",
    "train_agent3_summarizer/checkpoints/generator_qlora/final/adapter_model.safetensors",
    "train_agent3_summarizer/checkpoints/critic_qlora/final/adapter_config.json",
    "train_agent3_summarizer/checkpoints/critic_qlora/final/adapter_model.safetensors",
    "05_writer/checkpoints/writer_qlora/adapter_config.json",
    "05_writer/checkpoints/writer_qlora/adapter_model.safetensors",
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_lines(path):
    if not path.is_file():
        return []
    raw = path.read_bytes()
    return [json.loads(line) for line in raw.split(b"\n")[:-1] if line.strip()]


def agent_events(events):
    return [{k: row[k] for k in ("event", "action", "step", "status", "elapsed_ms") if k in row}
            for row in events if row.get("event") in {"tool_start", "agent_result"} and row.get("action") in ACTIONS]


class PdfLibrary:
    def __init__(self):
        import fitz

        self.manifest = json.loads((DATA / "manifest.json").read_bytes())
        raw = (DATA / "inputs.json").read_bytes()
        if digest(raw) != self.manifest["inputs_sha256"]:
            raise ValueError("Câu hỏi demo sai hash.")
        self.examples = json.loads(raw)
        self.papers = {}
        self.pages = []
        for name, entry in self.manifest["pdfs"].items():
            path = ROOT / entry["path"]
            if digest(path.read_bytes()) != entry["sha256"]:
                raise ValueError(f"PDF sai hash: {name}")
            with fitz.open(path) as doc:
                title = (doc.metadata.get("title") or "").strip() or path.stem
                self.papers[name] = {**entry, "path": path, "title": title, "pages": len(doc)}
                for page in doc:
                    text = page.get_text().strip()
                    if text:
                        self.pages.append({"doc_id": f"{name}:{page.number}", "text": text,
                                           "metadata": {"paper": name}})
        self.retriever = RetrievalService()

    def select(self, question):
        # Keep the PDF selection limited to locally available, hash-checked sources.
        hits = self.retriever.search(question, method="bm25", pdf_chunks=self.pages, top_k=5)["chunks"]
        query = set(tokenize(question)) - {
            "a", "an", "and", "are", "at", "can", "did", "do", "for", "from", "how", "in", "is",
            "of", "on", "or", "the", "to", "used", "was", "were", "what", "which", "with", "table",
        }
        return next((hit["metadata"]["paper"] for hit in hits
                     if hit["score"] > 0 and len(query.intersection(tokenize(hit["text"]))) >= 2), None)

    def result(self, state, paper, events, *, mode, uploaded=None):
        source = uploaded if uploaded is not None else self.papers[paper]
        pdf_url = source["url"] if uploaded is not None else f"/pdf/{paper}"
        chunks = {c["source_id"]: c for c in state.get("pdf_chunks", [])}
        claims = {}
        for claim in state.get("verified_claims", []):
            chunk = chunks.get(claim["source_id"])
            quote = claim["evidence"]
            if not chunk or not quote or quote not in chunk["text"]:
                raise ValueError("Claim đã xác minh thiếu đoạn nguồn PDF.")
            page = None
            index = chunk["metadata"].get("page_no")
            if type(index) is int and 0 <= index < source["pages"]:
                page = index + 1
            claims[claim["claim_id"]] = {
                "text": claim["text"], "source_id": claim["source_id"], "quote": quote,
                "title": source["title"], "page": page, "url": f"{pdf_url}#page={page}" if page else pdf_url,
            }
        if any(id_ not in claims for sentence in state["final_report"]["sentences"] for id_ in sentence["claim_ids"]):
            raise ValueError("Báo cáo tham chiếu claim chưa được xác minh.")
        return {
            "mode": mode, "question": state["question"], "paper": source["title"],
            "report": state["final_report"], "claims": claims, "events": agent_events(events),
            "graph_status": state["status"], "stop_reason": state.get("stop_reason"),
            "factcheck_calls": state.get("factcheck_calls_used", 0),
            "graph_errors": state.get("errors", []),
        }


def load_archive(path, library):
    if not path.is_file():
        return {}
    if digest(path.read_bytes()) != ARCHIVE_SHA:
        raise ValueError("ZIP GPU sai SHA-256.")
    with ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError("ZIP GPU bị hỏng.")
        review = json.loads(archive.read("review.json"))
        if not review["complete_roster"] or [c["id"] for c in review["cases"]] != [c["id"] for c in library.examples]:
            raise ValueError("ZIP GPU thiếu ca demo.")
        results = {}
        for case in review["cases"]:
            case_id = case["id"]
            records = [json.loads(line) for line in archive.read(f"{case_id}/trace.private.jsonl").splitlines()]
            state = next(row["state"] for row in reversed(records) if row["event"] == "graph_result")
            if state["final_report"] != case["report"] or case["process"]["exit_code"] != 0:
                raise ValueError(f"Báo cáo lưu sẵn sai trạng thái: {case_id}")
            events = [json.loads(line) for line in archive.read(f"{case_id}/events.jsonl").splitlines()]
            results[case_id] = library.result(state, case["paper"], events, mode="saved_gpu")
    return results


def live_preflight():
    problems = [f"Thiếu checkpoint {path}" for path in CHECKPOINT_FILES if not (ROOT / path).is_file()]
    try:
        import torch

        if not torch.cuda.is_available():
            problems.append(f"PyTorch {torch.__version__} không thấy CUDA. R8 v12 NF4 cần GPU NVIDIA.")
    except ImportError:
        problems.append("Môi trường Python thiếu PyTorch.")
    return problems


def read_submission(content_type, raw):
    if content_type.split(";", 1)[0].strip().lower() == "application/json":
        question = json.loads(raw)["question"]
        upload = None
    else:
        headers = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("ascii")
        message = BytesParser(policy=policy.default).parsebytes(headers + raw)
        if message.get_content_type() != "multipart/form-data" or not message.is_multipart() or message.defects:
            raise ValueError("Yêu cầu chứa PDF không hợp lệ.")
        parts = list(message.iter_parts())
        fields = {part.get_param("name", header="content-disposition"): part for part in parts}
        if set(fields) != {"question", "pdf"} or len(parts) != 2:
            raise ValueError("Gửi một câu hỏi và một file PDF.")
        question = fields["question"].get_payload(decode=True).decode("utf-8")
        part = fields["pdf"]
        title = (part.get_filename() or "").replace("\\", "/").rsplit("/", 1)[-1]
        pdf = part.get_payload(decode=True)
        if not title.lower().endswith(".pdf") or not pdf or len(pdf) > MAX_PDF_BYTES or not pdf.startswith(b"%PDF-"):
            raise ValueError("Chọn file PDF hợp lệ, tối đa 25 MiB.")
        import fitz

        try:
            with fitz.open(stream=pdf, filetype="pdf") as document:
                pages = document.page_count
                if document.needs_pass:
                    raise ValueError("PDF có mật khẩu.")
        except RuntimeError as exc:
            raise ValueError("Không đọc được file PDF.") from exc
        if not 1 <= pages <= MAX_PAGES:
            raise ValueError(f"PDF phải có từ 1 đến {MAX_PAGES} trang.")
        upload = {"title": title, "pages": pages, "bytes": pdf}
    if not isinstance(question, str) or not question.strip() or len(question.strip()) > 4000 or "\x00" in question:
        raise ValueError("Nhập câu hỏi từ 1 đến 4.000 ký tự.")
    return question.strip(), upload


class DemoEngine:
    def __init__(self, library, archived, problems, *, online=False):
        self.library = library
        self.archived = archived
        self.problems = problems
        self.online = online
        self.job = None
        self.lock = threading.Lock()

    def start(self, question, uploaded=None):
        if self.problems:
            return 503, {"error": " ".join(self.problems)}
        with self.lock:
            if self.job and self.job["status"] == "running":
                return 409, {"error": "Một câu hỏi đang chạy."}
            job = {"id": uuid.uuid4().hex, "status": "running", "question": question}
            if uploaded is not None:
                job["uploaded"] = {**uploaded, "url": f"/api/run/{job['id']}/pdf"}
            self.job = job
            threading.Thread(target=self.run, args=(job,), daemon=True).start()
        return 202, {"id": job["id"]}

    def run(self, job):
        try:
            question = job["question"]
            uploaded = job.get("uploaded")
            paper = self.library.select(question) if uploaded is None else None
            if paper is None and uploaded is None:
                job.update(status="done", result={
                    "mode": "live_local", "question": question, "paper": None, "claims": {}, "events": [],
                    "report": {"title": "Báo cáo nghiên cứu", "sentences": [],
                               "limitations": ["Thư viện PDF local chưa có tài liệu phù hợp với câu hỏi."]},
                    "graph_status": "no_local_source",
                })
                return
            with TemporaryDirectory(prefix="research-rag-web-") as tmp:
                folder = Path(tmp)
                events = folder / "events.jsonl"
                trace = folder / "trace.jsonl"
                source = uploaded if uploaded is not None else self.library.papers[paper]
                pdf_path = folder / "input.pdf" if uploaded is not None else source["path"]
                if uploaded is not None:
                    pdf_path.write_bytes(uploaded["bytes"])
                job.update(event_file=events, paper=source["title"])
                command = [
                    sys.executable, "-m", "research_rag.local", "--verifier", "r8-v12", "--quantize-4bit",
                    f"--question={question}", "--pdf", str(pdf_path), "--pdf-max-pages", str(MAX_PAGES),
                    "--pdf-table-coordinates", str(DATA / "table-coordinates.json"),
                    "--retrieval-policy", self.library.manifest["retrieval"],
                    "--initial-top-k", str(self.library.manifest["initial_top_k"]),
                    "--process-timeout", "3600", "--events-output", str(events), "--trace-output", str(trace),
                ]
                if self.online:
                    command.append("--online-model-downloads")
                env = {**os.environ, "PYTHONUTF8": "1"}
                with (folder / "stderr.log").open("w", encoding="utf-8") as stderr:
                    proc = subprocess.run(command, cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=stderr,
                                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                measured = json_lines(events)
                if proc.returncode:
                    LOG.error("Pipeline %s exited %s\n%s", job["id"], proc.returncode,
                              (folder / "stderr.log").read_text(encoding="utf-8", errors="replace")[-2400:])
                    job.update(status="failed", events=agent_events(measured),
                               error=f"Pipeline dừng với mã {proc.returncode}. Xem log ở cửa sổ khởi động.")
                    return
                state = next(row["state"] for row in reversed(json_lines(trace)) if row["event"] == "graph_result")
                result = self.library.result(state, paper, measured, mode="live_local", uploaded=uploaded)
                job.update(status="done", result=result)
        except Exception:
            LOG.exception("Pipeline %s failed", job["id"])
            job.update(status="failed", error="Không tạo được báo cáo. Xem log ở cửa sổ khởi động.")

    def status(self, id_):
        job = dict(self.job or {})
        if job.get("id") != id_:
            return None
        path = job.pop("event_file", None)
        job.pop("uploaded", None)
        if job["status"] == "running" and path:
            try:
                job["events"] = agent_events(json_lines(path))
            except FileNotFoundError:
                pass
        return job

    def uploaded_pdf(self, id_):
        job = self.job or {}
        if job.get("id") == id_ and (uploaded := job.get("uploaded")):
            return uploaded["bytes"]
        return None


def make_handler(engine):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, payload, kind="application/json"):
            raw = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            port = self.server.server_port
            if self.headers.get("Host") not in {f"127.0.0.1:{port}", f"localhost:{port}"}:
                self.reply(403, {"error": "Chỉ phục vụ web local."})
                return
            path = self.path.split("?", 1)[0]
            if path in STATIC_FILES:
                name, kind = STATIC_FILES[path]
                self.reply(200, (STATIC / name).read_bytes(), kind + "; charset=utf-8")
            elif path == "/api/status":
                self.reply(200, {"live_ready": not engine.problems, "problems": engine.problems,
                                 "examples": engine.library.examples, "saved_cases": list(engine.archived),
                                 "papers": [p["title"] for p in engine.library.papers.values()]})
            elif match := re.fullmatch(r"/api/run/([a-f0-9]{32})/pdf", path):
                pdf = engine.uploaded_pdf(match[1])
                if pdf is not None:
                    self.reply(200, pdf, "application/pdf")
                else:
                    self.reply(404, {"error": "Không tìm thấy PDF của lượt chạy."})
            elif path.startswith("/api/run/"):
                result = engine.status(path.rsplit("/", 1)[-1])
                self.reply(200 if result else 404, result or {"error": "Không tìm thấy lượt chạy."})
            elif path.startswith("/api/saved/"):
                result = engine.archived.get(path.rsplit("/", 1)[-1])
                self.reply(200 if result else 404, result or {"error": "Không tìm thấy kết quả lưu sẵn."})
            elif match := re.fullmatch(r"/pdf/([a-z0-9-]+)", path):
                paper = engine.library.papers.get(match[1])
                if paper:
                    raw = paper["path"].read_bytes()
                    if digest(raw) == paper["sha256"]:
                        self.reply(200, raw, "application/pdf")
                    else:
                        self.reply(409, {"error": "PDF nguồn sai hash."})
                else:
                    self.reply(404, {"error": "Không tìm thấy PDF."})
            else:
                self.reply(404, {"error": "Đường dẫn không tồn tại."})

        def do_POST(self):
            port = self.server.server_port
            hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
            if self.headers.get("Host") not in hosts or self.headers.get("Origin") not in {
                    None, *(f"http://{host}" for host in hosts)}:
                self.reply(403, {"error": "Chỉ nhận yêu cầu từ web local."})
                return
            if self.path != "/api/run":
                self.reply(404, {"error": "Đường dẫn không tồn tại."})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                content_type = self.headers.get("Content-Type", "")
                kind = self.headers.get_content_type()
                limit = 20000 if kind == "application/json" else MAX_PDF_BYTES + 65536
                if kind not in {"application/json", "multipart/form-data"} or not 0 < length <= limit:
                    raise ValueError("Câu hỏi hoặc file PDF vượt kích thước cho phép.")
                question, uploaded = read_submission(content_type, self.rfile.read(length))
            except ValueError as exc:
                self.reply(400, {"error": str(exc) if type(exc) is ValueError else "Câu hỏi hoặc file PDF không hợp lệ."})
                return
            except (TypeError, KeyError, AttributeError):
                self.reply(400, {"error": "Nhập câu hỏi từ 1 đến 4.000 ký tự."})
                return
            self.reply(*engine.start(question, uploaded))

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port", type=int, nargs="?", default=8080)
    parser.add_argument("--archive", type=Path, default=Path.home() / "Downloads" / ARCHIVE_NAME)
    parser.add_argument("--online-model-downloads", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    library = PdfLibrary()
    try:
        archived = load_archive(args.archive, library)
    except (OSError, ValueError) as exc:
        LOG.warning("Không mở được kết quả lưu sẵn: %s", exc)
        archived = {}
    engine = DemoEngine(library, archived, live_preflight(), online=args.online_model_downloads)
    with ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(engine)) as server:
        print(f"http://127.0.0.1:{server.server_port}", flush=True)
        for problem in engine.problems:
            print(problem, flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
