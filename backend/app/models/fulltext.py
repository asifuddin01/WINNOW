"""Full texts: PDFs, their scanning, annotations, ZIP uploads, and records whose full text
could not be found (guide 6.1, 8.8, 12.4).

A PDF becomes available only once ClamAV has called it clean (`scan_status`). An infected
file is moved under `quarantine/` and never served. With no scanner (`make local`) files are
kept as `skipped`, and the app says they were not scanned.
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, Timestamps, UUIDPrimaryKey, pg_enum


class ScanStatus(enum.StrEnum):
    PENDING = "pending"  # waiting for ClamAV
    CLEAN = "clean"
    INFECTED = "infected"  # quarantined, never served
    ERROR = "error"  # the scanner failed; tried again later
    SKIPPED = "skipped"  # this instance runs without a scanner


class FulltextSource(enum.StrEnum):
    UPLOAD = "upload"
    ZIP = "zip"
    OPEN_ACCESS = "open_access"


class BatchStatus(enum.StrEnum):
    CHECKING = "checking"  # the worker is opening and matching the ZIP
    READY = "ready"  # matched; waiting for someone to confirm
    APPLIED = "applied"
    REJECTED = "rejected"  # not a ZIP we accept (a bomb, too many files, bad names)
    FAILED = "failed"


def _project() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))


def _user(nullable: bool = False) -> Mapped[Any]:
    return mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL" if nullable else "CASCADE"),
        nullable=nullable,
    )


class Fulltext(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "fulltexts"
    __table_args__ = (Index("ix_fulltexts_project_id", "project_id"),)

    project_id: Mapped[uuid.UUID] = _project()
    record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("records.id", ondelete="CASCADE"), unique=True
    )
    file_key: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    mime: Mapped[str] = mapped_column(Text, nullable=False, default="application/pdf")
    scan_status: Mapped[ScanStatus] = mapped_column(
        pg_enum(ScanStatus, "scan_status"), nullable=False, default=ScanStatus.PENDING
    )
    scan_signature: Mapped[str | None] = mapped_column(Text)
    scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    text_extracted: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[FulltextSource] = mapped_column(
        pg_enum(FulltextSource, "fulltext_source"), nullable=False
    )
    source_url: Mapped[str | None] = mapped_column(Text)
    uploaded_by: Mapped[uuid.UUID | None] = _user(nullable=True)


class PdfAnnotation(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "pdf_annotations"
    __table_args__ = (Index("ix_pdf_annotations_fulltext_id", "fulltext_id"),)

    fulltext_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fulltexts.id", ondelete="CASCADE")
    )
    project_id: Mapped[uuid.UUID] = _project()
    user_id: Mapped[uuid.UUID] = _user()
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    # [[x, y, width, height], ...] as fractions of the page, so zoom never moves them.
    rects: Mapped[list[list[float]]] = mapped_column(JSONB, nullable=False)
    color: Mapped[str] = mapped_column(Text, nullable=False)
    quote: Mapped[str | None] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)


class FulltextBatch(UUIDPrimaryKey, Timestamps, Base):
    """One ZIP of PDFs, matched to records and waiting for someone to confirm."""

    __tablename__ = "fulltext_batches"
    __table_args__ = (Index("ix_fulltext_batches_project_id", "project_id"),)

    project_id: Mapped[uuid.UUID] = _project()
    zip_key: Mapped[str | None] = mapped_column(Text)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[BatchStatus] = mapped_column(
        pg_enum(BatchStatus, "fulltext_batch_status"),
        nullable=False,
        default=BatchStatus.CHECKING,
    )
    # [{"index", "name", "size", "key", "match": {...} | null, "candidates": [...]}]
    entries: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    problem: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = _user(nullable=True)


class UnretrievableRecord(CreatedAt, Base):
    """Guide 8.8: the full text could not be found; PRISMA counts it as not retrieved."""

    __tablename__ = "unretrievable_records"

    record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("records.id", ondelete="CASCADE"), primary_key=True
    )
    project_id: Mapped[uuid.UUID] = _project()
    marked_by: Mapped[uuid.UUID | None] = _user(nullable=True)
    note: Mapped[str | None] = mapped_column(Text)
