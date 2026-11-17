from copy import deepcopy
import unittest

from research_rag.pdf_table_cells import check_count_claim, count_cell_claim
from train_agent3_summarizer.node import SummarizerNode


class SourceClaimProjectionTests(unittest.TestCase):
    def test_count_ledger_checks_value_and_column_coordinates(self):
        row = "Items\n120\n80"
        cell = {"row_source_id": "pdf:example:p0:b1:c0", "table_id": "2",
                "row_label": "Items", "column_header": "Train", "cell_text": "120",
                "label_bbox": [10, 30, 30, 40], "column_bbox": [54, 10, 66, 20],
                "cell_bbox": [55, 30, 65, 40]}
        claim = count_cell_claim(cell)
        def check(answer, observed=cell):
            return check_count_claim(answer, row, cell["row_source_id"], observed)[0]
        self.assertEqual(check(claim), "support")
        self.assertEqual(check(claim.replace("120", "80")), "contradict")
        self.assertEqual(check(claim.replace("Train", "Test")), "not_enough_info")
        self.assertEqual(check(claim, {**cell, "cell_bbox": [80, 30, 90, 40]}), "not_enough_info")
        self.assertEqual(check(claim, {**cell, "cell_text": "121"}), "not_enough_info")

    def test_count_table_projection_keeps_split_and_row_roles(self):
        question = ("According to the Sentence Pair row of Table 4, how many total sentence pairs "
                    "are in the Train and Test sets of Atlas, respectively?")
        statement = "The Train set has 1,120 sentence pairs and the Test set has 340 sentence pairs."
        units = {"S1": "Sentence Pair†\n1,120\n410\n340"}
        raw = {"claims": [{"text": statement, "source_ids": ["S1"]}]}
        cells = {"S1": [{"table_id": "4", "row_label": "Sentence Pair†", "column_header": col, "cell_text": value}
                        for col, value in (("Train", "1,120"), ("Val", "410"), ("Test", "340"))]}
        def resolve(data=raw, metadata=cells, query=question):
            return SummarizerNode._resolve_source_ids(data, units, question=query, table_cells={},
                                                      table_scope={}, count_cells=metadata)

        result = resolve()
        self.assertEqual(list(result["claim_sources"]), [
            "In Table 4, the count for Sentence Pair† in the Train column is 1,120.",
            "In Table 4, the count for Sentence Pair† in the Test column is 340.",
        ])
        for wrong in (statement.replace("Train", "Val"),
                      statement.replace("1,120", "410"),
                      statement.replace("sentence pairs.", "sentence pairs after pruning.")):
            self.assertTrue(resolve({"claims": [{"text": wrong, "source_ids": ["S1"]}]})["missing_sources"])
        self.assertTrue(resolve(metadata={"S1": cells["S1"][:-1]})["missing_sources"])
        self.assertTrue(resolve(metadata={"S1": cells["S1"] + [cells["S1"][-1]]})["missing_sources"])
        self.assertTrue(resolve(query=question.replace("total sentence pairs", "total documents"))["missing_sources"])

    def test_count_uses_source_relation_and_keeps_other_forms_unchanged(self):
        question = "According to the abstract of the Atlas paper, how many questions does Atlas contain?"
        claim = "The Atlas dataset contains 1,240 questions over 350 Science papers."
        raw = {"claims": [{"text": claim, "source_ids": ["S1"]}]}
        text = "We present Atlas,\na dataset of 1,240 questions over 350 Science papers."
        result = SummarizerNode._resolve_source_ids(raw, {"S1": text}, question=question)
        self.assertEqual(result["claim_sources"], {"Atlas is a dataset of 1,240 questions.": ["S1"]})
        self.assertEqual(result["evidence_spans"], [text])
        for changed in (text.replace("Atlas", "Orion"), text.replace("questions", "articles"),
                        text.replace("Science papers", "previously filtered papers"),
                        text.replace("350 Science papers", "350 Science papers under review"),
                        text.replace("350 Science papers", "350 enrollment days")):
            with self.subTest(changed=changed):
                result = SummarizerNode._resolve_source_ids(raw, {"S1": changed}, question=question)
                self.assertNotEqual(result.get("answer"), "Atlas is a dataset of 1,240 questions.")
        conditioned = "The Atlas dataset contains 1,240 questions over 350 Science papers under review."
        raw["claims"][0]["text"] = conditioned
        result = SummarizerNode._resolve_source_ids(
            raw, {"S1": text.replace("Science papers.", "Science papers under review.")}, question=question)
        self.assertEqual(result["answer"], conditioned)
        raw["claims"][0]["text"] = claim.replace("Science papers", "selected papers")
        result = SummarizerNode._resolve_source_ids(
            raw, {"S1": text.replace("Science papers", "selected papers")}, question=question)
        self.assertEqual(result["answer"], raw["claims"][0]["text"])

    def test_table_projection_checks_each_binding_before_splitting(self):
        question = "In the evidence section of Table 4, what percentages are listed for optical and thermal evidence types, respectively?"
        claim = "The percentage for Optical evidence is 12.4% and for Thermal evidence is 19.1%."
        raw = {"claims": [{"text": claim, "source_ids": ["S2", "S1"]}]}
        units = {"S1": "Optical\n12.4%", "S2": "Thermal\n19.1%"}
        cells = {id_: {"row_label": row, "table_id": "4", "column_header": "%", "cell_text": value}
                 for id_, row, value in (("S1", "Optical", "12.4%"), ("S2", "Thermal", "19.1%"))}
        scope = {id_: ["Table 4: Groups.", "Evidence\nType\n%"] for id_ in cells}
        result = SummarizerNode._resolve_source_ids(raw, units, question=question, table_cells=cells, table_scope=scope)
        self.assertEqual(result["claim_sources"], {"In Table 4, the percentage for Optical is 12.4%.": ["S1"],
                                                   "In Table 4, the percentage for Thermal is 19.1%.": ["S2"]})
        for change in ({"table_id": "5"}, {"column_header": "ID"}, {"row_label": "Optical"},
                       {"cell_text": "12.4%"}):
            with self.subTest(change=change):
                wrong_cells = deepcopy(cells)
                wrong_cells["S2"].update(change)
                result = SummarizerNode._resolve_source_ids(
                    raw, units, question=question, table_cells=wrong_cells, table_scope=scope)
                self.assertTrue(result["missing_sources"])
        result = SummarizerNode._resolve_source_ids(
            raw, units, question=question, table_cells={"S1": cells["S1"]}, table_scope=scope)
        self.assertTrue(result["missing_sources"])
        wrong_scope = {**scope, "S2": ["Table 4: Groups.", "Answers\nType\n%"]}
        result = SummarizerNode._resolve_source_ids(raw, units, question=question, table_cells=cells, table_scope=wrong_scope)
        self.assertTrue(result["missing_sources"])
