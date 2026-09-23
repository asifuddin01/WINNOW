"""Screening: the queue, decisions, history, labels, notes and bulk decisions (guide 10).

Screening is for reviewers and above (guide 7); what each caller is told about other
people's decisions is decided in the services, under blind mode (guide 8.6).
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, status

from app.api.deps import ActorDep, AdminAccess, ReviewerAccess, ScreeningDep
from app.api.responses import CONFLICT, PROJECT
from app.models import ScreeningStage
from app.schemas.problem import problem_content
from app.schemas.screening import (
    BulkDecisionIn,
    BulkDecisionOut,
    DecisionIn,
    DecisionOut,
    HistoryPage,
    LabelsIn,
    NoteIn,
    NoteOut,
    Progress,
    QueuePage,
    QueueSort,
    ScreeningItem,
)
from app.services.pagination import MAX_LIMIT

router = APIRouter(prefix="/projects/{pid}", tags=["screening"])

Stage = Annotated[ScreeningStage, Query()]
INVALID: dict[int | str, dict[str, Any]] = {422: problem_content()}


@router.get("/screening/queue", responses=PROJECT)
async def screening_queue(
    access: ReviewerAccess,
    screening: ScreeningDep,
    stage: Stage = ScreeningStage.TITLE_ABSTRACT,
    n: Annotated[int, Query(ge=1, le=25)] = 10,
    sort: QueueSort = "relevance",
    exclude: Annotated[list[uuid.UUID] | None, Query(max_length=60)] = None,
    q: Annotated[str, Query(max_length=500)] = "",
) -> QueuePage:
    """The next records for me, to hold ahead of the one on screen (guide 8.5).

    `exclude` lists the records the screen already holds, so they are not sent twice.
    """
    return await screening.queue(
        access, stage=stage, n=n, sort=sort, exclude=exclude or [], search=q
    )


@router.get("/screening/progress", responses=PROJECT)
async def screening_progress(
    access: ReviewerAccess, screening: ScreeningDep, stage: Stage = ScreeningStage.TITLE_ABSTRACT
) -> Progress:
    """How far I am, and — only if I may know — how many conflicts are waiting."""
    return await screening.progress(access, stage)


@router.get("/screening/records/{rid}", responses=PROJECT)
async def screening_record(
    rid: uuid.UUID,
    access: ReviewerAccess,
    screening: ScreeningDep,
    stage: Stage = ScreeningStage.TITLE_ABSTRACT,
) -> ScreeningItem:
    """One record as the screen shows it, whether or not I have decided about it."""
    return await screening.item(access, rid, stage)


@router.put("/records/{rid}/decision", responses={**PROJECT, **CONFLICT, **INVALID})
async def decide(
    rid: uuid.UUID,
    body: DecisionIn,
    access: ReviewerAccess,
    screening: ScreeningDep,
    actor: ActorDep,
) -> DecisionOut:
    """Include, exclude or maybe; deciding again changes my decision."""
    return await screening.decide(access, rid, body, actor)


@router.delete("/records/{rid}/decision", responses=PROJECT)
async def undo_decision(
    rid: uuid.UUID,
    access: ReviewerAccess,
    screening: ScreeningDep,
    actor: ActorDep,
    stage: Stage = ScreeningStage.TITLE_ABSTRACT,
) -> DecisionOut:
    """Take my decision back (guide 8.5's undo)."""
    return await screening.undo(access, rid, stage, actor)


@router.get("/my-history", responses=PROJECT)
async def my_history(
    access: ReviewerAccess,
    screening: ScreeningDep,
    stage: Stage = ScreeningStage.TITLE_ABSTRACT,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 50,
) -> HistoryPage:
    """My decisions, latest first."""
    return await screening.history(access, stage, cursor=cursor, limit=limit)


@router.put("/records/{rid}/labels", responses={**PROJECT, **INVALID})
async def set_labels(
    rid: uuid.UUID, body: LabelsIn, access: ReviewerAccess, screening: ScreeningDep
) -> list[uuid.UUID]:
    """Replace the labels I have put on this record."""
    return await screening.set_labels(access, rid, body.label_ids)


@router.post(
    "/records/{rid}/notes", status_code=status.HTTP_201_CREATED, responses={**PROJECT, **INVALID}
)
async def add_note(
    rid: uuid.UUID, body: NoteIn, access: ReviewerAccess, screening: ScreeningDep
) -> NoteOut:
    """A note on the record: private to me, or for the team."""
    return await screening.add_note(access, rid, body.body, body.visibility)


@router.delete("/notes/{nid}", status_code=status.HTTP_204_NO_CONTENT, responses=PROJECT)
async def delete_note(nid: uuid.UUID, access: ReviewerAccess, screening: ScreeningDep) -> None:
    await screening.delete_note(access, nid)


@router.post("/bulk-decision/preview", responses=PROJECT)
async def bulk_preview(
    body: BulkDecisionIn, access: AdminAccess, screening: ScreeningDep
) -> BulkDecisionOut:
    """How many records a bulk decision would settle, for the confirmation."""
    return BulkDecisionOut(decided=await screening.bulk_count(access, body))


@router.post("/bulk-decision", responses={**PROJECT, **CONFLICT, **INVALID})
async def bulk_decision(
    body: BulkDecisionIn, access: AdminAccess, screening: ScreeningDep, actor: ActorDep
) -> BulkDecisionOut:
    """Decide every matching record at once (guide 8.5), logged with bulk=true."""
    return await screening.bulk(access, body, actor)
