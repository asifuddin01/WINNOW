"""Finding and reviewing duplicates: /api/v1/projects/{pid}/dedup (guide 10).

Running deduplication and merging are an admin's job, the same as importing (guide 7);
any member may look at what it found.
"""

import uuid

from fastapi import APIRouter

from app.api.deps import ActorDep, AdminAccess, DedupDep, ViewerAccess
from app.api.responses import CONFLICT, PROJECT
from app.models import ClusterStatus
from app.schemas.dedup import (
    AutoResolve,
    ClusterOut,
    DedupStarted,
    DedupSummary,
    MergeCluster,
    MergeResult,
)
from app.schemas.problem import problem_content

router = APIRouter(prefix="/projects/{pid}/dedup", tags=["dedup"])


@router.post("/run", responses=PROJECT)
async def run_dedup(access: AdminAccess, dedup: DedupDep, actor: ActorDep) -> DedupStarted:
    """Look for duplicates across everything imported so far (guide 9.1)."""
    return await dedup.run(access, actor)


@router.get("/summary", responses=PROJECT)
async def dedup_summary(access: ViewerAccess, dedup: DedupDep) -> DedupSummary:
    """How many groups are waiting, and how many duplicates have been merged."""
    return await dedup.summary(access)


@router.get("/clusters", responses=PROJECT)
async def list_clusters(
    access: ViewerAccess, dedup: DedupDep, status: ClusterStatus = ClusterStatus.PENDING
) -> list[ClusterOut]:
    """Groups of records that look like the same work, least certain first."""
    return await dedup.clusters(access, status)


@router.post("/clusters/{cid}/merge", responses={**PROJECT, **CONFLICT, 422: problem_content()})
async def merge_cluster(
    cid: uuid.UUID, body: MergeCluster, access: AdminAccess, dedup: DedupDep, actor: ActorDep
) -> MergeResult:
    """Keep one record of the group; the rest become its duplicates (never deleted)."""
    return await dedup.merge(access, cid, body.primary_id, actor)


@router.post("/clusters/{cid}/ignore", responses={**PROJECT, **CONFLICT})
async def ignore_cluster(
    cid: uuid.UUID, access: AdminAccess, dedup: DedupDep, actor: ActorDep
) -> ClusterOut:
    """ "Not duplicates": these are different works, and Winnow stops asking."""
    return await dedup.ignore(access, cid, actor)


@router.post("/auto-resolve", responses=PROJECT)
async def auto_resolve(
    body: AutoResolve, access: AdminAccess, dedup: DedupDep, actor: ActorDep
) -> MergeResult:
    """Merge every group Winnow is sure about in one go (guide 8.4)."""
    return await dedup.auto_resolve(access, body.min_score, actor)
