"""BibTeX, as Zotero, Mendeley and Google Scholar write it (guide 8.3).

    @article{smith2019,
      title = {Night shift work and sleep quality},
      author = {Smith, Jane A and Chowdhury, S},
      doi = {10.1136/bmj.l1234},
    }

Values may be braced, quoted or bare, and braces nest, so the field reader tracks depth
rather than matching a regular expression.
"""

import re
from collections.abc import Iterator
from dataclasses import replace

from app.parsers.common import (
    MAX_LIST,
    ParsedRecord,
    ParseItem,
    ParseProblem,
    normalise_year,
    record_from_fields,
)

FIELDS: dict[str, str] = {
    "title": "title",
    "booktitle": "title",
    "abstract": "abstract",
    "author": "authors",
    "year": "year",
    "date": "year",
    "journal": "journal",
    "journaltitle": "journal",
    "volume": "volume",
    "number": "issue",
    "issue": "issue",
    "pages": "pages",
    "doi": "doi",
    "url": "url",
    "keywords": "keywords",
    "language": "language",
    "isbn": "isbn",
    "issn": "isbn",
    "pmid": "pmid",
}
# A LaTeX accent: {\"o}, \'{e}, \~n. The letter is what matters for screening.
_ACCENT = re.compile(r"\{?\\[`'\"^~=.uvHtcdbra]+\s*\{?([A-Za-z])\}?\}?")
_COMMAND = re.compile(r"\\[a-zA-Z]+\s*")
_BRACES = re.compile(r"[{}]")


def _clean_latex(value: str) -> str:
    """Readable text from LaTeX: accents folded onto their letter, commands dropped."""
    text = _ACCENT.sub(r"\1", value)
    text = _COMMAND.sub(" ", text)
    text = _BRACES.sub("", text)
    return text.replace("--", "-").replace("\\&", "&").strip()


def _entries(text: str) -> Iterator[tuple[int, str, str]]:
    """(line, entry type, body) for every @entry in the file, braces balanced."""
    line = 1
    index = 0
    length = len(text)
    while index < length:
        at = text.find("@", index)
        if at == -1:
            return
        line += text.count("\n", index, at)
        open_brace = text.find("{", at)
        if open_brace == -1:
            return
        kind = text[at + 1 : open_brace].strip().lower()
        depth, cursor, in_quotes = 1, open_brace + 1, False
        while cursor < length and depth:
            char = text[cursor]
            if char == '"' and text[cursor - 1] != "\\":
                in_quotes = not in_quotes
            elif not in_quotes and char == "{":
                depth += 1
            elif not in_quotes and char == "}":
                depth -= 1
            cursor += 1
        body = text[open_brace + 1 : cursor - 1]
        if kind not in {"comment", "string", "preamble"}:
            yield line, kind, body
        line += text.count("\n", at, cursor)
        index = cursor


def _fields_of(body: str) -> dict[str, list[str]]:
    """The name = value pairs of one entry, in file order."""
    fields: dict[str, list[str]] = {}
    index = body.find(",")
    length = len(body)
    while index != -1 and index < length:
        equals = body.find("=", index)
        if equals == -1:
            break
        name = body[index + 1 : equals].strip().strip(",").lower()
        cursor = equals + 1
        while cursor < length and body[cursor] in " \t\r\n":
            cursor += 1
        if cursor >= length:
            break
        if body[cursor] in '{"':
            closer = "}" if body[cursor] == "{" else '"'
            depth, start = 1, cursor + 1
            cursor += 1
            while cursor < length and depth:
                if body[cursor] == "{":
                    depth += 1
                elif body[cursor] == closer or (closer == '"' and body[cursor] == '"'):
                    depth -= 1
                cursor += 1
            value = body[start : cursor - 1]
        else:
            end = body.find(",", cursor)
            end = length if end == -1 else end
            value, cursor = body[cursor:end], end
        if name and name.isascii() and len(fields.get(name, ())) < MAX_LIST:
            fields.setdefault(name, []).append(_clean_latex(value))
        index = body.find(",", cursor)
    return fields


def parse(text: str) -> Iterator[ParseItem]:
    """Yield a record per BibTeX entry, or a problem for an entry that cannot be read."""
    for line, kind, body in _entries(text):
        fields = _fields_of(body)
        if not fields:
            yield ParseProblem(line, "entry has no fields")
            continue
        record = record_from_fields(fields, FIELDS, commas_split_terms=True)
        record = _split_authors(record, fields)
        if record.year is None and fields.get("date"):
            record = replace(record, year=normalise_year(fields["date"][0]))
        if not record.publication_type:
            record = replace(record, publication_type=[kind] if kind else [])
        if not record.is_usable():
            yield ParseProblem(line, "no title, DOI or PubMed id")
            continue
        yield record


def _split_authors(record: ParsedRecord, fields: dict[str, list[str]]) -> ParsedRecord:
    """BibTeX joins authors with " and "; record_from_fields sees one long string."""
    raw = fields.get("author") or fields.get("editor")
    if not raw:
        return record
    names = [name for part in raw for name in re.split(r"\s+and\s+", part) if name.strip()]
    cleaned = record_from_fields({"a": names}, {"a": "authors"}).authors
    return replace(record, authors=cleaned) if cleaned else record
