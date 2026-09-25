"""Exports and backups (guide 8.16, 10)."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.models import ExportFormat, ExportKind, FullTextStatus, JobStatus, TitleAbstractStatus


class RecordFiltersIn(BaseModel):
    """The records table's filters: an export holds the records the table would show."""

    q: Annotated[str, Field(max_length=500)] = ""
    status: TitleAbstractStatus | None = None
    full_text: FullTextStatus | None = None
    batch: uuid.UUID | None = None
    duplicates: bool = False


class ExtractionExportIn(BaseModel):
    form_id: uuid.UUID
    # Long: one row per value (R, Stata). Wide: one row per study and extractor (RevMan).
    layout: Literal["long", "wide"] = "wide"
    # Final: the consensus, or the only extraction where there is one; all: every
    # extractor's submitted data and the consensus, each labelled.
    which: Literal["final", "all"] = "final"


class ExportIn(BaseModel):
    kind: ExportKind = ExportKind.RECORDS
    # Records: csv, xlsx, ris or bibtex. Extracted data: csv or xlsx. A backup is a ZIP.
    format: ExportFormat = ExportFormat.CSV
    filters: RecordFiltersIn = Field(default_factory=RecordFiltersIn)
    extraction: ExtractionExportIn | None = None


class ExportOut(BaseModel):
    id: uuid.UUID
    kind: ExportKind
    format: ExportFormat
    status: JobStatus
    filename: str | None
    size_bytes: int | None
    rows: int | None
    problem: str | None
    created_at: datetime
    expires_at: datetime | None


class RestoreOut(BaseModel):
    id: uuid.UUID
    filename: str
    status: JobStatus
    project_id: uuid.UUID | None
    problem: str | None
    restored: dict[str, int]
    created_at: datetime


ReadyState = Literal["queued", "running", "ready", "failed"]
