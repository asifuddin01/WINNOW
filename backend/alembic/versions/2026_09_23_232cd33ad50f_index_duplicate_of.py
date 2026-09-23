"""Index records.duplicate_of, so deleting records does not scan the table per row.

Revision ID: 232cd33ad50f
Revises: 09f4291c3d35
Create Date: 2026-09-23 16:06:30.859110
"""

from collections.abc import Sequence

from alembic import op

revision: str = "232cd33ad50f"
down_revision: str | Sequence[str] | None = "09f4291c3d35"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_records_duplicate_of",
        "records",
        ["duplicate_of"],
        unique=False,
        postgresql_where="duplicate_of IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_records_duplicate_of", table_name="records", postgresql_where="duplicate_of IS NOT NULL"
    )
