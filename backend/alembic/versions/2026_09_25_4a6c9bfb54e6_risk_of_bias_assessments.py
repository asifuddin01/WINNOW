"""Risk-of-bias assessments: one per record, person and tool, with its version (8.13).

Revision ID: 4a6c9bfb54e6
Revises: 706688f42f16
Create Date: 2026-09-25 01:13:47.771964
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "4a6c9bfb54e6"
down_revision: str | Sequence[str] | None = "706688f42f16"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rob_assessments",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("record_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("tool_key", sa.Text(), nullable=False),
        sa.Column("tool_version", sa.Text(), nullable=False),
        sa.Column("variant_key", sa.Text(), nullable=False),
        sa.Column("answers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("judgements", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("support", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("overall", sa.Text(), nullable=True),
        sa.Column("status", sa.Enum("draft", "submitted", name="rob_status"), nullable=False),
        sa.Column("final", sa.Boolean(), nullable=False),
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
            name=op.f("fk_rob_assessments_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["record_id"],
            ["records.id"],
            name=op.f("fk_rob_assessments_record_id_records"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_rob_assessments_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rob_assessments")),
        sa.UniqueConstraint(
            "record_id",
            "user_id",
            "tool_key",
            name=op.f("uq_rob_assessments_record_id_user_id_tool_key"),
        ),
    )
    op.create_index(
        "ix_rob_assessments_project_id_tool_key",
        "rob_assessments",
        ["project_id", "tool_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_rob_assessments_project_id_tool_key", table_name="rob_assessments")
    op.drop_table("rob_assessments")
    sa.Enum(name="rob_status").drop(op.get_bind(), checkfirst=True)
