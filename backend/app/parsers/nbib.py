"""PubMed's own format, MEDLINE/NBIB (guide 8.3).

    PMID- 31234567
    TI  - Night shift work and sleep quality in hospital
          nurses.
    FAU - Smith, Jane A
    LID - 10.1136/bmj.l1234 [doi]

A four-character tag, "- ", then the value; wrapped lines are indented. A PMID line
starts a new record, so a truncated file still yields everything before the cut.
"""

import re
from collections.abc import Iterator
from dataclasses import replace
from typing import Any

from app.parsers.common import (
    MAX_LIST,
    ParseItem,
    ParseProblem,
    clean_text,
    normalise_doi,
    record_from_fields,
)

TAGS: dict[str, str] = {
    "TI": "title",
    "BTI": "title",
    "AB": "abstract",
    "FAU": "authors",
    "DP": "year",
    "JT": "journal",
    "VI": "volume",
    "IP": "issue",
    "PG": "pages",
    "PT": "publication_type",
    "MH": "keywords",
    "OT": "keywords",
    "LA": "language",
    "PMC": "pmcid",
    "PMID": "pmid",
    "IS": "isbn",
}
_TAG_LINE = re.compile(r"^([A-Z][A-Z0-9]{0,3})\s*- ?(.*)$")
_DOI_MARKED = re.compile(r"(10\.\S+?)\s*\[doi\]", re.IGNORECASE)


def _doi_from(fields: dict[str, list[str]]) -> str | None:
    """LID and AID hold several identifiers, each marked with its kind."""
    for value in [*fields.get("LID", []), *fields.get("AID", [])]:
        marked = _DOI_MARKED.search(value)
        if marked:
            return normalise_doi(marked.group(1))
    return None


def _finish(fields: dict[str, list[str]], line: int) -> ParseItem | None:
    if not fields:
        return None
    record = record_from_fields(fields, TAGS)
    changes: dict[str, Any] = {}
    doi = _doi_from(fields)
    if doi:
        changes["doi"] = doi
    if not record.authors and fields.get("AU"):  # short forms only, e.g. "Smith JA"
        changes["authors"] = record_from_fields({"AU": fields["AU"]}, {"AU": "authors"}).authors
    if not record.journal and fields.get("TA"):
        changes["journal"] = clean_text(fields["TA"][0])
    record = replace(record, **changes) if changes else record
    if not record.is_usable():
        return ParseProblem(line, "no title, DOI or PubMed id")
    return record


def parse(text: str) -> Iterator[ParseItem]:
    """Yield a record per MEDLINE entry, or a problem for one that cannot be read."""
    fields: dict[str, list[str]] = {}
    last_tag: str | None = None
    started = 0
    for number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.lstrip("\ufeff").rstrip()
        if not line.strip():
            continue
        if line.startswith("      ") and last_tag:  # a wrapped continuation line
            fields[last_tag][-1] += " " + line.strip()
            continue
        match = _TAG_LINE.match(line)
        if match is None:
            continue
        tag, value = match.group(1), match.group(2).strip()
        if tag == "PMID" and fields:
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
