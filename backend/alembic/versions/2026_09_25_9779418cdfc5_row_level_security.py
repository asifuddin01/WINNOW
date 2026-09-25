"""Row-level security as defense in depth (guide 12.2, Phase 8).

Requests run as `winnow_app`, a role without login, superuser or BYPASSRLS, switched to at
the start of every request transaction (`app.db`), with the signed-in user's id in
`app.user_id`. On `records`, `decisions` and `notes` that role sees and writes only rows
of reviews the user belongs to, whatever a query forgets to filter. The owner the app logs
in as (workers, migrations, operator commands) is not subject to the policies.

`winnow_app` also cannot change or delete audit rows (guide 6: "REVOKE UPDATE, DELETE from
app role"), on top of the append-only trigger.

Revision ID: 9779418cdfc5
Revises: 8b19ffff1009
Create Date: 2026-09-25 06:40:13.861203
"""

from collections.abc import Sequence

from alembic import op

revision: str = "9779418cdfc5"
down_revision: str | Sequence[str] | None = "8b19ffff1009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "winnow_app"
TABLES = ("records", "decisions", "notes")
# The reviews the request's user belongs to; an unset or empty user sees none. An
# uncorrelated IN, so PostgreSQL works the list out once per query, not once per row.
MEMBER_OF = (
    "project_id IN (SELECT m.project_id FROM project_members m "
    "WHERE m.user_id = nullif(current_setting('app.user_id', true), '')::uuid)"
)


def upgrade() -> None:
    # Roles belong to the whole server, not one database: another database on it (the
    # tests') may have made it already.
    op.execute(
        f"""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                CREATE ROLE {APP_ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS;
            END IF;
        END $$
        """
    )
    # The login role must be able to switch to it (a superuser always can).
    op.execute(f"GRANT {APP_ROLE} TO CURRENT_USER")
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")
    # Tables that later migrations create get the same rights.
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {APP_ROLE}"
    )
    op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM {APP_ROLE}")

    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_members_only ON {table} TO {APP_ROLE} "
            f"USING ({MEMBER_OF}) WITH CHECK ({MEMBER_OF})"
        )


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_members_only ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"REVOKE USAGE, SELECT, UPDATE ON SEQUENCES FROM {APP_ROLE}"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {APP_ROLE}"
    )
    op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {APP_ROLE}")
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {APP_ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {APP_ROLE}")
    # The role itself stays: other databases on the server may still use it.
