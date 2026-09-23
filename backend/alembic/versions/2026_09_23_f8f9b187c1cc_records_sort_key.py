"""A stored random sort key for the screening queue (guide 2.2)

Revision ID: f8f9b187c1cc
Revises: 48563a867702
Create Date: 2026-09-23 09:30:02.216758
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f8f9b187c1cc"
down_revision: str | Sequence[str] | None = "48563a867702"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "records",
        sa.Column("sort_key", sa.Float(), server_default=sa.func.random(), nullable=False),
    )
    op.create_index(
        "ix_records_project_id_sort_key", "records", ["project_id", "sort_key"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_records_project_id_sort_key", table_name="records")
    op.drop_column("records", "sort_key")
