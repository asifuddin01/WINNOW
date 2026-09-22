"""users, email tokens and audit log

Revision ID: 5b1d0c3e9a47
Revises: 777d82a91403
Create Date: 2026-09-22 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "5b1d0c3e9a47"
down_revision: str | Sequence[str] | None = "777d82a91403"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

email_token_purpose = postgresql.ENUM("verify", "reset", "invite", name="email_token_purpose")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("totp_secret_enc", sa.LargeBinary(), nullable=True),
        sa.Column("totp_enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("totp_last_step", sa.BigInteger(), nullable=True),
        sa.Column(
            "recovery_codes_hash", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("orcid", sa.Text(), nullable=True),
        sa.Column("is_instance_admin", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("failed_login_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "preferences",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "email_tokens",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("purpose", email_token_purpose, nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_email_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_email_tokens_token_hash")),
    )
    op.create_index(op.f("ix_email_tokens_user_id"), "email_tokens", ["user_id"], unique=False)
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=True),
        sa.Column("entity_id", sa.UUID(), nullable=True),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index(
        "ix_audit_log_project_id_created_at",
        "audit_log",
        ["project_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_log_user_id_created_at", "audit_log", ["user_id", "created_at"], unique=False
    )

    # Guide 12.8: the audit log is append-only. A trigger enforces it for every role,
    # including the owner the application connects as in development.
    op.execute(
        """
        CREATE FUNCTION audit_log_is_append_only() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only: % is not allowed', TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_log_no_update_or_delete
        BEFORE UPDATE OR DELETE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION audit_log_is_append_only()
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_log_no_truncate
        BEFORE TRUNCATE ON audit_log
        FOR EACH STATEMENT EXECUTE FUNCTION audit_log_is_append_only()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_truncate ON audit_log")
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_update_or_delete ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit_log_is_append_only()")
    op.drop_index("ix_audit_log_user_id_created_at", table_name="audit_log")
    op.drop_index("ix_audit_log_project_id_created_at", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index(op.f("ix_email_tokens_user_id"), table_name="email_tokens")
    op.drop_table("email_tokens")
    op.drop_table("users")
    email_token_purpose.drop(op.get_bind(), checkfirst=True)
