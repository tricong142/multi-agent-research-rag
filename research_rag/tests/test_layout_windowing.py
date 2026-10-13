"""A page's final lines must survive the transformer's context-window limit."""
import contextlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


class Tensor(list):
    def __getitem__(self, index):
        value = super().__getitem__(index)
        return Tensor(value) if isinstance(value, list) else value

    def to(self, device):
        return self

    def unsqueeze(self, dim):
        return Tensor([self])

    def tolist(self):
        return list(self)


class Encoding(dict):
    def word_ids(self, batch_index=0):
        return [None, 0, 1, None] if batch_index == 0 else [None, 1, 2, None]


class LayoutWindowingTests(unittest.TestCase):
    def test_overflow_keeps_last_line_and_deduplicates_overlap_per_page(self):
        probabilities = SimpleNamespace(argmax=lambda **_: Tensor([0] * 4),
                                         max=lambda **_: SimpleNamespace(values=Tensor([0.9] * 4)))
        torch = SimpleNamespace(no_grad=contextlib.nullcontext, softmax=lambda *a, **k: probabilities)
        transformers = SimpleNamespace(LayoutLMv3ForTokenClassification=object, LayoutLMv3Processor=object)
        path = Path(__file__).resolve().parents[2] / "train_agent2_reader/tools/tool_layoutlmv3.py"
        spec = importlib.util.spec_from_file_location("train_agent2_reader.tools._windowing_test", path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict("sys.modules", {"torch": torch, "transformers": transformers}):
            spec.loader.exec_module(module)
        tool = module.LayoutLMv3Tool.__new__(module.LayoutLMv3Tool)
        tool.device, tool.id2label = "cpu", {0: "Text"}
        tool._extract_lines = lambda page: (["First line", "Shared line", "Final evidence"],
                                           [[0, 0, 10, 10], [0, 10, 10, 20], [0, 20, 10, 30]])
        tool._render_page_image = lambda page: object()

        def processor(*args, **kwargs):
            count = 2 if kwargs.get("return_overflowing_tokens") else 1
            return Encoding(input_ids=Tensor([[1] * 4] * count), attention_mask=Tensor([[1] * 4] * count),
                            bbox=Tensor([[[0, 0, 10, 10]] * 4] * count),
                            pixel_values=Tensor([[1]] * count), overflow_to_sample_mapping=Tensor([0] * count))

        tool.processor = processor
        tool.model = Mock(return_value=SimpleNamespace(logits=[None]))
        page = SimpleNamespace(rect=SimpleNamespace(width=100, height=100))

        class Document(dict):
            def close(self):
                pass

        with patch.object(module.fitz, "open", return_value=Document({0: page, 1: page})):
            blocks = tool.extract("fixture.pdf", page_numbers=[0, 1])
        self.assertEqual([(b.page_no, b.text) for b in blocks],
                         [(p, t) for p in [0, 1] for t in ["First line", "Shared line", "Final evidence"]])
        self.assertEqual(tool.model.call_count, 4)
        self.assertEqual(blocks[-1].bbox, [0, 20, 10, 30])
        self.assertTrue(all("overflow_to_sample_mapping" not in c.kwargs for c in tool.model.call_args_list))


if __name__ == "__main__":
    unittest.main()
