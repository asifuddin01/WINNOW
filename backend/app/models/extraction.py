"""Data extraction (guide 6.1, 8.12): forms, what each person extracted, and consensus.

A form is versioned. Its versions share a `family_id` (the first version's id); a
published version is locked, and changing it means starting the next version, so data
is always read with the form it was extracted on. Each person keeps one entry per study
and form version; with dual extraction, two entries become one consensus.
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamps, UUIDPrimaryKey, pg_enum


class EntryStatus(enum.StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    # Reconciled into a consensus by whoever resolves conflicts.
    VERIFIED = "verified"


class ExtractionForm(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "extraction_forms"
    __table_args__ = (
        UniqueConstraint("family_id", "version"),
        Index("ix_extraction_forms_project_id", "project_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # app.extraction's schema, as schema_to_json writes it.
    schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # Two people extract each study, then someone who resolves conflicts reconciles them.
    dual: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class ExtractionEntry(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "extraction_entries"
    __table_args__ = (
        UniqueConstraint("form_id", "record_id", "user_id"),
        Index("ix_extraction_entries_project_id", "project_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    form_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("extraction_forms.id", ondelete="CASCADE"), nullable=False
    )
    record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("records.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[EntryStatus] = mapped_column(
        pg_enum(EntryStatus, "extraction_entry_status"), nullable=False, default=EntryStatus.DRAFT
    )


class ExtractionConsensus(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "extraction_consensus"
    __table_args__ = (
        UniqueConstraint("form_id", "record_id"),
        Index("ix_extraction_consensus_project_id", "project_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    form_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("extraction_forms.id", ondelete="CASCADE"), nullable=False
    )
    record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("records.id", ondelete="CASCADE"), nullable=False
    )
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
