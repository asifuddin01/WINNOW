"""PRISMA counts Winnow cannot know: other sources and removals before screening (8.14).

Revision ID: 706688f42f16
Revises: 9779418cdfc5
Create Date: 2026-09-25 01:04:43.439772
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "706688f42f16"
down_revision: str | Sequence[str] | None = "9779418cdfc5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prisma_manual",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column(
            "other_sources",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("removed_other_reasons", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated_by", sa.UUID(), nullable=True),
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
            name=op.f("fk_prisma_manual_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_prisma_manual_updated_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("project_id", name=op.f("pk_prisma_manual")),
    )


def downgrade() -> None:
    op.drop_table("prisma_manual")
