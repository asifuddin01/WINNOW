"""Screening: decisions, record labels, notes and resolutions (guide 6.1)

Revision ID: 48563a867702
Revises: 6c22726ac66b
Create Date: 2026-09-23 09:07:49.742092
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "48563a867702"
down_revision: str | Sequence[str] | None = "6c22726ac66b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conflict_resolutions",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("record_id", sa.UUID(), nullable=False),
        sa.Column(
            "stage", sa.Enum("title_abstract", "full_text", name="screening_stage"), nullable=False
        ),
        sa.Column("resolved_by", sa.UUID(), nullable=True),
        sa.Column(
            "final_decision", sa.Enum("include", "exclude", name="final_decision"), nullable=False
        ),
        sa.Column("reason_ids", postgresql.ARRAY(sa.UUID()), server_default="{}", nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "source",
            sa.Enum("conflict", "bulk", name="resolution_source"),
            server_default="conflict",
            nullable=False,
        ),
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
            name=op.f("fk_conflict_resolutions_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["record_id"],
            ["records.id"],
            name=op.f("fk_conflict_resolutions_record_id_records"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by"],
            ["users.id"],
            name=op.f("fk_conflict_resolutions_resolved_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conflict_resolutions")),
        sa.UniqueConstraint(
            "record_id", "stage", name=op.f("uq_conflict_resolutions_record_id_stage")
        ),
    )
    op.create_index(
        "ix_conflict_resolutions_project_id_stage",
        "conflict_resolutions",
        ["project_id", "stage"],
        unique=False,
    )
    op.create_table(
        "decisions",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("record_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "stage", sa.Enum("title_abstract", "full_text", name="screening_stage"), nullable=False
        ),
        sa.Column(
            "decision",
            sa.Enum("include", "exclude", "maybe", name="decision_value"),
            nullable=False,
        ),
        sa.Column("reason_ids", postgresql.ARRAY(sa.UUID()), server_default="{}", nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("time_spent_ms", sa.Integer(), server_default="0", nullable=False),
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
            name=op.f("fk_decisions_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["record_id"],
            ["records.id"],
            name=op.f("fk_decisions_record_id_records"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_decisions_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_decisions")),
        sa.UniqueConstraint(
            "record_id", "user_id", "stage", name=op.f("uq_decisions_record_id_user_id_stage")
        ),
    )
    op.create_index(
        "ix_decisions_project_id_stage_user_id",
        "decisions",
        ["project_id", "stage", "user_id"],
        unique=False,
    )
    op.create_index(
        "ix_decisions_record_id_stage", "decisions", ["record_id", "stage"], unique=False
    )
    op.create_table(
        "notes",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("record_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("visibility", sa.Enum("private", "team", name="note_visibility"), nullable=False),
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
            name=op.f("fk_notes_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["record_id"],
            ["records.id"],
            name=op.f("fk_notes_record_id_records"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_notes_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notes")),
    )
    op.create_index("ix_notes_record_id", "notes", ["record_id"], unique=False)
    op.create_table(
        "record_labels",
        sa.Column("record_id", sa.UUID(), nullable=False),
        sa.Column("label_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["label_id"],
            ["labels.id"],
            name=op.f("fk_record_labels_label_id_labels"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["record_id"],
            ["records.id"],
            name=op.f("fk_record_labels_record_id_records"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_record_labels_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("record_id", "label_id", "user_id", name=op.f("pk_record_labels")),
    )
    op.create_index("ix_record_labels_label_id", "record_labels", ["label_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_record_labels_label_id", table_name="record_labels")
    op.drop_table("record_labels")
    op.drop_index("ix_notes_record_id", table_name="notes")
    op.drop_table("notes")
    op.drop_index("ix_decisions_record_id_stage", table_name="decisions")
    op.drop_index("ix_decisions_project_id_stage_user_id", table_name="decisions")
    op.drop_table("decisions")
    op.drop_index("ix_conflict_resolutions_project_id_stage", table_name="conflict_resolutions")
    op.drop_table("conflict_resolutions")
    for name in (
        "resolution_source",
        "final_decision",
        "note_visibility",
        "decision_value",
        "screening_stage",
    ):
        op.execute(f"DROP TYPE IF EXISTS {name}")
