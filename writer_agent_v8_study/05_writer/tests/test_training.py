"""CPU-only tests for completion masking and native split boundaries."""
from __future__ import annotations

import importlib
import json
from pathlib import Path
import tempfile
import unittest

U = importlib.import_module("05_writer.training_utils")
T = importlib.import_module("05_writer.train_writer_qlora")


class FakeTokenizer:
    """Small deterministic template whose assistant header is a prompt prefix."""

    def apply_chat_template(self, messages, *, tokenize, add_generation_prompt, return_dict):
        assert tokenize is True
        assert return_dict is False
        values = [1]
        for message in messages:
            values.extend([10 if message["role"] == "system" else 20 if message["role"] == "user" else 30])
            values.extend(ord(char) for char in message["content"])
            values.append(2)
        if add_generation_prompt:
            values.append(30)
        return values


class BadPrefixTokenizer(FakeTokenizer):
    def apply_chat_template(self, messages, *, tokenize, add_generation_prompt, return_dict):
        values = super().apply_chat_template(
            messages, tokenize=tokenize, add_generation_prompt=add_generation_prompt,
            return_dict=return_dict,
        )
        if not add_generation_prompt:
            values[0] = 99
        return values


class TrainingTests(unittest.TestCase):
    def setUp(self):
        self.messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "input"},
            {"role": "assistant", "content": '{"ok":true}'},
        ]

    def test_completion_only_mask_uses_exact_template_prefix(self):
        encoded = U.encode_completion(self.messages, FakeTokenizer(), 256)
        first_target = encoded["labels"].index(next(x for x in encoded["labels"] if x != -100))
        self.assertTrue(all(value == -100 for value in encoded["labels"][:first_target]))
        self.assertEqual(encoded["labels"][first_target:], encoded["input_ids"][first_target:])
        self.assertGreater(first_target, 0)

    def test_overlong_example_is_dropped_whole(self):
        self.assertIsNone(U.encode_completion(self.messages, FakeTokenizer(), 4))

    def test_template_prefix_mismatch_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "prefix does not match"):
            U.encode_completion(self.messages, BadPrefixTokenizer(), 256)

    def test_final_assistant_json_is_required(self):
        with self.assertRaises(ValueError):
            U.encode_completion(self.messages[:-1], FakeTokenizer(), 256)
        bad = self.messages[:-1] + [{"role": "assistant", "content": "not JSON"}]
        with self.assertRaises(json.JSONDecodeError):
            U.encode_completion(bad, FakeTokenizer(), 256)

    def test_training_split_loader_rejects_manual_file_by_name(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "writer_eval_manual.jsonl"
            path.write_text("", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Manual evaluation"):
                U.load_training_splits(path)

    def test_speed_arguments_are_explicit_and_overridable(self):
        defaults = T.build_parser().parse_args([])
        self.assertEqual(defaults.max_seq_length, 1536)
        self.assertEqual(defaults.eval_batch_size, 1)
        self.assertEqual(defaults.eval_steps, 250)
        self.assertEqual(defaults.save_steps, 250)
        self.assertEqual(defaults.epochs, 1.0)
        self.assertEqual(defaults.eval_strategy, "no")
        self.assertEqual(defaults.save_strategy, "epoch")
        self.assertEqual(defaults.optimizer, "adamw_torch_fused")
        overridden = T.build_parser().parse_args([
            "--eval-batch-size", "2", "--eval-steps", "50", "--save-steps", "50",
            "--eval-strategy", "steps", "--save-strategy", "steps",
            "--optimizer", "paged_adamw_8bit",
        ])
        self.assertEqual(overridden.eval_batch_size, 2)
        self.assertEqual(overridden.eval_steps, 50)
        self.assertEqual(overridden.save_steps, 50)
        self.assertEqual(overridden.eval_strategy, "steps")
        self.assertEqual(overridden.save_strategy, "steps")
        self.assertEqual(overridden.optimizer, "paged_adamw_8bit")


if __name__ == "__main__":
    unittest.main()
