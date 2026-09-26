"""Zotero RDF, the export that keeps everything a Zotero library holds (guide 8.3).

<rdf:RDF>
  <bib:Article rdf:about="…">
    <z:itemType>journalArticle</z:itemType>
    <dcterms:isPartOf><bib:Journal>
      <dc:title>…</dc:title><prism:volume>…</prism:volume>
      <dc:identifier>DOI 10.1111/jan.13894</dc:identifier>
    </bib:Journal></dcterms:isPartOf>
    <bib:authors><rdf:Seq><rdf:li><foaf:Person>
      <foaf:surname>Smith</foaf:surname><foaf:givenName>Jane</foaf:givenName>
    </foaf:Person></rdf:li></rdf:Seq></bib:authors>
    <dc:title>…</dc:title>
  </bib:Article>
</rdf:RDF>

Every top-level node with a z:itemType is a reference, except attachments and notes;
collections, journals and notes have none. The journal or book an item is part of is
usually nested in it, but it can be a separate node the item points at, before or after
it, so a first pass collects those when the file has any.
"""

import re
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
from app.parsers.xml_reader import children_of_root

RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
Z = "{http://www.zotero.org/namespaces/export#}"
DC = "{http://purl.org/dc/elements/1.1/}"
DCTERMS = "{http://purl.org/dc/terms/}"
BIB = "{http://purl.org/net/biblio#}"
FOAF = "{http://xmlns.com/foaf/0.1/}"
PRISM = "{http://prismstandard.org/namespaces/1.2/basic/}"

NOT_REFERENCES = {"attachment", "note"}
# Zotero keeps identifiers its item type has no field for in "Extra", one per line.
_EXTRA = re.compile(r"^\s*(DOI|PMID|PMCID):\s*(\S+)", re.IGNORECASE | re.MULTILINE)
_PUBMED_URL = re.compile(r"pubmed(?:\.ncbi\.nlm\.nih\.gov)?/(\d{1,8})")
_POINTED_AT = re.compile(r"isPartOf\s+rdf:resource=")
_CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z])")


def _text(node: Element | None) -> str | None:
    if node is None:
        return None
    return "".join(node.itertext()).strip() or None


def _all(node: Element, tag: str) -> list[str]:
    return [value for child in node.iterfind(tag) if (value := _text(child))]


def _container(item: Element, pointed_at: dict[str, Element]) -> Element | None:
    """The journal, book or proceedings the item is part of, nested or pointed at."""
    part = item.find(f"{DCTERMS}isPartOf")
    if part is None:
        return None
    nested = next(iter(part), None)
    if nested is not None:
        return nested
    return pointed_at.get(part.get(f"{RDF}resource", ""))


def _authors(item: Element) -> list[str]:
    names: list[str] = []
    for person in islice(item.iterfind(f"{BIB}authors//{FOAF}Person"), MAX_LIST):
        surname = _text(person.find(f"{FOAF}surname"))
        given = _text(person.find(f"{FOAF}givenName"))
        # No given name is Zotero's single-field name, such as an organisation: kept as is.
        if surname and given:
            name = normalise_author(f"{surname}, {given}")
        else:
            name = clean_text(surname or given)
        if name and name not in names:
            names.append(name)
    return names


def _record(item: Element, item_type: str, pointed_at: dict[str, Element]) -> ParsedRecord:
    container = _container(item, pointed_at)
    sources = [item] if container is None else [item, container]
    identifiers = [value for node in sources for value in _all(node, f"{DC}identifier")]
    by_kind = {kind.upper(): value for kind, _, value in (i.partition(" ") for i in identifiers)}
    extra = {
        kind.upper(): value
        for kind, value in _EXTRA.findall("\n".join(_all(item, f"{DC}description")))
    }
    url = next((i for i in identifiers if i.startswith(("http://", "https://"))), None)
    pubmed = _PUBMED_URL.search(f"{item.get(f'{RDF}about', '')} {url or ''}")

    def first(tag: str) -> str | None:
        return next((value for node in sources if (value := _text(node.find(tag)))), None)

    journal = None
    if container is not None and container.tag != f"{BIB}Series":
        journal = _text(container.find(f"{DC}title"))
    return ParsedRecord(
        title=clean_text(
            _text(item.find(f"{DC}title")) or _text(item.find(f"{Z}shortTitle")), 2_000
        ),
        abstract=clean_abstract(_text(item.find(f"{DCTERMS}abstract"))),
        authors=_authors(item),
        year=normalise_year(_text(item.find(f"{DC}date"))),
        journal=clean_text(journal),
        volume=clean_text(first(f"{PRISM}volume")),
        issue=clean_text(first(f"{PRISM}number")),
        pages=clean_text(_text(item.find(f"{BIB}pages"))),
        doi=normalise_doi(by_kind.get("DOI") or extra.get("DOI") or url),
        pmid=normalise_pmid(extra.get("PMID") or (pubmed.group(1) if pubmed else None)),
        pmcid=clean_text(extra.get("PMCID")),
        isbn=clean_text(by_kind.get("ISBN")),
        url=clean_text(url),
        keywords=terms_from(_all(item, f"{DC}subject")),
        language=clean_text(_text(item.find(f"{Z}language"))),
        publication_type=[_CAMEL.sub(" ", item_type).capitalize()],
        raw={},
    )


def parse(text: str) -> Iterator[ParseItem]:
    """Yield a record per Zotero item, streaming the file as it goes."""
    pointed_at: dict[str, Element] = {}
    if _POINTED_AT.search(text):
        for node in children_of_root(text):
            about = node.get(f"{RDF}about")
            if about and node.find(f"{Z}itemType") is None:
                # A copy: the reader clears each node once it has been yielded.
                kept = Element(node.tag)
                kept.extend(
                    child for child in node if child.tag in (f"{DC}title", f"{DC}identifier")
                )
                kept.extend(child for child in node if child.tag.startswith(PRISM))
                pointed_at[about] = kept
    ordinal = 0
    for node in children_of_root(text):
        item_type = _text(node.find(f"{Z}itemType"))
        if item_type is None or item_type in NOT_REFERENCES:
            continue
        ordinal += 1
        try:
            parsed = _record(node, item_type, pointed_at)
        except (ValueError, TypeError) as error:  # pragma: no cover - malformed beyond rescue
            yield ParseProblem(
                ordinal, f"could not read the record ({type(error).__name__})", "record"
            )
            continue
        if not parsed.is_usable():
            yield ParseProblem(ordinal, "no title, DOI or PubMed id", "record")
            continue
        yield parsed
