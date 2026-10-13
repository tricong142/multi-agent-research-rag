"""Opt-in local model loader and command line entry point for the five-agent graph."""

from __future__ import annotations

import argparse
import importlib
import json
import math
import sqlite3
import subprocess
import sys
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Callable

from .adapters import PdfReader
from .graph import build_graph
from .controller import budget_config
from .observe import run_with_metrics, observe_call
from .retrieval import CORPUS_PATH, INDEX_DIR, RetrievalService, RetrievalAgent


ROOT = Path(__file__).resolve().parents[1]


def _load_adapter(adapter_dir: Path, *, offline: bool, quantize_4bit: bool = False) -> tuple[Any, Any]:
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    adapter_config = json.loads((adapter_dir / "adapter_config.json").read_text(encoding="utf-8"))
    base_name = adapter_config["base_model_name_or_path"]
    tokenizer = AutoTokenizer.from_pretrained(adapter_dir, local_files_only=offline)
    load_options = {}
    if quantize_4bit:
        dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        load_options["torch_dtype"] = dtype
        load_options["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=dtype,
        )
    base = AutoModelForCausalLM.from_pretrained(
        base_name, device_map="auto", local_files_only=offline,
        **({"torch_dtype": "auto"} | load_options),
    )
    return PeftModel.from_pretrained(base, str(adapter_dir)).eval(), tokenizer


def build_local_graph(*, offline: bool = True, allow_cpu: bool = False, max_graph_retries: int = 1,
                      quantize_4bit: bool = False,
                      retrieval_policy: str = "adaptive",
                      initial_top_k: int = 5, max_factcheck_calls: int = 120,
                      agents: dict[str, Any] | None = None,
                      components_only: bool = False,
                      corpus_path: Path = CORPUS_PATH, index_dir: Path = INDEX_DIR,
                      on_model_loaded: Callable[[str], None] | None = None,
                      on_generation: Callable[[dict], None] | None = None,
                      max_steps: int = 30, max_seconds: float = 600.0,
                      max_cost_usd: float | None = None, action_cost_bounds: dict[str, float] | None = None,
                      checkpointer: Any = None, on_event: Callable[[dict], None] | None = None) -> Any:
    """Load local checkpoints. Two 7B Summarizer models need substantial memory."""
    graph_options = dict(max_graph_retries=max_graph_retries, initial_top_k=initial_top_k,
                         max_factcheck_calls=max_factcheck_calls,
                         max_steps=max_steps, max_seconds=max_seconds, max_cost_usd=max_cost_usd,
                         action_cost_bounds=action_cost_bounds, checkpointer=checkpointer, on_event=on_event)
    if agents is not None:
        return build_graph(**agents, **graph_options)
    import torch

    if not torch.cuda.is_available() and not allow_cpu:
        raise RuntimeError("No CUDA GPU detected; use a GPU host or inject remote model services")
    if quantize_4bit and not torch.cuda.is_available():
        raise RuntimeError("4-bit loading requires a CUDA GPU")
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    summarizer_module = importlib.import_module("train_agent3_summarizer.node")
    factchecker_module = importlib.import_module("04_factchecker.node")
    fact_inference = importlib.import_module("04_factchecker.inference")
    writer_module = importlib.import_module("05_writer.node")
    writer_loop = importlib.import_module("05_writer.loop_controller")
    writer_inference = importlib.import_module("05_writer.inference")

    generator, generator_tokenizer = _load_adapter(
        ROOT / "train_agent3_summarizer" / "checkpoints" / "generator_qlora" / "final",
        offline=offline, quantize_4bit=quantize_4bit
    )
    if on_model_loaded:
        on_model_loaded("summarizer_generator")
    critic, critic_tokenizer = _load_adapter(
        ROOT / "train_agent3_summarizer" / "checkpoints" / "critic_qlora" / "final",
        offline=offline, quantize_4bit=quantize_4bit
    )
    if on_model_loaded:
        on_model_loaded("summarizer_critic")
    summarizer = summarizer_module.SummarizerNode(generator, generator_tokenizer, critic, critic_tokenizer,
                                                 on_generation=on_generation)
    def backend_event(event):
        if on_event:
            on_event(event)
        if on_generation:
            on_generation(event)
    summarizer._call_generator = observe_call(summarizer._call_generator, "summarizer_generator", backend_event)
    summarizer._call_critic = observe_call(summarizer._call_critic, "summarizer_critic", backend_event)

    fact_dir = ROOT / "04_factchecker" / "checkpoints" / "factchecker_merged"
    fact_tokenizer = AutoTokenizer.from_pretrained(fact_dir, local_files_only=True)
    fact_load_options = {}
    if quantize_4bit:
        dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        fact_load_options = {
            "torch_dtype": dtype,
            "quantization_config": BitsAndBytesConfig(
                load_in_4bit=True, bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=dtype,
            ),
        }
    fact_model = AutoModelForCausalLM.from_pretrained(
        fact_dir, device_map="auto", local_files_only=True,
        **({"torch_dtype": "auto"} | fact_load_options),
    ).eval()
    if on_model_loaded:
        on_model_loaded("factchecker_merged")
    fact_backend = fact_inference.TransformersJSONBackend(fact_model, fact_tokenizer, on_generation=on_generation)
    fact_backend.generate_json = observe_call(fact_backend.generate_json, "factchecker", backend_event)
    factchecker = factchecker_module.FactCheckerNode(
        fact_inference.FactCheckJudge(fact_backend),
        fact_inference.ConfidenceEstimator(fact_backend),
        fact_inference.ActionRecommender(fact_backend),
    )

    writer_adapter = ROOT / "05_writer" / "checkpoints" / "writer_qlora"
    writer_base = json.loads((writer_adapter / "adapter_config.json").read_text(encoding="utf-8"))["base_model_name_or_path"]
    writer_backend = writer_inference.HFJsonBackend(
        writer_base, adapter_path=str(writer_adapter),
        load_in_4bit=torch.cuda.is_available(), local_files_only=offline,
    )
    writer = writer_module.WriterNode(writer_loop.WriterLoopController(
        writer_inference.ReportGenerator(writer_backend),
        writer_inference.Critic(writer_backend),
        writer_inference.ActionSelector(writer_backend),
    ))
    writer_backend.generate = observe_call(writer_backend.generate, "writer", backend_event)

    loaded = dict(retriever=RetrievalAgent(RetrievalService(corpus_path=corpus_path, index_dir=index_dir, offline=offline), policy=retrieval_policy),
                  reader=PdfReader(), summarizer=summarizer, factchecker=factchecker, writer=writer)
    return loaded if components_only else build_graph(**loaded, **graph_options)


def run_worker(command: list[str], timeout_seconds: float) -> int:
    """Hard process deadline, including model loading. Kill only the worker tree we started."""
    import psutil

    worker = subprocess.Popen(command)
    try:
        return worker.wait(timeout=timeout_seconds)
    except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
        try:
            processes = psutil.Process(worker.pid).children(recursive=True)
        except psutil.NoSuchProcess:
            processes = []
        worker.kill()
        for process in processes:
            try:
                process.kill()
            except psutil.NoSuchProcess:
                pass
        worker.wait()
        psutil.wait_procs(processes, timeout=5)
        if isinstance(exc, KeyboardInterrupt):
            raise
        print(json.dumps({"status": "timed_out", "stop_reason": "process_timeout",
                          "note": "Resume from the last saved checkpoint; unfinished calls may be repeated."}), file=sys.stderr)
        return 124


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the five-agent research RAG graph")
    parser.add_argument("--question")
    parser.add_argument("--pdf", help="Optional PDF; without it, search the selected corpus")
    parser.add_argument("--corpus", type=Path, default=CORPUS_PATH)
    parser.add_argument("--index-dir", type=Path, default=INDEX_DIR)
    parser.add_argument("--allow-cpu", action="store_true", help="Allow loading all local models without CUDA")
    parser.add_argument("--online-model-downloads", action="store_true", help="Allow downloading missing base models")
    parser.add_argument("--quantize-4bit", action="store_true", help="Try 4-bit loading for Summarizer and Fact-Checker on CUDA")
    parser.add_argument("--profile-resources", action="store_true", help="Log RSS and CUDA memory after model loading and graph execution")
    parser.add_argument("--max-graph-retries", type=int, default=1)
    parser.add_argument("--retrieval-policy", choices=["adaptive", "bm25", "dense"], default="adaptive")
    parser.add_argument("--initial-top-k", type=int, default=5)
    parser.add_argument("--max-factcheck-calls", type=int, default=120)
    parser.add_argument("--plan", type=Path, help="Optional structured research task specification; completion assertions are reset")
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument("--max-seconds", type=float, default=600,
                        help="Task deadline, checked between synchronous calls; persists across resume")
    parser.add_argument("--process-timeout", type=float,
                        help="Hard wall-clock timeout in a worker process, including model loading")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--max-cost-usd", type=float)
    parser.add_argument("--action-cost-bounds", type=Path,
                        help="JSON upper bounds in USD for read/search/summarize/factcheck/write, including internal calls")
    parser.add_argument("--checkpoint-db", type=Path, help="Private SQLite file containing task/evidence state")
    parser.add_argument("--thread-id", help="Required with --checkpoint-db; one ID per research task")
    parser.add_argument("--resume", action="store_true", help="Continue the saved task without resetting budgets")
    parser.add_argument("--events-output", type=Path, help="Append content-free decision and tool-call JSONL events")
    parser.add_argument("--metrics-output", type=Path, help="Write timings/status only; no prompt or report text")
    parser.add_argument("--trace-output", type=Path,
                        help="Opt-in PRIVATE JSONL: raw Summarizer output and final graph state, including source text; requires a new file")
    args = parser.parse_args()
    if bool(args.checkpoint_db) != bool(args.thread_id):
        parser.error("--checkpoint-db and --thread-id must be used together")
    if args.resume:
        if not args.checkpoint_db or args.question or args.pdf or args.plan:
            parser.error("--resume requires a checkpoint and thread ID; omit --question and --pdf")
    elif not args.question:
        parser.error("--question is required for a new task")
    if not 0 <= args.max_graph_retries <= 5:
        parser.error("--max-graph-retries must be in [0, 5]")
    if args.process_timeout is not None:
        if not math.isfinite(args.process_timeout) or args.process_timeout <= 0:
            parser.error("--process-timeout must be finite and positive")
        if not args.worker:
            raise SystemExit(run_worker([sys.executable, "-m", "research_rag.local", *sys.argv[1:], "--worker"], args.process_timeout))
    args.cost_bounds = json.loads(args.action_cost_bounds.read_text(encoding="utf-8")) if args.action_cost_bounds else None
    if args.cost_bounds is not None and not isinstance(args.cost_bounds, dict):
        parser.error("--action-cost-bounds must contain a JSON object")
    budget_config(max_steps=args.max_steps, max_seconds=args.max_seconds,
                  max_searches=args.max_graph_retries + 1, max_cost_usd=args.max_cost_usd,
                  action_cost_bounds=args.cost_bounds)
    with ExitStack() as stack:
        checkpointer = None
        if args.checkpoint_db:
            from langgraph.checkpoint.sqlite import SqliteSaver
            from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

            args.checkpoint_db.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(args.checkpoint_db, check_same_thread=False)
            stack.callback(connection.close)
            checkpointer = SqliteSaver(connection, serde=JsonPlusSerializer(allowed_msgpack_modules=[]))
            saved = checkpointer.get({"configurable": {"thread_id": args.thread_id}})
            if args.resume and saved is None:
                parser.error("No checkpoint exists for this thread")
            if not args.resume and saved is not None:
                parser.error("Thread already exists; use --resume or a new --thread-id")
        _run(args, checkpointer)


def _run(args: argparse.Namespace, checkpointer: Any) -> None:
    resource_snapshots = []
    if args.trace_output:
        args.trace_output.parent.mkdir(parents=True, exist_ok=True)
        # Refuse to overwrite a previous diagnostic run.
        with args.trace_output.open("x", encoding="utf-8"):
            pass

    def write_trace(event: dict) -> None:
        with args.trace_output.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def write_event(event: dict) -> None:
        args.events_output.parent.mkdir(parents=True, exist_ok=True)
        with args.events_output.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event | {"thread_id": args.thread_id}) + "\n")

    def record_resources(stage: str) -> None:
        import psutil
        import torch

        snapshot = {"stage": stage, "rss_bytes": psutil.Process().memory_info().rss,
                    "cuda": [{"device": index,
                              "allocated_bytes": torch.cuda.memory_allocated(index),
                              "peak_allocated_bytes": torch.cuda.max_memory_allocated(index),
                              "free_bytes": torch.cuda.mem_get_info(index)[0]}
                             for index in range(torch.cuda.device_count())]}
        resource_snapshots.append(snapshot)
        print(json.dumps(snapshot), file=sys.stderr, flush=True)

    graph = build_local_graph(offline=not args.online_model_downloads, allow_cpu=args.allow_cpu,
                              corpus_path=args.corpus, index_dir=args.index_dir,
                              max_graph_retries=args.max_graph_retries,
                              retrieval_policy=args.retrieval_policy, initial_top_k=args.initial_top_k,
                              max_factcheck_calls=args.max_factcheck_calls,
                              quantize_4bit=args.quantize_4bit,
                              on_model_loaded=record_resources if args.profile_resources else None,
                              on_generation=write_trace if args.trace_output else None,
                              max_steps=args.max_steps, max_seconds=args.max_seconds,
                              max_cost_usd=args.max_cost_usd, action_cost_bounds=args.cost_bounds,
                              checkpointer=checkpointer, on_event=write_event if args.events_output else None)
    input_state = None if args.resume else {"question": args.question, "pdf_path": args.pdf}
    if args.plan:
        input_state["research_plan"] = json.loads(args.plan.read_text(encoding="utf-8"))
    config = {"configurable": {"thread_id": args.thread_id}} if checkpointer else None
    if args.metrics_output:
        result, metrics = run_with_metrics(graph, input_state, config)
        if args.profile_resources:
            record_resources("graph_complete")
            metrics["resource_snapshots"] = resource_snapshots
        args.metrics_output.parent.mkdir(parents=True, exist_ok=True)
        args.metrics_output.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        result = graph.invoke(input_state, config) if config else graph.invoke(input_state)
        if args.profile_resources:
            record_resources("graph_complete")
    if args.trace_output:
        write_trace({"event": "graph_result", "state": result})
    print(json.dumps({key: result.get(key) for key in ("status", "stop_reason", "steps_used", "reserved_cost_usd",
                                                     "final_report", "verified_claims", "agent_result", "errors", "low_confidence_warning",
                                                     "summary_diagnostics", "research_plan", "active_task_id")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
