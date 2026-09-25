"""Match the live-records index to the queries

Revision ID: ae7b7eaeb077
Revises: 9555c7d5210e
Create Date: 2026-09-25 18:50:39.580535
"""

from collections.abc import Sequence

from alembic import op

revision: str = "ae7b7eaeb077"
down_revision: str | Sequence[str] | None = "9555c7d5210e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The queries say `is_duplicate IS false`; PostgreSQL cannot prove that from an index
    # built `WHERE is_duplicate = false`, so it read the table instead (1.3 s to count a
    # 100,000-record review). With the id in it, the same index also serves the newest-
    # and oldest-first list and an index-only count.
    op.drop_index("ix_records_project_id_live", table_name="records")
    op.create_index(
        "ix_records_project_id_live",
        "records",
        ["project_id", "id"],
        postgresql_where="is_duplicate IS false",
    )


def downgrade() -> None:
    op.drop_index("ix_records_project_id_live", table_name="records")
    op.create_index(
        "ix_records_project_id_live",
        "records",
        ["project_id"],
        postgresql_where="is_duplicate = false",
    )
