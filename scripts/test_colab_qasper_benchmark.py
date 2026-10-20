"""Verify notebook bytes and run regression from its exact isolated payload."""
import ast
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


class ColabQasperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.notebook_path = ROOT / "scripts/colab_qasper_bm25_dense_dev.ipynb"
        cls.notebook = json.loads(cls.notebook_path.read_text(encoding="utf-8"))
        cls.code = [c["source"] for c in cls.notebook["cells"] if c["cell_type"] == "code"]
        constants = {}
        for node in ast.parse(cls.code[0]).body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                if node.targets[0].id in {"payload", "payload_sha256", "manifest"}:
                    constants[node.targets[0].id] = ast.literal_eval(node.value)
        cls.constants = constants
        cls.raw = base64.b64decode(constants["payload"], validate=True)

    def test_payload_hashes_dev_only_and_notebook_syntax(self):
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(), self.constants["payload_sha256"])
        manifest = self.constants["manifest"]
        with zipfile.ZipFile(io.BytesIO(self.raw)) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(set(archive.namelist()), set(manifest))
            self.assertFalse(any("test_candidate" in n or "verifier" in n or "checkpoints" in n for n in manifest))
            for name, item in manifest.items():
                raw = archive.read(name)
                self.assertEqual(raw, (ROOT / name).read_bytes())
                self.assertEqual(len(raw), item["size"])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), item["sha256"])
            prefix = "kb_indexing/data/qasper_eval_20260926/"
            self.assertEqual(len(archive.read(prefix + "qrels_dev.jsonl").splitlines()), 393)
            self.assertEqual(len(archive.read(prefix + "corpus.jsonl").splitlines()), 18587)
        self.assertEqual(len(self.code), 4)
        for index, code in enumerate(self.code):
            compile(code, f"cell-{index}", "exec")
        self.assertIn("--dense", self.code[2])
        self.assertIn("--device", self.code[2])
        self.assertIn("'paired'", self.code[3])
        release = json.loads((ROOT / "docs/qasper-benchmark-colab-release.json").read_text())
        self.assertEqual(hashlib.sha256(self.notebook_path.read_bytes()).hexdigest(), release["notebook_sha256"])
        self.assertFalse(release["gpu_executed"])

    def test_exact_payload_regression_works_without_repository(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with zipfile.ZipFile(io.BytesIO(self.raw)) as archive:
                archive.extractall(root)  # exact trusted package paths checked above
            env = {**os.environ, "PYTHONPATH": str(root), "PYTHONDONTWRITEBYTECODE": "1"}
            result = subprocess.run([sys.executable, "-B", "-m", "unittest",
                                     "research_rag.tests.test_qasper_benchmark", "-v"],
                                    cwd=root, env=env, capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
