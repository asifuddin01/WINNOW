"""Append-only record of security-relevant actions (guide 12.8)."""

import uuid
from ipaddress import IPv4Address, IPv6Address
from typing import Any

from sqlalchemy import BigInteger, Index, Text
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt


class AuditLog(CreatedAt, Base):
    """Rows are only ever inserted. A database trigger rejects UPDATE, DELETE and TRUNCATE,
    so not even the application's own role can rewrite history."""

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_project_id_created_at", "project_id", "created_at"),
        Index("ix_audit_log_user_id_created_at", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(Text)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Written as text, read back by asyncpg as an ipaddress object.
    ip: Mapped[IPv4Address | IPv6Address | str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
