"""Risk-of-bias assessments (guide 6.1, 8.13).

One per record, person and tool. The tool's version and variant are stored with it, so
a later edition of a tool never reinterprets an old assessment; judgements are kept per
domain and per judgement axis (QUADAS-2 judges risk and applicability separately).
"""

import enum
import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamps, UUIDPrimaryKey, pg_enum


class RobStatus(enum.StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"


class RobAssessment(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "rob_assessments"
    __table_args__ = (
        UniqueConstraint("record_id", "user_id", "tool_key"),
        Index("ix_rob_assessments_project_id_tool_key", "project_id", "tool_key"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("records.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    tool_key: Mapped[str] = mapped_column(Text, nullable=False)
    tool_version: Mapped[str] = mapped_column(Text, nullable=False)
    variant_key: Mapped[str] = mapped_column(Text, nullable=False)
    # {domain: {question: answer}}
    answers: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # {domain: {axis: judgement}}
    judgements: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # {domain: text}: why the judgement was made.
    support: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    overall: Mapped[str | None] = mapped_column(Text)
    status: Mapped[RobStatus] = mapped_column(
        pg_enum(RobStatus, "rob_status"), nullable=False, default=RobStatus.DRAFT
    )
    # The assessment the review's plots use for this record and tool, when several
    # people assessed it (set by an owner or admin).
    final: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
