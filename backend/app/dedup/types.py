"""Plain data types shared by the pure duplicate-detection modules."""

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class RecordForDedup:
    """The database-independent bibliographic fields used for duplicate detection.

    ``imported_at`` is expected to be timezone-aware, and ``authors`` uses the import
    pipeline's ``Last, First`` representation. Adapters should turn ORM identifiers into
    ``uuid.UUID`` values before constructing this frozen value object.
    """

    id: uuid.UUID
    title: str
    title_norm: str
    authors: tuple[str, ...]
    year: int | None
    journal: str | None
    volume: str | None
    issue: str | None
    pages: str | None
    doi_norm: str | None
    pmid: str | None
    abstract_present: bool
    imported_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class Cluster:
    """A duplicate candidate cluster returned to the persistence adapter."""

    members: tuple[uuid.UUID, ...]
    score: float
    primary_id: uuid.UUID
    auto_resolvable: bool
