"""Which record is this PDF? Matching a file's name to the review's records (guide 8.8).

People name downloaded PDFs by DOI (`10.1016_j.kint.2020.01.001.pdf`), PubMed or PMC id,
arXiv id, first author and year (`Smith 2019 - Kidney segmentation.pdf`), or title. Each
is tried in that order; the first that points at exactly one record wins. An identifier is
"sure"; author and year or a title is "likely", and the review screen shows every match
for a person to confirm or change.
"""

import re
import unicodedata
import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Literal

By = Literal["doi", "pmcid", "pmid", "arxiv", "author_year", "title"]
Confidence = Literal["sure", "likely"]

TITLE_SIMILARITY = 0.9
MAX_CANDIDATES = 5
STOP = frozenset(
    {"a", "an", "and", "at", "by", "for", "from", "in", "into", "of", "on", "or", "the"}
    | {"to", "with", "vs", "versus", "et", "al", "pdf", "full", "text"}
)


@dataclass(frozen=True)
class RecordKeys:
    id: uuid.UUID
    title: str | None
    doi: str | None
    pmid: str | None
    pmcid: str | None
    first_author: str | None
    year: int | None


@dataclass(frozen=True)
class Match:
    record_id: uuid.UUID
    by: By
    confidence: Confidence


@dataclass(frozen=True)
class Outcome:
    match: Match | None
    # Records it could be, best first, when there was no single answer.
    candidates: tuple[uuid.UUID, ...] = field(default_factory=tuple)


def fold(text: str) -> str:
    """Lower case, accents off, anything not a letter or digit as a space."""
    decomposed = unicodedata.normalize("NFKD", text)
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", plain.lower()).strip()


def alnum(text: str) -> str:
    return fold(text).replace(" ", "")


def surname(author: str) -> str | None:
    """ "Smith, Jane A" or "Jane A Smith" → "smith"."""
    head = author.split(",", 1)[0] if "," in author else author.strip().rsplit(" ", 1)[-1]
    folded = fold(head).replace(" ", "")
    return folded or None


class Matcher:
    def __init__(self, records: Iterable[RecordKeys]) -> None:
        self._records = {record.id: record for record in records}
        self._dois: dict[str, uuid.UUID] = {}
        self._pmids: dict[str, uuid.UUID] = {}
        self._pmcids: dict[str, uuid.UUID] = {}
        self._arxiv: dict[str, uuid.UUID] = {}
        self._by_author_year: defaultdict[tuple[str, int], list[uuid.UUID]] = defaultdict(list)
        self._titles: dict[uuid.UUID, str] = {}
        for record in self._records.values():
            if record.doi:
                key = alnum(record.doi)
                self._dois[key] = record.id
                arxiv = re.search(r"arxiv\.(\d{4}\.\d{4,5})", record.doi.lower())
                if arxiv:
                    self._arxiv[arxiv.group(1)] = record.id
            if record.pmid:
                self._pmids[record.pmid.strip()] = record.id
            if record.pmcid:
                self._pmcids[record.pmcid.strip().lower()] = record.id
            if record.first_author and record.year:
                name = surname(record.first_author)
                if name:
                    self._by_author_year[(name, record.year)].append(record.id)
            if record.title:
                self._titles[record.id] = fold(record.title)

    def match(self, filename: str) -> Outcome:
        stem = re.sub(r"\.pdf$", "", filename.rsplit("/", 1)[-1], flags=re.IGNORECASE)
        lowered = stem.lower()
        squeezed = alnum(stem)

        if "10" in squeezed:
            found = {rid for key, rid in self._dois.items() if len(key) > 6 and key in squeezed}
            if len(found) == 1:
                return Outcome(Match(found.pop(), "doi", "sure"))
        pmc = re.search(r"pmc\s*[_-]?\s*(\d{5,9})", lowered)
        if pmc and f"pmc{pmc.group(1)}" in self._pmcids:
            return Outcome(Match(self._pmcids[f"pmc{pmc.group(1)}"], "pmcid", "sure"))
        pmid = re.fullmatch(r"(?:pmid[\s_-]*)?(\d{6,9})", lowered.strip())
        if pmid and pmid.group(1) in self._pmids:
            return Outcome(Match(self._pmids[pmid.group(1)], "pmid", "sure"))
        arxiv = re.search(r"(\d{4}\.\d{4,5})(v\d+)?", lowered)
        if arxiv and arxiv.group(1) in self._arxiv:
            return Outcome(Match(self._arxiv[arxiv.group(1)], "arxiv", "sure"))

        words = fold(stem).split()
        by_author = self._author_year(words)
        if len(by_author) == 1:
            return Outcome(Match(by_author[0], "author_year", "likely"))
        by_title = self._title(words)
        if by_title is not None:
            return Outcome(Match(by_title, "title", "likely"))
        return Outcome(None, tuple(by_author[:MAX_CANDIDATES]))

    def _author_year(self, words: Sequence[str]) -> list[uuid.UUID]:
        years = {int(word) for word in words if re.fullmatch(r"(19|20)\d{2}", word)}
        found: list[uuid.UUID] = []
        for word in words:
            if not word.isalpha() or len(word) < 2:
                continue
            for year in years:
                found += self._by_author_year.get((word, year), [])
        unique = list(dict.fromkeys(found))
        if len(unique) <= 1:
            return unique
        # Several papers by the same first author that year: the title words decide.
        rest = {word for word in words if word not in STOP and not word.isdigit()}
        scored = sorted(
            unique,
            key=lambda rid: -len(rest & set(self._titles.get(rid, "").split())),
        )
        best = len(rest & set(self._titles.get(scored[0], "").split()))
        runner_up = len(rest & set(self._titles.get(scored[1], "").split()))
        return [scored[0]] if best >= 2 and best > runner_up else scored

    def _title(self, words: Sequence[str]) -> uuid.UUID | None:
        meaningful = [word for word in words if word not in STOP]
        if len(meaningful) < 4:
            return None
        text = " ".join(words)
        best: tuple[float, uuid.UUID | None] = (0.0, None)
        for rid, title in self._titles.items():
            if not title:
                continue
            if set(meaningful) <= set(title.split()) and len(meaningful) >= 5:
                ratio = 1.0
            else:
                ratio = SequenceMatcher(None, text, title).quick_ratio()
                if ratio < TITLE_SIMILARITY:
                    continue
                ratio = SequenceMatcher(None, text, title).ratio()
            if ratio > best[0]:
                best = (ratio, rid)
        return best[1] if best[0] >= TITLE_SIMILARITY else None
