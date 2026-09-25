"""A review's audit log (guide 12.8, 8.16, 10): owners and admins, newest first, and as CSV."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.api.deps import AdminAccess, AuditLogDep
from app.api.responses import PROJECT
from app.schemas.audit import AuditPage

router = APIRouter(prefix="/projects/{pid}", tags=["audit"])

Action = Annotated[str | None, Query(max_length=100, pattern=r"^[a-z0-9_.]+$")]


@router.get("/audit", responses=PROJECT)
async def audit_log(
    access: AdminAccess,
    log: AuditLogDep,
    action: Action = None,
    user_id: Annotated[uuid.UUID | None, Query()] = None,
    since: Annotated[date | None, Query()] = None,
    until: Annotated[date | None, Query()] = None,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AuditPage:
    """What happened in the review, newest first. `action` matches a whole action or a
    family of them (`decision` matches `decision.made` and `decision.undone`)."""
    return await log.page(
        access, action=action, user_id=user_id, since=since, until=until, cursor=cursor, limit=limit
    )


@router.get(
    "/audit.csv",
    response_class=StreamingResponse,
    responses={**PROJECT, 200: {"content": {"text/csv": {}}}},
)
async def audit_log_csv(
    access: AdminAccess,
    log: AuditLogDep,
    action: Action = None,
    user_id: Annotated[uuid.UUID | None, Query()] = None,
    since: Annotated[date | None, Query()] = None,
    until: Annotated[date | None, Query()] = None,
) -> StreamingResponse:
    """The same log as a CSV file, with the same filters."""
    return StreamingResponse(
        log.csv(access, action=action, user_id=user_id, since=since, until=until),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="audit-log.csv"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
