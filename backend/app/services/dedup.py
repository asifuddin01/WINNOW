"""Reviewing duplicate clusters: run, read, merge, ignore, auto-resolve (guide 8.4).

Merging never deletes: the secondary keeps its row with `is_duplicate` and `duplicate_of`
set, because PRISMA reports how many duplicates were removed, and because someone has to
be able to see what was merged into what.
"""

import uuid
from datetime import UTC, datetime

from arq.connections import ArqRedis
from sqlalchemy import Select, Uuid, column, delete, func, select, tuple_, update, values
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ClusterStatus, DupCluster, DupClusterMember, ImportBatch, Record
from app.schemas.dedup import (
    ClusterMember,
    ClusterOut,
    DedupStarted,
    DedupSummary,
    MergeResult,
)
from app.security.permissions import ProjectAccess
from app.services import audit
from app.services.audit import Actor
from app.services.errors import ConflictError, NotFoundError, NotInClusterError

# The review screen shows the least certain clusters first: those are the ones that need
# a person. Certain ones are either already merged or one click away.
MAX_CLUSTERS = 500


async def merge_cluster(
    session: AsyncSession,
    cluster_row: DupCluster,
    primary_id: uuid.UUID,
    *,
    resolved_by: uuid.UUID | None,
    now: datetime | None = None,
) -> int:
    """Keep the primary, mark the rest as its duplicates, and move their work across."""
    member_ids = list(
        await session.scalars(
            select(DupClusterMember.record_id).where(DupClusterMember.cluster_id == cluster_row.id)
        )
    )
    secondaries = [record_id for record_id in member_ids if record_id != primary_id]
    if secondaries:
        await session.execute(
            update(Record)
            .where(Record.id.in_(secondaries))
            .values(
                is_duplicate=True,
                duplicate_of=primary_id,
                updated_at=now or datetime.now(UTC),
            )
        )
        await migrate_work(session, secondaries, primary_id)
    # The primary the person chose may not be the one the algorithm picked.
    await session.execute(
        update(DupClusterMember)
        .where(DupClusterMember.cluster_id == cluster_row.id)
        .values(is_primary=DupClusterMember.record_id == primary_id)
    )
    await session.execute(
        update(Record).where(Record.id == primary_id).values(is_duplicate=False, duplicate_of=None)
    )
    cluster_row.status = ClusterStatus.RESOLVED
    cluster_row.resolved_by = resolved_by
    return len(secondaries)


async def merge_clusters(
    session: AsyncSession,
    chosen: list[tuple[uuid.UUID, uuid.UUID]],
    *,
    resolved_by: uuid.UUID | None,
    now: datetime | None = None,
) -> int:
    """Merge many clusters at once: `chosen` is (cluster id, the record to keep).

    Auto-resolve on a large review settles thousands of clusters, and doing that one
    statement at a time is most of the time the whole run takes.
    """
    if not chosen:
        return 0
    when = now or datetime.now(UTC)
    cluster_ids = [cluster_id for cluster_id, _ in chosen]
    primary_by_cluster = dict(chosen)
    rows = await session.execute(
        select(DupClusterMember.cluster_id, DupClusterMember.record_id).where(
            DupClusterMember.cluster_id.in_(cluster_ids)
        )
    )
    secondaries = [
        {"rid": record_id, "primary": primary_by_cluster[cluster_id], "when": when}
        for cluster_id, record_id in rows
        if record_id != primary_by_cluster[cluster_id]
    ]
    if secondaries:
        # One statement for the whole batch: UPDATE ... FROM (VALUES …), so auto-resolving
        # thousands of clusters is one round trip rather than thousands.
        pairs = values(
            column("rid", Uuid(as_uuid=True)),
            column("kept", Uuid(as_uuid=True)),
            name="merged",
        ).data([(row["rid"], row["primary"]) for row in secondaries])
        await session.execute(
            update(Record)
            .where(Record.id == pairs.c.rid)
            .values(is_duplicate=True, duplicate_of=pairs.c.kept, updated_at=when)
            .execution_options(synchronize_session=None)
        )
        await migrate_work(session, [row["rid"] for row in secondaries], None)
    primaries = list(primary_by_cluster.values())
    await session.execute(
        update(Record).where(Record.id.in_(primaries)).values(is_duplicate=False, duplicate_of=None)
    )
    await session.execute(
        update(DupClusterMember)
        .where(DupClusterMember.cluster_id.in_(cluster_ids))
        .values(is_primary=False)
    )
    await session.execute(
        update(DupClusterMember)
        .where(tuple_(DupClusterMember.cluster_id, DupClusterMember.record_id).in_(chosen))
        .values(is_primary=True)
    )
    await session.execute(
        update(DupCluster)
        .where(DupCluster.id.in_(cluster_ids))
        .values(status=ClusterStatus.RESOLVED, resolved_by=resolved_by, updated_at=when)
    )
    return len(secondaries)


async def migrate_work(
    session: AsyncSession, secondaries: list[uuid.UUID], primary_id: uuid.UUID | None
) -> None:
    """Move decisions, labels and notes from the merged records onto the primary.

    Guide 8.4: what someone already did to a duplicate must not be lost when it is merged.
    Those tables arrive with screening in Phase 5, so today there is nothing to move; this
    is the one place that will have to know about them.
    """


class DedupService:
    def __init__(self, db: AsyncSession, queue: ArqRedis) -> None:
        self._db = db
        self._queue = queue

    # --- Running -----------------------------------------------------------------------

    async def run(self, access: ProjectAccess, actor: Actor) -> DedupStarted:
        """Hand the whole project to the worker (guide 8.4: it is never a request's job)."""
        from app.workers.settings import DEDUP_JOB

        audit.record(
            self._db,
            "dedup.started",
            actor,
            user_id=access.user.id,
            project_id=access.project_id,
            entity_type="project",
            entity_id=access.project_id,
        )
        await self._db.commit()
        job = await self._queue.enqueue_job(DEDUP_JOB, str(access.project_id))
        return DedupStarted(job_id=job.job_id if job else None)

    # --- Reading -----------------------------------------------------------------------

    async def summary(self, access: ProjectAccess) -> DedupSummary:
        """What is waiting: how many clusters, how many of them Winnow is sure about."""
        rows = await self._db.execute(
            select(DupCluster.status, func.count(), func.count().filter(DupCluster.auto_resolvable))
            .where(DupCluster.project_id == access.project_id)
            .group_by(DupCluster.status)
        )
        pending = resolved = ignored = certain = 0
        for status, count, auto in rows:
            if status is ClusterStatus.PENDING:
                pending, certain = count, auto
            elif status is ClusterStatus.RESOLVED:
                resolved = count
            else:
                ignored = count
        duplicates = await self._db.scalar(
            select(func.count())
            .select_from(Record)
            .where(Record.project_id == access.project_id, Record.is_duplicate.is_(True))
        )
        return DedupSummary(
            pending=pending,
            certain=certain,
            resolved=resolved,
            ignored=ignored,
            duplicates=duplicates or 0,
        )

    async def clusters(
        self, access: ProjectAccess, status: ClusterStatus = ClusterStatus.PENDING
    ) -> list[ClusterOut]:
        """The clusters to review, least certain first, each with its records side by side."""
        cluster_rows = list(
            await self._db.scalars(
                self._scoped(access, status)
                .order_by(DupCluster.score, DupCluster.id)
                .limit(MAX_CLUSTERS)
            )
        )
        if not cluster_rows:
            return []
        by_cluster = await self._members({row.id for row in cluster_rows})
        return [
            ClusterOut(
                id=row.id,
                status=row.status,
                score=row.score,
                auto_resolvable=row.auto_resolvable,
                created_at=row.created_at,
                members=by_cluster.get(row.id, []),
            )
            for row in cluster_rows
        ]

    async def cluster(self, access: ProjectAccess, cid: uuid.UUID) -> DupCluster:
        row = await self._db.scalar(
            select(DupCluster).where(
                DupCluster.id == cid, DupCluster.project_id == access.project_id
            )
        )
        if row is None:
            raise NotFoundError("That group of duplicates is no longer there.")
        return row

    # --- Deciding ----------------------------------------------------------------------

    async def merge(
        self, access: ProjectAccess, cid: uuid.UUID, primary_id: uuid.UUID, actor: Actor
    ) -> MergeResult:
        """Merge one cluster, keeping the record the reviewer chose."""
        row = await self.cluster(access, cid)
        if row.status is not ClusterStatus.PENDING:
            raise ConflictError("Someone has already decided about this group.")
        members = await self._db.scalars(
            select(DupClusterMember.record_id).where(DupClusterMember.cluster_id == row.id)
        )
        member_ids = set(members)
        if primary_id not in member_ids:
            raise NotInClusterError
        merged = await merge_cluster(self._db, row, primary_id, resolved_by=access.user.id)
        audit.record(
            self._db,
            "dedup.merged",
            actor,
            user_id=access.user.id,
            project_id=access.project_id,
            entity_type="dup_cluster",
            entity_id=row.id,
            after={"primary": str(primary_id), "merged": merged},
        )
        await self._db.commit()
        return MergeResult(cluster_id=row.id, primary_id=primary_id, merged=merged)

    async def ignore(self, access: ProjectAccess, cid: uuid.UUID, actor: Actor) -> ClusterOut:
        """ "Not duplicates": keep them apart, and do not ask again."""
        row = await self.cluster(access, cid)
        if row.status is not ClusterStatus.PENDING:
            raise ConflictError("Someone has already decided about this group.")
        row.status = ClusterStatus.IGNORED
        row.resolved_by = access.user.id
        audit.record(
            self._db,
            "dedup.ignored",
            actor,
            user_id=access.user.id,
            project_id=access.project_id,
            entity_type="dup_cluster",
            entity_id=row.id,
        )
        await self._db.commit()
        members = await self._members({row.id})
        return ClusterOut(
            id=row.id,
            status=row.status,
            score=row.score,
            auto_resolvable=row.auto_resolvable,
            created_at=row.created_at,
            members=members.get(row.id, []),
        )

    async def auto_resolve(
        self, access: ProjectAccess, min_score: float, actor: Actor
    ) -> MergeResult:
        """Merge every pending cluster Winnow is sure about (guide 8.4's bulk action).

        "Sure" means an exact DOI or PubMed id, or a score at or above `min_score`, and no
        conflicting DOI anywhere in the cluster.
        """
        rows = list(
            await self._db.scalars(
                self._scoped(access, ClusterStatus.PENDING).where(
                    DupCluster.auto_resolvable.is_(True) | (DupCluster.score >= min_score)
                )
            )
        )
        primaries = await self._db.execute(
            select(DupClusterMember.cluster_id, DupClusterMember.record_id).where(
                DupClusterMember.cluster_id.in_([row.id for row in rows]),
                DupClusterMember.is_primary.is_(True),
            )
        )
        merged = await merge_clusters(
            self._db,
            [(cluster_id, record_id) for cluster_id, record_id in primaries],
            resolved_by=access.user.id,
            now=datetime.now(UTC),
        )
        audit.record(
            self._db,
            "dedup.auto_resolved",
            actor,
            user_id=access.user.id,
            project_id=access.project_id,
            entity_type="project",
            entity_id=access.project_id,
            after={"clusters": len(rows), "merged": merged, "min_score": min_score},
        )
        await self._db.commit()
        return MergeResult(cluster_id=None, primary_id=None, merged=merged, clusters=len(rows))

    async def clear(self, access: ProjectAccess) -> int:
        """Drop the pending clusters, for a project that wants to start the review again."""
        pending = await self._db.scalar(
            select(func.count())
            .select_from(DupCluster)
            .where(
                DupCluster.project_id == access.project_id,
                DupCluster.status == ClusterStatus.PENDING,
            )
        )
        await self._db.execute(
            delete(DupCluster).where(
                DupCluster.project_id == access.project_id,
                DupCluster.status == ClusterStatus.PENDING,
            )
        )
        await self._db.commit()
        return pending or 0

    # --- Internals ---------------------------------------------------------------------

    @staticmethod
    def _scoped(access: ProjectAccess, status: ClusterStatus) -> Select[tuple[DupCluster]]:
        return select(DupCluster).where(
            DupCluster.project_id == access.project_id, DupCluster.status == status
        )

    async def _members(self, cluster_ids: set[uuid.UUID]) -> dict[uuid.UUID, list[ClusterMember]]:
        rows = await self._db.execute(
            select(
                DupClusterMember.cluster_id,
                DupClusterMember.is_primary,
                Record.id,
                Record.title,
                Record.authors,
                Record.year,
                Record.journal,
                Record.volume,
                Record.issue,
                Record.pages,
                Record.doi,
                Record.pmid,
                Record.abstract,
                Record.url,
                Record.keywords,
                Record.publication_type,
                Record.is_duplicate,
                Record.created_at,
                ImportBatch.source_name,
                ImportBatch.database_name,
            )
            .join(Record, Record.id == DupClusterMember.record_id)
            .outerjoin(ImportBatch, ImportBatch.id == Record.import_batch_id)
            .where(DupClusterMember.cluster_id.in_(cluster_ids))
            .order_by(DupClusterMember.is_primary.desc(), Record.created_at)
        )
        members: dict[uuid.UUID, list[ClusterMember]] = {}
        for row in rows:
            members.setdefault(row.cluster_id, []).append(
                ClusterMember(
                    id=row.id,
                    is_primary=row.is_primary,
                    title=row.title,
                    authors=row.authors,
                    year=row.year,
                    journal=row.journal,
                    volume=row.volume,
                    issue=row.issue,
                    pages=row.pages,
                    doi=row.doi,
                    pmid=row.pmid,
                    abstract=row.abstract,
                    url=row.url,
                    keywords=row.keywords,
                    publication_type=row.publication_type,
                    is_duplicate=row.is_duplicate,
                    created_at=row.created_at,
                    source=row.source_name,
                    database_name=row.database_name,
                )
            )
        return members
