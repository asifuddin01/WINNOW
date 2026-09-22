"""EndNote XML, which EndNote, Zotero and several databases export (guide 8.3).

<records><record>
  <titles><title>…</title><secondary-title>…</secondary-title></titles>
  <contributors><authors><author>Smith, Jane</author></authors></contributors>
  <electronic-resource-num>10.1136/bmj.l1234</electronic-resource-num>
</record></records>
"""

from collections.abc import Iterator
from itertools import islice
from xml.etree.ElementTree import Element

from app.parsers.common import (
    MAX_LIST,
    ParsedRecord,
    ParseItem,
    ParseProblem,
    clean_abstract,
    clean_text,
    normalise_author,
    normalise_doi,
    normalise_pmid,
    normalise_year,
    terms_from,
)
from app.parsers.xml_reader import records_of

RECORD = "record"


def _text(node: Element | None) -> str | None:
    """EndNote wraps most values in <style> elements; itertext sees through them."""
    if node is None:
        return None
    return "".join(node.itertext()).strip() or None


def _first(record: Element, *paths: str) -> str | None:
    for path in paths:
        value = _text(record.find(path))
        if value:
            return value
    return None


def _authors(record: Element) -> list[str]:
    names: list[str] = []
    for author in islice(record.iterfind(".//contributors/authors/author"), MAX_LIST):
        name = normalise_author(_text(author) or "")
        if name and name not in names:
            names.append(name)
    return names


def _record(record: Element) -> ParsedRecord:
    keywords = [_text(k) or "" for k in record.iterfind(".//keywords/keyword")]
    reference_type = record.find("ref-type")
    kind = reference_type.get("name") if reference_type is not None else None
    return ParsedRecord(
        title=clean_text(_first(record, "titles/title", "titles/short-title"), 2_000),
        abstract=clean_abstract(_first(record, "abstract")),
        authors=_authors(record),
        year=normalise_year(_first(record, "dates/year", "dates/pub-dates/date")),
        journal=clean_text(
            _first(record, "periodical/full-title", "titles/secondary-title", "titles/alt-title")
        ),
        volume=clean_text(_first(record, "volume")),
        issue=clean_text(_first(record, "number", "issue")),
        pages=clean_text(_first(record, "pages")),
        doi=normalise_doi(_first(record, "electronic-resource-num", "doi")),
        pmid=normalise_pmid(_first(record, "accession-num")),
        pmcid=None,
        isbn=clean_text(_first(record, "isbn")),
        url=clean_text(_first(record, "urls/related-urls/url", "urls/web-urls/url")),
        keywords=terms_from([k for k in keywords if k]),
        language=clean_text(_first(record, "language")),
        publication_type=[kind] if kind else [],
        raw={},
    )


def parse(text: str) -> Iterator[ParseItem]:
    """Yield a record per <record> element, streaming the file as it goes."""
    for line, element in records_of(text, RECORD):
        try:
            parsed = _record(element)
        except (ValueError, TypeError) as error:  # pragma: no cover - malformed beyond rescue
            yield ParseProblem(line, f"could not read the record ({type(error).__name__})")
            continue
        if not parsed.is_usable():
            yield ParseProblem(line, "no title, DOI or PubMed id", "record")
            continue
        yield parsed
