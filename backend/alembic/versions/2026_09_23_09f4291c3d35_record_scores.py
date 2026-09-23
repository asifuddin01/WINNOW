"""Scores move from records.relevance_score to their own table, per stage.

A ranking run rewrites every score; on `records` each write also rewrote the row's ten
indexes. See app/models/ranking.py.

Revision ID: 09f4291c3d35
Revises: 6990d24f3a5a
Create Date: 2026-09-23 16:22:15.098826
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "09f4291c3d35"
down_revision: str | Sequence[str] | None = "6990d24f3a5a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


STAGE = postgresql.ENUM("title_abstract", "full_text", name="screening_stage", create_type=False)
RECORDS = sa.table(
    "records",
    sa.column("id", sa.UUID()),
    sa.column("project_id", sa.UUID()),
    sa.column("relevance_score", sa.Float()),
)
SCORES = sa.table(
    "record_scores",
    sa.column("record_id", sa.UUID()),
    sa.column("stage", STAGE),
    sa.column("project_id", sa.UUID()),
    sa.column("score", sa.Float()),
)


def upgrade() -> None:
    op.create_table(
        "record_scores",
        sa.Column("record_id", sa.UUID(), nullable=False),
        sa.Column(
            "stage",
            postgresql.ENUM(
                "title_abstract", "full_text", name="screening_stage", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_record_scores_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["record_id"],
            ["records.id"],
            name=op.f("fk_record_scores_record_id_records"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("record_id", "stage", name=op.f("pk_record_scores")),
    )
    op.create_index(
        "ix_record_scores_project_id_stage_score",
        "record_scores",
        ["project_id", "stage", "score"],
        unique=False,
    )
    # The scores so far were title/abstract scores.
    op.execute(
        sa.insert(SCORES).from_select(
            ["record_id", "stage", "project_id", "score"],
            sa.select(
                RECORDS.c.id,
                sa.cast(sa.literal("title_abstract"), STAGE),
                RECORDS.c.project_id,
                RECORDS.c.relevance_score,
            ).where(RECORDS.c.relevance_score.is_not(None)),
        )
    )
    op.drop_index(op.f("ix_records_project_id_relevance_score"), table_name="records")
    op.drop_column("records", "relevance_score")


def downgrade() -> None:
    op.add_column(
        "records",
        sa.Column(
            "relevance_score", sa.DOUBLE_PRECISION(precision=53), autoincrement=False, nullable=True
        ),
    )
    op.create_index(
        op.f("ix_records_project_id_relevance_score"),
        "records",
        ["project_id", sa.literal_column("relevance_score DESC NULLS LAST")],
        unique=False,
    )
    op.execute(
        sa.update(RECORDS)
        .where(
            RECORDS.c.id == SCORES.c.record_id,
            SCORES.c.stage == sa.cast(sa.literal("title_abstract"), STAGE),
        )
        .values(relevance_score=SCORES.c.score)
    )
    op.drop_index("ix_record_scores_project_id_stage_score", table_name="record_scores")
    op.drop_table("record_scores")
