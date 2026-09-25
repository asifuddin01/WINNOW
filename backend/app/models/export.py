"""Exports and backups (guide 8.16), made in the worker and downloaded when ready.

An export belongs to the person who asked for it: what it holds depends on what they may
see (blind mode), so only they download it. Files expire after a day.
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamps, UUIDPrimaryKey, pg_enum


class ExportKind(enum.StrEnum):
    RECORDS = "records"
    BACKUP = "backup"


class ExportFormat(enum.StrEnum):
    CSV = "csv"
    XLSX = "xlsx"
    RIS = "ris"
    BIBTEX = "bibtex"
    ZIP = "zip"


class JobStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"


class ExportJob(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "export_jobs"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[ExportKind] = mapped_column(pg_enum(ExportKind, "export_kind"), nullable=False)
    format: Mapped[ExportFormat] = mapped_column(
        pg_enum(ExportFormat, "export_format"), nullable=False
    )
    filters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[JobStatus] = mapped_column(
        pg_enum(JobStatus, "job_status"), nullable=False, default=JobStatus.QUEUED
    )
    file_key: Mapped[str | None] = mapped_column(Text)
    filename: Mapped[str | None] = mapped_column(Text)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    rows: Mapped[int | None] = mapped_column(Integer)
    problem: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RestoreJob(UUIDPrimaryKey, Timestamps, Base):
    """A backup being turned into a new review, owned by whoever uploaded it."""

    __tablename__ = "restore_jobs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    zip_key: Mapped[str | None] = mapped_column(Text)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        pg_enum(JobStatus, "job_status"), nullable=False, default=JobStatus.QUEUED
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL")
    )
    problem: Mapped[str | None] = mapped_column(Text)
    # What was restored: counts per kind of row, for the person to check.
    restored: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
