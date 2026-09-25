"""Count every record for the instance admin (guide 8.18)

Requests run as `winnow_app`, which sees only the records of reviews the signed-in user
belongs to (row-level security). The admin health page needs the instance's total, so a
function owned by the table's owner counts them: it returns a number and nothing else,
and only `winnow_app` may call it. The policies stay on for every other query.

Revision ID: 705a5ce77b66
Revises: a6654580b1ae
Create Date: 2026-09-25 22:05:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "705a5ce77b66"
down_revision: str | Sequence[str] | None = "a6654580b1ae"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "winnow_app"


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION instance_record_count() RETURNS bigint
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$ SELECT count(*) FROM records $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION instance_record_count() FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION instance_record_count() TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS instance_record_count()")
