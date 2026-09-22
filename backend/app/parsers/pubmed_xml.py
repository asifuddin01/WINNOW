"""PubMed XML, as PubMed's own "Send to → File → XML" writes it (guide 8.3).

Parsed with defusedxml (guide 12.3): a search export is an untrusted file, and plain
ElementTree would follow entity declarations pointing at the server's own disk.
"""

from collections.abc import Iterator
from itertools import islice
from typing import Any
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

ARTICLE = "PubmedArticle"


def _text(node: Element | None) -> str | None:
    """All the text under a node, including mark-up children such as <i> and <sup>."""
    if node is None:
        return None
    return "".join(node.itertext()) or None


def _authors(article: Element) -> list[str]:
    names: list[str] = []
    for author in islice(article.iterfind(".//AuthorList/Author"), MAX_LIST):
        last = _text(author.find("LastName"))
        fore = _text(author.find("ForeName")) or _text(author.find("Initials"))
        collective = _text(author.find("CollectiveName"))
        raw = f"{last}, {fore}" if last and fore else last or collective
        name = normalise_author(raw) if raw else None
        if name and name not in names:
            names.append(name)
    return names


def _abstract(article: Element) -> str | None:
    """Structured abstracts arrive as several labelled sections."""
    parts: list[str] = []
    for section in article.iterfind(".//Abstract/AbstractText"):
        label = section.get("Label")
        body = _text(section)
        if body:
            parts.append(f"{label}: {body}" if label else body)
    return clean_abstract("\n\n".join(parts)) if parts else None


def _year(article: Element) -> int | None:
    date = article.find(".//Journal/JournalIssue/PubDate")
    if date is None:
        return None
    return normalise_year(_text(date.find("Year")) or _text(date.find("MedlineDate")))


def _identifiers(article: Element) -> dict[str, Any]:
    found: dict[str, Any] = {}
    for node in article.iterfind(".//ArticleIdList/ArticleId"):
        kind, value = node.get("IdType"), _text(node)
        if not value:
            continue
        if kind == "doi":
            found.setdefault("doi", normalise_doi(value))
        elif kind == "pmc":
            found.setdefault("pmcid", clean_text(value))
        elif kind == "pubmed":
            found.setdefault("pmid", normalise_pmid(value))
    for node in article.iterfind(".//ELocationID"):
        if node.get("EIdType") == "doi" and not found.get("doi"):
            found["doi"] = normalise_doi(_text(node))
    return found


def _record(article: Element) -> ParsedRecord:
    keywords = [_text(k) or "" for k in article.iterfind(".//KeywordList/Keyword")]
    mesh = [_text(m) or "" for m in article.iterfind(".//MeshHeading/DescriptorName")]
    identifiers = _identifiers(article)
    return ParsedRecord(
        title=clean_text(_text(article.find(".//Article/ArticleTitle")), 2_000),
        abstract=_abstract(article),
        authors=_authors(article),
        year=_year(article),
        journal=clean_text(
            _text(article.find(".//Journal/Title"))
            or _text(article.find(".//Journal/ISOAbbreviation"))
        ),
        volume=clean_text(_text(article.find(".//JournalIssue/Volume"))),
        issue=clean_text(_text(article.find(".//JournalIssue/Issue"))),
        pages=clean_text(_text(article.find(".//Pagination/MedlinePgn"))),
        doi=identifiers.get("doi"),
        pmid=identifiers.get("pmid") or normalise_pmid(_text(article.find(".//PMID"))),
        pmcid=identifiers.get("pmcid"),
        isbn=clean_text(_text(article.find(".//Journal/ISSN"))),
        url=None,
        keywords=terms_from([k for k in [*keywords, *mesh] if k]),
        language=clean_text(_text(article.find(".//Language"))),
        publication_type=terms_from(
            [_text(p) or "" for p in article.iterfind(".//PublicationType")]
        ),
        raw={},
    )


def parse(text: str) -> Iterator[ParseItem]:
    """Yield a record per <PubmedArticle>. The file is streamed, not held in memory."""
    for line, article in records_of(text, ARTICLE):
        try:
            record = _record(article)
        except (ValueError, TypeError) as error:  # pragma: no cover - malformed beyond rescue
            yield ParseProblem(line, f"could not read the article ({type(error).__name__})")
            continue
        if not record.is_usable():
            yield ParseProblem(line, "no title, DOI or PubMed id", "record")
            continue
        yield record
