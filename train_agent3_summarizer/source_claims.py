"""Project selected PDF evidence onto simple, explicitly scoped questions."""

from decimal import Decimal
import re

from research_rag.pdf_table_cells import count_cell_claim


_INTEGER = r"(?:\d{1,3}(?:,\d{3})+|\d+)"
_COUNT_QUESTION = re.compile(
    r"(?:According to the (?:abstract|paper|article)(?: of the [\w.-]+ paper)?, )?"
    r"how many (?P<unit>[\w-]+) does (?P<name>[\w.-]+) contain\?", re.I)
_FULL_COUNT = (
    rf"(?P<count>{_INTEGER}) (?P<unit>[\w-]+)"
    rf"(?: over (?P<corpus>{_INTEGER} (?:[\w-]+ )*(?:papers|documents|publications|articles)))?"
)
_DECLARATION = re.compile(
    rf"We (?:therefore )?(?:present|introduce) (?P<name>[\w.-]+), a dataset of {_FULL_COUNT}\.", re.I)
_COUNT_CLAIM = re.compile(rf"(?:The )?(?P<name>[\w.-]+)(?: dataset)? contains {_FULL_COUNT}\.", re.I)
_QUALIFIED_CORPUS = re.compile(
    r"\b(?:only|under|without|before|after|during|including|excluding|among|from|in|for|and|or|"
    r"filtered|restricted|sampled|selected|limited|subset)\b", re.I)
_TABLE = re.compile(r"\bTable\s+(\d+[A-Za-z]?)\b", re.I)
_PERCENT = r"[+-]?\d+(?:\.\d+)?\s*%"
_PERCENT_PART = re.compile(rf"for (?P<label>.+?) is (?P<value>{_PERCENT})", re.I)
_COUNT_ROWS = re.compile(
    r"According to Table (?P<table>\d+[A-Za-z]?), how many (?P<rows>.+?) are in (?P<owner>[\w.-]+)"
    r"(?:, respectively)?\?", re.I)
_COUNT_SPLITS = re.compile(
    r"According to the (?P<row>.+?) row of Table (?P<table>\d+[A-Za-z]?), how many (?:total )?(?P<unit>.+?)"
    r" are in the (?P<columns>.+?) sets? of (?P<owner>[\w.-]+)(?:, respectively)?\?", re.I)


def _normalized(text):
    return " ".join(re.sub(r"(?<=\w)-[ \t]*\r?\n[ \t]*(?=[a-z])", "", text).split())


def _count_projection(question, bindings, units):
    query = _COUNT_QUESTION.fullmatch(_normalized(question))
    if query is None or len(bindings) != 1:
        return None
    claim, ids = next(iter(bindings.items()))
    if len(ids) != 1:
        return None
    proposed = _COUNT_CLAIM.fullmatch(_normalized(claim))
    source = _DECLARATION.fullmatch(_normalized(units[ids[0]]))
    if source is None or proposed is None:
        return None
    if (any(m["name"].casefold() != source["name"].casefold() or m["unit"].casefold() != source["unit"].casefold()
            for m in (query, proposed))
            or proposed["count"].replace(",", "") != source["count"].replace(",", "")
            or (proposed["corpus"] or "").casefold() != (source["corpus"] or "").casefold()
            or _QUALIFIED_CORPUS.search(source["corpus"] or "")):
        return None
    return {f'{source["name"]} is a dataset of {source["count"]} {source["unit"]}.': ids}


def _table_projection(question, bindings, cells, scope):
    tables = list(_TABLE.finditer(question))
    if len(tables) != 1:
        return None
    table = tables[0][1]
    request = re.fullmatch(r"(?:of the [\w.-]+ paper)?,\s*what percentages? (?:are|is) "
                           r"(?:listed|reported|shown) for (.+?)(?:,\s*respectively)?\?",
                           question[tables[0].end():].strip(), re.I)
    if request is None:
        return None
    section = re.fullmatch(r"In (?:the ([A-Za-z]+) section of )?", question[:tables[0].start()], re.I)
    if section is None:
        return None
    qualifier = (section[1] or "").casefold()
    rows = re.sub(r"^the\s+", "", request[1], flags=re.I)
    if qualifier:
        rows = re.sub(rf"\s+{re.escape(qualifier)}\s+types?$", "", rows, flags=re.I)
    requested = [part.strip().casefold() for part in re.split(r"\s+and\s+", rows, flags=re.I)]
    if len(set(requested)) != len(requested):
        return {}
    resolved = {}
    for claim, ids in bindings.items():
        prefix = re.match(r"(?:(?:In Table (\d+[A-Za-z]?), )?the )?percentage for ", claim, re.I)
        if prefix is None or prefix[1] and prefix[1].casefold() != table.casefold():
            return {}
        parts = re.split(r"\s+and\s+(?=for\s+)", "for " + claim[prefix.end():].removesuffix("."), flags=re.I)
        for part in parts:
            value = _PERCENT_PART.fullmatch(part)
            if value is None:
                return {}
            label = re.sub(r"^the\s+", "", value["label"], flags=re.I).casefold()
            if qualifier:
                label = re.sub(rf"\s+{re.escape(qualifier)}(?:\s+type)?$", "", label)
            matches = [(id_, cells[id_]) for id_ in ids if id_ in cells
                       and cells[id_]["table_id"].casefold() == table.casefold()
                       and cells[id_]["column_header"] == "%"
                       and cells[id_]["row_label"].casefold() == label
                       and (not qualifier or qualifier in {line.strip().casefold() for line in scope[id_][1].splitlines()})]
            if len(matches) != 1 or label in resolved:
                return {}
            id_, cell = matches[0]
            if Decimal(value["value"][:-1].strip()) != Decimal(cell["cell_text"][:-1].strip()):
                return {}
            resolved[label] = (f'In Table {cell["table_id"]}, the percentage for {cell["row_label"]} is {cell["cell_text"]}.', id_)
    if set(resolved) != set(requested):
        return {}
    return {resolved[label][0]: [resolved[label][1]] for label in requested}


def _count_table_projection(question, bindings, cells):
    split_query = _COUNT_SPLITS.fullmatch(question)
    query = split_query or _COUNT_ROWS.fullmatch(question)
    if query is None:
        return None
    if split_query:
        if query["row"].casefold().removesuffix("s") != query["unit"].casefold().removesuffix("s"):
            return {}
        requested = [(query["row"], col) for col in re.split(r"\s+and\s+", query["columns"], flags=re.I)]
    else:
        requested = [(label, "Value") for label in re.split(r"\s+and\s+how many\s+", query["rows"], flags=re.I)]
    result = {}
    patterns = {}
    for row, column in requested:
        candidates = []
        for claim, ids in bindings.items():
            for id_ in ids:
                for cell in cells.get(id_, []):
                    if (cell["table_id"].casefold() == query["table"].casefold()
                            and cell["column_header"].casefold() == column.casefold()
                            and cell["row_label"].rstrip("†‡*").casefold() == row.casefold()):
                        candidates.append((claim, id_, cell))
        if len(candidates) != 1:
            return {}
        claim, id_, cell = candidates[0]
        count = re.escape(cell["cell_text"])
        patterns.setdefault(claim, []).append((row, column, count))
        result[count_cell_claim(cell)] = [id_]
    if set(patterns) != set(bindings):
        return {}
    for claim, pairs in patterns.items():
        if split_query:
            unit = re.escape(query["unit"])
            forms = [" and ".join(
                rf"(?:The )?{re.escape(column)} set (?:has|contains) {count} {unit}"
                for _, column, count in pairs)]
        else:
            forms = [
                " and ".join(rf"The number of {re.escape(row)} is {count}" for row, _, count in pairs),
                rf"{re.escape(query['owner'])} contains " +
                " and ".join(rf"{count} {re.escape(row)}" for row, _, count in pairs),
            ]
        if not any(re.fullmatch(form, claim.removesuffix("."), re.I) for form in forms):
            return {}
    return result


def project_claims(question, bindings, units, table_cells, table_scope, count_cells=None):
    if table_scope is not None:
        count_table = _count_table_projection(question, bindings, count_cells or {})
        if count_table is not None:
            return count_table
        table = _table_projection(question, bindings, table_cells or {}, table_scope)
        if table is not None:
            return table
    return _count_projection(question, bindings, units)
