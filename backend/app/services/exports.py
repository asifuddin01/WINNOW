"""Asking for exports and backups, and handing them over (guide 8.16).

The worker builds them (`app.workers.exports`). An export belongs to whoever asked: its
contents depend on what they may see, so only they can download it, and only for a day.
A full backup is the whole review, everyone's work included, so only its owner makes one.
"""

import uuid
from dataclasses import dataclass

from arq.connections import ArqRedis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ExportFormat, ExportJob, ExportKind, JobStatus, ProjectRole
from app.schemas.export import ExportIn, ExportOut
from app.security.permissions import ProjectAccess
from app.services import audit
from app.services.audit import Actor
from app.services.errors import ConflictError, DomainError, ForbiddenError, NotFoundError

EXPORT_JOB = "build_export"
RECENT = 20
RECORD_FORMATS = {ExportFormat.CSV, ExportFormat.XLSX, ExportFormat.RIS, ExportFormat.BIBTEX}


class UnsupportedFormatError(DomainError):
    status = 422
    code = "unsupported_format"


@dataclass(frozen=True)
class ReadyFile:
    key: str
    filename: str
    size: int
    media_type: str


MEDIA = {
    ExportFormat.CSV: "text/csv; charset=utf-8",
    ExportFormat.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ExportFormat.RIS: "application/x-research-info-systems; charset=utf-8",
    ExportFormat.BIBTEX: "application/x-bibtex; charset=utf-8",
    ExportFormat.ZIP: "application/zip",
}


def export_out(row: ExportJob) -> ExportOut:
    return ExportOut(
        id=row.id,
        kind=row.kind,
        format=row.format,
        status=row.status,
        filename=row.filename,
        size_bytes=row.size_bytes,
        rows=row.rows,
        problem=row.problem,
        created_at=row.created_at,
        expires_at=row.expires_at,
    )


class ExportService:
    def __init__(self, db: AsyncSession, queue: ArqRedis | None) -> None:
        self._db = db
        self._queue = queue

    async def create(self, access: ProjectAccess, body: ExportIn, actor: Actor) -> ExportOut:
        if body.kind is ExportKind.BACKUP:
            if access.role is not ProjectRole.OWNER:
                raise ForbiddenError("Only the review's owner can make a full backup.")
            fmt = ExportFormat.ZIP
        else:
            if body.format not in RECORD_FORMATS:
                raise UnsupportedFormatError("Records export as CSV, XLSX, RIS or BibTeX.")
            fmt = body.format
        row = ExportJob(
            project_id=access.project_id,
            requested_by=access.user.id,
            kind=body.kind,
            format=fmt,
            filters=body.filters.model_dump(mode="json") if body.kind is ExportKind.RECORDS else {},
            status=JobStatus.QUEUED,
        )
        self._db.add(row)
        audit.record(
            self._db,
            "export.requested",
            actor,
            user_id=access.user.id,
            project_id=access.project_id,
            entity_type="project",
            entity_id=access.project_id,
            after={"kind": body.kind.value, "format": fmt.value, "filters": row.filters},
        )
        await self._db.commit()
        if self._queue is not None:
            await self._queue.enqueue_job(EXPORT_JOB, str(row.id), _job_id=f"export:{row.id}")
        await self._db.refresh(row)
        return export_out(row)

    async def mine(self, access: ProjectAccess) -> list[ExportOut]:
        rows = await self._db.scalars(
            select(ExportJob)
            .where(
                ExportJob.project_id == access.project_id,
                ExportJob.requested_by == access.user.id,
            )
            .order_by(ExportJob.created_at.desc())
            .limit(RECENT)
        )
        return [export_out(row) for row in rows]

    async def get(self, access: ProjectAccess, export_id: uuid.UUID) -> ExportOut:
        return export_out(await self._own(access, export_id))

    async def ready_file(
        self, access: ProjectAccess, export_id: uuid.UUID, actor: Actor
    ) -> ReadyFile:
        row = await self._own(access, export_id)
        if row.status is not JobStatus.READY or row.file_key is None:
            raise ConflictError("This export is not ready yet.")
        audit.record(
            self._db,
            "export.downloaded",
            actor,
            user_id=access.user.id,
            project_id=access.project_id,
            entity_type="project",
            entity_id=access.project_id,
            after={"export": str(row.id), "kind": row.kind.value, "format": row.format.value},
        )
        await self._db.commit()
        return ReadyFile(
            key=row.file_key,
            filename=row.filename or f"export.{row.format.value}",
            size=row.size_bytes or 0,
            media_type=MEDIA[row.format],
        )

    async def _own(self, access: ProjectAccess, export_id: uuid.UUID) -> ExportJob:
        row = await self._db.scalar(
            select(ExportJob).where(
                ExportJob.id == export_id,
                ExportJob.project_id == access.project_id,
                ExportJob.requested_by == access.user.id,
            )
        )
        if row is None:
            raise NotFoundError("That export is not yours, or it has expired.")
        return row
