from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from research_rag import atomic_adapter
from scripts.build_cellfix29_e2e_quantity_candidate import QUANTITIES, candidate_bytes


class QuantityCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = TemporaryDirectory()
        cls.addClassCleanup(folder.cleanup)
        root = Path(folder.name)
        payload = candidate_bytes()
        path = root / "candidate.zip"
        path.write_bytes(payload)
        with ZipFile(BytesIO(payload)) as candidate, ZipFile(atomic_adapter.PAYLOAD) as baseline:
            assert set(candidate.namelist()) == set(baseline.namelist())
            assert {name for name in baseline.namelist() if baseline.read(name) != candidate.read(name)} == {QUANTITIES}
            for name in candidate.namelist():
                if name.startswith("04_factchecker/") or name == atomic_adapter.CRITERIA_FILE:
                    candidate.extract(name, root)
        with patch.multiple(atomic_adapter, PAYLOAD=path, PAYLOAD_SHA256=sha256(payload).hexdigest()):
            cls.runtime = atomic_adapter.cellfix29_runtime(root)

    def quantities(self, text):
        return [(item["value"], item["unit"], item["quote"])
                for item in self.runtime.atomic.numeric_requirements(text)]

    def test_count_unit_ends_before_a_coverage_phrase(self):
        self.assertEqual(self.quantities("There were 140 responses over 9 sites."),
                         [("140", "responses", "140 responses"), ("9", "sites", "9 sites")])
        self.assertEqual(self.quantities("There were 140 respondents from 9 sites.")[0],
                         ("140", "respondents", "140 respondents"))

    def test_figure_reference_keeps_percentages_in_row_labels(self):
        self.assertEqual(self.quantities("Table 2\nImage/Figure 14.2%\n"), [("14.2", "%", "14.2%")])
        self.assertEqual(self.quantities("See Section 3.2 and Figure 12."), [])
        self.assertEqual(self.quantities("Type\n%\nImage/Figure\nNot reported."), [])

    def test_preserving_the_value_does_not_make_a_wrong_row_or_unit_support(self):
        a = self.runtime.atomic
        claim = "Optical accounts for 14.2%."
        part = a.normalize_decomposition({
            "parts": [{"quote": claim, "quantifier": "atomic",
                       "scope": {"entity": "Optical", "metric": "accounts for 14.2%", "time": "", "condition": ""}}],
            "unresolved": [],
        }, claim)["parts"][0]
        keys = ("value", "unit", "quote")
        for text in ("Type\n%\nThermal\n14.2%", "Type\nDuration\nOptical\n14.2 seconds"):
            with self.subTest(text=text):
                left = {k: part["numeric_requirements"][0][k] for k in keys}
                right = {k: a.numeric_requirements(text)[0][k] for k in keys}
                record = {"kind": "value", "left": left, "right": right, "source_quote": text}
                self.assertNotEqual(a.check_numeric(record, claim, text, metric=part["scope"]["metric"])["truth"], "true")
