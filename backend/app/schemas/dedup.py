"""Request and response bodies for deduplication (guide 10)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models import ClusterStatus

AUTO_RESOLVE_SCORE = 0.98


class ClusterMember(BaseModel):
    """One record in a cluster, with everything the side-by-side comparison shows."""

    id: uuid.UUID
    is_primary: bool
    title: str | None
    authors: list[str]
    year: int | None
    journal: str | None
    volume: str | None
    issue: str | None
    pages: str | None
    doi: str | None
    pmid: str | None
    abstract: str | None
    url: str | None
    keywords: list[str]
    publication_type: list[str]
    is_duplicate: bool
    created_at: datetime
    # Which search brought this copy in: the difference that explains the duplicate.
    source: str | None = None
    database_name: str | None = None


class ClusterOut(BaseModel):
    id: uuid.UUID
    status: ClusterStatus
    # The weakest link holding the cluster together: 1.0 for an exact DOI or PubMed id.
    score: float
    auto_resolvable: bool
    members: list[ClusterMember]
    created_at: datetime


class DedupSummary(BaseModel):
    """What the duplicates screen says before you open it."""

    pending: int
    certain: int
    resolved: int
    ignored: int
    duplicates: int


class DedupStarted(BaseModel):
    job_id: str | None


class MergeCluster(BaseModel):
    primary_id: uuid.UUID


class AutoResolve(BaseModel):
    """Guide 8.4: merge everything at or above this score, plus the exact matches."""

    min_score: float = Field(default=AUTO_RESOLVE_SCORE, ge=0.9, le=1.0)


class MergeResult(BaseModel):
    cluster_id: uuid.UUID | None = None
    primary_id: uuid.UUID | None = None
    merged: int
    clusters: int = 1


__all__ = [
    "AUTO_RESOLVE_SCORE",
    "AutoResolve",
    "ClusterMember",
    "ClusterOut",
    "DedupStarted",
    "DedupSummary",
    "MergeCluster",
    "MergeResult",
]
