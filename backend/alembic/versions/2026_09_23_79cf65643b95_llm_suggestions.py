"""AI suggestions, kept for transparency (guide 8.11).

Revision ID: 79cf65643b95
Revises: 232cd33ad50f
Create Date: 2026-09-23 15:33:29.338144
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "79cf65643b95"
down_revision: str | Sequence[str] | None = "232cd33ad50f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_suggestions",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("record_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "stage",
            postgresql.ENUM(
                "title_abstract", "full_text", name="screening_stage", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column(
            "decision",
            postgresql.ENUM(
                "include", "exclude", "maybe", name="decision_value", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("criteria", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_llm_suggestions_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["record_id"],
            ["records.id"],
            name=op.f("fk_llm_suggestions_record_id_records"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_llm_suggestions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_suggestions")),
    )
    op.create_index(
        "ix_llm_suggestions_project_id_created_at",
        "llm_suggestions",
        ["project_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_llm_suggestions_record_id_user_id_stage",
        "llm_suggestions",
        ["record_id", "user_id", "stage"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_llm_suggestions_record_id_user_id_stage", table_name="llm_suggestions")
    op.drop_index("ix_llm_suggestions_project_id_created_at", table_name="llm_suggestions")
    op.drop_table("llm_suggestions")
