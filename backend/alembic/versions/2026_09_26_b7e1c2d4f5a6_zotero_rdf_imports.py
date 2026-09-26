"""Zotero RDF imports (guide 8.3, Phase 9)

Revision ID: b7e1c2d4f5a6
Revises: 30994bb69e27
Create Date: 2026-09-26 10:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b7e1c2d4f5a6"
down_revision: str | Sequence[str] | None = "30994bb69e27"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE file_format ADD VALUE IF NOT EXISTS 'zotero_rdf'")


def downgrade() -> None:
    # Kept: PostgreSQL cannot take a value out of an enum, and imports may use it.
    pass
