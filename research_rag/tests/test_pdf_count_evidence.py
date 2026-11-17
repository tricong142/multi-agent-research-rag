import unittest
from unittest.mock import Mock

from research_rag.atomic_adapter import AtomicFactCheckerNode, cellfix29_runtime
from research_rag.pdf_count_evidence import check_pdf_count_claim


class PdfCountEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = cellfix29_runtime()

    def check(self, claim, evidence, paragraph=None):
        return check_pdf_count_claim(claim, evidence, paragraph or evidence,
                                     self.runtime.atomic.numeric_requirements)

    def test_workflow_count_uses_annotation_relation(self):
        claim = "The paper reports 12 rounds of annotation."
        quote = "We conducted annotation over 12 rounds."
        self.assertEqual(self.check(claim, quote), "pdf_activity_count_matches")
        for different in ("We conducted zero-shot inference over 12 rounds.",
                          "We conducted annotation over 12 rounds on the test subset.",
                          "We did not conduct annotation over 12 rounds.",
                          "We conducted annotation over 11 rounds."):
            with self.subTest(different=different):
                self.assertIsNone(self.check(claim, different))

    def test_scaled_dataset_count_retains_bound_unit_and_comparator(self):
        claim = "The Atlas dataset contains more than 1.4 million sentence pairs."
        quote = "We developed a dataset containing over 1.4 million sentence pairs."
        owner = "The creation of Atlas, the first synthetic dataset for translation. "
        self.assertEqual(self.check(claim, quote, owner + quote), "pdf_dataset_count_matches")
        self.assertEqual(self.check(claim.replace("1.4 million", "1,400,000"), quote, owner + quote),
                         "pdf_dataset_count_matches")
        self.assertIsNone(self.check(claim, quote, owner.replace("Atlas", "Echo") + quote))
        self.assertIsNone(self.check(claim, quote, owner + "Another dataset is also described. " + quote))
        self.assertIsNone(self.check(claim, quote))
        for wrong in (claim.replace("more than", "under"), claim.replace("more than", "approximately"),
                      claim.replace("sentence pairs", "documents"), claim.replace("1.4", "1.5")):
            self.assertIsNone(self.check(wrong, quote, owner + quote))
        approximate = quote.replace("over", "about")
        self.assertEqual(self.check(claim.replace("more than", "approximately"), approximate, owner + approximate),
                         "pdf_dataset_count_matches")

    def test_benchmark_counts_only_the_explicit_class(self):
        claim = "Five LLMs were benchmarked on the new dialogue dataset."
        quote = ("To address these gaps, we benchmark five LLMs, a rule-based system and human-written texts "
                 "on a new dialogue dataset in English and Irish via LLM-based evaluation.")
        self.assertEqual(self.check(claim, quote), "pdf_benchmark_count_matches")
        for wrong in (claim.replace("Five", "Seven"), claim.replace("LLMs", "systems"),
                      claim.replace("dialogue", "translation")):
            self.assertIsNone(self.check(wrong, quote))
        self.assertIsNone(self.check(claim, quote.replace("five LLMs", "five rule-based systems")))

    def test_adapter_records_proof_and_keeps_verbatim_evidence(self):
        backend = Mock()
        events = []
        check = AtomicFactCheckerNode(backend, self.runtime, on_trace=events.append)
        context = "We performed validation over 12 cycles."
        result = check({"claim": "The paper reports 12 cycles of validation.", "context": context,
                        "pdf_source_context": context, "source_id": "pdf:fixture:p0:b0:c0"})
        self.assertEqual(result["fact_check_label"], "support")
        self.assertEqual(events[0]["evidence"], context)
        backend.generate_json.assert_not_called()
