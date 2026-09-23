"""Uploading search results and watching them load: /api/v1/projects/{pid} (guide 10).

Importing is an admin's job (guide 7). The upload is stored and previewed; only a confirm
starts the worker, and the browser follows progress on the project's event stream.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import date
from time import monotonic
from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile, status
from fastapi.responses import StreamingResponse

from app.api.deps import ActorDep, AdminAccess, ImportsDep, LimiterDep, ViewerAccess, enforce_limit
from app.api.responses import CONFLICT, PROJECT, RATE_LIMITED
from app.redis_client import RedisDep
from app.schemas.imports import (
    ConfirmImport,
    ImportAccepted,
    ImportMeta,
    ImportOut,
    ImportPreview,
    ImportUpload,
)
from app.schemas.problem import problem_content
from app.security import rate_limit as limits
from app.services import events
from app.services.imports import UploadedFile

router = APIRouter(prefix="/projects/{pid}", tags=["imports"])

CHUNK = 1024 * 1024
# How long a quiet event stream waits before sending a comment to keep the pipe open.
HEARTBEAT_SECONDS = 15.0
# How long one stream lives. An endless response keeps a server from ever finishing a
# graceful shutdown or reload; the browser reconnects on its own (after RETRY_MS) and is
# sent the recent events again, so ending a stream loses nothing.
STREAM_SECONDS = 300.0
RETRY_MS = 2000


async def _chunks(upload: UploadFile) -> AsyncIterator[bytes]:
    while chunk := await upload.read(CHUNK):
        yield chunk


@router.post(
    "/imports",
    status_code=status.HTTP_201_CREATED,
    responses={
        **PROJECT,
        400: problem_content(),
        413: problem_content(),
        415: problem_content(),
        **RATE_LIMITED,
    },
)
async def upload_imports(
    access: AdminAccess,
    imports: ImportsDep,
    limiter: LimiterDep,
    actor: ActorDep,
    files: Annotated[list[UploadFile], File(description="Search exports, several at a time")],
    source_name: Annotated[str | None, Form()] = None,
    database_name: Annotated[str, Form()] = "Other",
    databases: Annotated[
        list[str] | None,
        Form(description="One database per file, in the same order; overrides database_name"),
    ] = None,
    search_date: Annotated[date | None, Form()] = None,
    search_string: Annotated[str | None, Form()] = None,
) -> ImportUpload:
    """Store a search export, or a whole set of them, and work out what each one is.

    A search usually leaves a database in several files; they arrive together and each
    becomes its own import, so PRISMA can count them and any one of them can be undone.
    Nothing is imported until you confirm.
    """
    await enforce_limit(limiter, limits.UPLOADS_PER_USER, str(access.user.id))
    meta = ImportMeta(
        source_name=source_name,
        database_name=database_name,
        search_date=search_date,
        search_string=search_string,
    )
    per_file = databases or []
    uploads = [
        UploadedFile(
            filename=upload.filename or "upload",
            chunks=_chunks(upload),
            database_name=per_file[index] if index < len(per_file) else None,
        )
        for index, upload in enumerate(files)
    ]
    return await imports.upload_all(access, uploads, meta=meta, actor=actor)


@router.get("/imports", responses=PROJECT)
async def list_imports(access: ViewerAccess, imports: ImportsDep) -> list[ImportOut]:
    """Every import in this review, newest first (guide 8.3)."""
    return await imports.history(access)


@router.get("/imports/{bid}/preview", responses=PROJECT)
async def preview_import(bid: uuid.UUID, access: AdminAccess, imports: ImportsDep) -> ImportPreview:
    """The first records as Winnow reads them, and for CSV the column mapping to confirm."""
    return await imports.preview(access, bid)


@router.post("/imports/{bid}/confirm", responses={**PROJECT, **CONFLICT})
async def confirm_import(
    bid: uuid.UUID,
    body: ConfirmImport,
    access: AdminAccess,
    imports: ImportsDep,
    actor: ActorDep,
) -> ImportAccepted:
    """Start the import. It runs in the worker; watch /events for progress."""
    batch, job_id = await imports.confirm(access, bid, body, actor)
    from app.services.imports import out

    return ImportAccepted(batch=out(batch), job_id=job_id)


@router.delete(
    "/imports/{bid}", status_code=status.HTTP_204_NO_CONTENT, responses={**PROJECT, **CONFLICT}
)
async def undo_import(
    bid: uuid.UUID, access: AdminAccess, imports: ImportsDep, actor: ActorDep
) -> None:
    """Undo an import: the batch and the records it brought in go."""
    await imports.undo(access, bid, actor)


@router.get("/events", responses=PROJECT)
async def project_events(
    request: Request, access: ViewerAccess, redis: RedisDep
) -> StreamingResponse:
    """Server-sent events for this review: import progress today, more later (guide 10).

    Only members reach this, and events carry counts, never record contents.
    """
    project_id = access.project_id

    async def stream() -> AsyncIterator[str]:
        pubsub = redis.pubsub()
        await pubsub.subscribe(events.channel_for(project_id))
        ends = monotonic() + STREAM_SECONDS
        try:
            yield f"retry: {RETRY_MS}\n\n"
            for payload in await events.recent(redis, project_id):
                yield f"data: {payload}\n\n"
            while monotonic() < ends and not await request.is_disconnected():
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=HEARTBEAT_SECONDS
                )
                if message is None:
                    yield ": keep-alive\n\n"
                    continue
                yield f"data: {message['data']}\n\n"
        finally:
            await pubsub.unsubscribe(events.channel_for(project_id))
            await pubsub.aclose()  # type: ignore[no-untyped-call]

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
