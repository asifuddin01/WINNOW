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


# Escaped special characters (as Winnow's own writer and JabRef write them), kept aside in
# private-use characters while commands and braces are removed, then put back.
_ESCAPES = {
    r"\textbackslash{}": "\\",
    r"\textasciitilde{}": "~",
    r"\textasciicircum{}": "^",
    **{f"\\{character}": character for character in "&%$#_{}"},
}
_ESCAPED = re.compile("|".join(re.escape(escape) for escape in _ESCAPES))
_KEPT = {character: chr(0xE000 + index) for index, character in enumerate("\\~^&%$#_{}")}


def _clean_latex(value: str) -> str:
    """Readable text from LaTeX: accents folded onto their letter, commands dropped,
    escaped special characters kept."""
    text = _ESCAPED.sub(lambda match: _KEPT[_ESCAPES[match.group()]], value)
    text = _ACCENT.sub(r"\1", text)
    text = _COMMAND.sub(" ", text)
    text = _BRACES.sub("", text).replace("--", "-")
    for character, stand_in in _KEPT.items():
        text = text.replace(stand_in, character)
    return text.strip()


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
        previous = ""
        while cursor < length and depth:
            char = text[cursor]
            if char == "\\" and not in_quotes:  # \{ and \} are text, not structure
                previous = char
                cursor += 2
                continue
            if in_quotes:
                if char == '"' and text[cursor - 1] != "\\":
                    in_quotes = False
            # A quote only delimits a value at the top level of the entry, right after
            # the `=`. Inside a braced value it is ordinary text — abstracts are full of
            # them ("healthy" pancreases), and treating those as delimiters used to
            # swallow every entry after the first one that had a quote in it.
            elif char == '"' and depth == 1 and previous == "=":
                in_quotes = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
            if not char.isspace():
                previous = char
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
                if body[cursor] == "\\":  # an escaped character never opens or closes
                    cursor += 2
                    continue
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
