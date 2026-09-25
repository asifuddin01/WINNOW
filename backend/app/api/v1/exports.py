"""Exports and backups (guide 8.16, 10), and restoring a backup as a new review.

Exports are made in the worker: ask for one, follow its status (also sent on the review's
event stream), then download it. It is yours alone and lasts a day.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, File, UploadFile, status
from fastapi.responses import StreamingResponse

from app.api.deps import (
    ActorDep,
    AuthDep,
    ExportsDep,
    LimiterDep,
    RestoresDep,
    StorageDep,
    ViewerAccess,
    enforce_limit,
)
from app.api.responses import CONFLICT, PROJECT, RATE_LIMITED, UNAUTHORIZED
from app.schemas.export import ExportIn, ExportOut, RestoreOut
from app.schemas.problem import problem_content
from app.security import rate_limit as limits

router = APIRouter(prefix="/projects/{pid}", tags=["exports"])
restores = APIRouter(tags=["exports"])


@router.post(
    "/exports",
    status_code=status.HTTP_201_CREATED,
    responses={**PROJECT, **RATE_LIMITED, 422: problem_content()},
)
async def request_export(
    body: ExportIn, access: ViewerAccess, exports: ExportsDep, limiter: LimiterDep, actor: ActorDep
) -> ExportOut:
    """Records (CSV, XLSX, RIS, BibTeX), filtered as in the records table, or the review's
    full backup (owner only)."""
    await enforce_limit(limiter, limits.EXPORTS_PER_USER, str(access.user.id))
    return await exports.create(access, body, actor)


@router.get("/exports", responses=PROJECT)
async def my_exports(access: ViewerAccess, exports: ExportsDep) -> list[ExportOut]:
    return await exports.mine(access)


@router.get("/exports/{eid}", responses=PROJECT)
async def export_status(eid: uuid.UUID, access: ViewerAccess, exports: ExportsDep) -> ExportOut:
    return await exports.get(access, eid)


@router.get(
    "/exports/{eid}/file",
    response_class=StreamingResponse,
    responses={**PROJECT, **CONFLICT, 200: {"content": {"application/octet-stream": {}}}},
)
async def download_export(
    eid: uuid.UUID,
    access: ViewerAccess,
    exports: ExportsDep,
    storage: StorageDep,
    actor: ActorDep,
) -> StreamingResponse:
    ready = await exports.ready_file(access, eid, actor)
    return StreamingResponse(
        storage.iter_bytes(ready.key),
        media_type=ready.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{ready.filename}"',
            "Content-Length": str(ready.size),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@restores.post(
    "/restores",
    status_code=status.HTTP_201_CREATED,
    responses={**UNAUTHORIZED, **RATE_LIMITED, 403: problem_content(), 413: problem_content()},
)
async def restore_backup(
    auth: AuthDep,
    restorer: RestoresDep,
    limiter: LimiterDep,
    actor: ActorDep,
    file: Annotated[UploadFile, File(description="A Winnow project backup (.zip)")],
) -> RestoreOut:
    """Restore a backup as a new review of yours; it is checked, then built in the worker."""
    await enforce_limit(limiter, limits.PROJECT_CREATE_PER_USER, str(auth.user.id))
    await enforce_limit(limiter, limits.UPLOADS_PER_USER, str(auth.user.id))
    return await restorer.start(auth.user, file, actor)


@restores.get("/restores/{restore_id}", responses={**UNAUTHORIZED, 404: problem_content()})
async def restore_status(restore_id: uuid.UUID, auth: AuthDep, restorer: RestoresDep) -> RestoreOut:
    return await restorer.get(auth.user, restore_id)
