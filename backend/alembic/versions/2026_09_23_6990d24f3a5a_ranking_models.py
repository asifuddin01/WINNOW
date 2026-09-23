"""Ranking models: one row per training run (guide 6.1, 9.2).

Revision ID: 6990d24f3a5a
Revises: f8f9b187c1cc
Create Date: 2026-09-23 14:53:43.223901
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "6990d24f3a5a"
down_revision: str | Sequence[str] | None = "f8f9b187c1cc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ranking_models",
        sa.Column("project_id", sa.UUID(), nullable=False),
        # The stage type exists already (decisions use it).
        sa.Column(
            "stage",
            postgresql.ENUM(
                "title_abstract", "full_text", name="screening_stage", create_type=False
            ),
            nullable=False,
        ),
        sa.Column(
            "trained_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("n_labeled", sa.Integer(), nullable=False),
        sa.Column("n_included", sa.Integer(), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("artifact_key", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_ranking_models_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ranking_models")),
    )
    op.create_index(
        "ix_ranking_models_project_id_stage_trained_at",
        "ranking_models",
        ["project_id", "stage", "trained_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ranking_models_project_id_stage_trained_at", table_name="ranking_models")
    op.drop_table("ranking_models")
