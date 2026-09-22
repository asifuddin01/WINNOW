"""Request and response bodies for records (guide 10)."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from app.models import FullTextStatus, TitleAbstractStatus

Sort = Literal["added", "oldest", "year", "year_asc", "title", "relevance"]


class RecordOut(BaseModel):
    """A row in the records table; the detail view adds the rest."""

    id: uuid.UUID
    title: str | None
    authors: list[str]
    year: int | None
    journal: str | None
    doi: str | None
    pmid: str | None
    ta_final: TitleAbstractStatus
    ft_final: FullTextStatus
    is_duplicate: bool
    relevance_score: float | None
    import_batch_id: uuid.UUID | None
    created_at: datetime


class RecordDetail(RecordOut):
    abstract: str | None
    volume: str | None
    issue: str | None
    pages: str | None
    pmcid: str | None
    isbn: str | None
    url: str | None
    keywords: list[str]
    language: str | None
    publication_type: list[str]
    duplicate_of: uuid.UUID | None
    raw: dict[str, Any]
    source: str | None


class RecordPage(BaseModel):
    items: list[RecordOut]
    next_cursor: str | None
    # How many match the current filters, up to a ceiling: exact counts on 100k rows are
    # slow, and "10,000+" is as useful as the number itself.
    total: int
    total_is_exact: bool


class Count(BaseModel):
    value: str
    label: str
    count: int


class RecordFacets(BaseModel):
    """Counts for the filter panel (guide 10)."""

    title_abstract: list[Count]
    full_text: list[Count]
    years: list[Count]
    imports: list[Count]
    duplicates: int
    total: int
