"""Request and response bodies for screening, conflicts and bulk decisions (guide 10)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models import DecisionValue, FinalDecision, NoteVisibility, ScreeningStage
from app.schemas.common import LongText, OptionalLongText
from app.schemas.fulltext import FulltextOut

QueueSort = Literal["relevance", "random", "year", "title", "added"]
# Thirty minutes: longer than anyone reads one abstract, short enough that a laptop left
# open over lunch does not count as screening time.
MAX_TIME_MS = 30 * 60 * 1000


class MyDecision(BaseModel):
    decision: DecisionValue
    reason_ids: list[uuid.UUID]
    note: str | None
    updated_at: datetime


class OtherDecision(BaseModel):
    """Someone else's decision: only ever sent to a caller who is allowed to see it."""

    user_id: uuid.UUID
    name: str
    decision: DecisionValue
    reason_ids: list[uuid.UUID]
    note: str | None
    updated_at: datetime


class NoteOut(BaseModel):
    id: uuid.UUID
    body: str
    visibility: NoteVisibility
    author: str
    mine: bool
    created_at: datetime


class ScreeningItem(BaseModel):
    """One record as the screening screen shows it (guide 10's queue item)."""

    id: uuid.UUID
    title: str | None
    authors: list[str]
    year: int | None
    journal: str | None
    volume: str | None
    issue: str | None
    pages: str | None
    doi: str | None
    pmid: str | None
    pmcid: str | None = None
    url: str | None
    abstract: str | None
    keywords: list[str]
    publication_type: list[str]
    relevance_score: float | None
    # At full text: the record's PDF, whatever its scan says (guide 8.8).
    fulltext: FulltextOut | None = None
    not_retrievable: bool = False
    my_decision: MyDecision | None
    labels: list[uuid.UUID]
    notes: list[NoteOut]
    # Always null for a blinded caller (guide 8.6).
    others: list[OtherDecision] | None


class QueuePage(BaseModel):
    """The next records for me. Fewer than asked for means the queue is empty after them;
    how many are left overall is in the progress."""

    items: list[ScreeningItem]


class Progress(BaseModel):
    stage: ScreeningStage
    screened: int  # by me
    total: int  # what I am expected to screen
    remaining: int
    included: int  # my includes, excludes and maybes
    excluded: int
    maybe: int
    # Null when the caller may not know: the count alone says someone disagreed.
    conflicts: int | None
    blind: bool
    can_resolve: bool
    assignment: Literal["all", "split"]


class DecisionIn(BaseModel):
    stage: ScreeningStage = ScreeningStage.TITLE_ABSTRACT
    decision: DecisionValue
    reason_ids: list[uuid.UUID] = Field(default_factory=list, max_length=30)
    note: OptionalLongText = None
    time_spent_ms: int = Field(default=0, ge=0)


class DecisionOut(BaseModel):
    record_id: uuid.UUID
    stage: ScreeningStage
    decision: MyDecision | None


class HistoryItem(BaseModel):
    record_id: uuid.UUID
    title: str | None
    year: int | None
    decision: DecisionValue
    reason_ids: list[uuid.UUID]
    updated_at: datetime


class HistoryPage(BaseModel):
    items: list[HistoryItem]
    next_cursor: str | None


class LabelsIn(BaseModel):
    label_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)


class NoteIn(BaseModel):
    body: LongText
    visibility: NoteVisibility = NoteVisibility.PRIVATE


class BulkDecisionIn(BaseModel):
    """Guide 8.5: an owner or admin decides many records at once, with confirmation.

    `expected` is the count the person was shown; if the filter now matches a different
    number, nothing is changed and the new count comes back.
    """

    stage: ScreeningStage = ScreeningStage.TITLE_ABSTRACT
    final_decision: FinalDecision
    q: str = Field(default="", max_length=500)
    status: Literal["pending", "included", "excluded", "maybe", "conflict"] | None = None
    batch: uuid.UUID | None = None
    record_ids: list[uuid.UUID] | None = Field(default=None, max_length=10_000)
    reason_ids: list[uuid.UUID] = Field(default_factory=list, max_length=30)
    note: OptionalLongText = None
    expected: int = Field(ge=0)


class BulkDecisionOut(BaseModel):
    decided: int


class ConflictDecision(BaseModel):
    user_id: uuid.UUID
    name: str
    decision: DecisionValue
    reason_ids: list[uuid.UUID]
    note: str | None


class ConflictOut(BaseModel):
    record_id: uuid.UUID
    title: str | None
    authors: list[str]
    year: int | None
    journal: str | None
    abstract: str | None
    doi: str | None
    decisions: list[ConflictDecision]
    notes: list[NoteOut]
    resolution: FinalDecision | None


class ConflictPage(BaseModel):
    items: list[ConflictOut]
    next_cursor: str | None
    total: int


class ResolveIn(BaseModel):
    stage: ScreeningStage = ScreeningStage.TITLE_ABSTRACT
    final_decision: FinalDecision
    reason_ids: list[uuid.UUID] = Field(default_factory=list, max_length=30)
    note: OptionalLongText = None


class DiscussIn(BaseModel):
    body: LongText
    stage: ScreeningStage = ScreeningStage.TITLE_ABSTRACT
