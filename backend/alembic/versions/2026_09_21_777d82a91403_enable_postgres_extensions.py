"""enable postgres extensions

Revision ID: 777d82a91403
Revises:
Create Date: 2026-09-21 14:20:22.617707
"""

from collections.abc import Sequence

from alembic import op

revision: str = "777d82a91403"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Guide 6.3: citext for case-insensitive emails and DOIs, pg_trgm for fuzzy title
# matching, pgcrypto for gen_random_bytes and digests. All three are trusted
# extensions, so the database owner can create them without superuser rights.


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    op.execute("DROP EXTENSION IF EXISTS citext")
