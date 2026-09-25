"""BibTeX, as LaTeX, Zotero and JabRef read it.

Entries are `@article` when there is a journal, `@misc` otherwise, keyed by the first
author's surname and the year (`okafor2016`, then `okafor2016a`, `okafor2016b` …, ASCII
only). LaTeX's special characters are escaped; other text stays UTF-8, which biber and
modern BibTeX read. Winnow's decisions go in `note`.
"""

import re
import unicodedata
from collections.abc import Iterable

from app.exports.types import ExportRecord, decision_notes, one_line, split_pages

_SPECIALS = {
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}
_SPECIAL = re.compile("|".join(re.escape(character) for character in _SPECIALS))


def escape(value: object) -> str:
    return _SPECIAL.sub(lambda match: _SPECIALS[match.group()], one_line(value))


def _ascii_word(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", folded.lower())


def _surname(author: str) -> str:
    """ "Okafor, Ngozi" → "okafor"; "Ngozi Okafor" → "okafor"."""
    name = author.split(",")[0] if "," in author else (author.split() or [""])[-1]
    return _ascii_word(name)


class BibtexWriter:
    """Writes entries in batches; keys stay unique across the whole file."""

    def __init__(self) -> None:
        self._used: set[str] = set()

    def _key(self, record: ExportRecord) -> str:
        stem = (_surname(record.authors[0]) if record.authors else "") or "winnow"
        stem += str(record.year) if record.year else "nd"
        if stem not in self._used:
            self._used.add(stem)
            return stem
        for index in range(26 * 27):
            first, second = divmod(index, 26)
            suffix = ("abcdefghijklmnopqrstuvwxyz"[first - 1] if first else "") + (
                "abcdefghijklmnopqrstuvwxyz"[second]
            )
            if stem + suffix not in self._used:
                self._used.add(stem + suffix)
                return stem + suffix
        key = f"{stem}{record.id.replace('-', '')[:8]}"
        self._used.add(key)
        return key

    def _entry(self, record: ExportRecord) -> str:
        start, end = split_pages(record.pages)
        pages = f"{start}--{end}" if start and end else start
        fields: list[tuple[str, object]] = [
            ("title", record.title),
            ("author", " and ".join(one_line(a) for a in record.authors if one_line(a))),
            ("year", record.year),
            ("journal", record.journal),
            ("volume", record.volume),
            ("number", record.issue),
            ("pages", pages),
            ("doi", record.doi),
            ("pmid", record.pmid),
            ("url", record.url),
            ("keywords", ", ".join(one_line(k) for k in record.keywords if one_line(k))),
            ("language", record.language),
            ("abstract", record.abstract),
            ("note", ". ".join(decision_notes(record))),
        ]
        body = "".join(
            f"  {name} = {{{escape(value)}}},\n" for name, value in fields if one_line(value)
        )
        kind = "article" if record.journal else "misc"
        return f"@{kind}{{{self._key(record)},\n{body}}}\n\n"

    def write(self, records: Iterable[ExportRecord]) -> str:
        return "".join(self._entry(record) for record in records)


def write_bibtex(records: Iterable[ExportRecord]) -> str:
    return BibtexWriter().write(records)
