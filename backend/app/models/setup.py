"""What a project screens against: criteria, keyword groups, exclusion reasons and labels
(guide 6.1). Each row belongs to one project; keywords belong to it through their group."""

import enum
import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, Timestamps, UUIDPrimaryKey, pg_enum


class CriterionKind(enum.StrEnum):
    INCLUSION = "inclusion"
    EXCLUSION = "exclusion"


class KeywordKind(enum.StrEnum):
    INCLUDE = "include"
    EXCLUDE = "exclude"
    NEUTRAL = "neutral"


class ReasonStage(enum.StrEnum):
    TITLE_ABSTRACT = "title_abstract"
    FULL_TEXT = "full_text"
    BOTH = "both"


def _project_fk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )


class Criterion(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "criteria"

    project_id: Mapped[uuid.UUID] = _project_fk()
    kind: Mapped[CriterionKind] = mapped_column(
        pg_enum(CriterionKind, "criterion_kind"), nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class KeywordGroup(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "keyword_groups"

    project_id: Mapped[uuid.UUID] = _project_fk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    color: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[KeywordKind] = mapped_column(pg_enum(KeywordKind, "keyword_kind"), nullable=False)


class Keyword(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "keywords"
    __table_args__ = (UniqueConstraint("group_id", "term"),)

    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("keyword_groups.id", ondelete="CASCADE"), index=True
    )
    term: Mapped[str] = mapped_column(CITEXT, nullable=False)
    is_regex: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    whole_word: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class ExclusionReason(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "exclusion_reasons"
    __table_args__ = (UniqueConstraint("project_id", "label"),)

    project_id: Mapped[uuid.UUID] = _project_fk()
    label: Mapped[str] = mapped_column(CITEXT, nullable=False)
    stage: Mapped[ReasonStage] = mapped_column(pg_enum(ReasonStage, "reason_stage"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class Label(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "labels"
    __table_args__ = (UniqueConstraint("project_id", "name"),)

    project_id: Mapped[uuid.UUID] = _project_fk()
    name: Mapped[str] = mapped_column(CITEXT, nullable=False)
    color: Mapped[str] = mapped_column(Text, nullable=False)
