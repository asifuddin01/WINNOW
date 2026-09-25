"""RIS, as EndNote, Zotero and Mendeley read it.

Winnow's decisions go in `N1` (notes, which every reference manager keeps) and in the
custom fields `C1` (title/abstract status), `C2` (full-text status), `C3` (reasons) and
`C4` (labels), which EndNote and Zotero keep as fields. Lines end with CRLF, as those
programs expect.
"""

from collections.abc import Iterable

from app.exports.types import ExportRecord, decision_notes, one_line, split_pages

CRLF = "\r\n"


def _line(tag: str, value: object) -> str:
    return f"{tag}  - {one_line(value)}{CRLF}"


def _record(record: ExportRecord) -> str:
    lines = [_line("TY", "JOUR" if record.journal else "GEN")]
    if record.title:
        lines.append(_line("TI", record.title))
    lines += [_line("AU", author) for author in record.authors if one_line(author)]
    start, end = split_pages(record.pages)
    for tag, value in (
        ("PY", record.year),
        ("JO", record.journal),
        ("VL", record.volume),
        ("IS", record.issue),
        ("SP", start),
        ("EP", end),
        ("DO", record.doi),
        # The PubMed id as an accession number, with its database, as Ovid writes it.
        ("AN", record.pmid),
        ("DB", "PubMed" if record.pmid else record.database),
        ("UR", record.url),
    ):
        if one_line(value):
            lines.append(_line(tag, value))
    lines += [_line("KW", keyword) for keyword in record.keywords if one_line(keyword)]
    if record.language:
        lines.append(_line("LA", record.language))
    if record.abstract:
        lines.append(_line("AB", record.abstract))
    lines += [_line("N1", note) for note in decision_notes(record)]
    for tag, value in (
        ("C1", record.ta_status),
        ("C2", record.ft_status),
        ("C3", "; ".join([*record.ta_reasons, *record.ft_reasons])),
        ("C4", "; ".join(record.labels)),
    ):
        if one_line(value):
            lines.append(_line(tag, value))
    lines.append(f"ER  - {CRLF}")
    return "".join(lines)


def write_ris(records: Iterable[ExportRecord]) -> str:
    """The records as RIS, a blank line between them."""
    return "".join(_record(record) + CRLF for record in records)
