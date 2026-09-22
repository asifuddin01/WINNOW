"""Blocking produces stable candidate buckets without the database trigram block."""

import uuid
from datetime import UTC, datetime

from app.dedup import RecordForDedup, blocks


def make_record(
    record_id: int,
    *,
    title: str = "Alpha beta gamma delta",
    title_norm: str = "",
    year: int | None = 2020,
) -> RecordForDedup:
    return RecordForDedup(
        id=uuid.UUID(int=record_id),
        title=title,
        title_norm=title_norm,
        authors=(),
        year=year,
        journal=None,
        volume=None,
        issue=None,
        pages=None,
        doi_norm=None,
        pmid=None,
        abstract_present=False,
        imported_at=datetime(2026, 1, record_id, tzinfo=UTC),
    )


def test_blocks_use_both_guide_keys_and_sorted_unique_ids() -> None:
    later = make_record(2, title="Café-au-lait spots elsewhere", year=2021)
    earlier = make_record(1, title="Cafe au lait spots here", year=2021)

    result = blocks([later, earlier, earlier])

    assert result == {
        "title3:cafe au lait": [earlier.id, later.id],
        "year-title10:2021:cafeaulait": [earlier.id, later.id],
    }


def test_missing_year_omits_only_the_year_key() -> None:
    record = make_record(1, year=None)
    assert blocks([record]) == {"title3:alpha beta gamma": [record.id]}


def test_empty_title_has_no_blocks() -> None:
    assert blocks([make_record(1, title="...", title_norm="")]) == {}


def test_supplied_title_normalisation_is_used() -> None:
    record = make_record(1, title="Ignored title", title_norm="database normal form", year=2024)
    assert set(blocks([record])) == {
        "title3:database normal form",
        "year-title10:2024:databaseno",
    }
