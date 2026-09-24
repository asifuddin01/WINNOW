"""Full texts (guide 8.8): a record's PDF, its links, annotations, open-access finds, and
ZIP uploads with their matching."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models import BatchStatus, FulltextSource, ScanStatus
from app.schemas.common import OptionalLongText


class FulltextOut(BaseModel):
    id: uuid.UUID
    record_id: uuid.UUID
    filename: str
    size_bytes: int
    scan_status: ScanStatus
    page_count: int | None
    source: FulltextSource
    source_url: str | None
    created_at: datetime


class RecordFulltext(BaseModel):
    """What there is for a record at full text: a PDF, or a note that none could be found."""

    fulltext: FulltextOut | None
    not_retrievable: bool
    not_retrievable_note: str | None = None


class SignedLink(BaseModel):
    """A link to the PDF that works for five minutes, for the person who asked (guide 10)."""

    url: str
    expires_in: int


class UnretrievableIn(BaseModel):
    note: OptionalLongText = None


class AnnotationIn(BaseModel):
    page: int = Field(ge=1, le=100_000)
    # [x, y, width, height] as fractions of the page.
    rects: list[list[float]] = Field(min_length=1, max_length=200)
    color: Literal["yellow", "green", "blue", "pink"] = "yellow"
    quote: str | None = Field(default=None, max_length=5_000)
    comment: OptionalLongText = None


class AnnotationPatch(BaseModel):
    color: Literal["yellow", "green", "blue", "pink"] | None = None
    comment: OptionalLongText = None


class AnnotationOut(BaseModel):
    id: uuid.UUID
    page: int
    rects: list[list[float]]
    color: str
    quote: str | None
    comment: str | None
    author: str
    mine: bool
    created_at: datetime


class OpenAccessCandidate(BaseModel):
    id: str
    source: Literal["unpaywall", "pmc"]
    host: str
    version: str | None
    license: str | None


class OpenAccessFinds(BaseModel):
    candidates: list[OpenAccessCandidate]
    # Why nothing could be looked up, when nothing could: no DOI or PMCID, no Unpaywall
    # email on this instance, or the finder switched off.
    note: str | None = None


class FetchIn(BaseModel):
    candidate: str = Field(min_length=1, max_length=64)


class MatchOut(BaseModel):
    record_id: uuid.UUID
    title: str | None
    year: int | None
    by: Literal["doi", "pmcid", "pmid", "arxiv", "author_year", "title"] | None = None
    confidence: Literal["sure", "likely"] | None = None
    has_fulltext: bool = False


class BatchEntryOut(BaseModel):
    index: int
    name: str
    size: int
    skip: Literal["not_pdf", "too_large", "encrypted", "system"] | None
    match: MatchOut | None
    candidates: list[MatchOut]


class BatchOut(BaseModel):
    id: uuid.UUID
    filename: str
    size_bytes: int
    status: BatchStatus
    problem: str | None
    entries: list[BatchEntryOut]
    created_at: datetime


class BatchConfirm(BaseModel):
    # Entry index → the record it is the full text of; entries left out are not kept.
    choices: dict[int, uuid.UUID] = Field(max_length=1_000)
    # Replace a PDF a record already has; otherwise that entry is skipped.
    replace: bool = False


class BatchApplied(BaseModel):
    attached: int
    skipped: int


class FulltextRecord(BaseModel):
    """A record at full text and where its PDF stands; no one's decisions (guide 8.6)."""

    id: uuid.UUID
    title: str | None
    first_author: str | None
    year: int | None
    journal: str | None
    doi: str | None
    pmid: str | None
    pmcid: str | None
    fulltext: FulltextOut | None
    not_retrievable: bool


class FulltextSummary(BaseModel):
    """The full-text stage at a glance: how many records have their PDF."""

    records: int
    with_pdf: int
    scanning: int
    quarantined: int
    missing: int
    not_retrievable: int
    scanner: bool
    open_access: bool
