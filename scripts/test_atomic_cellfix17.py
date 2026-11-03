"""Regression for actual invalid coverage and source-punctuation controls."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import unittest

from .test_atomic_cellfix16 import accepts

a = importlib.import_module("04_factchecker.inference.atomic_verifier")
d = importlib.import_module("04_factchecker.inference.atomic_decoding")
coverage = importlib.import_module("04_factchecker.inference.cellfix17_coverage")
runtime = importlib.import_module("04_factchecker.inference.cellfix14_runtime")


def fixture17():
    return json.loads((Path(__file__).parent / "fixtures/cellfix16_full39_failure.json").read_bytes())


def token_paths17():
    sample = fixture17();case, part = sample["case"], sample["part"]
    paths = [("cf17_received_coverage_" + str(i), case["claim"], part, case["context"], deepcopy(raw), False)
             for i, raw in enumerate(sample["raw_outputs"], 1)]
    fixed = deepcopy(sample["raw_outputs"][0])
    fixed["coverage"]["members"] = [fixed["observations"][0]["member"]]
    return paths + [("cf17_source_collective_coverage", case["claim"], part, case["context"], fixed, True)]


class Cellfix17Tests(unittest.TestCase):
    def test_received_schema_bug_reproduced_in_parent_and_blocked_now(self):
        sample = fixture17();case, part = sample["case"], sample["part"]
        with runtime.decode_request(None):
            old = d._cf16_final_assessment_schema(case["claim"], part, case["context"])
            self.assertEqual(old["properties"]["coverage"]["properties"]["members"]["items"]["enum"], [])
            new = d.assessment_schema(case["claim"], part, case["context"])
            self.assertEqual(new["properties"]["coverage"]["properties"]["members"]["items"]["enum"], ["Birch, Elm and Fir"])
            for raw in sample["raw_outputs"]:
                self.assertTrue(accepts(old, json.dumps(raw)))
                self.assertFalse(accepts(new, json.dumps(raw)))
                with self.assertRaisesRegex(ValueError, "quote_membership"):
                    a.assess_part(raw, part, case["context"])

    def test_corrected_source_member_reachable_without_changing_validator(self):
        name, claim, part, context, raw, expected = token_paths17()[-1]
        with runtime.decode_request(None):
            self.assertTrue(accepts(d.assessment_schema(claim, part, context), json.dumps(raw)))
            self.assertEqual(a.assess_part(raw, part, context)["assessed_label"], "contradict")
            bad = deepcopy(raw);bad["coverage"]["members"] = ["birch, elm and fir"]
            self.assertFalse(accepts(d.assessment_schema(claim, part, context), json.dumps(bad)))

    def schema(self, members, *, complete=True):
        return {"properties": {"observations": {"items": {"properties": {"member": {"type": "string", "enum": members}}}},
            "coverage": {"type": "object", "properties": {"complete": {"const": complete},
                "members": {"type": "array", "items": {"type": "string", "enum": members}, "minItems": int(complete), "maxItems": 1},
                "quotes": {"type": "array", "items": {"type": "string"}}}}}}

    def test_punctuation_and_unicode_source_spans_are_not_discarded(self):
        for member in ("Juniper, Cedar and Larch", "O'Neil and Node-B", "A; B; C", "Érable, Chêne et Pin"):
            with self.subTest(member=member):
                schema = coverage.bind_coverage(self.schema([member]), "The complete set was " + member + ".")
                self.assertEqual(schema["properties"]["coverage"]["properties"]["members"]["items"]["enum"], [member])

    def test_impossible_required_coverage_fails_before_decoding(self):
        for names in ([], ["invented member"]):
            with self.subTest(names=names), self.assertRaisesRegex(ValueError, "unrepresentable_coverage_members"):
                coverage.bind_coverage(self.schema(names), "No such source reference.")

    def test_empty_optional_coverage_has_only_empty_array_path(self):
        schema = coverage.bind_coverage(self.schema([], complete=False), "No entity measured.")
        names = schema["properties"]["coverage"]["properties"]["members"]
        self.assertEqual(names["maxItems"], 0)
        self.assertNotIn("enum", names["items"])
        self.assertEqual(schema["properties"]["coverage"]["properties"]["complete"], {"const": False})

    def test_impossible_complete_branch_removed_without_losing_unknown_path(self):
        schema = self.schema([])
        impossible = schema["properties"]["coverage"]
        optional = self.schema([], complete=False)["properties"]["coverage"]
        schema["properties"]["coverage"] = {"anyOf": [impossible, optional]}
        fixed = coverage.bind_coverage(schema, "No entity measured.")
        self.assertEqual(fixed["properties"]["coverage"]["properties"]["complete"], {"const": False})


if __name__ == "__main__":
    unittest.main()
