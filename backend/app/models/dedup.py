"""Duplicate clusters and their members (guide 6.1, 8.4).

A cluster is what one run of the algorithm in 9.1 believes to be the same work, found
more than once. Nothing is deleted when a cluster is merged: the secondaries keep their
rows and gain `is_duplicate` and `duplicate_of`, because PRISMA has to report them.
"""

import enum
import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Index, PrimaryKeyConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamps, UUIDPrimaryKey, pg_enum


class ClusterStatus(enum.StrEnum):
    PENDING = "pending"  # waiting for someone to decide
    RESOLVED = "resolved"  # merged: one primary, the rest marked as duplicates
    IGNORED = "ignored"  # looked at and kept apart ("not duplicates")


class DupCluster(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "dup_clusters"
    __table_args__ = (
        # The review screen asks for one project's pending clusters, worst score first.
        Index("ix_dup_clusters_project_id_status", "project_id", "status"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE")
    )
    status: Mapped[ClusterStatus] = mapped_column(
        pg_enum(ClusterStatus, "dup_status"),
        default=ClusterStatus.PENDING,
        server_default="pending",
    )
    # The weakest edge holding the cluster together: 1.0 for an exact DOI or PubMed id.
    score: Mapped[float] = mapped_column(Float)
    # Whether the algorithm is confident enough to merge this without being asked
    # (exact identifiers, or a score at or above 0.98, and no conflicting DOI anywhere).
    auto_resolvable: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class DupClusterMember(Base):
    __tablename__ = "dup_cluster_members"
    __table_args__ = (
        PrimaryKeyConstraint("cluster_id", "record_id"),
        # A record's clusters, for the record detail panel and for pruning a rerun.
        Index("ix_dup_cluster_members_record_id", "record_id"),
    )

    cluster_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dup_clusters.id", ondelete="CASCADE")
    )
    record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("records.id", ondelete="CASCADE")
    )
    # The record the algorithm would keep: the most complete one (guide 9.1 step 5).
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
