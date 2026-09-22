"""projects, members, invites and setup

Revision ID: 3c7f1a9d2e58
Revises: 8e4a2f6b1c90
Create Date: 2026-09-22 20:00:00
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "3c7f1a9d2e58"
down_revision: str | Sequence[str] | None = "8e4a2f6b1c90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

review_type = postgresql.ENUM(
    "systematic", "scoping", "rapid", "umbrella", "other", name="review_type", create_type=False
)
project_status = postgresql.ENUM(
    "setup",
    "screening",
    "fulltext",
    "extraction",
    "complete",
    "archived",
    name="project_status",
    create_type=False,
)
project_role = postgresql.ENUM(
    "owner", "admin", "reviewer", "viewer", name="project_role", create_type=False
)
criterion_kind = postgresql.ENUM("inclusion", "exclusion", name="criterion_kind", create_type=False)
keyword_kind = postgresql.ENUM(
    "include", "exclude", "neutral", name="keyword_kind", create_type=False
)
reason_stage = postgresql.ENUM(
    "title_abstract", "full_text", "both", name="reason_stage", create_type=False
)
ENUMS = (review_type, project_status, project_role, criterion_kind, keyword_kind, reason_stage)


def _timestamps() -> list[sa.Column[Any]]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def _project_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["project_id"],
        ["projects.id"],
        name=op.f(f"fk_{table}_project_id_projects"),
        ondelete="CASCADE",
    )


def upgrade() -> None:
    bind = op.get_bind()
    for enum in ENUMS:
        enum.create(bind, checkfirst=False)

    op.create_table(
        "projects",
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("review_type", review_type, nullable=False),
        sa.Column("research_question", sa.Text(), nullable=True),
        sa.Column("pico", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", project_status, nullable=False),
        sa.Column("settings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_projects_owner_id_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
    )
    op.create_index(op.f("ix_projects_owner_id"), "projects", ["owner_id"])

    op.create_table(
        "project_members",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("role", project_role, nullable=False),
        sa.Column("can_resolve_conflicts", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "stages",
            postgresql.ARRAY(sa.Text()),
            server_default="{title_abstract,full_text}",
            nullable=False,
        ),
        sa.Column("keep_blind", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        _project_fk("project_members"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_project_members_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("project_id", "user_id", name=op.f("pk_project_members")),
    )
    op.create_index(op.f("ix_project_members_user_id"), "project_members", ["user_id"])
    op.create_index(
        "uq_project_members_one_owner",
        "project_members",
        ["project_id"],
        unique=True,
        postgresql_where="role = 'owner'",
    )

    op.create_table(
        "project_invites",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("role", project_role, nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("invited_by", sa.UUID(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        _project_fk("project_invites"),
        sa.ForeignKeyConstraint(
            ["invited_by"],
            ["users.id"],
            name=op.f("fk_project_invites_invited_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["accepted_by"],
            ["users.id"],
            name=op.f("fk_project_invites_accepted_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_invites")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_project_invites_token_hash")),
    )
    op.create_index(op.f("ix_project_invites_project_id"), "project_invites", ["project_id"])
    op.create_index(
        "uq_project_invites_pending",
        "project_invites",
        ["project_id", "email"],
        unique=True,
        postgresql_where="accepted_at IS NULL",
    )

    op.create_table(
        "criteria",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("kind", criterion_kind, nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        *_timestamps(),
        _project_fk("criteria"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_criteria")),
    )
    op.create_index(op.f("ix_criteria_project_id"), "criteria", ["project_id"])

    op.create_table(
        "keyword_groups",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("color", sa.Text(), nullable=False),
        sa.Column("kind", keyword_kind, nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        *_timestamps(),
        _project_fk("keyword_groups"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_keyword_groups")),
    )
    op.create_index(op.f("ix_keyword_groups_project_id"), "keyword_groups", ["project_id"])

    op.create_table(
        "keywords",
        sa.Column("group_id", sa.UUID(), nullable=False),
        sa.Column("term", postgresql.CITEXT(), nullable=False),
        sa.Column("is_regex", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("whole_word", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["keyword_groups.id"],
            name=op.f("fk_keywords_group_id_keyword_groups"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_keywords")),
        sa.UniqueConstraint("group_id", "term", name=op.f("uq_keywords_group_id_term")),
    )
    op.create_index(op.f("ix_keywords_group_id"), "keywords", ["group_id"])

    op.create_table(
        "exclusion_reasons",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("label", postgresql.CITEXT(), nullable=False),
        sa.Column("stage", reason_stage, nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        *_timestamps(),
        _project_fk("exclusion_reasons"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exclusion_reasons")),
        sa.UniqueConstraint(
            "project_id", "label", name=op.f("uq_exclusion_reasons_project_id_label")
        ),
    )
    op.create_index(op.f("ix_exclusion_reasons_project_id"), "exclusion_reasons", ["project_id"])

    op.create_table(
        "labels",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("name", postgresql.CITEXT(), nullable=False),
        sa.Column("color", sa.Text(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        *_timestamps(),
        _project_fk("labels"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_labels")),
        sa.UniqueConstraint("project_id", "name", name=op.f("uq_labels_project_id_name")),
    )
    op.create_index(op.f("ix_labels_project_id"), "labels", ["project_id"])


def downgrade() -> None:
    for table in ("labels", "exclusion_reasons", "keywords", "keyword_groups", "criteria"):
        op.drop_table(table)
    op.drop_table("project_invites")
    op.drop_table("project_members")
    op.drop_table("projects")
    bind = op.get_bind()
    for enum in reversed(ENUMS):
        enum.drop(bind, checkfirst=False)
