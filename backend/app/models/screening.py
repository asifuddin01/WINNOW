"""Screening: decisions, labels on records, notes, and final resolutions (guide 6.1).

A record's `ta_final` / `ft_final` are never written anywhere but
`app.services.status.recompute_record_status`, from the rows in these tables (guide 6.4).
"""

import enum
import uuid

from sqlalchemy import ForeignKey, Index, Integer, PrimaryKeyConstraint, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamps, UUIDPrimaryKey, pg_enum
from app.models.project import ScreeningStage


class DecisionValue(enum.StrEnum):
    INCLUDE = "include"
    EXCLUDE = "exclude"
    MAYBE = "maybe"


class FinalDecision(enum.StrEnum):
    INCLUDE = "include"
    EXCLUDE = "exclude"


class NoteVisibility(enum.StrEnum):
    PRIVATE = "private"  # only its author
    TEAM = "team"  # every member of the review


class ResolutionSource(enum.StrEnum):
    CONFLICT = "conflict"  # someone settled a disagreement (guide 8.7)
    BULK = "bulk"  # an owner or admin decided many records at once (guide 8.5)


def _stage_column() -> Mapped[ScreeningStage]:
    return mapped_column(pg_enum(ScreeningStage, "screening_stage"), nullable=False)


def _uuid_array() -> Mapped[list[uuid.UUID]]:
    return mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list, server_default="{}"
    )


class Decision(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "decisions"
    __table_args__ = (
        UniqueConstraint("record_id", "user_id", "stage"),
        # Guide 6.3: a reviewer's progress and queue, and a record's decisions.
        Index("ix_decisions_project_id_stage_user_id", "project_id", "stage", "user_id"),
        Index("ix_decisions_record_id_stage", "record_id", "stage"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE")
    )
    record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("records.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    stage: Mapped[ScreeningStage] = _stage_column()
    decision: Mapped[DecisionValue] = mapped_column(
        pg_enum(DecisionValue, "decision_value"), nullable=False
    )
    reason_ids: Mapped[list[uuid.UUID]] = _uuid_array()
    note: Mapped[str | None] = mapped_column(Text)
    # Guide 8.5: time on the record, paused while the tab is hidden, summed over visits.
    time_spent_ms: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class RecordLabel(Base):
    __tablename__ = "record_labels"
    __table_args__ = (
        PrimaryKeyConstraint("record_id", "label_id", "user_id"),
        Index("ix_record_labels_label_id", "label_id"),
    )

    record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("records.id", ondelete="CASCADE")
    )
    label_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("labels.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )


class Note(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "notes"
    __table_args__ = (Index("ix_notes_record_id", "record_id"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE")
    )
    record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("records.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[NoteVisibility] = mapped_column(
        pg_enum(NoteVisibility, "note_visibility"), nullable=False
    )


class ConflictResolution(UUIDPrimaryKey, Timestamps, Base):
    """The final word on a record at one stage, overriding the reviewers (guide 6.4 rule 1)."""

    __tablename__ = "conflict_resolutions"
    __table_args__ = (
        UniqueConstraint("record_id", "stage"),
        Index("ix_conflict_resolutions_project_id_stage", "project_id", "stage"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE")
    )
    record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("records.id", ondelete="CASCADE")
    )
    stage: Mapped[ScreeningStage] = _stage_column()
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    final_decision: Mapped[FinalDecision] = mapped_column(
        pg_enum(FinalDecision, "final_decision"), nullable=False
    )
    reason_ids: Mapped[list[uuid.UUID]] = _uuid_array()
    note: Mapped[str | None] = mapped_column(Text)
    source: Mapped[ResolutionSource] = mapped_column(
        pg_enum(ResolutionSource, "resolution_source"),
        default=ResolutionSource.CONFLICT,
        server_default="conflict",
    )
