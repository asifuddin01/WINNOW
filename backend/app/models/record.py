"""Imports and the records they bring in (guide 6.1).

A record is one reference from a search export. Everything a reviewer screens hangs off
this table, so it carries the search vector and the normalised keys deduplication needs.
"""

import enum
import uuid
from datetime import date
from typing import Any

from sqlalchemy import (
    Boolean,
    Computed,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamps, UUIDPrimaryKey, pg_enum


class FileFormat(enum.StrEnum):
    RIS = "ris"
    BIB = "bib"
    NBIB = "nbib"
    PUBMED_XML = "pubmed_xml"
    ENDNOTE_XML = "endnote_xml"
    CSV = "csv"


class ImportStatus(enum.StrEnum):
    QUEUED = "queued"  # uploaded and parsed for preview, waiting to be confirmed
    PARSING = "parsing"
    DONE = "done"
    FAILED = "failed"


class TitleAbstractStatus(enum.StrEnum):
    PENDING = "pending"
    INCLUDED = "included"
    EXCLUDED = "excluded"
    CONFLICT = "conflict"
    MAYBE = "maybe"


class FullTextStatus(enum.StrEnum):
    NOT_ELIGIBLE = "not_eligible"
    PENDING = "pending"
    INCLUDED = "included"
    EXCLUDED = "excluded"
    CONFLICT = "conflict"


# Guide 6.1: title weighted above abstract, keywords last. The work happens in an
# immutable SQL function (see the migration), because array_to_string is only stable and
# PostgreSQL refuses to generate a column from anything less.
SEARCH_VECTOR = "winnow_search_vector(title, abstract, keywords)"
# Authors are not in the search vector (guide 6.1 weights title, abstract and keywords),
# so `author:smith` needs its own indexable column.
AUTHORS_TEXT = "winnow_authors_text(authors)"


class ImportBatch(UUIDPrimaryKey, Timestamps, Base):
    """One uploaded file: what it was, how far it got, and what could not be read."""

    __tablename__ = "import_batches"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    database_name: Mapped[str] = mapped_column(Text, nullable=False)
    file_key: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    file_format: Mapped[FileFormat] = mapped_column(pg_enum(FileFormat, "file_format"))
    status: Mapped[ImportStatus] = mapped_column(
        pg_enum(ImportStatus, "import_status"), default=ImportStatus.QUEUED
    )
    total: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    imported: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # [{"line": 42, "reason": "no title"}], capped; downloadable as a report.
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    # Which CSV column feeds which field, chosen in the mapping step.
    column_mapping: Mapped[dict[str, str] | None] = mapped_column(JSONB)
    # Recorded for PRISMA-S and the methods text (guide 8.3).
    search_date: Mapped[date | None] = mapped_column(Date)
    search_string: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class Record(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "records"
    __table_args__ = (
        # Guide 6.3, in the order the list and screening queries need them.
        Index("ix_records_project_id_live", "project_id", postgresql_where="is_duplicate = false"),
        Index("ix_records_project_id_ta_final", "project_id", "ta_final"),
        Index("ix_records_project_id_ft_final", "project_id", "ft_final"),
        Index("ix_records_project_id_doi_norm", "project_id", "doi_norm"),
        Index("ix_records_project_id_pmid", "project_id", "pmid"),
        Index("ix_records_search_vector", "search_vector", postgresql_using="gin"),
        Index(
            "ix_records_title_norm_trgm",
            "title_norm",
            postgresql_using="gin",
            postgresql_ops={"title_norm": "gin_trgm_ops"},
        ),
        Index(
            "ix_records_authors_text_trgm",
            "authors_text",
            postgresql_using="gin",
            postgresql_ops={"authors_text": "gin_trgm_ops"},
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE")
    )
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("import_batches.id", ondelete="CASCADE"), index=True
    )

    title: Mapped[str | None] = mapped_column(Text)
    abstract: Mapped[str | None] = mapped_column(Text)
    authors: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")
    year: Mapped[int | None] = mapped_column(Integer)
    journal: Mapped[str | None] = mapped_column(Text)
    volume: Mapped[str | None] = mapped_column(Text)
    issue: Mapped[str | None] = mapped_column(Text)
    pages: Mapped[str | None] = mapped_column(Text)
    # Plain text, not citext: binary COPY has no encoder for it, and every lookup goes
    # through doi_norm, which is already lowercased and stripped (guide 8.3).
    doi: Mapped[str | None] = mapped_column(Text)
    pmid: Mapped[str | None] = mapped_column(Text)
    pmcid: Mapped[str | None] = mapped_column(Text)
    isbn: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")
    language: Mapped[str | None] = mapped_column(Text)
    publication_type: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default="{}"
    )
    # The record exactly as the file had it, for anything Winnow does not model yet.
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")

    authors_text: Mapped[str | None] = mapped_column(Text, Computed(AUTHORS_TEXT, persisted=True))

    # Normalised on import (guide 8.3); deduplication matches on these.
    title_norm: Mapped[str | None] = mapped_column(Text)
    doi_norm: Mapped[str | None] = mapped_column(Text)
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR, Computed(SEARCH_VECTOR, persisted=True)
    )

    duplicate_of: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("records.id", ondelete="SET NULL")
    )
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    ta_final: Mapped[TitleAbstractStatus] = mapped_column(
        pg_enum(TitleAbstractStatus, "ta_status"),
        default=TitleAbstractStatus.PENDING,
        server_default="pending",
    )
    ft_final: Mapped[FullTextStatus] = mapped_column(
        pg_enum(FullTextStatus, "ft_status"),
        default=FullTextStatus.NOT_ELIGIBLE,
        server_default="not_eligible",
    )
    relevance_score: Mapped[float | None] = mapped_column(Float)


# The screening queue reads the best-scoring records first; nulls (not yet scored) last.
Index(
    "ix_records_project_id_relevance_score",
    Record.project_id,
    Record.relevance_score.desc().nullslast(),
)


# The columns an import writes with COPY, in order. Anything left out takes its default:
# the screening statuses, the duplicate flags, and search_vector, which the database
# generates from the row itself.
COPY_COLUMNS = (
    "id",
    "project_id",
    "import_batch_id",
    "title",
    "abstract",
    "authors",
    "year",
    "journal",
    "volume",
    "issue",
    "pages",
    "doi",
    "pmid",
    "pmcid",
    "isbn",
    "url",
    "keywords",
    "language",
    "publication_type",
    "raw",
    "title_norm",
    "doi_norm",
    "created_at",
    "updated_at",
)
