"""Exact proofs for explicit counts in a cited PDF sentence."""

from __future__ import annotations

from decimal import Decimal
import re


_NUMBER = r"(?:\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?|[A-Za-z]+)"
_TEXT = r"[A-Za-z][\w-]*(?: [A-Za-z][\w-]*)*"
_SCALE = {"thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000}
_COMPARISON = {"over": "gt", "more than": "gt", "under": "lt", "less than": "lt",
               "approximately": "approx", "about": "approx", "around": "approx"}
_COMPARATOR = "|".join(_COMPARISON)
_MASS = rf"(?:(?P<op>{_COMPARATOR}) )?(?P<number>{_NUMBER})(?: (?P<scale>{'|'.join(_SCALE)}))?"
_ACTIVITY_CLAIM = re.compile(rf"The paper reports (?P<number>{_NUMBER}) (?P<unit>rounds|cycles|passes) of (?P<activity>{_TEXT})\.", re.I)
_ACTIVITY_SOURCE = re.compile(
    rf"We (?:conducted|performed|carried out) (?P<activity>{_TEXT}?) (?:over|in|across) (?P<number>{_NUMBER}) "
    r"(?P<unit>rounds|cycles|passes)(?:, with inter-annotator agreement tracked for consistency"
    r"(?: \(Figure\s*\d+\))?)?\.", re.I)
_DATASET_CLAIM = re.compile(rf"(?:The )?(?P<entity>[\w.-]+) dataset contains {_MASS} (?P<unit>{_TEXT})\.", re.I)
_DATASET_SOURCE = re.compile(
    rf"(?:(?P<entity>[\w.-]+) is a dataset containing|We (?:developed|created|built) a dataset containing)"
    rf" {_MASS} (?P<unit>{_TEXT}?)(?: across diverse topics)?\.", re.I)
_BENCHMARK_CLAIM = re.compile(
    rf"(?P<number>{_NUMBER}) (?P<unit>LLMs|models|systems) were benchmarked on "
    rf"(?:the|a|an) (?P<target>{_TEXT})\.", re.I)
_BENCHMARK_SOURCE = re.compile(
    rf"(?:To (?:address|close) (?:these|such) gaps, )?we benchmark(?:ed)? (?P<number>{_NUMBER}) "
    rf"(?P<unit>LLMs|models|systems)(?:, an? [\w-]+ system and [\w-]+ texts)? on (?:a|an|the) "
    rf"(?P<target>{_TEXT}?)(?: in [A-Z][\w-]+ and [A-Z][\w-]+ via [\w-]+ evaluation)?\.", re.I)


def _canonical(text: str) -> str:
    return " ".join(re.sub(r"(?<=\w)-[ \t]*\r?\n[ \t]*(?=[a-z])", "", text).split())


def _number(match, numeric_requirements):
    number = match["number"]
    if re.fullmatch(r"[\d,.]+", number):
        value = Decimal(number.replace(",", ""))
    else:
        found = numeric_requirements(number)
        if len(found) != 1:
            return None
        value = Decimal(found[0]["value"])
    return value * _SCALE.get((match.groupdict().get("scale") or "").lower(), 1)


def _dataset_owner(entity: str, evidence: str, paragraph: str) -> bool:
    # Link only an adjacent, uniquely chosen sentence in the same original PDF block.
    if paragraph.count(evidence) != 1:
        return False
    preceding = _canonical(paragraph[:paragraph.index(evidence)])
    match = re.search(
        rf"(?:^|[.!?]\s+)(?:\d+\.\s+)?The (?:creation|introduction|development) of "
        rf"{re.escape(entity)}, (?:a|the) (?:[\w-]+ )*dataset for {_TEXT}\.$", preceding, re.I)
    return match is not None


def check_pdf_count_claim(claim: str, evidence: str, paragraph: str, numeric_requirements):
    """Return a proof only when the relation, unit, scope and value all bind."""
    if not paragraph or evidence not in paragraph:
        return None
    statement, sentence = _canonical(claim), _canonical(evidence)
    for claim_form, source_form, fields, reason in (
        (_ACTIVITY_CLAIM, _ACTIVITY_SOURCE, ("activity", "unit"), "pdf_activity_count_matches"),
        (_DATASET_CLAIM, _DATASET_SOURCE, ("unit",), "pdf_dataset_count_matches"),
        (_BENCHMARK_CLAIM, _BENCHMARK_SOURCE, ("unit", "target"), "pdf_benchmark_count_matches"),
    ):
        proposed, source = claim_form.fullmatch(statement), source_form.fullmatch(sentence)
        if proposed is None or source is None:
            continue
        if any(proposed[key].casefold() != source[key].casefold() for key in fields):
            return None
        if claim_form is _DATASET_CLAIM:
            explicit = source["entity"]
            if explicit and explicit.casefold() != proposed["entity"].casefold():
                return None
            if not explicit and not _dataset_owner(proposed["entity"], evidence, paragraph):
                return None
            if _COMPARISON.get((proposed["op"] or "").lower()) != _COMPARISON.get((source["op"] or "").lower()):
                return None
        expected, observed = (_number(match, numeric_requirements) for match in (proposed, source))
        return reason if expected is not None and expected == observed else None
    return None
