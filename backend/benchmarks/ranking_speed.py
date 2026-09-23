"""Guide 9.2's budget: a 50,000-record review scores in under 10 seconds.

Runs the ranking job itself — database reads, training, scoring and the score writes —
on a review of 50,000 real abstracts (the SYNERGY records fetched by
`benchmarks/synergy.py`, repeated if there are fewer), in the *test* database, and removes
the review again. The first run builds the review's TF-IDF corpus; later runs reuse it, as
the worker does between imports.

    python -m benchmarks.ranking_speed [--records 50000] [--labelled 2000]
"""

import argparse
import asyncio
import csv
import random
import sys
import time
import uuid
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import delete, insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import (
    Decision,
    DecisionValue,
    Project,
    ProjectMember,
    ProjectRole,
    Record,
    ScreeningStage,
    User,
)
from app.models.base import uuid7
from app.schemas.projects import ProjectSettings
from app.security.permissions import ProjectAccess
from app.services.screening import ScreeningService
from app.workers.ranking import run_ranking
from benchmarks.ranking import DATA
from tests.conftest import _test_database_url, _test_redis_url

csv.field_size_limit(sys.maxsize)


def abstracts(count: int) -> list[tuple[str, str, int]]:
    rows: list[tuple[str, str, int]] = []
    for path in sorted(DATA.glob("*.csv")):
        with path.open(encoding="utf-8") as source:
            rows += [(r["title"], r["abstract"], int(r["label"])) for r in csv.DictReader(source)]
    if not rows:
        sys.exit("No SYNERGY data: run benchmarks/synergy.py first.")
    return [rows[index % len(rows)] for index in range(count)]


async def queue_timings(
    sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID, project_id: uuid.UUID
) -> None:
    """The next ten records in relevance order, as the screen asks for them (guide 2.2)."""
    async with sessions() as session:
        user = await session.get_one(User, user_id)
        project = await session.get_one(Project, project_id)
        member = await session.get_one(ProjectMember, (project_id, user_id))
        access = ProjectAccess(user=user, project=project, member=member)
        screening = ScreeningService(session)
        timings = []
        for _ in range(30):
            started = time.perf_counter()
            await screening.queue(access, stage=ScreeningStage.TITLE_ABSTRACT, n=10)
            timings.append((time.perf_counter() - started) * 1000)
    timings.sort()
    print(f"queue, relevance order      p50 {timings[14]:.0f} ms  p95 {timings[28]:.0f} ms")


async def main(records: int, labelled: int, *, keep: bool = False) -> None:
    engine = create_async_engine(_test_database_url())
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    redis = Redis.from_url(_test_redis_url(), decode_responses=True)
    now = datetime.now(UTC)
    user_id, project_id = uuid7(), uuid7()
    texts = abstracts(records)
    async with sessions() as session:
        # "!" is no Argon2 hash, so this account can never sign in; it is removed below.
        unusable = "!"
        session.add(
            User(
                id=user_id,
                email=f"speed-{user_id}@example.org",
                name="Speed",
                password_hash=unusable,
            )
        )
        await session.flush()
        session.add(
            Project(
                id=project_id,
                owner_id=user_id,
                title="Ranking speed",
                settings=ProjectSettings(reviewers_per_record_ta=1).model_dump(mode="json"),
            )
        )
        await session.flush()
        session.add(
            ProjectMember(
                project_id=project_id,
                user_id=user_id,
                role=ProjectRole.OWNER,
                stages=[ScreeningStage.TITLE_ABSTRACT.value, ScreeningStage.FULL_TEXT.value],
            )
        )
        await session.flush()
        ids = [uuid7() for _ in texts]
        for start in range(0, len(ids), 5_000):
            await session.execute(
                insert(Record),
                [
                    {
                        "id": record_id,
                        "project_id": project_id,
                        "title": title,
                        "abstract": abstract,
                        "authors": [],
                        "created_at": now,
                        "updated_at": now,
                    }
                    for record_id, (title, abstract, _) in zip(
                        ids[start : start + 5_000], texts[start : start + 5_000], strict=True
                    )
                ],
            )
        rng = random.Random(0)
        chosen = rng.sample(range(len(ids)), labelled)
        await session.execute(
            insert(Decision),
            [
                {
                    "id": uuid7(),
                    "project_id": project_id,
                    "record_id": ids[index],
                    "user_id": user_id,
                    "stage": ScreeningStage.TITLE_ABSTRACT,
                    "decision": DecisionValue.INCLUDE if texts[index][2] else DecisionValue.EXCLUDE,
                }
                for index in chosen
            ],
        )
        await session.commit()
    try:
        for run in ("cold (builds the corpus)", "warm", "warm"):
            started = time.perf_counter()
            result = await run_ranking(
                sessionmaker=sessions,
                redis=redis,
                project_id=project_id,
                stage=ScreeningStage.TITLE_ABSTRACT,
            )
            seconds = time.perf_counter() - started
            print(
                f"{run:26} {seconds:6.2f} s  trained={result.trained} "
                f"labelled={result.labeled:,} scored={result.scored:,}",
                flush=True,
            )
        await queue_timings(sessions, user_id, project_id)
    finally:
        if keep:
            print(f"kept project {project_id}")
        else:
            async with sessions() as session:
                await session.execute(delete(Project).where(Project.id == project_id))
                await session.execute(delete(User).where(User.id == user_id))
                await session.commit()
        await redis.aclose()
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=int, default=50_000)
    parser.add_argument("--labelled", type=int, default=2_000)
    parser.add_argument("--keep", action="store_true", help="leave the review for inspection")
    arguments = parser.parse_args()
    asyncio.run(main(arguments.records, arguments.labelled, keep=arguments.keep))
