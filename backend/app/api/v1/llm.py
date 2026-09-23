"""AI suggestions (guide 8.11, 10): ask about one record, see my last answer, export all.

Asking sends the record and the review's criteria to the instance's AI provider, so it is
counted against a per-person limit of 60 an hour (guide 12.6). Seeing a stored answer
sends nothing.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.api.deps import (
    ActorDep,
    AdminAccess,
    LimiterDep,
    LlmDep,
    ReviewerAccess,
    enforce_limit,
)
from app.api.responses import CONFLICT, PROJECT
from app.models import ScreeningStage
from app.schemas.llm import MaybeSuggestion, SuggestionOut
from app.security import rate_limit as limits

router = APIRouter(prefix="/projects/{pid}", tags=["ai"])

Stage = Annotated[ScreeningStage, Query()]


@router.get("/records/{rid}/llm-suggest", responses=PROJECT)
async def my_suggestion(
    rid: uuid.UUID,
    access: ReviewerAccess,
    llm: LlmDep,
    stage: Stage = ScreeningStage.TITLE_ABSTRACT,
) -> MaybeSuggestion:
    """My latest suggestion for this record, if I have asked. Sends nothing anywhere."""
    return MaybeSuggestion(suggestion=await llm.latest(access, rid, stage))


@router.post(
    "/records/{rid}/llm-suggest",
    responses={**PROJECT, **CONFLICT, 429: {}, 502: {}},
)
async def suggest(
    rid: uuid.UUID,
    access: ReviewerAccess,
    llm: LlmDep,
    limiter: LimiterDep,
    actor: ActorDep,
    stage: Stage = ScreeningStage.TITLE_ABSTRACT,
) -> SuggestionOut:
    """Ask the AI provider about this record now. Advice only: nothing is decided."""
    llm.check_available(access, stage)
    await enforce_limit(limiter, limits.LLM_SUGGEST_PER_USER, str(access.user.id))
    return await llm.suggest(access, rid, stage, actor)


@router.get("/llm-suggestions.csv", responses=PROJECT, response_class=Response)
async def export_suggestions(access: AdminAccess, llm: LlmDep) -> Response:
    """Every AI suggestion in the review, for reporting the use of AI in the methods."""
    return Response(
        content=await llm.export_csv(access),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="ai-suggestions.csv"'},
    )
