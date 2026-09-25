"""Restoring a project backup as a new review (guide 8.16), started here and done in the
worker (`app.workers.exports.run_restore`). Anyone who may start a review may restore one;
it becomes theirs alone."""

import uuid
from collections.abc import AsyncIterator

from arq.connections import ArqRedis
from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import JobStatus, RestoreJob, User
from app.schemas.export import RestoreOut
from app.services import audit
from app.services.audit import Actor
from app.services.errors import DomainError, NotFoundError
from app.services.projects import ProjectService
from app.storage import Storage, TooLargeError, new_key

RESTORE_JOB = "restore_backup"


class BackupTooLargeError(DomainError):
    status = 413
    code = "too_large"


def restore_out(row: RestoreJob) -> RestoreOut:
    return RestoreOut(
        id=row.id,
        filename=row.filename,
        status=row.status,
        project_id=row.project_id,
        problem=row.problem,
        restored={str(key): int(value) for key, value in row.restored.items()},
        created_at=row.created_at,
    )


class RestoreService:
    def __init__(
        self, db: AsyncSession, settings: Settings, storage: Storage, queue: ArqRedis | None
    ) -> None:
        self._db = db
        self._settings = settings
        self._storage = storage
        self._queue = queue

    async def start(self, user: User, file: UploadFile, actor: Actor) -> RestoreOut:
        ProjectService(self._db, self._settings).check_can_own(user)
        key = new_key("restores")

        async def chunks() -> AsyncIterator[bytes]:
            while chunk := await file.read(1024 * 1024):
                yield chunk

        try:
            await self._storage.save(key, chunks(), self._settings.max_backup_mb * 1024 * 1024)
        except TooLargeError as error:
            raise BackupTooLargeError(
                f"Backups up to {self._settings.max_backup_mb:,} MB can be restored here."
            ) from error
        row = RestoreJob(
            user_id=user.id,
            zip_key=key,
            filename=(file.filename or "backup.zip")[:200],
            status=JobStatus.QUEUED,
        )
        self._db.add(row)
        audit.record(
            self._db,
            "project.restore_started",
            actor,
            user_id=user.id,
            after={"filename": row.filename},
        )
        await self._db.commit()
        if self._queue is not None:
            await self._queue.enqueue_job(RESTORE_JOB, str(row.id), _job_id=f"restore:{row.id}")
        await self._db.refresh(row)
        return restore_out(row)

    async def get(self, user: User, restore_id: uuid.UUID) -> RestoreOut:
        row = await self._db.scalar(
            select(RestoreJob).where(RestoreJob.id == restore_id, RestoreJob.user_id == user.id)
        )
        if row is None:
            raise NotFoundError("That restore is not yours.")
        return restore_out(row)
