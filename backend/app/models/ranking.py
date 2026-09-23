"""Relevance ranking: training runs and the scores they give (guide 6.1, 8.10, 9.2).

`ranking_models` has one row per training run, the latest per project and stage marked
active. The fitted model itself is not kept: every run refits from the decisions, so
there is nothing to load back (and no pickled object to trust); `artifact_key` stays
empty for that reason.

`record_scores` holds each record's score at each stage. The guide puts the score on
`records`, but a run rewrites every score in the review, and on the records table each of
those writes also rewrote the row's ten indexes (three of them GIN): 15 of the 19 seconds
a 50,000-record run took. A narrow table of its own makes the same writes a fraction of
that, and keeps the title/abstract and full-text scores apart.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKey, pg_enum
from app.models.project import ScreeningStage


class RankingModel(UUIDPrimaryKey, Base):
    __tablename__ = "ranking_models"
    __table_args__ = (
        Index(
            "ix_ranking_models_project_id_stage_trained_at",
            "project_id",
            "stage",
            "trained_at",
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE")
    )
    stage: Mapped[ScreeningStage] = mapped_column(
        pg_enum(ScreeningStage, "screening_stage"), nullable=False
    )
    trained_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    n_labeled: Mapped[int] = mapped_column(Integer, nullable=False)
    n_included: Mapped[int] = mapped_column(Integer, nullable=False)
    # auc (cross-validated, from 50 labels), scored, seconds, decisions (at training).
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    artifact_key: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class RecordScore(Base):
    __tablename__ = "record_scores"
    __table_args__ = (
        PrimaryKeyConstraint("record_id", "stage"),
        # The queue: a review's records at a stage, most likely relevant first.
        Index("ix_record_scores_project_id_stage_score", "project_id", "stage", "score"),
    )

    record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("records.id", ondelete="CASCADE")
    )
    stage: Mapped[ScreeningStage] = mapped_column(
        pg_enum(ScreeningStage, "screening_stage"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE")
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
