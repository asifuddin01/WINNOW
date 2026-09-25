"""In-app notifications (guide 8.17)."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models import NotificationKind


class NotificationOut(BaseModel):
    id: uuid.UUID
    kind: NotificationKind
    project_id: uuid.UUID | None
    # How many of it (conflicts gather into one notice).
    count: int
    # What the page shows: the review's title, who did it, a note's opening words.
    data: dict[str, Any]
    read: bool
    created_at: datetime
    updated_at: datetime


class NotificationPage(BaseModel):
    items: list[NotificationOut]
    next_cursor: str | None
    unread: int


class UnreadCount(BaseModel):
    unread: int


class NotificationSettings(BaseModel):
    # A daily email of what is unread; off by default (guide 8.17).
    email_digest: bool = False
