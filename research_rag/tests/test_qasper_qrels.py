from copy import deepcopy
import unittest

from research_rag.evaluation.prepare_qasper import paper_records


class QasperQrelTests(unittest.TestCase):
    def setUp(self):
        self.paper = {"id": "fixture", "title": "A study",
                      "full_text": [{"section_name": "Results", "paragraphs": ["First result.", "Second\nresult."]}],
                      "qas": [{"question_id": "q1", "question": "What were the results?", "answers": [
                          {"answer": {"unanswerable": False, "yes_no": None, "evidence": ["First result."]}},
                          {"answer": {"unanswerable": False, "yes_no": None, "evidence": ["Second result."]}},
                      ]}]}

    def test_union_human_annotations_maps_to_original_paragraph_ids(self):
        corpus, qrels, rejected = paper_records(self.paper)
        self.assertEqual(corpus[1]["text"], "Second\nresult.")
        self.assertEqual(qrels[0]["relevant_doc_ids"], ["qasper:fixture:paragraph:0", "qasper:fixture:paragraph:1"])
        self.assertEqual(rejected, {})

    def test_partial_mapping_never_silently_drops_a_positive(self):
        self.paper["qas"][0]["answers"][1]["answer"]["evidence"] = ["Unmatched evidence"]
        _, qrels, rejected = paper_records(self.paper)
        self.assertEqual(qrels, [])
        self.assertEqual(rejected["missing_visual_or_unmatched_evidence"], 1)

    def test_disagreement_and_unanswerability_are_not_negative_qrels(self):
        for field, values in [("unanswerable", [False, True]), ("yes_no", [False, True])]:
            with self.subTest(field=field):
                paper = deepcopy(self.paper)
                for answer, value in zip(paper["qas"][0]["answers"], values):
                    answer["answer"][field] = value
                _, qrels, rejected = paper_records(paper)
                self.assertEqual(qrels, [])
                self.assertEqual(sum(rejected.values()), 1)


if __name__ == "__main__":
    unittest.main()
