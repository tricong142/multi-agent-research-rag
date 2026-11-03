"""Real Cellfix16 validators with synthetic model outputs; no inference score claim."""
from copy import deepcopy
from contextlib import closing, redirect_stderr, redirect_stdout
import importlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from research_rag import atomic_adapter as a, local
from research_rag.tests.test_integration import FakeRetriever, FakeSummarizer, WriterNode, chunk


CLAIM = "The service reduced latency."


class Backend:
    def __init__(self, outputs):
        self.outputs, self.calls = iter(outputs), []

    def generate_json(self, messages, **options):
        self.calls.append((messages, options))
        return deepcopy(next(self.outputs))


def outputs(context=CLAIM, truth="true"):
    return [
        {"parts": [{"quote": CLAIM, "quantifier": "atomic",
                    "scope": {"entity": "service", "metric": "latency", "time": "", "condition": ""}}],
         "unresolved": []},
        {"scope_match": "matched", "coverage": {"complete": False, "members": [], "quotes": []},
         "observations": [{"member": "service", "truth": truth, "quotes": [context], "numeric": None,
                           "explanation": "Predicate evidence recorded."}],
         "missing_information": ["measurement_unreported"] if truth == "unknown" else [],
         "explanation": "Assess the recorded evidence ledger."},
    ]


class AtomicAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.legacy = importlib.import_module("04_factchecker.inference.atomic_verifier")
        cls.runtime = a.cellfix16_runtime()

    def test_import_uses_exact_candidate_without_replacing_legacy(self):
        self.assertIs(importlib.import_module("04_factchecker.inference.atomic_verifier"), self.legacy)
        self.assertIsNot(self.runtime.atomic, self.legacy)
        self.assertEqual(self.runtime.atomic.POLICY, "atomic-verifier-constrained-v8-cellfix16")
        self.assertTrue(Path(self.runtime.atomic.__file__).resolve().is_relative_to(a.WORKSPACE.resolve()))

    def test_changed_candidate_fails_before_import(self):
        manifest = json.loads((a.ROOT / "docs/atomic-verifier-cellfix16-release.json").read_bytes())["payload_files"]
        with tempfile.TemporaryDirectory() as folder:
            for name in manifest:
                if name.startswith("04_factchecker/") or name == a.CRITERIA_FILE:
                    target = Path(folder) / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes((a.WORKSPACE / name).read_bytes())
            (Path(folder) / "04_factchecker/inference/atomic_verifier.py").write_text("raise RuntimeError('untrusted')")
            with self.assertRaisesRegex(ValueError, "Changed frozen Cellfix16 input"):
                a.cellfix16_runtime(Path(folder))

    def test_completed_labels_and_private_ledger(self):
        cases = [(CLAIM, "true", "support"),
                 ("The service did not reduce latency.", "false", "contradict"),
                 ("The service latency was not measured.", "unknown", "not_enough_info")]
        for context, truth, label in cases:
            with self.subTest(label=label):
                backend = Backend(outputs(context, truth))
                trace = []
                result = a.AtomicFactCheckerNode(backend, self.runtime, on_trace=trace.append)({"claim": CLAIM, "context": context})
                self.assertEqual(result["fact_check_status"], "ok", result)
                self.assertEqual(result["fact_check_label"], label)
                self.assertEqual(result["confidence_score"], float(label == "support"))
                self.assertIn("not a calibrated probability", result["confidence_reasoning"])
                self.assertEqual(len(backend.calls), 2)
                self.assertEqual(trace[0]["result"], result["fact_check_raw"]["atomic"])
                self.assertEqual(result["fact_check_raw"]["atomic"]["parts"][0]["observations"][0]["quotes"], [context])

    def test_invalid_output_exhaustion_never_publishes_support(self):
        backend = Backend([{}] * self.runtime.criteria["max_attempts"])
        result = a.AtomicFactCheckerNode(backend, self.runtime)({"claim": CLAIM, "context": CLAIM})
        self.assertEqual(result["fact_check_status"], "incomplete")
        self.assertEqual(result["fact_check_label"], "not_enough_info")
        self.assertEqual(result["confidence_score"], 0.0)
        self.assertEqual(result["fact_check_raw"]["atomic"]["stop_reason"], "invalid_output_exhausted")

    def test_missing_input_or_expired_deadline_does_not_call_backend(self):
        backend = Backend([])
        node = a.AtomicFactCheckerNode(backend, self.runtime)
        self.assertEqual(node({"claim": CLAIM})["fact_check_status"], "invalid_input")
        self.assertEqual(node({"claim": CLAIM, "context": CLAIM, "deadline_at": 0})["fact_check_status"], "deadline_exceeded")
        self.assertEqual(backend.calls, [])

    def test_remaining_graph_time_limits_atomic_case(self):
        backend = Backend(outputs())
        with patch.object(a.time, "time", return_value=100):
            result = a.AtomicFactCheckerNode(backend, self.runtime)({"claim": CLAIM, "context": CLAIM, "deadline_at": 107})
        self.assertEqual(result["fact_check_raw"]["atomic"]["budget"]["timeout_seconds"], 7)
        self.assertEqual(result["fact_check_raw"]["atomic"]["budget"]["max_calls"], self.runtime.criteria["max_calls_per_case"])

    def graph(self, backend, **options):
        node = a.AtomicFactCheckerNode(backend, self.runtime)
        return local.build_local_graph(verifier="atomic", agents={
            "retriever": FakeRetriever([chunk(CLAIM, "paper:atomic")]),
            "summarizer": FakeSummarizer(CLAIM, CLAIM), "factchecker": node, "writer": WriterNode(),
        }, max_graph_retries=0, **options)

    def test_e2e_support_keeps_source_and_incomplete_blocks_writer(self):
        result = self.graph(Backend(outputs())).invoke({"question": "What happened to latency?"})
        self.assertEqual(result["verified_claims"][0]["source_id"], "paper:atomic")
        self.assertEqual(result["verified_claims"][0]["evidence"], CLAIM)
        self.assertTrue(result["final_report"]["sentences"])
        self.assertEqual(result["budget"]["policy"]["verifier"], a.POLICY_ID)
        failed = self.graph(Backend([{}] * self.runtime.criteria["max_attempts"])).invoke({"question": "Latency?"})
        self.assertEqual(failed["verified_claims"], [])
        self.assertEqual(failed["final_report"]["sentences"], [])

    def test_resume_rejects_switching_verifier(self):
        from langgraph.checkpoint.sqlite import SqliteSaver
        from research_rag.graph import build_graph
        from research_rag.tests.test_integration import FakeFactchecker
        with closing(sqlite3.connect(":memory:", check_same_thread=False)) as connection:
            saver = SqliteSaver(connection)
            config = {"configurable": {"thread_id": "atomic-adapter"}}
            self.graph(Backend(outputs()), checkpointer=saver).invoke(
                {"question": "Latency?"}, config, interrupt_before=["controller"])
            legacy = build_graph(retriever=FakeRetriever([chunk(CLAIM)]), summarizer=FakeSummarizer(CLAIM, CLAIM),
                                 factchecker=FakeFactchecker(["support"]), writer=WriterNode(),
                                 max_graph_retries=0, checkpointer=saver)
            with self.assertRaisesRegex(ValueError, "Resume must use the same budget"):
                legacy.invoke(None, config)

    def test_cli_flag_defaults_legacy_and_forwards_atomic(self):
        for flags, selected in [([], "legacy"), (["--verifier", "atomic"], "atomic")]:
            graph = SimpleNamespace(invoke=lambda state: {"status": "insufficient_evidence"})
            with patch.object(local, "build_local_graph", return_value=graph) as build, \
                    patch.object(sys, "argv", ["local", "--question", "fixture", *flags]), redirect_stdout(io.StringIO()):
                local.main()
            self.assertEqual(build.call_args.kwargs["verifier"], selected)

    def test_unknown_verifier_rejected_before_loading_models(self):
        with self.assertRaisesRegex(ValueError, "verifier must be"):
            local.build_local_graph(verifier="typo")

    def test_atomic_cpu_rejected_before_any_model_load(self):
        torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
        with patch.dict(sys.modules, {"torch": torch}), patch.object(local, "_load_adapter") as load:
            with self.assertRaisesRegex(RuntimeError, "CUDA/NF4"):
                local.build_local_graph(verifier="atomic", allow_cpu=True)
            load.assert_not_called()

    def test_cli_rejects_switching_verifier_on_completed_checkpoint(self):
        from langgraph.checkpoint.sqlite import SqliteSaver
        from research_rag.graph import build_graph
        from research_rag.tests.test_integration import FakeFactchecker
        with tempfile.TemporaryDirectory() as directory:
            for original, selected in [("atomic", "legacy"), ("legacy", "atomic")]:
                database = Path(directory) / (original + ".sqlite")
                config = {"configurable": {"thread_id": "completed-task"}}
                with closing(sqlite3.connect(database, check_same_thread=False)) as connection:
                    saver = SqliteSaver(connection)
                    graph = (self.graph(Backend(outputs()), checkpointer=saver) if original == "atomic" else
                             build_graph(retriever=FakeRetriever([chunk(CLAIM)]), summarizer=FakeSummarizer(CLAIM, CLAIM),
                                         factchecker=FakeFactchecker(["support"]), writer=WriterNode(),
                                         max_graph_retries=0, checkpointer=saver))
                    graph.invoke({"question": "Latency?"}, config)
                stderr = io.StringIO()
                with patch.object(local, "build_local_graph") as build, redirect_stderr(stderr), \
                        patch.object(sys, "argv", ["local", "--resume", "--checkpoint-db", str(database),
                                                  "--thread-id", "completed-task", "--verifier", selected]):
                    with self.assertRaises(SystemExit) as raised:
                        local.main()
                self.assertEqual(raised.exception.code, 2)
                self.assertIn("original --verifier", stderr.getvalue())
                build.assert_not_called()

    def test_model_loader_uses_pinned_base_nf4_and_constrained_backend(self):
        shared = self.runtime.workspace / "04_factchecker/checkpoints/factchecker_merged"
        config = json.loads((shared / "config.json").read_bytes())
        model = SimpleNamespace(config=SimpleNamespace(**config))
        model.eval = lambda: model
        transformers = SimpleNamespace(AutoModelForCausalLM=Mock(), AutoTokenizer=Mock(),
                                       BitsAndBytesConfig=Mock(), GenerationConfig=Mock())
        transformers.AutoModelForCausalLM.from_pretrained.return_value = model
        torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True), float16="float16", manual_seed=Mock())
        snapshot = Mock(return_value="pinned-snapshot")
        backend = SimpleNamespace(generate_json=Mock())
        runtime = SimpleNamespace(**vars(self.runtime))
        runtime.decoding = SimpleNamespace(ConstrainedAtomicBackend=Mock(return_value=backend))
        loaded, generation, events = Mock(), Mock(), []
        with patch.object(a, "cellfix16_runtime", return_value=runtime), \
                patch.dict(sys.modules, {"torch": torch, "transformers": transformers,
                                       "huggingface_hub": SimpleNamespace(snapshot_download=snapshot)}):
            node = a.load_atomic_factchecker(offline=True, on_generation=generation, on_event=events.append, on_model_loaded=loaded)
        snapshot.assert_called_once_with(runtime.criteria["base_model"], revision=runtime.criteria["base_revision"],
                                         local_files_only=True, allow_patterns=["*.json", "*.safetensors", "*.txt", "LICENSE"])
        self.assertEqual(transformers.AutoModelForCausalLM.from_pretrained.call_args.args, ("pinned-snapshot",))
        self.assertEqual(transformers.BitsAndBytesConfig.call_args.kwargs["bnb_4bit_quant_type"], "nf4")
        torch.manual_seed.assert_called_once_with(42)
        self.assertIs(node.backend, backend)
        self.assertIs(backend.on_generation, generation)
        runtime.decoding.ConstrainedAtomicBackend.assert_called_once_with(model, transformers.AutoTokenizer.from_pretrained.return_value)
        loaded.assert_called_once_with("atomic_base_instruct_cellfix16")
        backend.generate_json([], max_new_tokens=1)
        self.assertEqual(events[0]["component"], "atomic_verifier")


if __name__ == "__main__":
    unittest.main()
