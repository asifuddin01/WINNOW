"""Reading a review's audit log (guide 12.8): newest first, filtered, and as CSV (8.16).

The log also records what people decided. A reader who is blind to others' decisions
(guide 8.6) sees that someone acted, and when, but not the details of their decisions,
resolutions or assessments.
"""

import csv
import io
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, User
from app.schemas.audit import AuditEntryOut, AuditPage
from app.security.permissions import ProjectAccess
from app.services.blinding import sees_others
from app.services.errors import InvalidCursorError
from app.services.pagination import decode_cursor, encode_cursor
from app.spreadsheet import safe_cell

# Actions whose details carry a judgement about a record.
BLINDED = ("decision.", "conflict.", "rob.", "llm.", "extraction.", "bulk_decision.")
CSV_BATCH = 1_000
CSV_COLUMNS = (
    "id",
    "time",
    "action",
    "person",
    "entity_type",
    "entity_id",
    "before",
    "after",
    "ip",
    "user_agent",
)


class AuditLogService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    def _query(
        self,
        access: ProjectAccess,
        *,
        action: str | None,
        user_id: uuid.UUID | None,
        since: date | None,
        until: date | None,
    ) -> Select[tuple[AuditLog, str]]:
        statement = (
            select(AuditLog, User.name)
            .outerjoin(User, User.id == AuditLog.user_id)
            .where(AuditLog.project_id == access.project_id)
        )
        if action:
            statement = statement.where(
                (AuditLog.action == action)
                | AuditLog.action.startswith(f"{action}.", autoescape=True)
            )
        if user_id is not None:
            statement = statement.where(AuditLog.user_id == user_id)
        if since is not None:
            statement = statement.where(AuditLog.created_at >= datetime.combine(since, time(), UTC))
        if until is not None:
            end = datetime.combine(until + timedelta(days=1), time(), UTC)
            statement = statement.where(AuditLog.created_at < end)
        return statement.order_by(AuditLog.id.desc())

    async def page(
        self,
        access: ProjectAccess,
        *,
        action: str | None = None,
        user_id: uuid.UUID | None = None,
        since: date | None = None,
        until: date | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> AuditPage:
        statement = self._query(access, action=action, user_id=user_id, since=since, until=until)
        if cursor:
            try:
                (last,) = decode_cursor(cursor, 1)
                statement = statement.where(AuditLog.id < int(last))
            except ValueError as error:
                raise InvalidCursorError from error
        rows = list(await self._db.execute(statement.limit(limit + 1)))
        blind = not sees_others(access)
        items = [_out(row, name, access, blind) for row, name in rows[:limit]]
        more = len(rows) > limit
        return AuditPage(
            items=items, next_cursor=encode_cursor(str(items[-1].id)) if more and items else None
        )

    async def csv(
        self,
        access: ProjectAccess,
        *,
        action: str | None = None,
        user_id: uuid.UUID | None = None,
        since: date | None = None,
        until: date | None = None,
    ) -> AsyncIterator[str]:
        """The whole filtered log, streamed in batches."""
        blind = not sees_others(access)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(CSV_COLUMNS)
        yield buffer.getvalue()
        base = self._query(access, action=action, user_id=user_id, since=since, until=until)
        last: int | None = None
        while True:
            statement = base if last is None else base.where(AuditLog.id < last)
            rows = list(await self._db.execute(statement.limit(CSV_BATCH)))
            if not rows:
                return
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            for row, name in rows:
                entry = _out(row, name, access, blind)
                writer.writerow(
                    [
                        safe_cell(value)
                        for value in (
                            entry.id,
                            entry.at.isoformat(),
                            entry.action,
                            entry.actor,
                            entry.entity_type,
                            entry.entity_id,
                            entry.before,
                            entry.after,
                            entry.ip,
                            entry.user_agent,
                        )
                    ]
                )
            yield buffer.getvalue()
            last = rows[-1][0].id


def _out(row: AuditLog, name: str | None, access: ProjectAccess, blind: bool) -> AuditEntryOut:
    withheld = blind and row.user_id != access.user.id and row.action.startswith(BLINDED)
    return AuditEntryOut(
        id=row.id,
        at=row.created_at,
        action=row.action,
        actor=name,
        actor_id=row.user_id,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        before=None if withheld else row.before,
        after=None if withheld else row.after,
        withheld=withheld,
        ip=None if row.ip is None else str(row.ip),
        user_agent=row.user_agent,
    )
