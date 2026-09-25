"""Exports, backups and restores, made in the worker (guide 8.16).

Revision ID: e2bea7d974ea
Revises: 4a6c9bfb54e6
Create Date: 2026-09-25 01:28:57.090408
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e2bea7d974ea"
down_revision: str | Sequence[str] | None = "4a6c9bfb54e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "export_jobs",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("requested_by", sa.UUID(), nullable=True),
        sa.Column("kind", sa.Enum("records", "backup", name="export_kind"), nullable=False),
        sa.Column(
            "format",
            sa.Enum("csv", "xlsx", "ris", "bibtex", "zip", name="export_format"),
            nullable=False,
        ),
        sa.Column("filters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status",
            sa.Enum("queued", "running", "ready", "failed", name="job_status"),
            nullable=False,
        ),
        sa.Column("file_key", sa.Text(), nullable=True),
        sa.Column("filename", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("rows", sa.Integer(), nullable=True),
        sa.Column("problem", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
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
            name=op.f("fk_export_jobs_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name=op.f("fk_export_jobs_requested_by_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_export_jobs")),
    )
    op.create_index(op.f("ix_export_jobs_project_id"), "export_jobs", ["project_id"], unique=False)
    op.create_index(
        op.f("ix_export_jobs_requested_by"), "export_jobs", ["requested_by"], unique=False
    )
    op.create_table(
        "restore_jobs",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("zip_key", sa.Text(), nullable=True),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("queued", "running", "ready", "failed", name="job_status"),
            nullable=False,
        ),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("problem", sa.Text(), nullable=True),
        sa.Column("restored", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
            name=op.f("fk_restore_jobs_project_id_projects"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_restore_jobs_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_restore_jobs")),
    )
    op.create_index(op.f("ix_restore_jobs_user_id"), "restore_jobs", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_restore_jobs_user_id"), table_name="restore_jobs")
    op.drop_table("restore_jobs")
    op.drop_index(op.f("ix_export_jobs_requested_by"), table_name="export_jobs")
    op.drop_index(op.f("ix_export_jobs_project_id"), table_name="export_jobs")
    op.drop_table("export_jobs")
    for name in ("job_status", "export_format", "export_kind"):
        sa.Enum(name=name).drop(op.get_bind(), checkfirst=True)
