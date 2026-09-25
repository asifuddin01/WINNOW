"""PRISMA 2020 counts (guide 8.14, 9.4) and screening statistics (guide 8.15, 9.3)."""

import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.models import ScreeningStage

SourceName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Count = Annotated[int, Field(ge=0, le=100_000_000)]


class SourceIn(BaseModel):
    name: SourceName
    count: Count


class PrismaManualIn(BaseModel):
    """What Winnow cannot count itself: records found outside the imported databases
    (citation searching, websites, organisations) and records removed before screening
    for other reasons (e.g. marked ineligible by an automation tool)."""

    other_sources: list[SourceIn] = Field(default_factory=list, max_length=50)
    removed_other_reasons: Count = 0


class SourceOut(BaseModel):
    name: str
    count: int


class ReasonOut(BaseModel):
    reason: str
    count: int


class PrismaManualOut(BaseModel):
    other_sources: list[SourceOut]
    removed_other_reasons: int
    updated_at: datetime | None


class PrismaOut(BaseModel):
    """The flow, with where screening still has work to do: an unfinished stage makes
    the diagram a snapshot, not the review's final numbers."""

    database_sources: list[SourceOut]
    other_sources: list[SourceOut]
    records_identified: int
    duplicates_removed: int
    records_removed_other_reasons: int
    records_screened: int
    records_excluded: int
    reports_sought: int
    reports_not_retrieved: int
    reports_assessed: int
    reports_excluded: list[ReasonOut]
    reports_excluded_total: int
    studies_included: int
    # Still undecided (pending or in conflict) at each stage.
    awaiting_title_abstract: int
    awaiting_full_text: int
    manual: PrismaManualOut


class ReviewerProgress(BaseModel):
    user_id: uuid.UUID
    name: str
    mine: bool
    decided: int
    included: int
    excluded: int
    maybe: int
    # Median seconds on a record, counting every visit to it.
    median_seconds: float | None


class DayCount(BaseModel):
    day: date
    decisions: int


class PairAgreement(BaseModel):
    reviewer_a: str
    reviewer_b: str
    records: int
    percent: float | None
    kappa: float | None
    band: str | None


class Agreement(BaseModel):
    """Guide 9.3. `None` means not calculable (no overlap, or one category only)."""

    pairs: list[PairAgreement]
    # Fleiss' kappa, over the records rated by exactly `raters` reviewers, when ≥ 3.
    fleiss_kappa: float | None
    fleiss_band: str | None
    fleiss_records: int
    raters: int


class StageStats(BaseModel):
    stage: ScreeningStage
    records: int
    decided: int
    conflicts: int | None
    reviewers: list[ReviewerProgress]
    per_day: list[DayCount]
    # Only for members who may see others' decisions (guide 8.6); null otherwise.
    agreement: Agreement | None


class StatsOut(BaseModel):
    stages: list[StageStats]
    # Whether the numbers about other reviewers were left out (blind mode).
    blind: bool
