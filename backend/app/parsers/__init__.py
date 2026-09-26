"""Readers for the formats search databases export (guide 8.3).

Every parser takes the file's text and yields `ParsedRecord` or `ParseProblem`, so one bad
entry never stops an import. The upload cap (MAX_UPLOAD_MB) bounds how much text this is.
"""

from collections.abc import Iterator

from app.parsers import bibtex, csv_parser, endnote_xml, nbib, pubmed_xml, ris, zotero_rdf
from app.parsers.common import ParsedRecord, ParseItem, ParseProblem

# Value → the module that reads it. The values match the FileFormat column.
FORMATS = {
    "ris": ris,
    "bib": bibtex,
    "nbib": nbib,
    "pubmed_xml": pubmed_xml,
    "endnote_xml": endnote_xml,
    "csv": csv_parser,
    "zotero_rdf": zotero_rdf,
}
EXTENSIONS = {
    ".ris": "ris",
    ".bib": "bib",
    ".bibtex": "bib",
    ".nbib": "nbib",
    ".csv": "csv",
    ".tsv": "csv",
    ".rdf": "zotero_rdf",
}
SNIFF = 8 * 1024


def detect(filename: str, text: str) -> str | None:
    """The format of an uploaded file, from its name and then its content (guide 12.4).

    Content decides: a file named .txt is common, and an extension is only a claim.
    """
    head = text[:SNIFF]
    stripped = head.lstrip("﻿ \t\r\n")
    if stripped.startswith("<"):
        if "PubmedArticle" in head or "MedlineCitation" in head:
            return "pubmed_xml"
        if "zotero.org/namespaces/export" in head or "purl.org/net/biblio" in head:
            return "zotero_rdf"
        if "<records" in head or "EndNote" in head or "<xml>" in stripped[:200]:
            return "endnote_xml"
        return None
    if "\nTY  - " in f"\n{head}" or "\nER  -" in head:
        return "ris"
    if "\nPMID- " in f"\n{head}" or "\nPMID-" in head:
        return "nbib"
    if (
        "@" in head
        and "{" in head
        and any(f"@{kind}" in head.lower() for kind in ("article", "book", "inproceedings", "misc"))
    ):
        return "bib"
    suffix = filename[filename.rfind(".") :].lower() if "." in filename else ""
    if suffix in EXTENSIONS and EXTENSIONS[suffix] == "csv" and head.count(",") + head.count("\t"):
        return "csv"
    return EXTENSIONS.get(suffix)


def parse(
    file_format: str, text: str, mapping: dict[str, str] | None = None
) -> Iterator[ParseItem]:
    """Read `text` with the parser for `file_format`; `mapping` is CSV's column mapping."""
    module = FORMATS[file_format]
    if file_format == "csv":
        return csv_parser.parse(text, mapping)
    return module.parse(text)  # type: ignore[no-any-return]


__all__ = [
    "EXTENSIONS",
    "FORMATS",
    "ParseItem",
    "ParseProblem",
    "ParsedRecord",
    "detect",
    "parse",
]
