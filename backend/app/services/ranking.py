"""Relevance ranking in the app: when to retrain, and what people are shown (guide 8.10).

Training runs in the worker (`app.workers.ranking`). Here: nudging it after decisions —
the first model as soon as a stage has one include and one exclude, then after every 25 new
decisions, never more than once a minute per review and stage — plus the model's status,
the recall curve and the stopping-rule helper.
"""

import asyncio
import time
import uuid
from typing import Any

from arq.connections import ArqRedis
from arq.jobs import Job, JobStatus
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Decision,
    DecisionValue,
    RankingModel,
    Record,
    ScreeningStage,
    TitleAbstractStatus,
)
from app.ranking.labels import training_label
from app.ranking.model import MIN_EACH
from app.ranking.stopping import estimate_remaining, excluded_in_a_row
from app.schemas.projects import ProjectSettings
from app.schemas.ranking import (
    Curve,
    Estimate,
    ModelOut,
    RankingStatus,
    RecallCurve,
    StoppingAdvice,
    TrainStarted,
)
from app.security.permissions import ProjectAccess
from app.services.blinding import sees_others, settings_of

# Guide 8.10.
RETRAIN_AFTER = 25
MIN_INTERVAL_SECONDS = 60
# Decisions come in bursts; wait this long so one run covers the burst.
SETTLE_SECONDS = 10
# Guide 9.2: one record in this many comes from random order in relevance sort.
EXPLORE_EVERY = 20
# How long a stopping estimate is kept, and how many decisions it stands for.
ESTIMATE_TTL_SECONDS = 24 * 3600
ESTIMATE_EVERY = 25

RELEVANT = (DecisionValue.INCLUDE, DecisionValue.MAYBE)


def ranking_job_id(project_id: uuid.UUID, stage: ScreeningStage) -> str:
    """One ranking job per review and stage at a time."""
    return f"rank:{project_id}:{stage.value}"


def _new_key(project_id: uuid.UUID, stage: ScreeningStage) -> str:
    return f"rank:new:{project_id}:{stage.value}"


def _trained_key(project_id: uuid.UUID, stage: ScreeningStage) -> str:
    return f"rank:trained:{project_id}:{stage.value}"


async def enqueue_ranking(
    queue: ArqRedis, project_id: uuid.UUID, stage: ScreeningStage, *, defer: float = 0
) -> bool:
    """Queue a run unless one is queued or running already for this review and stage."""
    from app.workers.settings import RANK_JOB

    job = await queue.enqueue_job(
        RANK_JOB,
        str(project_id),
        stage.value,
        _job_id=ranking_job_id(project_id, stage),
        _defer_by=defer or None,
    )
    return job is not None


async def nudge(
    queue: ArqRedis | None,
    project_id: uuid.UUID,
    stage: ScreeningStage,
    settings: ProjectSettings,
    *,
    count: int = 1,
) -> None:
    """Count `count` new decisions at `stage` and queue a run if one is due.

    Two Redis round trips and, at most, an enqueue: cheap enough for every decision.
    """
    if queue is None or not settings.ranking_enabled:
        return
    new = await queue.incrby(_new_key(project_id, stage), count)
    trained = await queue.get(_trained_key(project_id, stage))
    if trained is not None and new < RETRAIN_AFTER:
        return
    elapsed = time.time() - float(trained) if trained is not None else MIN_INTERVAL_SECONDS
    await enqueue_ranking(
        queue, project_id, stage, defer=max(SETTLE_SECONDS, MIN_INTERVAL_SECONDS - elapsed)
    )


async def mark_trained(
    redis: Redis,
    project_id: uuid.UUID,
    stage: ScreeningStage,
    *,
    begin: bool,
    counted: int = 0,
) -> int:
    """At the start of a run, how many new decisions it covers; at the end, take those
    off the count (decisions made during the run still count) and note the time."""
    if begin:
        value = await redis.get(_new_key(project_id, stage))
        return int(value or 0)
    await redis.decrby(_new_key(project_id, stage), counted)
    await redis.set(_trained_key(project_id, stage), str(time.time()))
    return 0


class RankingService:
    def __init__(self, db: AsyncSession, queue: ArqRedis | None, redis: Redis) -> None:
        self._db = db
        self._queue = queue
        self._redis = redis

    async def status(self, access: ProjectAccess, stage: ScreeningStage) -> RankingStatus:
        settings = settings_of(access)
        told = sees_others(access)
        model = await self._active(access.project_id, stage)
        have_included = have_excluded = None
        if told and model is None:
            labels = await self._labels(access.project_id, stage)
            have_included = sum(labels)
            have_excluded = len(labels) - have_included
        return RankingStatus(
            stage=stage,
            enabled=settings.ranking_enabled,
            model=None
            if model is None
            else ModelOut(
                trained_at=model.trained_at,
                n_labeled=model.n_labeled if told else None,
                n_included=model.n_included if told else None,
                auc=model.metrics.get("auc") if told else None,
                scored=int(model.metrics.get("scored", 0)),
            ),
            needs_each=MIN_EACH,
            have_included=have_included,
            have_excluded=have_excluded,
            retrain_after=RETRAIN_AFTER,
            training=await self._training(access.project_id, stage),
            explore_every=EXPLORE_EVERY,
        )

    async def train(self, access: ProjectAccess, stage: ScreeningStage) -> TrainStarted:
        """Guide 8.10: retrain on demand. Queued behind a run that is already waiting."""
        if self._queue is None or not settings_of(access).ranking_enabled:
            return TrainStarted(queued=False)
        await enqueue_ranking(self._queue, access.project_id, stage)
        return TrainStarted(queued=True)

    async def curve(self, access: ProjectAccess, stage: ScreeningStage) -> RecallCurve:
        conditions = _eligible(access.project_id, stage)
        total = await self._db.scalar(select(func.count()).select_from(Record).where(*conditions))
        mine = await self._my_sequence(access, stage)
        team = None
        if sees_others(access):
            team = _curve(await self._team_sequence(access.project_id, stage))
        return RecallCurve(stage=stage, total=total or 0, mine=_curve(mine), team=team)

    async def stopping(self, access: ProjectAccess, stage: ScreeningStage) -> StoppingAdvice:
        settings = settings_of(access)
        rule = settings.stopping_rule
        mine = await self._my_sequence(access, stage)
        in_a_row = excluded_in_a_row(mine)
        remaining = await self._remaining(access, stage)
        advice = StoppingAdvice(
            stage=stage,
            rule="consecutive_excludes",
            threshold=rule.n,
            in_a_row=in_a_row,
            remaining=remaining,
            estimate=None,
        )
        # Guide 8.5: only with ranking on, and only once the reviewer reaches the rule.
        if (
            rule.type != "consecutive_excludes"
            or in_a_row < rule.n
            or not settings.ranking_enabled
            or await self._active(access.project_id, stage) is None
        ):
            return advice
        # Worked out again every ESTIMATE_EVERY decisions, not on every one.
        bucket = len(mine) // ESTIMATE_EVERY
        key = f"rank:stop:{access.project_id}:{stage.value}:{access.user.id}:{bucket}"
        cached = await self._redis.get(key)
        if cached is not None:
            estimate = Estimate.model_validate_json(cached)
        else:
            ranked_from = await self._before_ranking(access, stage)
            found = await asyncio.to_thread(
                estimate_remaining, mine, remaining, ranked_from=ranked_from
            )
            estimate = Estimate(expected=round(found.expected, 1), low=found.low, high=found.high)
            await self._redis.set(key, estimate.model_dump_json(), ex=ESTIMATE_TTL_SECONDS)
        return advice.model_copy(update={"estimate": estimate})

    # --- Internals ---------------------------------------------------------------------

    async def _active(self, project_id: uuid.UUID, stage: ScreeningStage) -> RankingModel | None:
        model: RankingModel | None = await self._db.scalar(
            select(RankingModel)
            .where(
                RankingModel.project_id == project_id,
                RankingModel.stage == stage,
                RankingModel.is_active.is_(True),
            )
            .order_by(RankingModel.trained_at.desc())
            .limit(1)
        )
        return model

    async def _training(self, project_id: uuid.UUID, stage: ScreeningStage) -> bool:
        if self._queue is None:
            return False
        job = Job(ranking_job_id(project_id, stage), self._queue)
        state = await job.status()
        return state in (JobStatus.deferred, JobStatus.queued, JobStatus.in_progress)

    async def _labels(self, project_id: uuid.UUID, stage: ScreeningStage) -> list[int]:
        status = Record.ta_final if stage is ScreeningStage.TITLE_ABSTRACT else Record.ft_final
        rows = await self._db.execute(
            select(
                status,
                func.array_agg(Decision.decision).filter(Decision.id.is_not(None)),
            )
            .outerjoin(Decision, (Decision.record_id == Record.id) & (Decision.stage == stage))
            .where(*_eligible(project_id, stage))
            .group_by(Record.id)
        )
        labels = []
        for final, votes in rows:
            label = training_label(_value(final), [_value(vote) for vote in votes or ()])
            if label is not None:
                labels.append(label)
        return labels

    async def _my_sequence(self, access: ProjectAccess, stage: ScreeningStage) -> list[bool]:
        """My decisions at `stage` in the order I first made them: relevant or not."""
        rows = await self._db.scalars(
            select(Decision.decision.in_(RELEVANT))
            .join(Record, Record.id == Decision.record_id)
            .where(
                Decision.project_id == access.project_id,
                Decision.user_id == access.user.id,
                Decision.stage == stage,
                Record.is_duplicate.is_(False),
            )
            .order_by(Decision.created_at, Decision.id)
        )
        return [bool(found) for found in rows]

    async def _before_ranking(self, access: ProjectAccess, stage: ScreeningStage) -> int:
        """How many of my decisions came before the stage's first model: those records
        were served in random order, so they say nothing about the ranking's decay."""
        first = await self._db.scalar(
            select(func.min(RankingModel.trained_at)).where(
                RankingModel.project_id == access.project_id, RankingModel.stage == stage
            )
        )
        if first is None:
            return 0
        count = await self._db.scalar(
            select(func.count())
            .select_from(Decision)
            .join(Record, Record.id == Decision.record_id)
            .where(
                Decision.project_id == access.project_id,
                Decision.user_id == access.user.id,
                Decision.stage == stage,
                Decision.created_at < first,
                Record.is_duplicate.is_(False),
            )
        )
        return int(count or 0)

    async def _team_sequence(self, project_id: uuid.UUID, stage: ScreeningStage) -> list[bool]:
        """Every record anyone has decided at `stage`, in the order of its first decision,
        relevant if the team's decisions so far make it so."""
        status = Record.ta_final if stage is ScreeningStage.TITLE_ABSTRACT else Record.ft_final
        rows = await self._db.execute(
            select(status, func.array_agg(Decision.decision), func.min(Decision.created_at))
            .join(Decision, (Decision.record_id == Record.id) & (Decision.stage == stage))
            .where(*_eligible(project_id, stage))
            .group_by(Record.id)
            .order_by(func.min(Decision.created_at), Record.id)
        )
        return [
            training_label(_value(final), [_value(vote) for vote in votes]) == 1
            for final, votes, _ in rows
        ]

    async def _remaining(self, access: ProjectAccess, stage: ScreeningStage) -> int:
        """What is left for me, as my queue counts it (split assignment included)."""
        from app.services.screening import ScreeningService

        waiting = ScreeningService(self._db).waiting(access, stage)
        count = await self._db.scalar(select(func.count()).select_from(Record).where(*waiting))
        return int(count or 0)


def _eligible(project_id: uuid.UUID, stage: ScreeningStage) -> list[Any]:
    conditions: list[Any] = [Record.project_id == project_id, Record.is_duplicate.is_(False)]
    if stage is ScreeningStage.FULL_TEXT:
        conditions.append(Record.ta_final == TitleAbstractStatus.INCLUDED)
    return conditions


def _curve(sequence: list[bool]) -> Curve:
    return Curve(
        screened=len(sequence),
        found_at=[index + 1 for index, found in enumerate(sequence) if found],
    )


def _value(item: object) -> str:
    return str(getattr(item, "value", item))
