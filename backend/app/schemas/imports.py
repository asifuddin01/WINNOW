"""Request and response bodies for imports (guide 10)."""

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models import FileFormat, ImportStatus
from app.schemas.common import LongText, Name, OptionalLongText, Title


class ImportMeta(BaseModel):
    """What a search was, recorded for PRISMA-S and the methods text (guide 8.3)."""

    source_name: Title | None = None
    database_name: Name = "Other"
    search_date: date | None = None
    search_string: OptionalLongText = None


class ConfirmImport(BaseModel):
    source_name: Title | None = None
    database_name: Name | None = None
    search_date: date | None = None
    search_string: OptionalLongText = None
    # CSV only: which column feeds which field.
    column_mapping: dict[str, str] | None = Field(default=None, max_length=200)


class RecordPreview(BaseModel):
    title: str | None
    authors: list[str]
    year: int | None
    journal: str | None
    doi: str | None
    pmid: str | None
    abstract: str | None


class ImportProblem(BaseModel):
    at: int
    unit: str
    reason: str


class ImportOut(BaseModel):
    id: uuid.UUID
    filename: str
    file_format: FileFormat
    status: ImportStatus
    source_name: str
    database_name: str
    search_date: date | None
    search_string: str | None
    size_bytes: int
    total: int
    imported: int
    problems: list[ImportProblem]
    created_at: datetime
    updated_at: datetime


class ImportPreview(BaseModel):
    """What the upload found, before anything is written to the review."""

    batch: ImportOut
    records: list[RecordPreview]
    problems: list[ImportProblem]
    # CSV only: the header and what each column looks like it holds.
    columns: list[str] = Field(default_factory=list)
    suggested_mapping: dict[str, str] = Field(default_factory=dict)
    sample_rows: list[dict[str, str]] = Field(default_factory=list)


class ImportAccepted(BaseModel):
    batch: ImportOut
    job_id: str | None


def problems_of(stored: list[dict[str, Any]]) -> list[ImportProblem]:
    return [ImportProblem.model_validate(problem) for problem in stored]


__all__ = [
    "ConfirmImport",
    "ImportAccepted",
    "ImportMeta",
    "ImportOut",
    "ImportPreview",
    "ImportProblem",
    "LongText",
    "RecordPreview",
    "problems_of",
]
