"""Full texts: PDFs, annotations, ZIP uploads and records not retrievable (guide 8.8).

Revision ID: 8b19ffff1009
Revises: 79cf65643b95
Create Date: 2026-09-24 18:47:40.464972
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "8b19ffff1009"
down_revision: str | Sequence[str] | None = "79cf65643b95"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Guide 8.8: a record whose full text could not be found. (Kept on downgrade: PostgreSQL
    # cannot take a value out of an enum; the rows using it are moved back to pending.)
    op.execute("ALTER TYPE ft_status ADD VALUE IF NOT EXISTS 'not_retrievable'")
    op.create_table(
        "fulltext_batches",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("zip_key", sa.Text(), nullable=True),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "checking", "ready", "applied", "rejected", "failed", name="fulltext_batch_status"
            ),
            nullable=False,
        ),
        sa.Column("entries", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("problem", sa.Text(), nullable=True),
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
            name=op.f("fk_fulltext_batches_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_fulltext_batches_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fulltext_batches")),
    )
    op.create_index(
        "ix_fulltext_batches_project_id", "fulltext_batches", ["project_id"], unique=False
    )
    op.create_table(
        "fulltexts",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("record_id", sa.UUID(), nullable=False),
        sa.Column("file_key", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("mime", sa.Text(), nullable=False),
        sa.Column(
            "scan_status",
            sa.Enum("pending", "clean", "infected", "error", "skipped", name="scan_status"),
            nullable=False,
        ),
        sa.Column("scan_signature", sa.Text(), nullable=True),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("text_extracted", sa.Text(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column(
            "source",
            sa.Enum("upload", "zip", "open_access", name="fulltext_source"),
            nullable=False,
        ),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("uploaded_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_fulltexts_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["record_id"],
            ["records.id"],
            name=op.f("fk_fulltexts_record_id_records"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
            name=op.f("fk_fulltexts_uploaded_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fulltexts")),
        sa.UniqueConstraint("record_id", name=op.f("uq_fulltexts_record_id")),
    )
    op.create_index("ix_fulltexts_project_id", "fulltexts", ["project_id"], unique=False)
    op.create_table(
        "unretrievable_records",
        sa.Column("record_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("marked_by", sa.UUID(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["marked_by"],
            ["users.id"],
            name=op.f("fk_unretrievable_records_marked_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_unretrievable_records_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["record_id"],
            ["records.id"],
            name=op.f("fk_unretrievable_records_record_id_records"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("record_id", name=op.f("pk_unretrievable_records")),
    )
    op.create_table(
        "pdf_annotations",
        sa.Column("fulltext_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("rects", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("color", sa.Text(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
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
            ["fulltext_id"],
            ["fulltexts.id"],
            name=op.f("fk_pdf_annotations_fulltext_id_fulltexts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_pdf_annotations_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_pdf_annotations_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pdf_annotations")),
    )
    op.create_index(
        "ix_pdf_annotations_fulltext_id", "pdf_annotations", ["fulltext_id"], unique=False
    )


def downgrade() -> None:
    records = sa.table("records", sa.column("ft_final", sa.Text()))
    op.execute(
        records.update()
        .where(sa.cast(records.c.ft_final, sa.Text()) == "not_retrievable")
        .values(ft_final=sa.cast(sa.literal("pending"), postgresql.ENUM(name="ft_status")))
    )
    op.drop_index("ix_pdf_annotations_fulltext_id", table_name="pdf_annotations")
    op.drop_table("pdf_annotations")
    op.drop_table("unretrievable_records")
    op.drop_index("ix_fulltexts_project_id", table_name="fulltexts")
    op.drop_table("fulltexts")
    op.drop_index("ix_fulltext_batches_project_id", table_name="fulltext_batches")
    op.drop_table("fulltext_batches")
    for name in ("fulltext_batch_status", "fulltext_source", "scan_status"):
        op.execute(f"DROP TYPE IF EXISTS {name}")
