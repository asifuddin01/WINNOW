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


class ExportIn(BaseModel):
    kind: ExportKind = ExportKind.RECORDS
    # Records: csv, xlsx, ris or bibtex. A backup is always a ZIP.
    format: ExportFormat = ExportFormat.CSV
    filters: RecordFiltersIn = Field(default_factory=RecordFiltersIn)


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
