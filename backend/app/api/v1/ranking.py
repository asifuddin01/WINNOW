"""Relevance ranking: the model's state, retraining on demand, the recall curve and the
stopping-rule helper (guide 8.5, 8.10, 10).

Team-wide numbers are shown only to someone allowed to see other people's decisions
(guide 8.6); the services decide that.
"""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import RankingDep, ReviewerAccess, ViewerAccess
from app.api.responses import PROJECT
from app.models import ScreeningStage
from app.schemas.ranking import RankingStatus, RecallCurve, StoppingAdvice, TrainStarted

router = APIRouter(prefix="/projects/{pid}", tags=["ranking"])

Stage = Annotated[ScreeningStage, Query()]


@router.get("/ranking/status", responses=PROJECT)
async def ranking_status(
    access: ViewerAccess, ranking: RankingDep, stage: Stage = ScreeningStage.TITLE_ABSTRACT
) -> RankingStatus:
    """Whether a model exists for the stage, and what it has learnt from."""
    return await ranking.status(access, stage)


@router.post("/ranking/train", status_code=202, responses=PROJECT)
async def ranking_train(
    access: ReviewerAccess, ranking: RankingDep, stage: Stage = ScreeningStage.TITLE_ABSTRACT
) -> TrainStarted:
    """Retrain now rather than after the next 25 decisions (guide 8.10)."""
    return await ranking.train(access, stage)


@router.get("/ranking/curve", responses=PROJECT)
async def recall_curve(
    access: ViewerAccess, ranking: RankingDep, stage: Stage = ScreeningStage.TITLE_ABSTRACT
) -> RecallCurve:
    """Includes found against records screened: mine, and the team's if I may see it."""
    return await ranking.curve(access, stage)


@router.get("/screening/stopping", responses=PROJECT)
async def stopping_advice(
    access: ReviewerAccess, ranking: RankingDep, stage: Stage = ScreeningStage.TITLE_ABSTRACT
) -> StoppingAdvice:
    """Guide 8.5: how many records in a row I have excluded, and, once that reaches the
    review's rule, an estimate of the relevant records still unscreened. Advice only."""
    return await ranking.stopping(access, stage)
