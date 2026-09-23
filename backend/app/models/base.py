"""Declarative base shared by every model, with deterministic constraint names."""

import enum
import secrets
import threading
import time
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, MetaData, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Named constraints make Alembic autogenerate and downgrades predictable.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class _Clock:
    """The last (millisecond, counter) handed out, so ids never go backwards."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last = 0

    def next(self) -> int:
        # A new millisecond starts its counter at a random point in the lower half, so the
        # counter itself does not tell how many ids came before it.
        now = (time.time_ns() // 1_000_000) << 12 | secrets.randbits(11)
        with self._lock:
            self._last = now if now > self._last else self._last + 1
            return self._last


_clock = _Clock()


def uuid7() -> uuid.UUID:
    """RFC 9562 UUIDv7: a 48-bit millisecond timestamp, a 12-bit counter, random bits.

    Time-ordered ids keep B-tree inserts at the right edge of the index. The counter
    (RFC 9562 section 6.2, method 1) makes the ids from one process strictly increasing
    even within a millisecond, so records keep the order they were read from a file in;
    if it overflows, the id borrows the next millisecond.
    """
    head = _clock.next()
    millis, counter = head >> 12, head & 0x0FFF
    rand_b = secrets.randbits(62)
    value = (millis & ((1 << 48) - 1)) << 80 | 0x7 << 76 | counter << 64 | 0b10 << 62 | rand_b
    return uuid.UUID(int=value)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def pg_enum(values: type[enum.StrEnum], name: str) -> Enum:
    """A PostgreSQL enum that stores each member's value ("title_abstract"), not its name."""
    return Enum(values, name=name, values_callable=lambda members: [m.value for m in members])


class UUIDPrimaryKey:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)


class CreatedAt:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Timestamps(CreatedAt):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
