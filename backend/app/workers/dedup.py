"""The deduplication job: find the same work imported twice (guide 8.4, 9.1).

The algorithm itself is pure and lives in `app.dedup`. This is the adapter around it: it
loads a project's live records, asks PostgreSQL for the trigram candidates that in-process
blocking cannot see (block C), stores the clusters, and — when the project allows it —
merges the ones the algorithm is certain about.
"""

import uuid
from dataclasses import dataclass
from typing import Any

import structlog
from redis.asyncio import Redis
from sqlalchemy import Row, and_, delete, func, insert, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from app.dedup import Cluster, RecordForDedup, cluster
from app.models import ClusterStatus, DupCluster, DupClusterMember, Project, Record
from app.models.base import uuid7
from app.schemas.projects import ProjectSettings
from app.services import events
from app.services.dedup import merge_clusters
from app.services.dedup_blocks import merged, split_certain, token_pairs

log = structlog.get_logger(__name__)

# Guide 9.1 block C: pg_trgm similarity over title_norm, through the GIN index.
TRIGRAM_THRESHOLD = 0.6
# A cap on what the database hands back, so one project of near-identical titles cannot
# turn into a pairwise explosion.
MAX_TRIGRAM_PAIRS = 100_000
# The trigram self-join only for small reviews. A review is about one topic, so its titles
# share most of their trigrams ("kidney", "ct", "segmentation") and every index probe
# returns much of the table: on a real 8,278-record scoping review the join ran past 60 s,
# where the word block in `app.services.dedup_blocks` took under a second and, measured
# against a real search's provenance, missed nothing.
TRIGRAM_MAX_RECORDS = 1_000
# And even there, never long enough to matter.
TRIGRAM_TIMEOUT_MS = 5_000

FIELDS = (
    Record.id,
    Record.title,
    Record.title_norm,
    Record.authors,
    Record.year,
    Record.journal,
    Record.volume,
    Record.issue,
    Record.pages,
    Record.doi_norm,
    Record.pmid,
    Record.abstract,
    Record.created_at,
)


@dataclass(frozen=True, slots=True)
class DedupResult:
    records: int
    clusters: int
    duplicates: int
    auto_resolved: int


def _for_dedup(row: Row[Any]) -> RecordForDedup:
    return RecordForDedup(
        id=row.id,
        title=row.title or "",
        title_norm=row.title_norm or "",
        authors=tuple(row.authors or ()),
        year=row.year,
        journal=row.journal,
        volume=row.volume,
        issue=row.issue,
        pages=row.pages,
        doi_norm=row.doi_norm,
        pmid=row.pmid,
        abstract_present=bool(row.abstract and row.abstract.strip()),
        imported_at=row.created_at,
    )


async def load_records(session: AsyncSession, project_id: uuid.UUID) -> list[RecordForDedup]:
    """Every record still in the review: merged duplicates are already settled."""
    rows = await session.execute(
        select(*FIELDS).where(Record.project_id == project_id, Record.is_duplicate.is_(False))
    )
    return [_for_dedup(row) for row in rows]


async def trigram_pairs(
    sessionmaker: async_sessionmaker[AsyncSession], project_id: uuid.UUID
) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """Block C through the database, bounded by a statement timeout (see TRIGRAM_*).

    It runs in a session of its own that is never committed, so the timeout and threshold
    set for it are rolled back with it. If it runs out of time, the word block stands in.
    """
    try:
        async with sessionmaker() as session:
            await session.execute(
                select(func.set_config("statement_timeout", str(TRIGRAM_TIMEOUT_MS), True))
            )
            return await _trigram_query(session, project_id)
    except DBAPIError:
        log.warning("dedup.trigram_skipped", project_id=str(project_id))
        return []


async def _trigram_query(
    session: AsyncSession, project_id: uuid.UUID
) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """Block C: pairs whose titles are similar enough for the trigram index to say so.

    This is the block the pure package cannot do, because it is the database that holds
    the index. `%>` is pg_trgm's word-similarity operator, which answers through the GIN
    index on `title_norm`, so a subtitle or a trailing "[Erratum]" cannot hide a duplicate
    from blocks A and B. The threshold is set for this transaction only.
    """
    await session.execute(
        select(func.set_config("pg_trgm.word_similarity_threshold", str(TRIGRAM_THRESHOLD), True))
    )
    other = aliased(Record)
    rows = await session.execute(
        select(Record.id, other.id)
        .join(
            other,
            and_(
                other.project_id == Record.project_id,
                Record.id < other.id,
                other.is_duplicate.is_(False),
                # pg_trgm word similarity, through the index (guide 9.1 block C).
                Record.title_norm.op("%>", is_comparison=True)(other.title_norm),
            ),
        )
        .where(
            Record.project_id == project_id,
            Record.is_duplicate.is_(False),
            Record.title_norm != "",
        )
        .limit(MAX_TRIGRAM_PAIRS)
    )
    return [(left, right) for left, right in rows]


async def _settings(
    sessionmaker: async_sessionmaker[AsyncSession], project_id: uuid.UUID
) -> ProjectSettings:
    async with sessionmaker() as session:
        return await _settings_of(session, project_id)


async def _settings_of(session: AsyncSession, project_id: uuid.UUID) -> ProjectSettings:
    raw = await session.scalar(select(Project.settings).where(Project.id == project_id))
    return ProjectSettings.model_validate(raw or {})


async def _decided_member_sets(
    session: AsyncSession, project_id: uuid.UUID
) -> set[frozenset[uuid.UUID]]:
    """The exact groups someone has already merged or set apart, so a rerun stays quiet."""
    rows = await session.execute(
        select(DupCluster.id, DupClusterMember.record_id)
        .join(DupClusterMember, DupClusterMember.cluster_id == DupCluster.id)
        .where(
            DupCluster.project_id == project_id,
            DupCluster.status != ClusterStatus.PENDING,
        )
    )
    members: dict[uuid.UUID, set[uuid.UUID]] = {}
    for cluster_id, record_id in rows:
        members.setdefault(cluster_id, set()).add(record_id)
    return {frozenset(ids) for ids in members.values()}


async def _replace_pending(
    session: AsyncSession, project_id: uuid.UUID, clusters: list[Cluster]
) -> int:
    """Swap this project's pending clusters for the ones this run found."""
    await session.execute(
        delete(DupCluster).where(
            DupCluster.project_id == project_id, DupCluster.status == ClusterStatus.PENDING
        )
    )
    decided = await _decided_member_sets(session, project_id)
    rows: list[dict[str, Any]] = []
    members: list[dict[str, Any]] = []
    for found in clusters:
        if frozenset(found.members) in decided:
            continue
        cluster_id = uuid7()
        rows.append(
            {
                "id": cluster_id,
                "project_id": project_id,
                "status": ClusterStatus.PENDING,
                "score": min(found.score, 1.0),
                "auto_resolvable": found.auto_resolvable,
            }
        )
        members.extend(
            {
                "cluster_id": cluster_id,
                "record_id": member_id,
                "is_primary": member_id == found.primary_id,
            }
            for member_id in found.members
        )
    # A review of 50,000 records can produce thousands of clusters; they go in together.
    if rows:
        await session.execute(insert(DupCluster), rows)
        await session.execute(insert(DupClusterMember), members)
    return len(rows)


# If imports keep landing while a run works, it looks again — but not for ever.
MAX_PASSES = 3


async def _live_count(session: AsyncSession, project_id: uuid.UUID) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(Record)
        .where(Record.project_id == project_id, Record.is_duplicate.is_(False))
    )
    return count or 0


async def run_dedup(
    *,
    sessionmaker: async_sessionmaker[AsyncSession],
    redis: Redis,
    project_id: uuid.UUID,
) -> DedupResult:
    """Run 9.1 until the review stops changing under it.

    Only one run per review is ever queued (`enqueue_dedup`), so an import that finishes
    while this one works cannot queue its own; instead, when a pass ends and there are
    records it did not see, it goes round again.
    """
    await events.publish(redis, project_id, "dedup.started", {})
    total = DedupResult(records=0, clusters=0, duplicates=0, auto_resolved=0)
    for _ in range(MAX_PASSES):
        result = await _one_pass(sessionmaker=sessionmaker, redis=redis, project_id=project_id)
        total = DedupResult(
            records=result.records,
            clusters=total.clusters + result.clusters,
            duplicates=total.duplicates + result.duplicates,
            auto_resolved=total.auto_resolved + result.auto_resolved,
        )
        async with sessionmaker() as session:
            live = await _live_count(session, project_id)
        # Everything live now was seen by this pass (merging only ever lowers the count).
        if live <= result.records - result.duplicates:
            break
    await events.publish(
        redis,
        project_id,
        "dedup.finished",
        {
            "records": total.records,
            "clusters": total.clusters - total.auto_resolved,
            "duplicates": total.duplicates,
            "auto_resolved": total.auto_resolved,
        },
    )
    return total


async def _one_pass(
    *,
    sessionmaker: async_sessionmaker[AsyncSession],
    redis: Redis,
    project_id: uuid.UUID,
) -> DedupResult:
    """Find duplicate clusters in one review, and merge the certain ones if allowed.

    Everything the algorithm needs is loaded once; the pairwise work is in memory, the
    two writes are one transaction each, and the review screen is told over the event
    stream when there is something new to look at.
    """
    async with sessionmaker() as session:
        records = await load_records(session, project_id)
    # Blocks A and B key on the start of a title; these two catch the rest: the word block
    # always, and the database's trigram index while the review is small enough for it.
    by_words = token_pairs(records)
    by_trigram = (
        await trigram_pairs(sessionmaker, project_id)
        if 0 < len(records) <= TRIGRAM_MAX_RECORDS
        else []
    )
    extra = merged(by_words, by_trigram)
    found = cluster(records, extra_pairs=extra) if len(records) > 1 else []
    settings = await _settings(sessionmaker, project_id)
    if settings.dedup_auto_resolve:
        # Identical copies inside an uncertain group are not a question for anyone.
        found = split_certain(found, records)

    async with sessionmaker() as session:
        saved = await _replace_pending(session, project_id, found)
        settings = await _settings_of(session, project_id)
        await session.commit()

    auto_resolved = 0
    duplicates = 0
    if settings.dedup_auto_resolve:
        async with sessionmaker() as session:
            rows = list(
                await session.execute(
                    select(DupClusterMember.cluster_id, DupClusterMember.record_id)
                    .join(DupCluster, DupCluster.id == DupClusterMember.cluster_id)
                    .where(
                        DupCluster.project_id == project_id,
                        DupCluster.status == ClusterStatus.PENDING,
                        DupCluster.auto_resolvable.is_(True),
                        DupClusterMember.is_primary.is_(True),
                    )
                )
            )
            chosen = [(cluster_id, record_id) for cluster_id, record_id in rows]
            duplicates = await merge_clusters(session, chosen, resolved_by=None)
            auto_resolved = len(chosen)
            await session.commit()

    result = DedupResult(
        records=len(records),
        clusters=saved,
        duplicates=duplicates,
        auto_resolved=auto_resolved,
    )
    log.info(
        "dedup.pass",
        project_id=str(project_id),
        records=result.records,
        clusters=result.clusters,
        auto_resolved=result.auto_resolved,
        candidate_pairs=len(extra),
        trigram_pairs=len(by_trigram),
    )
    return result
