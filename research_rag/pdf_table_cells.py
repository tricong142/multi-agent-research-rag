"""Extract verifiable percentage cells from a bounded PDF table region."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal
from pathlib import Path
import re

from .state import SourceChunk, TableCell


_PERCENT = re.compile(r"[+-]?\d+(?:\.\d+)?\s*%")
_LABEL_HEADERS = {"type", "category", "label"}
_CAPTION = re.compile(r"^\s*Table\s+(\d+[A-Za-z]?)\s*[:.]", re.I)
_PERCENT_CLAIM = re.compile(
    r"In Table (?P<table>\d+[A-Za-z]?), the percentage for (?P<label>[^,;\n]+?) is "
    r"(?P<value>[+-]?\d+(?:\.\d+)?\s*%)\.", re.I)
_INTEGER = re.compile(r"(?:\d{1,3}(?:,\d{3})+|\d+)")
_COUNT_CLAIM = re.compile(
    r"In Table (?P<table>\d+[A-Za-z]?), the count for (?P<label>[^,;\n]+?) "
    rf"in the (?P<column>[^,;\n]+?) column is (?P<value>{_INTEGER.pattern})\.", re.I)


def count_table_header(text: str) -> bool:
    lines = text.casefold().split()
    if not lines or lines[0] not in {"statistic", "statistics"}:
        return False
    columns = lines[1:]
    return columns == ["value"] or (
        len(columns) >= 2 and len(set(columns)) == len(columns)
        and set(columns) <= {"train", "training", "val", "validation", "dev", "development", "test", "testing"}
    )


def _inside(word, bounds) -> bool:
    return all((word[i] >= bounds[i] - 1 if i < 2 else word[i] <= bounds[i] + 1) for i in range(4))


def _same_line(first, second) -> bool:
    return abs(first[1] - second[1]) <= 2


def _center_x(bounds) -> float:
    return (bounds[0] + bounds[2]) / 2


def table_count_cells(pdf_path: str, table: list[SourceChunk]) -> dict[str, list[TableCell]]:
    """Recover integer cells from explicit statistic or dataset-split headers."""
    if not table or not Path(pdf_path).is_file():
        return {}
    caption, *blocks = table
    matched = _CAPTION.match(caption["text"])
    page = caption["metadata"]["page_no"]
    headers = [b for b in blocks if b["metadata"]["page_no"] == page and count_table_header(b["text"])]
    if matched is None or len(headers) != 1:
        return {}
    import fitz

    header = headers[0]
    header_box = header["metadata"]["bbox"]
    caption_box = caption["metadata"]["bbox"]
    with fitz.open(pdf_path) as doc:
        words = doc[page].get_text("words")
    headings = sorted((w for w in words if _inside(w, header_box)), key=lambda w: w[0])
    if [w[4].casefold() for w in headings] != header["text"].casefold().split():
        return {}
    label_header, *columns = headings
    if not all(_same_line(label_header, col) for col in columns):
        return {}
    upper_bound = caption_box[1] if caption_box[1] > header_box[3] else header_box[3] + 72
    result = {}
    keys = Counter()
    for block in blocks:
        bounds = block["metadata"]["bbox"]
        if block["metadata"]["page_no"] != page or not header_box[3] < bounds[1] < upper_bound:
            continue
        local = [w for w in words if _inside(w, bounds) and w[3] < upper_bound]
        starts = [w for w in local if abs(w[0] - label_header[0]) <= 2]
        for start in starts:
            row = sorted((w for w in local if _same_line(w, start)), key=lambda w: w[0])
            values = [[w for w in row if abs(_center_x(w) - _center_x(col)) <= 4
                       and _INTEGER.fullmatch(w[4])] for col in columns]
            if not all(len(v) == 1 for v in values):
                continue
            values = [v[0] for v in values]
            labels = [w for w in row if w[2] < values[0][0]]
            label = " ".join(w[4] for w in labels)
            original_sequence = " ".join([label, *(v[4] for v in values)])
            if not labels or original_sequence not in " ".join(block["text"].split()):
                continue
            for col, value in zip(columns, values, strict=True):
                cell = {
                    "page_no": page, "table_id": matched[1], "caption_source_id": caption["source_id"],
                    "header_source_id": header["source_id"], "row_source_id": block["source_id"],
                    "label_header": label_header[4], "column_header": col[4],
                    "row_label": label, "cell_text": value[4], "column_bbox": list(col[:4]),
                    "label_bbox": [labels[0][0], start[1], labels[-1][2], start[3]],
                    "cell_bbox": list(value[:4]),
                }
                keys[label.casefold(), col[4].casefold()] += 1
                result.setdefault(block["source_id"], []).append(cell)
    return {id_: unique for id_, cells in result.items()
            if (unique := [c for c in cells if keys[c["row_label"].casefold(), c["column_header"].casefold()] == 1])}


def count_cell_claim(cell: TableCell) -> str:
    return (f'In Table {cell["table_id"]}, the count for {cell["row_label"]} '
            f'in the {cell["column_header"]} column is {cell["cell_text"]}.')


def check_count_claim(claim: str, context: str, source_id: str | None,
                      cell: TableCell) -> tuple[str, str] | None:
    parsed = _COUNT_CLAIM.fullmatch(claim.strip())
    if parsed is None:
        return None
    unknown = "not_enough_info"
    if not source_id or cell.get("row_source_id") != source_id:
        return unknown, "table_row_source_mismatch"
    if (parsed["table"].casefold() != cell.get("table_id", "").casefold()
            or parsed["label"] != cell["row_label"] or parsed["column"] != cell["column_header"]
            or not _INTEGER.fullmatch(cell["cell_text"])):
        return unknown, "table_scope_mismatch"
    words = " " + " ".join(context.split()) + " "
    if f' {cell["row_label"]} ' not in words or f' {cell["cell_text"]} ' not in words:
        return unknown, "table_cell_absent_from_source"
    label, value, header = cell["label_bbox"], cell["cell_bbox"], cell["column_bbox"]
    if (not _same_line(label, value) or label[2] >= value[0]
            or abs(_center_x(header) - _center_x(value)) > 4 or value[1] <= header[3]):
        return unknown, "table_cell_geometry_mismatch"
    expected = int(parsed["value"].replace(",", ""))
    observed = int(cell["cell_text"].replace(",", ""))
    return ("support", "table_count_matches") if expected == observed else ("contradict", "table_count_differs")


def table_percentage_cells(pdf_path: str, table: list[SourceChunk]) -> dict[str, TableCell]:
    """Bind each row to one percentage column using PDF coordinates and exact text."""
    if not table or not Path(pdf_path).is_file():
        return {}
    import fitz

    caption, *blocks = table
    caption_match = _CAPTION.match(caption["text"])
    if caption_match is None:
        return {}
    page = caption["metadata"]["page_no"]
    with fitz.open(pdf_path) as doc:
        words = doc[page].get_text("words")
    # Work from the lowest qualifying header. Earlier sections may reuse the same column names.
    header_block = None
    header = []
    for block in reversed(blocks):
        if block["metadata"]["page_no"] != page:
            continue
        lines = {line.strip().casefold() for line in block["text"].splitlines()}
        if "%" in lines and lines & _LABEL_HEADERS:
            header_block = block
            header = [w for w in words if _inside(w, block["metadata"]["bbox"])]
            break
    if header_block is None:
        return {}
    columns = [w for w in header if w[4] == "%"]
    labels = [w for w in header if w[4].casefold() in _LABEL_HEADERS]
    if len(columns) != 1 or len(labels) != 1:
        return {}
    column, label_header = columns[0], labels[0]
    if not _same_line(column, label_header) or label_header[2] >= column[0]:
        return {}
    following = [w[0] for w in header if w[0] > column[0] and _same_line(w, column)]
    column_limit = min(following, default=header_block["metadata"]["bbox"][2])
    result: dict[str, TableCell] = {}
    for row in blocks:
        bounds = row["metadata"]["bbox"]
        if row["metadata"]["page_no"] != page or bounds[1] <= header_block["metadata"]["bbox"][3]:
            continue
        row_words = [w for w in words if _inside(w, bounds)]
        values = [w for w in row_words if abs(w[0] - column[0]) <= 2
                  and w[2] <= column_limit + 1 and _PERCENT.fullmatch(w[4])]
        if len(values) != 1:
            continue
        value = values[0]
        label_words = sorted((w for w in row_words if _same_line(w, value)
                              and w[0] >= label_header[0] - 2 and w[2] < column[0]), key=lambda w: w[0])
        if not label_words or abs(label_words[0][0] - label_header[0]) > 2:
            continue
        label = " ".join(w[4] for w in label_words)
        source_words = row["text"].split()
        source_text = " " + " ".join(source_words) + " "
        if f" {label} " not in source_text or source_words.count(value[4]) != 1:
            continue
        result[row["source_id"]] = {
            "page_no": page,
            "table_id": caption_match[1],
            "caption_source_id": caption["source_id"],
            "header_source_id": header_block["source_id"],
            "row_source_id": row["source_id"],
            "label_header": label_header[4],
            "column_header": column[4],
            "row_label": label,
            "cell_text": value[4],
            "column_bbox": list(column[:4]),
            "label_bbox": [min(w[0] for w in label_words), min(w[1] for w in label_words),
                           max(w[2] for w in label_words), max(w[3] for w in label_words)],
            "cell_bbox": list(value[:4]),
        }
    labels_by_row = Counter(cell["row_label"].casefold() for cell in result.values())
    return {id_: cell for id_, cell in result.items() if labels_by_row[cell["row_label"].casefold()] == 1}


def check_percentage_claim(claim: str, context: str, source_id: str | None,
                           cell: TableCell) -> tuple[str, str] | None:
    """Assess a single explicitly named table cell. Other claim forms use the verifier."""
    parsed = _PERCENT_CLAIM.fullmatch(claim.strip())
    if parsed is None:
        return None
    unknown = "not_enough_info"
    if not source_id or cell.get("row_source_id") != source_id:
        return unknown, "table_row_source_mismatch"
    if (parsed["table"].casefold() != cell.get("table_id", "").casefold()
            or parsed["label"] != cell["row_label"] or cell["column_header"] != "%"
            or cell["label_header"].casefold() not in _LABEL_HEADERS):
        return unknown, "table_scope_mismatch"
    label = cell["row_label"]
    observed = cell["cell_text"]
    words = context.split()
    if (not _PERCENT.fullmatch(observed) or words.count(observed.replace(" ", "")) != 1
            or f" {label} " not in " " + " ".join(words) + " "):
        return unknown, "table_cell_absent_from_source"
    label_box, value_box, header_box = cell["label_bbox"], cell["cell_bbox"], cell["column_bbox"]
    if (not _same_line(label_box, value_box) or label_box[2] >= value_box[0]
            or abs(value_box[0] - header_box[0]) > 2 or value_box[1] <= header_box[3]):
        return unknown, "table_cell_geometry_mismatch"
    expected = Decimal(parsed["value"][:-1].strip())
    value = Decimal(observed[:-1].strip())
    if not all(Decimal(0) <= n <= Decimal(100) for n in (expected, value)):
        return unknown, "table_percentage_out_of_range"
    if expected == value:
        return "support", "table_percentage_matches"
    return "contradict", "table_percentage_differs"
