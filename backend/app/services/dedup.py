"""Reviewing duplicate clusters: run, read, merge, ignore, auto-resolve (guide 8.4).

Merging never deletes: the secondary keeps its row with `is_duplicate` and `duplicate_of`
set, because PRISMA reports how many duplicates were removed, and because someone has to
be able to see what was merged into what.
"""

import uuid
from datetime import UTC, datetime

from arq.connections import ArqRedis
from sqlalchemy import Select, Uuid, column, delete, func, or_, select, update, values
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import (
    ClusterStatus,
    ConflictResolution,
    Decision,
    DupCluster,
    DupClusterMember,
    Fulltext,
    ImportBatch,
    Note,
    Project,
    Record,
    RecordLabel,
    ScanStatus,
    ScreeningStage,
    UnretrievableRecord,
)
from app.schemas.dedup import (
    ClusterMember,
    ClusterOut,
    DedupStarted,
    DedupSummary,
    MergeResult,
)
from app.schemas.projects import ProjectSettings
from app.security.permissions import ProjectAccess
from app.services import audit
from app.services.audit import Actor
from app.services.errors import ConflictError, NotFoundError, NotInClusterError
from app.services.status import recompute

# The review screen shows the least certain clusters first: those are the ones that need
# a person. Certain ones are either already merged or one click away.
MAX_CLUSTERS = 500
# How long to wait after an import before looking: a drop of twenty files finishes as
# twenty imports within seconds, and they should make one dedup run, not twenty.
SETTLE_SECONDS = 5


def dedup_job_id(project_id: uuid.UUID) -> str:
    """One dedup job per review at a time. Two at once would each replace the other's
    pending clusters and could merge the same records twice."""
    return f"dedup:{project_id}"


async def enqueue_dedup(queue: ArqRedis, project_id: uuid.UUID, *, settle: float = 0) -> str | None:
    """Queue a dedup run unless one is already queued or running for this review.

    arq refuses a second job with the same id, so a burst of imports collapses into the
    one run that is waiting; the run itself goes round again if records arrive while it
    works (see `run_dedup`).
    """
    from app.workers.settings import DEDUP_JOB

    job = await queue.enqueue_job(
        DEDUP_JOB,
        str(project_id),
        _job_id=dedup_job_id(project_id),
        _defer_by=settle or None,
    )
    return job.job_id if job else None


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
        # Whatever was merged into these earlier now points at the record that was kept.
        await session.execute(
            update(Record)
            .where(Record.duplicate_of.in_(secondaries))
            .values(duplicate_of=primary_id)
        )
        await migrate_work(session, [(copy, primary_id) for copy in secondaries])
    # The primary the person chose may not be the one the algorithm picked.
    await session.execute(
        update(DupClusterMember)
        .where(DupClusterMember.cluster_id == cluster_row.id)
        .values(is_primary=DupClusterMember.record_id == primary_id)
    )
    await session.execute(
        update(Record)
        .where(
            Record.id == primary_id,
            or_(Record.is_duplicate.is_(True), Record.duplicate_of.is_not(None)),
        )
        .values(is_duplicate=False, duplicate_of=None)
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
        # Copies merged earlier into a record that is itself merged now follow it, so
        # duplicate_of always names the record that was kept, never a link in a chain.
        await session.execute(
            update(Record)
            .where(Record.duplicate_of == pairs.c.rid)
            .values(duplicate_of=pairs.c.kept, updated_at=when)
            .execution_options(synchronize_session=None)
        )
        await migrate_work(session, [(row["rid"], row["primary"]) for row in secondaries])
    primaries = list(primary_by_cluster.values())
    # Only the kept records that were themselves marked as copies: rewriting a row that
    # would not change still writes a new version of it into every index (26 s for 5,000
    # at the Phase 9 audit).
    await session.execute(
        update(Record)
        .where(
            Record.id.in_(primaries),
            or_(Record.is_duplicate.is_(True), Record.duplicate_of.is_not(None)),
        )
        .values(is_duplicate=False, duplicate_of=None)
    )
    # Each cluster's primary, set against a VALUES list like the records above: an IN of
    # 5,000 (cluster, record) pairs took 22 s at the Phase 9 audit; this is one join.
    kept = values(
        column("cid", Uuid(as_uuid=True)),
        column("kept", Uuid(as_uuid=True)),
        name="kept",
    ).data(chosen)
    await session.execute(
        update(DupClusterMember)
        .where(DupClusterMember.cluster_id == kept.c.cid)
        .values(is_primary=DupClusterMember.record_id == kept.c.kept)
        .execution_options(synchronize_session=None)
    )
    await session.execute(
        update(DupCluster)
        .where(DupCluster.id.in_(cluster_ids))
        .values(status=ClusterStatus.RESOLVED, resolved_by=resolved_by, updated_at=when)
    )
    return len(secondaries)


async def migrate_work(session: AsyncSession, merged: list[tuple[uuid.UUID, uuid.UUID]]) -> None:
    """Move what people did to the merged copies onto the record that was kept (guide 8.4).

    `merged` is (the copy, the record kept). Decisions, labels, notes, resolutions and the
    full text (a PDF with its highlights, or a "not retrievable" mark) all follow; where
    the kept record already has a person's decision (or a resolution) for a stage, or a
    PDF, it stands and the copy's is left behind on the copy. Then the kept records'
    statuses are recomputed. Right after an import there is nothing to move, and one query
    says so.
    """
    if not merged:
        return
    copies = [copy for copy, _ in merged]
    touched = await session.scalar(
        select(
            select(Decision.id).where(Decision.record_id.in_(copies)).exists()
            | select(Note.id).where(Note.record_id.in_(copies)).exists()
            | select(RecordLabel.record_id).where(RecordLabel.record_id.in_(copies)).exists()
            | select(ConflictResolution.id).where(ConflictResolution.record_id.in_(copies)).exists()
            | select(Fulltext.id).where(Fulltext.record_id.in_(copies)).exists()
            | select(UnretrievableRecord.record_id)
            .where(UnretrievableRecord.record_id.in_(copies))
            .exists()
        )
    )
    if not touched:
        return

    by_kept: dict[uuid.UUID, list[uuid.UUID]] = {}
    for copy, kept in merged:
        by_kept.setdefault(kept, []).append(copy)
    for kept, sources in by_kept.items():
        await _move_decisions(session, sources, kept)
        await _move_resolutions(session, sources, kept)
        await _move_fulltext(session, sources, kept)
        await session.execute(
            update(Note)
            .where(Note.record_id.in_(sources))
            .values(record_id=kept)
            .execution_options(synchronize_session=None)
        )
        labels = (
            select(RecordLabel.label_id, RecordLabel.user_id)
            .where(RecordLabel.record_id.in_(sources))
            .distinct()
        )
        rows = [
            {"record_id": kept, "label_id": label_id, "user_id": user_id}
            for label_id, user_id in await session.execute(labels)
        ]
        if rows:
            await session.execute(pg_insert(RecordLabel).values(rows).on_conflict_do_nothing())

    project_id = await session.scalar(select(Record.project_id).where(Record.id == copies[0]))
    raw = await session.scalar(select(Project.settings).where(Project.id == project_id))
    if project_id is None:  # pragma: no cover - the records were just read
        return
    settings = ProjectSettings.model_validate(raw or {})
    for stage in ScreeningStage:
        await recompute(session, project_id, stage, settings, list(by_kept))


async def _move_decisions(session: AsyncSession, sources: list[uuid.UUID], kept: uuid.UUID) -> None:
    """Each person's latest decision per stage on the copies, where the kept record has
    none from them."""
    candidates = (
        select(Decision.id)
        .where(Decision.record_id.in_(sources))
        .distinct(Decision.user_id, Decision.stage)
        .order_by(Decision.user_id, Decision.stage, Decision.updated_at.desc())
    )
    taken = aliased(Decision)
    clash = (
        select(taken.id)
        .where(
            taken.record_id == kept,
            taken.user_id == Decision.user_id,
            taken.stage == Decision.stage,
        )
        .exists()
    )
    await session.execute(
        update(Decision)
        .where(Decision.id.in_(candidates), ~clash)
        .values(record_id=kept)
        .execution_options(synchronize_session=None)
    )


async def _move_fulltext(session: AsyncSession, sources: list[uuid.UUID], kept: uuid.UUID) -> None:
    """A copy's PDF (a readable one first, then the newest), where the kept record has
    none; failing that, a copy's "not retrievable" mark."""
    if await session.scalar(select(Fulltext.id).where(Fulltext.record_id == kept)):
        return
    best = await session.scalar(
        select(Fulltext.id)
        .where(Fulltext.record_id.in_(sources))
        .order_by(
            Fulltext.scan_status.in_([ScanStatus.CLEAN, ScanStatus.SKIPPED]).desc(),
            Fulltext.created_at.desc(),
        )
        .limit(1)
    )
    if best is not None:
        await session.execute(
            update(Fulltext)
            .where(Fulltext.id == best)
            .values(record_id=kept)
            .execution_options(synchronize_session=None)
        )
        # A PDF found after all outweighs "not retrievable".
        await session.execute(
            delete(UnretrievableRecord).where(UnretrievableRecord.record_id == kept)
        )
        return
    if await session.scalar(
        select(UnretrievableRecord.record_id).where(UnretrievableRecord.record_id == kept)
    ):
        return
    mark = await session.scalar(
        select(UnretrievableRecord.record_id)
        .where(UnretrievableRecord.record_id.in_(sources))
        .limit(1)
    )
    if mark is not None:
        await session.execute(
            update(UnretrievableRecord)
            .where(UnretrievableRecord.record_id == mark)
            .values(record_id=kept)
            .execution_options(synchronize_session=None)
        )


async def _move_resolutions(
    session: AsyncSession, sources: list[uuid.UUID], kept: uuid.UUID
) -> None:
    candidates = (
        select(ConflictResolution.id)
        .where(ConflictResolution.record_id.in_(sources))
        .distinct(ConflictResolution.stage)
        .order_by(ConflictResolution.stage, ConflictResolution.updated_at.desc())
    )
    taken = aliased(ConflictResolution)
    clash = (
        select(taken.id)
        .where(taken.record_id == kept, taken.stage == ConflictResolution.stage)
        .exists()
    )
    await session.execute(
        update(ConflictResolution)
        .where(ConflictResolution.id.in_(candidates), ~clash)
        .values(record_id=kept)
        .execution_options(synchronize_session=None)
    )


class DedupService:
    def __init__(self, db: AsyncSession, queue: ArqRedis) -> None:
        self._db = db
        self._queue = queue

    # --- Running -----------------------------------------------------------------------

    async def run(self, access: ProjectAccess, actor: Actor) -> DedupStarted:
        """Hand the whole project to the worker (guide 8.4: it is never a request's job).

        If a run is already queued or under way, that run is the answer: it will see
        everything this one would have.
        """
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
        job_id = await enqueue_dedup(self._queue, access.project_id)
        return DedupStarted(job_id=job_id or dedup_job_id(access.project_id))

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
