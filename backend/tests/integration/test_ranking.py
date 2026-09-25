"""Relevance ranking end to end (guide 8.5, 8.10, 9.2): the job, the order it gives the
queue, when it retrains, the recall curve, the stopping-rule helper, and who sees what."""

import uuid

from arq.connections import ArqRedis
from arq.constants import default_queue_name, job_key_prefix
from arq.jobs import Job, JobStatus
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Decision, DecisionValue, RankingModel, Record, RecordScore, ScreeningStage
from app.services.ranking import RETRAIN_AFTER, mark_trained, ranking_job_id
from app.services.screening import _start_for
from app.workers.ranking import RankingResult, run_ranking
from tests.conftest import MemoryMailer
from tests.project_helpers import add_member, api, get, person, post
from tests.screening_helpers import add_records, decide, settings, team

TA = ScreeningStage.TITLE_ABSTRACT
KIDNEY = {
    "title": "Deep learning segmentation of kidney tumours on contrast CT",
    "abstract": "Renal tumour segmentation with convolutional networks in adults.",
}
HEART = {
    "title": "Heart valve surgery outcomes in older patients",
    "abstract": "A randomised trial of valve replacement and survival after surgery.",
}


async def train(db_app: FastAPI, pid: str) -> RankingResult:
    return await run_ranking(
        sessionmaker=db_app.state.sessionmaker,
        redis=db_app.state.redis,
        project_id=uuid.UUID(pid),
        stage=TA,
    )


async def forget(queue: ArqRedis, job_id: str) -> None:
    """Take a queued job back out, as if the worker had run it."""
    await queue.delete(f"{job_key_prefix}{job_id}")
    await queue.zrem(default_queue_name, job_id)


async def me(client: AsyncClient) -> uuid.UUID:
    return uuid.UUID((await get(client, "/auth/me")).json()["id"])


async def test_the_first_model_comes_with_the_first_include_and_ranks_what_is_left(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer, records=0) as t:
        await settings(t.owner, t.pid, reviewers_per_record_ta=1)
        kidney = await add_records(db, t.pid, 15, **KIDNEY)
        heart = await add_records(db, t.pid, 15, **HEART)
        for record in heart[:5]:
            await decide(t.owner, t.pid, record, "exclude")

        # Excludes alone teach nothing about what is relevant.
        assert (await train(db_app, t.pid)).trained is False
        status = (await get(t.owner, f"/projects/{t.pid}/ranking/status")).json()
        assert status["model"] is None
        assert (status["needs_each"], status["have_included"], status["have_excluded"]) == (1, 0, 5)

        await decide(t.owner, t.pid, kidney[0], "include")
        result = await train(db_app, t.pid)
        assert result.trained is True
        assert (result.labeled, result.scored) == (6, 24)
        scores = dict(
            (
                await db.execute(
                    select(RecordScore.record_id, RecordScore.score).where(RecordScore.stage == TA)
                )
            )
            .tuples()
            .all()
        )
        assert set(scores) == set(kidney[1:] + heart[5:])
        assert min(scores[r] for r in kidney[1:]) > max(scores[r] for r in heart[5:])
        model = await db.scalar(select(RankingModel).where(RankingModel.is_active.is_(True)))
        assert model is not None
        assert (model.n_labeled, model.n_included) == (6, 1)

        # The owner sees what the model learnt from; a reviewer screening blind does not.
        status = (await get(t.owner, f"/projects/{t.pid}/ranking/status")).json()
        assert status["model"]["n_labeled"] == 6
        blind = (await get(t.reviewer, f"/projects/{t.pid}/ranking/status")).json()
        assert blind["model"]["n_labeled"] is None
        assert blind["model"]["auc"] is None
        assert blind["have_included"] is None

        # Relevance order: the kidney records come first for the reviewer.
        queue = (await get(t.reviewer, f"/projects/{t.pid}/screening/queue?n=10")).json()
        first = {uuid.UUID(item["id"]) for item in queue["items"][:9]}
        assert first <= set(kidney)


async def test_the_queue_reads_further_when_the_best_scores_are_used_up(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    """The best scores are read 20n at a time: with all of the first 20 already held by
    the screen, the next record is the 21st best, from a longer read."""
    async with team(db_app, db, mailer, records=40) as t:
        by_score = list(t.records)
        db.add_all(
            RecordScore(record_id=record, stage=TA, project_id=uuid.UUID(t.pid), score=1 - i / 100)
            for i, record in enumerate(by_score)
        )
        await db.commit()
        held = "&".join(f"exclude={record}" for record in by_score[:20])
        queue = (await get(t.reviewer, f"/projects/{t.pid}/screening/queue?n=1&{held}")).json()
        assert [uuid.UUID(item["id"]) for item in queue["items"]] == [by_score[20]]


async def test_one_record_in_twenty_comes_from_random_order(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    """Guide 9.2's exploration: the 20th record served is the next in the reviewer's
    random order, not the 20th best."""
    async with team(db_app, db, mailer, records=40) as t:
        by_score = list(t.records)
        db.add_all(
            RecordScore(record_id=record, stage=TA, project_id=uuid.UUID(t.pid), score=1 - i / 100)
            for i, record in enumerate(by_score)
        )
        # The lowest-scored record is the first in this reviewer's random order.
        start = _start_for(await me(t.reviewer))
        await db.execute(update(Record).where(Record.id.in_(by_score)).values(sort_key=start / 2))
        await db.execute(update(Record).where(Record.id == by_score[-1]).values(sort_key=start))
        await db.commit()

        queue = (await get(t.reviewer, f"/projects/{t.pid}/screening/queue?n=25")).json()
        served = [uuid.UUID(item["id"]) for item in queue["items"]]
        assert served[:19] == by_score[:19]
        assert served[19] == by_score[-1]
        assert served[20:] == by_score[19:24]

        # With ranking off, "relevance" is the random order.
        await settings(t.owner, t.pid, ranking_enabled=False)
        unranked = (await get(t.reviewer, f"/projects/{t.pid}/screening/queue?n=5")).json()
        assert uuid.UUID(unranked["items"][0]["id"]) == by_score[-1]


async def test_decisions_queue_a_retrain_after_every_twenty_five(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer, records=RETRAIN_AFTER + 2) as t:
        queue = db_app.state.queue
        job = Job(ranking_job_id(uuid.UUID(t.pid), TA), queue)
        # No model yet: any decision may be the one that makes training possible.
        await decide(t.reviewer, t.pid, t.records[0], "include")
        assert await job.status() is JobStatus.deferred

        await forget(queue, job.job_id)
        # A model now exists, and the decision above is the one it was trained on.
        await mark_trained(db_app.state.redis, uuid.UUID(t.pid), TA, begin=False, counted=1)
        for record in t.records[1:RETRAIN_AFTER]:
            await decide(t.reviewer, t.pid, record, "exclude")
        assert await job.status() is JobStatus.not_found
        await decide(t.reviewer, t.pid, t.records[RETRAIN_AFTER], "exclude")
        assert await job.status() is JobStatus.deferred

        # And on demand.
        await forget(queue, job.job_id)
        started = await post(t.reviewer, f"/projects/{t.pid}/ranking/train")
        assert started.status_code == 202
        assert started.json() == {"queued": True}
        status = (await get(t.reviewer, f"/projects/{t.pid}/ranking/status")).json()
        assert status["training"] is True


async def test_the_stopping_rule_speaks_up_only_with_a_model_and_a_long_run_of_excludes(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer, records=0) as t:
        await settings(t.owner, t.pid, reviewers_per_record_ta=1)
        relevant = await add_records(db, t.pid, 10, **KIDNEY)
        other = await add_records(db, t.pid, 230, **HEART)
        reviewer = await me(t.reviewer)
        db.add_all(
            Decision(
                project_id=uuid.UUID(t.pid),
                record_id=record,
                user_id=reviewer,
                stage=TA,
                decision=DecisionValue.INCLUDE if record in relevant else DecisionValue.EXCLUDE,
            )
            for record in [*relevant, *other[:210]]
        )
        await db.commit()
        path = f"/projects/{t.pid}/screening/stopping"

        # 210 excludes in a row, but no model yet: nothing to say.
        advice = (await get(t.reviewer, path)).json()
        assert (advice["in_a_row"], advice["threshold"], advice["remaining"]) == (210, 200, 20)
        assert advice["estimate"] is None

        assert (await train(db_app, t.pid)).trained is True
        advice = (await get(t.reviewer, path)).json()
        estimate = advice["estimate"]
        assert estimate is not None
        assert 0 <= estimate["low"] <= estimate["expected"] <= estimate["high"] <= 20
        # The same answer again, from the cache.
        assert (await get(t.reviewer, path)).json()["estimate"] == estimate

        await settings(t.owner, t.pid, stopping_rule={"type": "consecutive_excludes", "n": 500})
        assert (await get(t.reviewer, path)).json()["estimate"] is None


async def test_the_recall_curve_shows_mine_and_only_the_unblinded_see_the_team(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer, records=4) as t:
        first, second, third, _ = t.records
        await decide(t.reviewer, t.pid, first, "include")
        await decide(t.reviewer, t.pid, second, "exclude")
        await decide(t.reviewer, t.pid, third, "maybe")
        await decide(t.owner, t.pid, second, "include")

        mine = (await get(t.reviewer, f"/projects/{t.pid}/ranking/curve")).json()
        assert mine["total"] == 4
        assert mine["mine"] == {"screened": 3, "found_at": [1, 3]}
        assert mine["team"] is None

        owner = (await get(t.owner, f"/projects/{t.pid}/ranking/curve")).json()
        assert owner["mine"] == {"screened": 1, "found_at": [1]}
        # The team: three records decided; the second is a tie (include, exclude).
        assert owner["team"] == {"screened": 3, "found_at": [1, 3]}


async def test_viewers_may_look_but_not_ask(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with (
        team(db_app, db, mailer) as t,
        person(db_app, mailer, "vi@example.org", ip="10.9.0.9") as viewer,
    ):
        await add_member(t.owner, viewer, t.pid, "vi@example.org", role="viewer")
        base = f"/projects/{t.pid}"
        assert (await get(viewer, f"{base}/ranking/status")).status_code == 200
        assert (await get(viewer, f"{base}/ranking/curve")).status_code == 200
        assert (await get(viewer, f"{base}/screening/stopping")).status_code == 403
        assert (await post(viewer, f"{base}/ranking/train")).status_code == 403


async def test_nothing_runs_for_a_review_that_is_gone_or_has_ranking_off(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    missing = await run_ranking(
        sessionmaker=db_app.state.sessionmaker,
        redis=db_app.state.redis,
        project_id=uuid.uuid4(),
        stage=TA,
    )
    assert missing.trained is False
    async with team(db_app, db, mailer) as t:
        await settings(t.owner, t.pid, ranking_enabled=False)
        assert (await train(db_app, t.pid)).trained is False
        started = await post(t.owner, f"/projects/{t.pid}/ranking/train")
        assert started.json() == {"queued": False}


async def test_a_deleted_review_is_not_ranked(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer, records=12) as t:
        await settings(t.owner, t.pid, reviewers_per_record_ta=1)
        for index, record in enumerate(t.records[:10]):
            await decide(t.owner, t.pid, record, "include" if index < 5 else "exclude")
        deleted = await api(t.owner, "DELETE", f"/projects/{t.pid}")
        assert deleted.status_code == 204
        assert (await train(db_app, t.pid)).trained is False
