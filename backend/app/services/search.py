"""The search box's syntax (guide 8.9).

    sleep quality "night shift" -paediatric author:smith year:2018..2024 journal:BMJ

Quoted phrases, -exclusions and bare words go to PostgreSQL's own web search parser;
`field:value` terms are pulled out first and become ordinary WHERE conditions, because a
text-search query cannot express "the year is between these two".
"""

import re
from dataclasses import dataclass, field

MAX_QUERY = 500
MAX_TERMS = 20
_TOKEN = re.compile(r'(-?)(\w+):("[^"]{0,200}"|\S{0,200})|("[^"]{0,200}")|(\S+)')
_YEAR_RANGE = re.compile(r"^(\d{4})?\.\.(\d{4})?$")
_DOI = re.compile(r"^10\.\d{4,9}/\S+$")


@dataclass(frozen=True, slots=True)
class Query:
    """A search, split into the part PostgreSQL's text search handles and the rest."""

    text: str = ""
    authors: list[str] = field(default_factory=list)
    journals: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    year_from: int | None = None
    year_to: int | None = None
    doi: str | None = None
    pmid: str | None = None
    labels: list[str] = field(default_factory=list)
    types: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not any(
            (
                self.text,
                self.authors,
                self.journals,
                self.keywords,
                self.year_from,
                self.year_to,
                self.doi,
                self.pmid,
                self.labels,
                self.types,
            )
        )


def parse_query(raw: str) -> Query:
    """Read the search box. Anything unrecognised stays as ordinary search words."""
    text_parts: list[str] = []
    authors: list[str] = []
    journals: list[str] = []
    keywords: list[str] = []
    year_from: int | None = None
    year_to: int | None = None
    doi: str | None = None
    pmid: str | None = None
    labels: list[str] = []
    types: list[str] = []

    for match in _TOKEN.finditer((raw or "")[:MAX_QUERY]):
        negate, field_name, value, phrase, word = match.groups()
        if field_name:
            clean = (value or "").strip('"')
            if not clean:
                continue
            name = field_name.lower()
            if name in {"author", "au"} and len(authors) < MAX_TERMS:
                authors.append(clean)
            elif name in {"journal", "source", "jo"} and len(journals) < MAX_TERMS:
                journals.append(clean)
            elif name in {"keyword", "kw"} and len(keywords) < MAX_TERMS:
                keywords.append(clean)
            elif name == "year":
                year_from, year_to = _years(clean, year_from, year_to)
            elif name == "doi":
                doi = clean.lower()
            elif name == "pmid" and clean.isdigit():
                pmid = clean
            elif name == "label" and len(labels) < MAX_TERMS:
                labels.append(clean)
            elif name in {"type", "pt"} and len(types) < MAX_TERMS:
                types.append(clean)
            else:  # an unknown field is just words
                text_parts.append(f"{negate}{field_name}:{clean}")
            continue
        token = phrase or word or ""
        if not token:
            continue
        if _DOI.match(token):
            doi = token.lower()
        elif token.isdigit() and 6 <= len(token) <= 8:
            pmid = token
        elif len(text_parts) < MAX_TERMS:
            text_parts.append(token)

    return Query(
        text=" ".join(text_parts).strip(),
        authors=authors,
        journals=journals,
        keywords=keywords,
        year_from=year_from,
        year_to=year_to,
        doi=doi,
        pmid=pmid,
        labels=labels,
        types=types,
    )


def _years(
    value: str, current_from: int | None, current_to: int | None
) -> tuple[int | None, int | None]:
    ranged = _YEAR_RANGE.match(value)
    if ranged:
        start, end = ranged.groups()
        return (int(start) if start else current_from, int(end) if end else current_to)
    if value.isdigit() and len(value) == 4:
        return int(value), int(value)
    return current_from, current_to
