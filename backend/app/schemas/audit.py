"""The review's audit log, as its owners and admins read it (guide 12.8, 8.16)."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditEntryOut(BaseModel):
    id: int
    at: datetime
    action: str
    actor: str | None
    actor_id: uuid.UUID | None
    entity_type: str | None
    entity_id: uuid.UUID | None
    # Withheld (null) for other people's decisions while the reader is blind (guide 8.6).
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    withheld: bool
    ip: str | None
    user_agent: str | None


class AuditPage(BaseModel):
    items: list[AuditEntryOut]
    next_cursor: str | None
