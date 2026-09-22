"""Projects (reviews), their members and invitations (guide 6.1, 7)."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base, CreatedAt, Timestamps, UUIDPrimaryKey, pg_enum


class ReviewType(enum.StrEnum):
    SYSTEMATIC = "systematic"
    SCOPING = "scoping"
    RAPID = "rapid"
    UMBRELLA = "umbrella"
    OTHER = "other"


class ProjectStatus(enum.StrEnum):
    SETUP = "setup"
    SCREENING = "screening"
    FULLTEXT = "fulltext"
    EXTRACTION = "extraction"
    COMPLETE = "complete"
    ARCHIVED = "archived"


class ProjectRole(enum.StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    REVIEWER = "reviewer"
    VIEWER = "viewer"


class ScreeningStage(enum.StrEnum):
    TITLE_ABSTRACT = "title_abstract"
    FULL_TEXT = "full_text"


ALL_STAGES = [stage.value for stage in ScreeningStage]


class Project(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "projects"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    review_type: Mapped[ReviewType] = mapped_column(
        pg_enum(ReviewType, "review_type"), default=ReviewType.SYSTEMATIC, nullable=False
    )
    research_question: Mapped[str | None] = mapped_column(Text)
    pico: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[ProjectStatus] = mapped_column(
        pg_enum(ProjectStatus, "project_status"), default=ProjectStatus.SETUP, nullable=False
    )
    # The shape lives in app.schemas.projects.ProjectSettings (guide 6.2).
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProjectMember(Base):
    __tablename__ = "project_members"
    __table_args__ = (
        # Exactly one owner per project; ownership moves only by transfer.
        Index(
            "uq_project_members_one_owner",
            "project_id",
            unique=True,
            postgresql_where="role = 'owner'",
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    role: Mapped[ProjectRole] = mapped_column(pg_enum(ProjectRole, "project_role"), nullable=False)
    can_resolve_conflicts: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    stages: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        default=lambda: list(ALL_STAGES),
        server_default="{title_abstract,full_text}",
    )
    # Guide 7: owners and admins who also screen stay blind unless they opt out.
    keep_blind: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ProjectInvite(UUIDPrimaryKey, CreatedAt, Base):
    """Only the SHA-256 of the invitation token is stored; the token is in one email."""

    __tablename__ = "project_invites"
    __table_args__ = (
        # One open invitation per address and project; inviting again replaces it.
        Index(
            "uq_project_invites_pending",
            "project_id",
            "email",
            unique=True,
            postgresql_where="accepted_at IS NULL",
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    role: Mapped[ProjectRole] = mapped_column(pg_enum(ProjectRole, "project_role"), nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
