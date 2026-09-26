"""Clean GIN pending lists in the background (Phase 9 load test)

A decision that changes a record's screening status writes a new version of the row, and
with it entries in the three GIN indexes (search, title and author trigrams). GIN keeps
those in a pending list and merges it into the index when the list fills, and whichever
request fills it pays: 50 reviewers screening at once saw single status updates take up
to 1.8 s, p95 120 ms against a budget of 100.

Bigger pending lists (16 MB) and autovacuum after 2% of the table changes, instead of
20%, move the merging to autovacuum; p95 fell to 55 ms. The guide's indexes all stay.

Revision ID: 30994bb69e27
Revises: ae7b7eaeb077
Create Date: 2026-09-26 02:15:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "30994bb69e27"
down_revision: str | Sequence[str] | None = "ae7b7eaeb077"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


GIN_INDEXES = (
    "ix_records_search_vector",
    "ix_records_title_norm_trgm",
    "ix_records_authors_text_trgm",
)
PENDING_LIST_KB = 16384
AUTOVACUUM = (
    "autovacuum_vacuum_scale_factor",
    "autovacuum_vacuum_insert_scale_factor",
    "autovacuum_analyze_scale_factor",
)


def upgrade() -> None:
    for index in GIN_INDEXES:
        op.execute(f"ALTER INDEX {index} SET (gin_pending_list_limit = {PENDING_LIST_KB})")
    settings = ", ".join(f"{name} = 0.02" for name in AUTOVACUUM)
    op.execute(f"ALTER TABLE records SET ({settings})")


def downgrade() -> None:
    op.execute(f"ALTER TABLE records RESET ({', '.join(AUTOVACUUM)})")
    for index in GIN_INDEXES:
        op.execute(f"ALTER INDEX {index} RESET (gin_pending_list_limit)")
