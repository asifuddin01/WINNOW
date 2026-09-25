"""In-app notifications (guide 8.17) and the optional daily email digest.

Other services call `notify` inside their own transaction, so a notification exists only
if what it announces does. A person sees their notifications from reviews they still
belong to (and those about no review), newest activity first.
"""

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Notification,
    NotificationKind,
    ProjectMember,
    ProjectRole,
    User,
)
from app.schemas.notifications import NotificationOut, NotificationPage, NotificationSettings
from app.services.errors import InvalidCursorError, NotFoundError
from app.services.pagination import decode_cursor, encode_cursor

PAGE = 20
NOTE_EXCERPT = 140


async def notify(
    db: AsyncSession,
    user_ids: list[uuid.UUID],
    kind: NotificationKind,
    *,
    project_id: uuid.UUID | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    """Add a notification for each person; not committed."""
    people = list(dict.fromkeys(user_ids))
    if not people:
        return
    if kind is NotificationKind.CONFLICTS:
        # One unread notice per person and review, counting the conflicts as they come.
        statement = insert(Notification).values(
            [
                {
                    "user_id": user_id,
                    "project_id": project_id,
                    "kind": kind.value,
                    "data": data or {},
                }
                for user_id in people
            ]
        )
        await db.execute(
            statement.on_conflict_do_update(
                index_elements=[Notification.user_id, Notification.project_id],
                index_where=(Notification.kind == NotificationKind.CONFLICTS.value)
                & Notification.read_at.is_(None),
                set_={"count": Notification.count + 1, "updated_at": func.now()},
            )
        )
        return
    db.add_all(
        Notification(user_id=user_id, project_id=project_id, kind=kind.value, data=data or {})
        for user_id in people
    )


async def resolvers(db: AsyncSession, project_id: uuid.UUID) -> list[uuid.UUID]:
    """Who may resolve conflicts in the review: owners, admins and trusted reviewers."""
    return list(
        await db.scalars(
            select(ProjectMember.user_id).where(
                ProjectMember.project_id == project_id,
                or_(
                    ProjectMember.role.in_([ProjectRole.OWNER, ProjectRole.ADMIN]),
                    ProjectMember.can_resolve_conflicts.is_(True),
                ),
            )
        )
    )


def excerpt(text: str) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= NOTE_EXCERPT else flat[: NOTE_EXCERPT - 1] + "…"


def mentioned(body: str, members: list[tuple[uuid.UUID, str]]) -> list[uuid.UUID]:
    """Members named as "@Name" in a note, however the name is capitalised."""
    folded = body.casefold()
    return [
        user_id
        for user_id, name in members
        if name.strip() and f"@{name.strip().casefold()}" in folded
    ]


class NotificationService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    def _mine(self, user: User) -> list[Any]:
        still_member = select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)
        return [
            Notification.user_id == user.id,
            or_(Notification.project_id.is_(None), Notification.project_id.in_(still_member)),
        ]

    async def page(self, user: User, cursor: str | None, limit: int = PAGE) -> NotificationPage:
        statement = (
            select(Notification)
            .where(*self._mine(user))
            .order_by(Notification.updated_at.desc(), Notification.id.desc())
            .limit(limit + 1)
        )
        if cursor:
            stamp, last_id = decode_cursor(cursor, 2)
            try:
                at, last = datetime.fromisoformat(stamp), uuid.UUID(last_id)
            except ValueError:
                raise InvalidCursorError from None
            statement = statement.where(
                (Notification.updated_at < at)
                | ((Notification.updated_at == at) & (Notification.id < last))
            )
        rows = list(await self._db.scalars(statement))
        more = len(rows) > limit
        rows = rows[:limit]
        return NotificationPage(
            items=[_out(row) for row in rows],
            next_cursor=encode_cursor(rows[-1].updated_at.isoformat(), str(rows[-1].id))
            if more
            else None,
            unread=await self.unread(user),
        )

    async def unread(self, user: User) -> int:
        return (
            await self._db.scalar(
                select(func.count())
                .select_from(Notification)
                .where(*self._mine(user), Notification.read_at.is_(None))
            )
            or 0
        )

    async def mark_read(self, user: User, notification_id: uuid.UUID) -> None:
        done = await self._db.execute(
            update(Notification)
            .where(Notification.id == notification_id, Notification.user_id == user.id)
            .values(read_at=func.coalesce(Notification.read_at, func.now()))
            .returning(Notification.id)
        )
        if done.first() is None:
            raise NotFoundError
        await self._db.commit()

    async def mark_all_read(self, user: User) -> None:
        await self._db.execute(
            update(Notification)
            .where(Notification.user_id == user.id, Notification.read_at.is_(None))
            .values(read_at=func.now())
        )
        await self._db.commit()

    def settings(self, user: User) -> NotificationSettings:
        return NotificationSettings(email_digest=bool(user.preferences.get("email_digest", False)))

    async def update_settings(self, user: User, body: NotificationSettings) -> NotificationSettings:
        user.preferences = {**user.preferences, "email_digest": body.email_digest}
        await self._db.commit()
        return self.settings(user)


def _out(row: Notification) -> NotificationOut:
    return NotificationOut(
        id=row.id,
        kind=NotificationKind(row.kind),
        project_id=row.project_id,
        count=row.count,
        data=row.data,
        read=row.read_at is not None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def digests_due(db: AsyncSession, now: datetime) -> list[tuple[User, list[Notification]]]:
    """People who asked for a daily digest and have unread news from the last day."""
    since = now - timedelta(days=1)
    people = list(
        await db.scalars(
            select(User).where(
                User.deleted_at.is_(None),
                User.email_verified_at.is_not(None),
                User.preferences["email_digest"].astext == "true",
            )
        )
    )
    due = []
    for person in people:
        sent = person.preferences.get("digest_sent_at")
        if sent and datetime.fromisoformat(sent) > now - timedelta(hours=23):
            continue
        news = list(
            await db.scalars(
                select(Notification)
                .where(
                    Notification.user_id == person.id,
                    Notification.read_at.is_(None),
                    Notification.updated_at >= since,
                )
                .order_by(Notification.updated_at.desc())
                .limit(50)
            )
        )
        if news:
            due.append((person, news))
    return due


def digest_line(row: Notification) -> str:
    """One notification in words, for the email."""
    data = row.data
    review = data.get("project_title", "a review")
    who = data.get("by", "Someone")
    what = data.get("filename", "a file")
    if row.kind == NotificationKind.CONFLICTS:
        conflicts = "conflict" if row.count == 1 else "conflicts"
        return f"{row.count} new {conflicts} to resolve in {review}."
    if row.kind == NotificationKind.INVITE:
        return f"{who} invited you to {review}. The invitation email has the link."
    if row.kind == NotificationKind.MENTION:
        return f"{who} mentioned you in a note in {review}: “{data.get('excerpt', '')}”"
    if row.kind == NotificationKind.IMPORT_FINISHED:
        records = f"{data.get('imported', 0):,} records"
        return f"Your import of {what} into {review} finished: {records}."
    if row.kind == NotificationKind.IMPORT_FAILED:
        return f"Your import of {what} into {review} failed."
    return "Something happened in Winnow."
