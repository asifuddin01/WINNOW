"""AI suggestions, kept for transparency (guide 8.11).

Every suggestion anyone asked for is stored with the provider, model and prompt version
that produced it, so a review can report its use of AI in the methods. A suggestion is
never a decision: nothing reads these rows to decide a record.
"""

import uuid
from typing import Any

from sqlalchemy import Float, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, UUIDPrimaryKey, pg_enum
from app.models.project import ScreeningStage
from app.models.screening import DecisionValue


class LlmSuggestion(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "llm_suggestions"
    __table_args__ = (
        # The latest suggestion for one person on one record, and the review's export.
        Index("ix_llm_suggestions_record_id_user_id_stage", "record_id", "user_id", "stage"),
        Index("ix_llm_suggestions_project_id_created_at", "project_id", "created_at"),
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
    stage: Mapped[ScreeningStage] = mapped_column(
        pg_enum(ScreeningStage, "screening_stage"), nullable=False
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[DecisionValue] = mapped_column(
        pg_enum(DecisionValue, "decision_value"), nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    # [{"criterion_id", "kind", "text", "verdict"}], the criteria as they read when asked.
    criteria: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
