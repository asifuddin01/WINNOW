"""Writes to the append-only audit log (guide 12.8), inside the caller's transaction."""

import ipaddress
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


@dataclass(frozen=True, slots=True)
class Actor:
    """Who is acting and from where, as seen by the API."""

    ip: str | None = None
    user_agent: str | None = None


def _address(ip: str | None) -> str | None:
    """A valid IP in canonical text form, or None. Text, because asyncpg's batched inserts
    accept only strings for INET."""
    try:
        return str(ipaddress.ip_address(ip)) if ip else None
    except ValueError:  # e.g. a test client's "testclient"
        return None


def record(
    db: AsyncSession,
    action: str,
    actor: Actor,
    *,
    user_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> AuditLog:
    """Stage one audit row; it commits with the change it describes, or not at all.

    Never pass passwords, tokens, secrets or record contents in `before`/`after`.
    """
    row = AuditLog(
        action=action,
        user_id=user_id,
        project_id=project_id,
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=after,
        ip=_address(actor.ip),
        user_agent=(actor.user_agent or "")[:512] or None,
    )
    db.add(row)
    return row
