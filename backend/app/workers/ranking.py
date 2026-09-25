"""The ranking job: train on a stage's decisions and score what is left (guide 8.10, 9.2).

The model is `app.ranking`; this is the adapter around it. It reuses the review's TF-IDF
corpus while the records are unchanged, turns decisions into training labels, scores the
records still waiting at the stage, replaces the stage's scores in `record_scores`, and
records the run in `ranking_models`.
"""

import asyncio
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from redis.asyncio import Redis
from sqlalchemy import Text, cast, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import (
    Decision,
    FullTextStatus,
    Project,
    RankingModel,
    Record,
    RecordScore,
    ScreeningStage,
    TitleAbstractStatus,
)
from app.ranking.features import Corpus, build, text_of
from app.ranking.labels import training_label
from app.ranking.model import can_train, rank
from app.schemas.projects import ProjectSettings
from app.services import events
from app.services.ranking import mark_trained

log = structlog.get_logger(__name__)


# Corpora kept in this worker's memory; a 50,000-record review's is ~100 MB.
CACHED_CORPORA = 2


@dataclass(frozen=True)
class RankingResult:
    trained: bool
    labeled: int = 0
    included: int = 0
    scored: int = 0
    seconds: float = 0.0


class _Corpora:
    """The last few reviews' corpora, each valid while its records are unchanged."""

    def __init__(self, size: int) -> None:
        self._size = size
        self._items: OrderedDict[uuid.UUID, tuple[tuple[int, str], Corpus[uuid.UUID]]] = (
            OrderedDict()
        )

    def get(self, project_id: uuid.UUID, signature: tuple[int, str]) -> Corpus[uuid.UUID] | None:
        cached = self._items.get(project_id)
        if cached is None or cached[0] != signature:
            return None
        self._items.move_to_end(project_id)
        return cached[1]

    def put(
        self, project_id: uuid.UUID, signature: tuple[int, str], corpus: Corpus[uuid.UUID]
    ) -> None:
        self._items[project_id] = (signature, corpus)
        self._items.move_to_end(project_id)
        while len(self._items) > self._size:
            self._items.popitem(last=False)

    def clear(self) -> None:
        self._items.clear()


corpora = _Corpora(CACHED_CORPORA)


async def run_ranking(
    *,
    sessionmaker: async_sessionmaker[AsyncSession],
    redis: Redis,
    project_id: uuid.UUID,
    stage: ScreeningStage,
) -> RankingResult:
    started = time.perf_counter()
    async with sessionmaker() as session:
        project = await session.get(Project, project_id)
        if project is None or project.deleted_at is not None:
            return RankingResult(trained=False)
        settings = ProjectSettings.model_validate(project.settings)
        if not settings.ranking_enabled:
            return RankingResult(trained=False)

        counted = await mark_trained(redis, project_id, stage, begin=True)
        phases: dict[str, float] = {}
        clock = time.perf_counter()

        def lap(name: str) -> None:
            nonlocal clock
            now = time.perf_counter()
            phases[name] = round(now - clock, 3)
            clock = now

        labels, targets, decisions = await _labels(session, project_id, stage)
        lap("labels")
        if not can_train(labels):
            return RankingResult(trained=False, labeled=len(labels))
        corpus = await _corpus(session, project_id)
        lap("corpus")
        # Training is CPU work; off the event loop, so the worker's other jobs keep going.
        # ponytail: a thread cannot be stopped, so a run past the job's timeout keeps a
        # core busy until it ends (seen only on generated near-identical texts; real
        # 100,000-record reviews train in minutes). A process pool would make it
        # killable, at the price of the corpus cache.
        ranking = await asyncio.to_thread(rank, corpus, labels, targets)
        lap("train")
        await _write_scores(session, project_id, stage, ranking.scores)
        lap("write")
        seconds = round(time.perf_counter() - started, 3)
        await session.execute(
            update(RankingModel)
            .where(RankingModel.project_id == project_id, RankingModel.stage == stage)
            .values(is_active=False)
        )
        session.add(
            RankingModel(
                project_id=project_id,
                stage=stage,
                trained_at=datetime.now(UTC),
                n_labeled=ranking.n_labeled,
                n_included=ranking.n_included,
                metrics={
                    "auc": ranking.auc,
                    "scored": len(ranking.scores),
                    "seconds": seconds,
                    "decisions": decisions,
                    "vocabulary": corpus.matrix.shape[1],
                    "phases": phases,
                },
                is_active=True,
            )
        )
        await session.commit()

    await mark_trained(redis, project_id, stage, begin=False, counted=counted)
    # Tells open pages that the order and the model changed; it carries no decisions.
    await events.publish(redis, project_id, "ranking.updated", {"stage": stage.value})
    log.info(
        "ranking.trained",
        project_id=str(project_id),
        stage=stage.value,
        labeled=ranking.n_labeled,
        scored=len(ranking.scores),
        seconds=seconds,
        **phases,
    )
    return RankingResult(
        trained=True,
        labeled=ranking.n_labeled,
        included=ranking.n_included,
        scored=len(ranking.scores),
        seconds=seconds,
    )


async def _corpus(session: AsyncSession, project_id: uuid.UUID) -> Corpus[uuid.UUID]:
    """Every record of the review, duplicates included (their words are harmless and it
    keeps the corpus valid across merges). Rebuilt only when records come or go."""
    count, last = (
        await session.execute(
            select(func.count(), func.max(cast(Record.id, Text))).where(
                Record.project_id == project_id
            )
        )
    ).one()
    signature = (int(count), str(last))
    cached = corpora.get(project_id, signature)
    if cached is not None:
        return cached
    rows = await session.execute(
        select(Record.id, Record.title, Record.abstract, Record.keywords)
        .where(Record.project_id == project_id)
        .order_by(Record.id)
    )
    keys: list[uuid.UUID] = []
    texts: list[str] = []
    for record_id, title, abstract, keywords in rows:
        keys.append(record_id)
        texts.append(text_of(title, abstract, keywords or ()))
    corpus = await asyncio.to_thread(build, keys, texts)
    corpora.put(project_id, signature, corpus)
    return corpus


async def _labels(
    session: AsyncSession, project_id: uuid.UUID, stage: ScreeningStage
) -> tuple[dict[uuid.UUID, int], list[uuid.UUID], int]:
    """Training labels, the records to score, and how many decisions there were."""
    status = Record.ta_final if stage is ScreeningStage.TITLE_ABSTRACT else Record.ft_final
    conditions = [Record.project_id == project_id, Record.is_duplicate.is_(False)]
    if stage is ScreeningStage.FULL_TEXT:
        conditions.append(Record.ta_final == TitleAbstractStatus.INCLUDED)
    rows = await session.execute(
        select(
            Record.id,
            status,
            func.array_agg(Decision.decision).filter(Decision.id.is_not(None)),
        )
        .outerjoin(Decision, (Decision.record_id == Record.id) & (Decision.stage == stage))
        .where(*conditions)
        .group_by(Record.id)
    )
    waiting = {TitleAbstractStatus.PENDING.value, TitleAbstractStatus.CONFLICT.value}
    waiting |= {FullTextStatus.PENDING.value, FullTextStatus.CONFLICT.value}
    labels: dict[uuid.UUID, int] = {}
    targets: list[uuid.UUID] = []
    decisions = 0
    for record_id, final, cast_votes in rows:
        votes = [str(getattr(vote, "value", vote)) for vote in cast_votes or ()]
        decisions += len(votes)
        final_value = str(getattr(final, "value", final))
        label = training_label(final_value, votes)
        if label is not None:
            labels[record_id] = label
        if final_value in waiting:
            targets.append(record_id)
    return labels, targets, decisions


async def _write_scores(
    session: AsyncSession,
    project_id: uuid.UUID,
    stage: ScreeningStage,
    scores: dict[uuid.UUID, float],
) -> None:
    """Replace the stage's scores in one go: DELETE, then COPY. Scores of records that are
    no longer waiting go too, so the queue only ever orders by this run's scores."""
    await session.execute(
        delete(RecordScore).where(RecordScore.project_id == project_id, RecordScore.stage == stage)
    )
    if not scores:
        return
    connection = await session.connection()
    raw = await connection.get_raw_connection()
    driver = raw.driver_connection
    if driver is None:  # pragma: no cover - only if the driver changes
        raise RuntimeError("COPY needs the asyncpg connection behind SQLAlchemy")
    await driver.copy_records_to_table(
        "record_scores",
        records=[(record, stage.value, project_id, score) for record, score in scores.items()],
        columns=["record_id", "stage", "project_id", "score"],
    )
    # Fresh statistics for the planner: with none (a new table) or stale ones it read the
    # queue's "best first" by sorting the whole review, 200 ms instead of 20. ANALYZE
    # samples a fixed number of rows, so this costs the same however large the table grows.
    # A constant statement with nothing interpolated (guide 12.3's concern is built SQL).
    await driver.execute("ANALYZE record_scores")
