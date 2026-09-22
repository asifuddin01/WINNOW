"""CSV and TSV, which every database offers and none of them agree on (guide 8.3).

There is no standard, so the columns are mapped to fields: `suggest_mapping` guesses from
the header (it knows what Scopus, Web of Science and CINAHL call things) and the person
confirms or changes it in the mapping step before the import runs.
"""

import csv
import io
from collections.abc import Iterator

from app.parsers.common import (
    MAX_LIST,
    ParsedRecord,
    ParseItem,
    ParseProblem,
    record_from_fields,
)

# Sample enough of the file to sniff the delimiter without reading all of it.
SNIFF_BYTES = 64 * 1024
MAX_COLUMNS = 200
DELIMITERS = ",;\t|"

# Header name (lowercased, punctuation-free) → field. The right-hand side is what
# record_from_fields understands, plus page_start/page_end which are joined afterwards.
HEADERS: dict[str, str] = {
    "title": "title",
    "article title": "title",
    "document title": "title",
    "ti": "title",
    "abstract": "abstract",
    "ab": "abstract",
    "authors": "authors",
    "author": "authors",
    "author full names": "authors",
    "au": "authors",
    "year": "year",
    "publication year": "year",
    "py": "year",
    "date": "year",
    "journal": "journal",
    "journal title": "journal",
    "source title": "journal",
    "source": "journal",
    "so": "journal",
    "volume": "volume",
    "vl": "volume",
    "issue": "issue",
    "is": "issue",
    "pages": "pages",
    "page range": "pages",
    "page start": "page_start",
    "beginning page": "page_start",
    "start page": "page_start",
    "page end": "page_end",
    "ending page": "page_end",
    "end page": "page_end",
    "doi": "doi",
    "di": "doi",
    "pmid": "pmid",
    "pubmed id": "pmid",
    "pmcid": "pmcid",
    "url": "url",
    "link": "url",
    "keywords": "keywords",
    "author keywords": "keywords",
    "index keywords": "keywords",
    "keywords plus": "keywords",
    "de": "keywords",
    "language": "language",
    "la": "language",
    "document type": "publication_type",
    "publication type": "publication_type",
    "isbn": "isbn",
    "issn": "isbn",
}
FIELDS = (
    "title",
    "abstract",
    "authors",
    "year",
    "journal",
    "volume",
    "issue",
    "pages",
    "page_start",
    "page_end",
    "doi",
    "pmid",
    "pmcid",
    "url",
    "keywords",
    "language",
    "publication_type",
    "isbn",
)


def _tidy(header: str) -> str:
    return "".join(c if c.isalnum() or c.isspace() else " " for c in header).strip().lower()


def delimiter_of(text: str) -> str:
    """The delimiter the file uses, sniffed from its first lines."""
    sample = text[:SNIFF_BYTES]
    try:
        return csv.Sniffer().sniff(sample, delimiters=DELIMITERS).delimiter
    except csv.Error:
        first = sample.splitlines()[0] if sample.splitlines() else ""
        counts = {d: first.count(d) for d in DELIMITERS}
        best = max(counts, key=lambda d: counts[d])
        return best if counts[best] else ","


def columns_of(text: str) -> list[str]:
    """The header row, in file order."""
    reader = csv.reader(io.StringIO(text.lstrip("﻿")), delimiter=delimiter_of(text))
    header = next(reader, [])
    return [column.strip() for column in header[:MAX_COLUMNS]]


def suggest_mapping(columns: list[str]) -> dict[str, str]:
    """Column → field for the columns this reader recognises; the rest are left alone."""
    mapping: dict[str, str] = {}
    for column in columns:
        field = HEADERS.get(_tidy(column))
        if field and field not in mapping.values():
            mapping[column] = field
    return mapping


def sample_rows(text: str, limit: int = 5) -> list[dict[str, str]]:
    """The first rows as column → value, for the preview table."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")), delimiter=delimiter_of(text))
    rows: list[dict[str, str]] = []
    for row in reader:
        rows.append({k: (v or "") for k, v in row.items() if k})
        if len(rows) >= limit:
            break
    return rows


def parse(text: str, mapping: dict[str, str] | None = None) -> Iterator[ParseItem]:
    """Yield a record per row, using `mapping` (or the guess) to name the columns."""
    stream = io.StringIO(text.lstrip("﻿"))
    delimiter = delimiter_of(text)
    reader = csv.DictReader(stream, delimiter=delimiter)
    columns = [c.strip() for c in (reader.fieldnames or [])]
    chosen = mapping or suggest_mapping(columns)
    wanted = {column: field for column, field in chosen.items() if field in FIELDS}
    if not wanted:
        yield ParseProblem(1, "no column holds a title, DOI or PubMed id")
        return
    for number, row in enumerate(reader, start=2):
        fields: dict[str, list[str]] = {}
        for column, value in row.items():
            field = wanted.get((column or "").strip())
            if field and value:
                fields.setdefault(field, []).append(str(value)[:100_000])
            if len(fields) > MAX_LIST:
                break
        if not fields:
            continue
        record = record_from_fields(fields, {f: f for f in FIELDS}, commas_split_terms=True)
        record = _pages(record, fields)
        if not record.is_usable():
            yield ParseProblem(number, "no title, DOI or PubMed id in this row")
            continue
        yield record


def _pages(record: ParsedRecord, fields: dict[str, list[str]]) -> ParsedRecord:
    """Scopus and Web of Science split the page range over two columns."""
    from dataclasses import replace

    if record.pages:
        return record
    start = next(iter(fields.get("page_start", [])), "").strip()
    end = next(iter(fields.get("page_end", [])), "").strip()
    pages = f"{start}-{end}" if start and end else start or end
    return replace(record, pages=pages or None)
