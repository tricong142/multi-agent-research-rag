"""Synthetic fixtures test parsing/label integrity; none are real QASPER rows."""
from __future__ import annotations

from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
generation = importlib.import_module("05_writer.generate_training_data")
validation = importlib.import_module("05_writer.validate_labels")


def fixture_paper(paper_id: str = "fixture-only") -> dict:
    first = "The synthetic test dataset contains ten documents."
    second = "The synthetic test experiment uses one held-out partition."
    answer = {
        "unanswerable": False, "yes_no": False,
        "extractive_spans": [], "free_form_answer": "",
        "evidence": [first, second], "highlighted_evidence": [first, second],
    }
    return {
        "id": paper_id, "title": "Synthetic unit test fixture",
        "full_text": [{"section_name": "Tests", "paragraphs": [first, second]}],
        "qas": [{
            "question": "Does the synthetic experiment use two partitions?",
            "question_id": "fixture-question",
            "answers": [{"answer": answer, "annotation_id": "fixture-annotation"}],
        }],
    }


class DataPipelineTests(unittest.TestCase):
    def examples(self, paper: dict | None = None, split: str = "train") -> list:
        return list(generation.examples_for_paper(paper or fixture_paper(), split))

    def test_native_and_arrow_normalization_preserve_no_answer(self) -> None:
        paper = fixture_paper()
        native = self.examples(paper)
        question = paper["qas"][0]
        answer = question["answers"][0]["answer"]
        paper["qas"] = {
            "question": [question["question"]], "question_id": [question["question_id"]],
            "answers": [{"answer": [answer], "annotation_id": ["fixture-annotation"]}],
        }
        paper["full_text"] = {"section_name": ["Tests"], "paragraphs": [paper["full_text"][0]["paragraphs"]]}
        arrow = self.examples(paper)
        self.assertEqual([row.model_dump() for row in native], [row.model_dump() for row in arrow])
        self.assertIs(arrow[0].provenance["answer_annotations"][0]["yes_no"], False)
        self.assertEqual(len(arrow[0].verified_claims), 2)

    def test_only_verbatim_textual_evidence_becomes_claim(self) -> None:
        paper = fixture_paper()
        answer = paper["qas"][0]["answers"][0]["answer"]
        answer["evidence"] += ["FLOAT SELECTED: Figure 1", "This paragraph is not in the paper."]
        answer["highlighted_evidence"] += ["This highlight is fabricated."]
        claims, metadata = generation.extract_claims(paper, paper["qas"][0])
        self.assertEqual(len(claims), 2)
        self.assertEqual(metadata["dropped_visual_evidence"], 1)
        self.assertEqual(metadata["dropped_unmatched_evidence"], 1)
        self.assertTrue(all(claim.text in claim.evidence for claim in claims))

    def test_contradictory_polarity_produces_explicit_empty_pool(self) -> None:
        paper = fixture_paper()
        opposite = deepcopy(paper["qas"][0]["answers"][0])
        opposite["answer"]["yes_no"] = True
        paper["qas"][0]["answers"].append(opposite)
        rows = self.examples(paper)
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[0].provenance["contradictory_annotations"])
        self.assertEqual(rows[0].verified_claims, [])
        self.assertTrue(rows[0].critique.needs_more_evidence)
        for row in rows:
            validation.validate_example(row)

    def test_unanswerable_is_not_converted_into_a_fact(self) -> None:
        paper = fixture_paper()
        paper["qas"][0]["answers"][0]["answer"]["unanswerable"] = True
        rows = self.examples(paper)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].report.sentences, [])
        self.assertEqual(rows[0].verified_claims, [])
        self.assertTrue(rows[0].critique.needs_more_evidence)

    def test_long_evidence_is_omitted_without_fragment_truncation(self) -> None:
        paper = fixture_paper()
        claims, metadata = generation.extract_claims(paper, paper["qas"][0], max_claim_chars=8)
        self.assertEqual(claims, [])
        self.assertEqual(metadata["dropped_long_snippets"], 2)

    def test_action_is_only_reselection_within_existing_pool(self) -> None:
        rows = self.examples()
        for row in rows:
            validation.validate_example(row)
        actions = [row for row in rows if row.task == "action"]
        self.assertEqual(len(actions), 1)
        row = actions[0]
        self.assertEqual(row.action.action, "reselect_claims")
        self.assertTrue(set(row.action.claim_ids).isdisjoint(row.report.sentences[0].claim_ids))
        pool = {claim.claim_id: claim for claim in row.verified_claims}
        self.assertEqual(row.action.replacement_text, pool[row.action.claim_ids[0]].text)
        self.assertFalse(row.human_reviewed)

    def test_hallucinated_report_label_is_rejected(self) -> None:
        row = self.examples()[0].model_dump()
        row["report"]["sentences"][0]["text"] = "An unsupported test result."
        with self.assertRaisesRegex(ValueError, "Cannot certify sentence"):
            validation.validate_example(row)

    def test_incorrect_synthetic_critic_label_is_rejected(self) -> None:
        row = next(row for row in self.examples() if row.label_origin == "synthetic_unsupported").model_dump()
        row["critique"]["sentence_reviews"][0]["verdict"] = "supported"
        with self.assertRaisesRegex(ValueError, "Incorrect verdict"):
            validation.validate_example(row)

    def test_external_action_claim_is_rejected(self) -> None:
        row = next(row for row in self.examples() if row.task == "action").model_dump()
        row["action"]["claim_ids"] = ["external_new_claim"]
        with self.assertRaisesRegex(ValueError, "cannot introduce new claims"):
            validation.validate_example(row)

    def test_paper_leakage_rejected_before_generation_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "generated"
            with self.assertRaisesRegex(ValueError, "Duplicate/leaked paper"):
                generation.generate_dataset({"train": [fixture_paper()], "validation": [fixture_paper()]}, output)
            self.assertFalse(output.exists())

    def test_validator_rejects_all_rows_for_leaked_paper(self) -> None:
        train = self.examples(split="train")[0].model_dump()
        dev = self.examples(split="validation")[0].model_dump()
        dev["example_id"] += ":distinct"
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            source = folder / "raw.jsonl"
            source.write_text("\n".join(json.dumps(row) for row in (train, dev)), encoding="utf-8")
            result = validation.validate_file(source, folder / "valid.jsonl", folder / "rejected.jsonl")
            self.assertEqual(result["accepted"], 0)
            self.assertEqual(result["rejected"], 2)

    def test_eval_candidates_are_not_pretended_human_labels(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            manual = folder / "writer_eval_manual.jsonl"
            manual.write_text("preserve existing annotations\n", encoding="utf-8")
            result = generation.generate_dataset({"train": [fixture_paper("train-fixture")], "test": [fixture_paper("test-fixture")]}, folder)
            self.assertEqual(result["human_reviewed_examples_generated"], 0)
            self.assertEqual(manual.read_text(encoding="utf-8"), "preserve existing annotations\n")
            candidates = [json.loads(line) for line in (folder / "writer_eval_candidates.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0]["split"], "test")
            self.assertIs(candidates[0]["human_reviewed"], False)

    def test_unequal_arrow_columns_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "inconsistent length"):
            generation.columnar_records({"question": ["a", "b"], "answers": [[]]}, "question")

    def test_yes_no_string_is_not_silently_coerced(self) -> None:
        with self.assertRaisesRegex(ValueError, "true, false, or null"):
            generation.answer_metadata({"yes_no": "False"})


if __name__ == "__main__":
    unittest.main()
