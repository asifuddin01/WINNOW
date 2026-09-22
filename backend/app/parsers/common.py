"""What every parser produces, and the normalisation the guide asks for (8.3).

Parsers yield `ParsedRecord` for a reference they could read and `ParseProblem` for one they
could not, so a bad entry in the middle of a file never stops the import. Nothing here
touches the database: an import is a stream of these, batched into COPY by the worker.
"""

import html
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Literal

# Guide 12.3: bounds on everything that goes into the database.
MAX_TITLE = 2_000
MAX_ABSTRACT = 50_000
MAX_FIELD = 1_000
MAX_LIST = 200
MAX_AUTHOR = 200

_TAG = re.compile(r"<[^>]{0,200}>")
_WHITESPACE = re.compile(r"[^\S\n]+")
_BLANK_LINES = re.compile(r"\n{3,}")
_NOT_WORD = re.compile(r"[^\w\s]", re.UNICODE)
_SPACES = re.compile(r"\s+")
_YEAR = re.compile(r"(1[6-9]\d{2}|20\d{2}|21\d{2})")
_DOI_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*|info:doi/)", re.IGNORECASE)
_DOI = re.compile(r"10\.\d{4,9}/\S+")
_PMID = re.compile(r"\d{1,8}")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass(frozen=True, slots=True)
class ParsedRecord:
    """One reference, in Winnow's shape, before it reaches the database."""

    title: str | None = None
    abstract: str | None = None
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    journal: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    doi: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    isbn: str | None = None
    url: str | None = None
    keywords: list[str] = field(default_factory=list)
    language: str | None = None
    publication_type: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def title_norm(self) -> str | None:
        return normalise_title(self.title)

    @property
    def doi_norm(self) -> str | None:
        return normalise_doi(self.doi)

    def is_usable(self) -> bool:
        """A reference with no title and no identifier cannot be screened or matched."""
        return bool(self.title or self.doi or self.pmid)


@dataclass(frozen=True, slots=True)
class ParseProblem:
    """A reference that could not be read, and where it was.

    `unit` says how to read `at`: text formats count lines, XML counts records, because
    an XML reader cannot map an element back to a line in the file.
    """

    at: int
    reason: str
    unit: Literal["line", "record"] = "line"

    def where(self) -> str:
        return f"{self.unit} {self.at}"


type ParseItem = ParsedRecord | ParseProblem


def clean_text(value: str | None, limit: int = MAX_FIELD) -> str | None:
    """Plain text from a field that may carry HTML or JATS mark-up: tags out, entities
    decoded, control characters dropped, whitespace collapsed, trimmed to `limit`."""
    if value is None:
        return None
    text = _TAG.sub(" ", value)
    text = html.unescape(text)
    text = _CONTROL.sub("", text)
    text = _WHITESPACE.sub(" ", text)
    text = _BLANK_LINES.sub("\n\n", text)
    text = "\n".join(line.strip() for line in text.split("\n")).strip()
    if not text:
        return None
    return text[:limit].strip()


def clean_abstract(value: str | None) -> str | None:
    """As clean_text, but paragraphs are kept (guide 8.3)."""
    if value is None:
        return None
    text = re.sub(r"</(?:p|sec|abstract)>", "\n\n", value, flags=re.IGNORECASE)
    return clean_text(text, MAX_ABSTRACT)


def normalise_title(title: str | None) -> str | None:
    """Lowercase, accent-free, punctuation-free form used to match near-identical titles."""
    text = clean_text(title, MAX_TITLE)
    if text is None:
        return None
    folded = unicodedata.normalize("NFKD", text.lower())
    folded = "".join(char for char in folded if not unicodedata.combining(char))
    folded = _NOT_WORD.sub(" ", folded)
    return _SPACES.sub(" ", folded).strip() or None


def normalise_doi(doi: str | None) -> str | None:
    """A bare DOI: no resolver prefix, lowercase, no trailing punctuation."""
    if not doi:
        return None
    text = _DOI_PREFIX.sub("", doi.strip())
    found = _DOI.search(text)
    if found is None:
        return None
    return found.group(0).rstrip(".,;)]>\"'").lower()[:MAX_FIELD] or None


def normalise_pmid(pmid: str | None) -> str | None:
    """PubMed ids are digits; exports wrap them in all sorts of decoration."""
    if not pmid:
        return None
    found = _PMID.search(pmid.replace("PMID:", " "))
    return found.group(0) if found else None


def normalise_year(value: str | int | None) -> int | None:
    """The four-digit year out of "2019 Jul 3", "c2020", "2018-2019" and friends."""
    if value is None:
        return None
    if isinstance(value, int):
        return value if 1600 <= value <= 2199 else None
    found = _YEAR.search(value)
    return int(found.group(0)) if found else None


def normalise_author(name: str) -> str | None:
    """ "Last, First" from the shapes exports use: "Smith J", "John Smith", "Smith, J."."""
    text = clean_text(name, MAX_AUTHOR)
    if text is None:
        return None
    text = text.rstrip(";,")
    if "," in text:
        last, _, rest = text.partition(",")
        return f"{last.strip()}, {rest.strip()}".rstrip(", ").strip() or None
    parts = text.split()
    if len(parts) == 1:
        return parts[0]
    # "Smith J", "Smith JA" and "Smith J.A." put the initials last; "John Smith" does not.
    initials = parts[-1].replace(".", "")
    if len(initials) <= 3 and initials.isupper():
        return f"{' '.join(parts[:-1])}, {parts[-1]}"
    if len(parts) > 3:
        # Four words or more without a comma: a body such as "World Health Organization
        # Collaborating Centre", not "Last First".
        return text
    return f"{parts[-1]}, {' '.join(parts[:-1])}"


_AUTHOR_SEPARATOR = re.compile(r";|\s+\band\b\s+")


def authors_from(values: list[str]) -> list[str]:
    """Author names, however the file lists them: one per tag (RIS), or several in one
    field separated by semicolons (Scopus) or "and" (BibTeX)."""
    seen: list[str] = []
    for value in values[:MAX_LIST]:
        for part in _AUTHOR_SEPARATOR.split(value):
            name = normalise_author(part)
            if name and name not in seen:
                seen.append(name)
        if len(seen) >= MAX_LIST:
            break
    return seen[:MAX_LIST]


def terms_from(values: list[str], commas: bool = False) -> list[str]:
    """Keywords or publication types, deduplicated.

    Semicolons and line breaks always separate terms. Commas only do when the format says
    so (BibTeX and CSV write "nurses, shift work"); MeSH headings such as "Neoplasms,
    Second Primary" carry their own commas, so RIS and MEDLINE keep them whole.
    """
    separator = r"[;,\n]" if commas else r"[;\n]"
    terms: list[str] = []
    for value in values:
        for part in re.split(separator, value):
            term = clean_text(part, MAX_FIELD)
            if term and term not in terms:
                terms.append(term)
        if len(terms) >= MAX_LIST:
            break
    return terms[:MAX_LIST]


def first(values: list[str]) -> str | None:
    return values[0] if values else None


def record_from_fields(
    fields: dict[str, list[str]], mapping: dict[str, str], *, commas_split_terms: bool = False
) -> ParsedRecord:
    """Build a record from a tag → values mapping, e.g. RIS's TI/AB/AU tags.

    `mapping` maps a source tag to one of ParsedRecord's field names; unmapped tags are
    still kept in `raw`, so nothing from the file is lost.
    """
    values: dict[str, list[str]] = {}
    for tag, items in fields.items():
        target = mapping.get(tag)
        if target:
            values.setdefault(target, []).extend(items)
    return ParsedRecord(
        title=clean_text(first(values.get("title", [])), MAX_TITLE),
        abstract=clean_abstract(" ".join(values.get("abstract", [])) or None),
        authors=authors_from(values.get("authors", [])),
        year=normalise_year(first(values.get("year", []))),
        journal=clean_text(first(values.get("journal", []))),
        volume=clean_text(first(values.get("volume", []))),
        issue=clean_text(first(values.get("issue", []))),
        pages=clean_text(first(values.get("pages", []))),
        doi=normalise_doi(first(values.get("doi", []))),
        pmid=normalise_pmid(first(values.get("pmid", []))),
        pmcid=clean_text(first(values.get("pmcid", []))),
        isbn=clean_text(first(values.get("isbn", []))),
        url=clean_text(first(values.get("url", []))),
        keywords=terms_from(values.get("keywords", []), commas_split_terms),
        language=clean_text(first(values.get("language", []))),
        publication_type=terms_from(values.get("publication_type", []), commas_split_terms),
        raw={tag: items for tag, items in fields.items() if items},
    )
