"""Read audited table coordinates from the exact PDF used to register them."""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal

from .state import SourceChunk


def coordinate_chunks(page, document_hash: str, tables: list[dict]) -> list[SourceChunk]:
    if not tables:
        return []
    page_words = page.get_text("words")

    def read(box):
        left, top, right, bottom = box
        words = " ".join(word[4] for word in page_words
                         if left <= (word[0] + word[2]) / 2 < right
                         and top <= (word[1] + word[3]) / 2 < bottom)
        return unicodedata.normalize("NFKC", words)

    def label_text(box):
        return re.sub(r"([+−])\s+(?=\w)", r"\1", read(box))

    chunks = []
    for table in tables:
        caption = read(table["caption"])
        number = table["number"]
        if not re.match(rf"^Table {re.escape(number)}\b", caption):
            raise ValueError("Table caption does not match the audited coordinates")
        for panel_index, panel in enumerate(table["panels"]):
            group = read(panel["group"]) if "group" in panel else ""
            headers = [read(box) for box in panel["headers"]]
            if not all(headers) or len(set(headers)) != len(headers):
                raise ValueError("Table column coordinates did not resolve unique headers")
            for row_index, row in enumerate(panel["rows"]):
                labels = [label_text(box) for box in row["labels"]]
                label = " / ".join(labels)
                if not labels or not all(labels) or len(row["values"]) != len(headers):
                    raise ValueError("Table row coordinates did not match the header")
                for column_index, (column, box) in enumerate(zip(headers, row["values"])):
                    raw = read(box)
                    if not re.fullmatch(r"[+−-]?\d+(?:\.\d+)?", raw):
                        continue
                    source_id = (f"pdf:{document_hash}:p{page.number}:table{number}:"
                                 f"r{panel_index}-{row_index}:c{column_index}")
                    scope = " | ".join(filter(None, (group, label, column)))
                    value = raw + "%" if table["unit"] == "%" else raw
                    chunks.append({
                        "doc_id": source_id, "source_id": source_id,
                        "text": f"{caption}\n{scope} | {value}",
                        "metadata": {"page_no": page.number, "bbox": box, "label": "table_cell",
                                     "source_tool": "pdf_coordinates", "table_number": number,
                                     "row_group": group, "row_label": label, "column": column,
                                     "raw_value": raw, "unit": table["unit"]},
                        "score": 0.0, "method": "reader",
                    })
    return chunks


def relevant_coordinate_cells(question: str, chunks: list[SourceChunk]) -> list[SourceChunk]:
    names = set(re.findall(r"\btable\s+(\d+[a-z]?)\b", question.casefold()))
    if len(names) != 1:
        return []

    def terms(text):
        return set(re.findall(r"[+−-]?\w+", text.casefold()))

    query = terms(question)
    query_unsigned = {token.lstrip("+−-") for token in query}
    matches = []
    for chunk in chunks:
        meta = chunk["metadata"]
        if meta.get("source_tool") != "pdf_coordinates" or meta["table_number"] not in names:
            continue
        column = terms(meta["column"])
        row = terms(meta["row_label"])
        group = terms(meta["row_group"])
        if column and column <= query and row & query:
            # Keep opposite-sign rows visible as alternatives, but prefer an exact signed match.
            near = {token.lstrip("+−-") for token in row} & query_unsigned
            matches.append(((len(near) + len(group & query), len(row & query)), chunk))
    return [chunk for _, chunk in sorted(matches, key=lambda match: match[0], reverse=True)[:8]]


_METRIC = r"(?:exact[- ]match )?accuracy"
_VALUE = r"(?P<value>\d+(?:\.\d+)?)\s*%"
_CELL_CLAIMS = (
    re.compile(
        rf"(?P<condition>(?:with|without) [^,]+), (?P<model>.+?) (?:achieved|recorded|had) "
        rf"{_VALUE} (?P<metric>{_METRIC}) on (?:the )?(?P<column>.+?)"
        r"(?: (?:database|dataset|benchmark))?\.", re.I),
    re.compile(
        rf"(?:the )?(?:reported )?(?P<column>[\w.-]+) (?P<metric>{_METRIC}) for "
        rf"(?P<model>.+?) with (?P<condition>.+?) (?:is|was) {_VALUE}\.", re.I),
)


def check_coordinate_claim(claim: str, context: str, source_id: str, question: str,
                           chunks: list[SourceChunk]) -> tuple[str, str]:
    """Check a single scoped value against the Reader's audited PDF cells."""
    unknown = "not_enough_info"
    parsed = None
    named_tables = set(re.findall(r"\btable\s+(\d+[a-z]?)\b", question.casefold()))
    suffix = re.search(r" in Table (\d+[a-z]?)\.$", claim, re.I)
    if len(named_tables) != 1 or (suffix and suffix[1].casefold() not in named_tables):
        return unknown, "pdf_table_number_mismatch"
    claim_text = claim[:suffix.start()] + "." if suffix else claim
    for form in _CELL_CLAIMS:
        if parsed := form.fullmatch(claim_text):
            break
    if parsed is None:
        return unknown, "pdf_table_claim_not_single_scalar"

    def normalize(text):
        return " ".join(unicodedata.normalize("NFKC", text).casefold().replace("−", "-").split())

    def mentioned(phrase, text):
        return bool(phrase and re.search(rf"(?<![\w+\-]){re.escape(phrase)}(?![\w+\-])", text))

    def scope(chunk):
        meta = chunk["metadata"]
        row = re.sub(r"^\([a-z0-9]+\)\s+", "", meta["row_label"], flags=re.I)
        model, _, setting = row.partition(" / ")
        if meta["row_group"] and setting:
            return None
        caption = chunk["text"].partition("\n")[0]
        metric = re.search(rf"\b{_METRIC}\b", caption, re.I)
        return (normalize(model), normalize(meta["row_group"] or setting), normalize(meta["column"]),
                normalize(metric[0]).replace("-", " ") if metric else "")

    expected = (*[normalize(parsed[key]) for key in ("model", "condition", "column")],
                normalize(parsed["metric"]).replace("-", " "))
    query = normalize(question)
    if not all(mentioned(term, query) for term in expected[:3]):
        return unknown, "pdf_table_claim_outside_question"
    matches = [
        chunk for chunk in chunks
        if chunk["metadata"].get("source_tool") == "pdf_coordinates"
        and chunk["metadata"]["table_number"].casefold() in named_tables
        and (axes := scope(chunk)) and all(mentioned(term, query) for term in axes[:3])
    ]
    if len(matches) != 1:
        return unknown, "pdf_table_cell_missing_or_ambiguous"
    cell = matches[0]
    if scope(cell) != expected or cell["source_id"] != source_id or cell["text"] != context:
        return unknown, "pdf_table_source_mismatch"
    meta = cell["metadata"]
    raw = meta["raw_value"]
    if meta["unit"] != "%" or not re.fullmatch(r"\d+(?:\.\d+)?", raw):
        return unknown, "pdf_table_unit_mismatch"
    observed, claimed = Decimal(raw), Decimal(parsed["value"])
    if not all(0 <= value <= 100 for value in (observed, claimed)):
        return unknown, "pdf_table_percent_out_of_range"
    return ("support", "pdf_table_value_matches") if observed == claimed else (
        "contradict", "pdf_table_value_differs")
