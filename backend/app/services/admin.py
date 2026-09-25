"""The instance administrator's panel (guide 8.18): people, live settings, health.

Everything here acts on the instance, not a review, so it is audited without one. An
administrator cannot disable their own account (someone must be left to enable it).
"""

import asyncio
import json
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from redis.asyncio import Redis
from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.config import Settings
from app.email import messages
from app.email.mailer import Mailer
from app.llm.providers import is_configured as llm_configured
from app.models import Project, ProjectMember, Record, User
from app.schemas.admin import (
    AdminUserOut,
    AdminUserPage,
    DiskHealth,
    HealthOut,
    InstanceSettingsOut,
    InstanceSettingsPatch,
    LastBackup,
    QueueHealth,
    Source,
)
from app.security.sessions import SessionStore
from app.services import audit
from app.services.audit import Actor
from app.services.errors import ConflictError, InvalidCursorError, NotFoundError
from app.services.instance import REGISTRATION, UNPAYWALL_EMAIL, store, stored
from app.services.pagination import decode_cursor, encode_cursor

ARQ_QUEUE = "arq:queue"
ARQ_HEALTH = "arq:queue:health-check"
# Written by `make backup` (scripts/backup.sh) after each successful backup.
LAST_BACKUP_KEY = "winnow:last-backup"


class AdminService:
    def __init__(
        self,
        db: AsyncSession,
        sessions: SessionStore,
        redis: Redis,
        mailer: Mailer,
        settings: Settings,
    ) -> None:
        self._db = db
        self._sessions = sessions
        self._redis = redis
        self._mailer = mailer
        self._settings = settings

    # --- People -------------------------------------------------------------------

    async def users(self, query: str, cursor: str | None, limit: int) -> AdminUserPage:
        scope: list[ColumnElement[bool]] = [User.deleted_at.is_(None)]
        if query.strip():
            pattern = f"%{query.strip()}%"
            scope.append(or_(User.email.ilike(pattern), User.name.ilike(pattern)))
        total = await self._db.scalar(select(func.count()).select_from(User).where(*scope)) or 0
        reviews = (
            select(ProjectMember.user_id, func.count().label("reviews"))
            .join(Project, Project.id == ProjectMember.project_id)
            .where(Project.deleted_at.is_(None))
            .group_by(ProjectMember.user_id)
            .subquery()
        )
        statement = (
            select(User, func.coalesce(reviews.c.reviews, 0))
            .outerjoin(reviews, reviews.c.user_id == User.id)
            .where(*scope)
            .order_by(User.created_at.desc(), User.id.desc())
            .limit(limit + 1)
        )
        if cursor:
            stamp, last = decode_cursor(cursor, 2)
            try:
                at, last_id = datetime.fromisoformat(stamp), uuid.UUID(last)
            except ValueError:
                raise InvalidCursorError from None
            statement = statement.where(
                (User.created_at < at) | ((User.created_at == at) & (User.id < last_id))
            )
        rows = (await self._db.execute(statement)).all()
        more = len(rows) > limit
        rows = rows[:limit]
        return AdminUserPage(
            items=[_user_out(user, count) for user, count in rows],
            next_cursor=(
                encode_cursor(rows[-1][0].created_at.isoformat(), str(rows[-1][0].id))
                if more
                else None
            ),
            total=total,
        )

    async def _user(self, user_id: uuid.UUID) -> User:
        user = await self._db.get(User, user_id)
        if user is None or user.deleted_at is not None:
            raise NotFoundError("No such account on this Winnow.")
        return user

    async def disable(self, admin: User, user_id: uuid.UUID, actor: Actor) -> AdminUserOut:
        if user_id == admin.id:
            raise ConflictError("You cannot disable your own account.")
        user = await self._user(user_id)
        if user.disabled_at is None:
            user.disabled_at = datetime.now(UTC)
            self._audit(admin, actor, "admin.user_disabled", user)
            await self._db.commit()
        await self._sessions.delete_all(user.id)
        return await self._one(user)

    async def enable(self, admin: User, user_id: uuid.UUID, actor: Actor) -> AdminUserOut:
        user = await self._user(user_id)
        if user.disabled_at is not None:
            user.disabled_at = None
            self._audit(admin, actor, "admin.user_enabled", user)
            await self._db.commit()
        return await self._one(user)

    async def reset_two_factor(self, admin: User, user_id: uuid.UUID, actor: Actor) -> AdminUserOut:
        """For someone who lost their authenticator and their recovery codes."""
        user = await self._user(user_id)
        if not user.totp_enabled and user.totp_secret_enc is None:
            raise ConflictError("Two-factor authentication is not on for this account.")
        user.totp_enabled = False
        user.totp_secret_enc = None
        user.totp_last_step = None
        user.recovery_codes_hash = []
        self._audit(admin, actor, "admin.2fa_reset", user)
        await self._db.commit()
        await self._sessions.delete_all(user.id)
        await self._mailer.send(messages.two_factor_changed(user.email, user.name, enabled=False))
        return await self._one(user)

    async def sign_out(self, admin: User, user_id: uuid.UUID, actor: Actor) -> int:
        user = await self._user(user_id)
        ended = await self._sessions.delete_all(user.id)
        self._audit(admin, actor, "admin.sessions_ended", user, {"sessions": ended})
        await self._db.commit()
        return ended

    async def _one(self, user: User) -> AdminUserOut:
        reviews = await self._db.scalar(
            select(func.count())
            .select_from(ProjectMember)
            .join(Project, Project.id == ProjectMember.project_id)
            .where(ProjectMember.user_id == user.id, Project.deleted_at.is_(None))
        )
        return _user_out(user, reviews or 0)

    def _audit(
        self,
        admin: User,
        actor: Actor,
        action: str,
        user: User,
        after: dict[str, Any] | None = None,
    ) -> None:
        audit.record(
            self._db,
            action,
            actor,
            user_id=admin.id,
            entity_type="user",
            entity_id=user.id,
            after={"email": user.email, **(after or {})},
        )

    # --- Settings -----------------------------------------------------------------

    async def instance_settings(self) -> InstanceSettingsOut:
        settings = self._settings
        registration = await stored(self._db, REGISTRATION)
        unpaywall = await stored(self._db, UNPAYWALL_EMAIL)
        return InstanceSettingsOut(
            registration=Source(
                value=registration or settings.registration,
                source="admin" if registration else "environment",
            ),
            unpaywall_email=Source(
                value=unpaywall or settings.unpaywall_email,
                source="admin" if unpaywall else "environment",
            ),
            public_url=settings.public_origin,
            single_user=settings.winnow_single_user,
            email_configured=settings.email_enabled,
            email_from=settings.smtp_from,
            storage_backend=settings.storage_backend,
            open_access_lookup=settings.open_access_lookup,
            llm_provider=settings.llm_provider,
            llm_model=settings.llm_model,
            llm_configured=llm_configured(settings),
            virus_scanner=bool(settings.clamav_host),
            max_upload_mb=settings.max_upload_mb,
            max_pdf_mb=settings.max_pdf_mb,
            max_backup_mb=settings.max_backup_mb,
            version=__version__,
        )

    async def update_settings(
        self, admin: User, body: InstanceSettingsPatch, actor: Actor
    ) -> InstanceSettingsOut:
        changed: dict[str, Any] = {}
        if body.registration is not None:
            mode = None if body.registration == "environment" else body.registration
            await store(self._db, REGISTRATION, mode, admin.id)
            changed["registration"] = body.registration
        if body.unpaywall_email is not None:
            email = str(body.unpaywall_email) or None
            await store(self._db, UNPAYWALL_EMAIL, email, admin.id)
            changed["unpaywall_email"] = body.unpaywall_email or "environment"
        if changed:
            audit.record(self._db, "admin.settings_changed", actor, user_id=admin.id, after=changed)
            await self._db.commit()
        return await self.instance_settings()

    # --- Health -------------------------------------------------------------------

    async def health(self) -> HealthOut:
        redis = cast("Any", self._redis)
        waiting = int(await redis.zcard(ARQ_QUEUE) or 0)
        report = await redis.get(ARQ_HEALTH)
        backup = await redis.get(LAST_BACKUP_KEY)
        return HealthOut(
            database_bytes=await self._db.scalar(
                select(func.pg_database_size(func.current_database()))
            )
            or 0,
            queue=QueueHealth(
                waiting=waiting,
                worker_alive=report is not None,
                worker_report=_worker_report(report),
            ),
            disk=await asyncio.to_thread(self._disk),
            last_backup=_last_backup(backup),
            users=await self._count(User, User.deleted_at.is_(None)),
            reviews=await self._count(Project, Project.deleted_at.is_(None)),
            records=await self._count(Record),
            version=__version__,
        )

    async def _count(self, model: Any, *where: Any) -> int:
        return await self._db.scalar(select(func.count()).select_from(model).where(*where)) or 0

    def _disk(self) -> DiskHealth | None:
        if self._settings.storage_backend != "local":
            return None
        path = Path(self._settings.storage_path)
        if not path.exists():
            return None
        usage = shutil.disk_usage(path)
        return DiskHealth(
            path=str(path), total_bytes=usage.total, used_bytes=usage.used, free_bytes=usage.free
        )


def _user_out(user: User, reviews: int) -> AdminUserOut:
    return AdminUserOut(
        id=user.id,
        name=user.name,
        email=user.email,
        email_verified=user.email_verified,
        two_factor=user.totp_enabled,
        is_instance_admin=user.is_instance_admin,
        disabled=user.disabled_at is not None,
        reviews=reviews,
        created_at=user.created_at,
    )


def _worker_report(raw: str | bytes | None) -> dict[str, int]:
    """arq's health line: "Sep-25 07:24:16 j_complete=12 j_failed=0 j_retried=0 j_ongoing=1
    queued=0"."""
    if raw is None:
        return {}
    text = raw.decode() if isinstance(raw, bytes) else raw
    report = {}
    for part in text.split():
        name, _, value = part.partition("=")
        if value.isdigit():
            report[name] = int(value)
    return report


def _last_backup(raw: str | bytes | None) -> LastBackup | None:
    if raw is None:
        return None
    try:
        data = json.loads(raw)
        return LastBackup.model_validate(data)
    except ValueError:
        return None
