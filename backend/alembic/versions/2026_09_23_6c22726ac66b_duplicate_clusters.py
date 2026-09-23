"""Duplicate clusters and their members (guide 6.1, 8.4)

Revision ID: 6c22726ac66b
Revises: c5d7e99d96a5
Create Date: 2026-09-23 06:15:15.516842
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6c22726ac66b"
down_revision: str | Sequence[str] | None = "c5d7e99d96a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dup_clusters",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "resolved", "ignored", name="dup_status"),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("auto_resolvable", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("resolved_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_dup_clusters_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by"],
            ["users.id"],
            name=op.f("fk_dup_clusters_resolved_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dup_clusters")),
    )
    op.create_index(
        "ix_dup_clusters_project_id_status", "dup_clusters", ["project_id", "status"], unique=False
    )
    op.create_table(
        "dup_cluster_members",
        sa.Column("cluster_id", sa.UUID(), nullable=False),
        sa.Column("record_id", sa.UUID(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default="false", nullable=False),
        sa.ForeignKeyConstraint(
            ["cluster_id"],
            ["dup_clusters.id"],
            name=op.f("fk_dup_cluster_members_cluster_id_dup_clusters"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["record_id"],
            ["records.id"],
            name=op.f("fk_dup_cluster_members_record_id_records"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("cluster_id", "record_id", name=op.f("pk_dup_cluster_members")),
    )
    op.create_index(
        "ix_dup_cluster_members_record_id", "dup_cluster_members", ["record_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_dup_cluster_members_record_id", table_name="dup_cluster_members")
    op.drop_table("dup_cluster_members")
    op.drop_index("ix_dup_clusters_project_id_status", table_name="dup_clusters")
    op.drop_table("dup_clusters")
    op.execute("DROP TYPE IF EXISTS dup_status")
