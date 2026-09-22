"""RIS, the format nearly every database exports (guide 8.3).

    TY  - JOUR
    AU  - Smith, Jane
    TI  - A title that runs
          onto a second line
    ER  -

Tags vary between databases, so the mapping below covers the ones Ovid, Scopus, Web of
Science, CINAHL, Cochrane, Zotero, EndNote and Mendeley actually write.
"""

from collections.abc import Iterator
from dataclasses import replace
from typing import Any

from app.parsers.common import (
    MAX_LIST,
    ParsedRecord,
    ParseItem,
    ParseProblem,
    clean_text,
    normalise_pmid,
    record_from_fields,
)

# Tag → field in ParsedRecord. Tags not listed stay in `raw`.
TAGS: dict[str, str] = {
    "TI": "title",
    "T1": "title",
    "CT": "title",
    "BT": "title",
    "AB": "abstract",
    "N2": "abstract",
    "AU": "authors",
    "A1": "authors",
    "PY": "year",
    "Y1": "year",
    "DA": "year",
    "JO": "journal",
    "JF": "journal",
    "JA": "journal",
    "J2": "journal",
    "T2": "journal",
    "SO": "journal",
    "VL": "volume",
    "IS": "issue",
    "DO": "doi",
    "DI": "doi",
    "UR": "url",
    "L3": "doi",
    "KW": "keywords",
    "DE": "keywords",
    "ID": "keywords",
    "LA": "language",
    "TY": "publication_type",
    "M3": "publication_type",
    "SN": "isbn",
}
START_TAGS = frozenset({"TY", "PMID", "PT"})
MEDLINE_DATABASES = ("medline", "pubmed")


def _is_tag_line(line: str) -> tuple[str, str] | None:
    """("TI", "the title") when the line starts a field, else None."""
    if len(line) < 6 or line[4:6] != "- ":
        if len(line) == 5 and line[4] == "-":  # "ER  -" with nothing after it
            return line[:4].strip(), ""
        return None
    tag = line[:4].strip()
    return (tag, line[6:].strip()) if tag.isalnum() else None


def _finish(fields: dict[str, list[str]], line: int) -> ParseItem | None:
    if not fields:
        return None
    record = record_from_fields(fields, TAGS)
    record = _pages(record, fields)
    record = _pubmed_id(record, fields)
    if not record.is_usable():
        return ParseProblem(line, "no title, DOI or PubMed id")
    return record


def _pages(record: ParsedRecord, fields: dict[str, list[str]]) -> ParsedRecord:
    """RIS splits pages across SP and EP."""
    start = clean_text(next(iter(fields.get("SP", [])), None))
    end = clean_text(next(iter(fields.get("EP", [])), None))
    if start and end:
        return _replace(record, pages=f"{start}-{end}")
    return _replace(record, pages=start or end) if (start or end) else record


def _pubmed_id(record: ParsedRecord, fields: dict[str, list[str]]) -> ParsedRecord:
    """Ovid and CINAHL put the PubMed id in AN when the database is MEDLINE."""
    database = " ".join(fields.get("DB", []) + fields.get("DP", [])).lower()
    candidates = fields.get("AN", []) if any(n in database for n in MEDLINE_DATABASES) else []
    for value in [*fields.get("PMID", []), *candidates]:
        pmid = normalise_pmid(value)
        if pmid:
            return _replace(record, pmid=pmid)
    return record


def _replace(record: ParsedRecord, **changes: Any) -> ParsedRecord:
    return replace(record, **changes)


def parse(text: str) -> Iterator[ParseItem]:
    """Yield a record per RIS entry, or a problem for an entry that cannot be read.

    Reads line by line, so a 100k-record file costs one pass and one record in memory.
    """
    fields: dict[str, list[str]] = {}
    last_tag: str | None = None
    started = 0
    for number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.lstrip("﻿").rstrip()
        tagged = _is_tag_line(line)
        if tagged is None:
            if last_tag and line.strip():  # a wrapped continuation line
                fields[last_tag][-1] += " " + line.strip()
            continue
        tag, value = tagged
        if tag == "ER":
            item = _finish(fields, started or number)
            if item is not None:
                yield item
            fields, last_tag, started = {}, None, 0
            continue
        if tag in START_TAGS and fields.get(tag):  # a file without ER lines
            item = _finish(fields, started or number)
            if item is not None:
                yield item
            fields, last_tag, started = {}, None, 0
        if not fields:
            started = number
        if len(fields.get(tag, ())) < MAX_LIST:
            fields.setdefault(tag, []).append(value)
            last_tag = tag
    item = _finish(fields, started or 1)
    if item is not None:
        yield item
