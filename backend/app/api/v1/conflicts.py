"""Conflicts and their resolution: /api/v1/projects/{pid}/conflicts (guide 10, 8.7).

Only resolvers reach these routes (guide 7): owners, admins, and reviewers trusted with
`can_resolve_conflicts`. For them, on these records only, blind mode is lifted.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import ActorDep, ConflictsDep, MailerDep, ResolverAccess, SettingsDep
from app.api.responses import CONFLICT, PROJECT
from app.models import ScreeningStage
from app.schemas.problem import problem_content
from app.schemas.screening import ConflictOut, ConflictPage, DiscussIn, NoteOut, ResolveIn
from app.services.pagination import MAX_LIMIT

router = APIRouter(prefix="/projects/{pid}/conflicts", tags=["conflicts"])


@router.get("", responses=PROJECT)
async def list_conflicts(
    access: ResolverAccess,
    conflicts: ConflictsDep,
    stage: Annotated[ScreeningStage, Query()] = ScreeningStage.TITLE_ABSTRACT,
    reviewer_a: uuid.UUID | None = None,
    reviewer_b: uuid.UUID | None = None,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 25,
) -> ConflictPage:
    """Records whose reviewers disagree, with each decision side by side."""
    return await conflicts.page(
        access,
        stage=stage,
        reviewer_a=reviewer_a,
        reviewer_b=reviewer_b,
        cursor=cursor,
        limit=limit,
    )


@router.post("/{rid}/resolve", responses={**PROJECT, **CONFLICT, 422: problem_content()})
async def resolve_conflict(
    rid: uuid.UUID,
    body: ResolveIn,
    access: ResolverAccess,
    conflicts: ConflictsDep,
    actor: ActorDep,
) -> ConflictOut:
    """The final decision on one record."""
    return await conflicts.resolve(access, rid, body, actor)


@router.post("/{rid}/discuss", status_code=status.HTTP_201_CREATED, responses=PROJECT)
async def discuss_conflict(
    rid: uuid.UUID,
    body: DiscussIn,
    access: ResolverAccess,
    conflicts: ConflictsDep,
    actor: ActorDep,
    mailer: MailerDep,
    settings: SettingsDep,
) -> NoteOut:
    """Leave a team note and ask the record's reviewers to talk it over."""
    return await conflicts.discuss(access, rid, body, actor, mailer=mailer, settings=settings)
