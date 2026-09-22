"""import batches and records

Revision ID: c5d7e99d96a5
Revises: 3c7f1a9d2e58
Create Date: 2026-09-22 18:49:47.544198
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c5d7e99d96a5"
down_revision: str | Sequence[str] | None = "3c7f1a9d2e58"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SEARCH_VECTOR_FUNCTION = """
CREATE FUNCTION winnow_search_vector(title text, abstract text, keywords text[])
RETURNS tsvector LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT setweight(to_tsvector('english', coalesce(title, '')), 'A')
      || setweight(to_tsvector('english', coalesce(abstract, '')), 'B')
      || setweight(to_tsvector('english', coalesce(array_to_string(keywords, ' '), '')), 'C')
$$
"""
AUTHORS_TEXT_FUNCTION = """
CREATE FUNCTION winnow_authors_text(authors text[])
RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT coalesce(array_to_string(authors, ' '), '')
$$
"""


def upgrade() -> None:
    # Guide 6.1's weighting, in a function PostgreSQL will accept in a generated column:
    # array_to_string is only stable, so the wrapper declares what is true of the whole
    # expression, that the same row always gives the same vector.
    op.execute(SEARCH_VECTOR_FUNCTION)
    op.execute(AUTHORS_TEXT_FUNCTION)
    op.create_table(
        "import_batches",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("database_name", sa.Text(), nullable=False),
        sa.Column("file_key", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "file_format",
            sa.Enum("ris", "bib", "nbib", "pubmed_xml", "endnote_xml", "csv", name="file_format"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("queued", "parsing", "done", "failed", name="import_status"),
            nullable=False,
        ),
        sa.Column("total", sa.Integer(), server_default="0", nullable=False),
        sa.Column("imported", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "errors", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
        ),
        sa.Column("column_mapping", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("search_date", sa.Date(), nullable=True),
        sa.Column("search_string", sa.Text(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_import_batches_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_import_batches_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_batches")),
    )
    op.create_index(
        op.f("ix_import_batches_project_id"), "import_batches", ["project_id"], unique=False
    )
    op.create_table(
        "records",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("import_batch_id", sa.UUID(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.Column("authors", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("journal", sa.Text(), nullable=True),
        sa.Column("volume", sa.Text(), nullable=True),
        sa.Column("issue", sa.Text(), nullable=True),
        sa.Column("pages", sa.Text(), nullable=True),
        sa.Column("doi", sa.Text(), nullable=True),
        sa.Column("pmid", sa.Text(), nullable=True),
        sa.Column("pmcid", sa.Text(), nullable=True),
        sa.Column("isbn", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("keywords", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("language", sa.Text(), nullable=True),
        sa.Column(
            "publication_type", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column(
            "raw", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column(
            "authors_text",
            sa.Text(),
            sa.Computed("winnow_authors_text(authors)", persisted=True),
            nullable=True,
        ),
        sa.Column("title_norm", sa.Text(), nullable=True),
        sa.Column("doi_norm", sa.Text(), nullable=True),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed("winnow_search_vector(title, abstract, keywords)", persisted=True),
            nullable=True,
        ),
        sa.Column("duplicate_of", sa.UUID(), nullable=True),
        sa.Column("is_duplicate", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "ta_final",
            sa.Enum("pending", "included", "excluded", "conflict", "maybe", name="ta_status"),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "ft_final",
            sa.Enum(
                "not_eligible", "pending", "included", "excluded", "conflict", name="ft_status"
            ),
            server_default="not_eligible",
            nullable=False,
        ),
        sa.Column("relevance_score", sa.Float(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["duplicate_of"],
            ["records.id"],
            name=op.f("fk_records_duplicate_of_records"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["import_batch_id"],
            ["import_batches.id"],
            name=op.f("fk_records_import_batch_id_import_batches"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_records_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_records")),
    )
    op.create_index(
        op.f("ix_records_import_batch_id"), "records", ["import_batch_id"], unique=False
    )
    op.create_index(
        "ix_records_project_id_doi_norm", "records", ["project_id", "doi_norm"], unique=False
    )
    op.create_index(
        "ix_records_project_id_ft_final", "records", ["project_id", "ft_final"], unique=False
    )
    op.create_index(
        "ix_records_project_id_live",
        "records",
        ["project_id"],
        unique=False,
        postgresql_where="is_duplicate = false",
    )
    op.create_index("ix_records_project_id_pmid", "records", ["project_id", "pmid"], unique=False)
    op.create_index(
        "ix_records_project_id_relevance_score",
        "records",
        ["project_id", sa.literal_column("relevance_score DESC NULLS LAST")],
        unique=False,
    )
    op.create_index(
        "ix_records_project_id_ta_final", "records", ["project_id", "ta_final"], unique=False
    )
    op.create_index(
        "ix_records_search_vector",
        "records",
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_records_authors_text_trgm",
        "records",
        ["authors_text"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"authors_text": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_records_title_norm_trgm",
        "records",
        ["title_norm"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"title_norm": "gin_trgm_ops"},
    )


def downgrade() -> None:
    op.drop_index(
        "ix_records_authors_text_trgm",
        table_name="records",
        postgresql_using="gin",
        postgresql_ops={"authors_text": "gin_trgm_ops"},
    )
    op.drop_index(
        "ix_records_title_norm_trgm",
        table_name="records",
        postgresql_using="gin",
        postgresql_ops={"title_norm": "gin_trgm_ops"},
    )
    op.drop_index("ix_records_search_vector", table_name="records", postgresql_using="gin")
    op.drop_index("ix_records_project_id_ta_final", table_name="records")
    op.drop_index("ix_records_project_id_relevance_score", table_name="records")
    op.drop_index("ix_records_project_id_pmid", table_name="records")
    op.drop_index(
        "ix_records_project_id_live", table_name="records", postgresql_where="is_duplicate = false"
    )
    op.drop_index("ix_records_project_id_ft_final", table_name="records")
    op.drop_index("ix_records_project_id_doi_norm", table_name="records")
    op.drop_index(op.f("ix_records_import_batch_id"), table_name="records")
    op.drop_table("records")
    op.drop_index(op.f("ix_import_batches_project_id"), table_name="import_batches")
    op.drop_table("import_batches")
    op.execute("DROP FUNCTION winnow_search_vector(text, text, text[])")
    op.execute("DROP FUNCTION winnow_authors_text(text[])")
    for name in ("ta_status", "ft_status", "import_status", "file_format"):
        op.execute(f"DROP TYPE IF EXISTS {name}")
