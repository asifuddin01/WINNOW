"""In-app notifications (guide 8.17): conflicts to resolve, invitations, mentions in
notes, imports finished.

Each belongs to one person. `data` holds what the page shows (names, counts, a note's
opening words), never another person's decision. New conflicts in a review gather into
one unread notification per person, counted, instead of one each.
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamps, UUIDPrimaryKey


class NotificationKind(enum.StrEnum):
    CONFLICTS = "conflicts"
    INVITE = "invite"
    MENTION = "mention"
    IMPORT_FINISHED = "import_finished"
    IMPORT_FAILED = "import_failed"


class Notification(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_id_updated_at", "user_id", "updated_at"),
        # One unread "conflicts" notification per person and review, counted up.
        Index(
            "uq_notifications_unread_conflicts",
            "user_id",
            "project_id",
            unique=True,
            postgresql_where="kind = 'conflicts' AND read_at IS NULL",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
