"""Blocking produces stable candidate buckets without the database trigram block."""

import uuid
from dataclasses import replace
from datetime import UTC, datetime

from app.dedup import RecordForDedup, blocks
from app.dedup.blocking import MAX_BLOCK


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


def many(titles: list[str], *, year: int | None = 2020) -> list[RecordForDedup]:
    """One record per title, with ids beyond what make_record's dates allow."""
    base = make_record(1, year=year)
    return [
        replace(base, id=uuid.UUID(int=index + 1), title=title)
        for index, title in enumerate(titles)
    ]


def test_a_block_too_large_to_compare_is_split_by_more_of_the_title() -> None:
    # 450 titles start "a systematic review": all pairs would be 101,025 comparisons.
    topics = ("sleep", "fatigue", "melatonin")
    records = many(
        [f"A systematic review of {topics[i % 3]} outcomes number {i}" for i in range(450)]
    )
    found = blocks(records)
    assert "title3:a systematic review" not in found
    split = {key: ids for key, ids in found.items() if key.startswith("title6:")}
    assert sorted(split) == [
        "title6:a systematic review of fatigue outcomes",
        "title6:a systematic review of melatonin outcomes",
        "title6:a systematic review of sleep outcomes",
    ]
    assert all(len(ids) == 150 for ids in split.values())
    assert max(len(ids) for ids in found.values()) <= MAX_BLOCK


def test_identical_titles_by_the_hundred_are_left_to_exact_identifiers() -> None:
    # "Erratum" 250 times in one year: no part of the title tells them apart.
    assert blocks(many(["Erratum"] * (MAX_BLOCK + 50))) == {}
    # In different years they are small enough to compare again.
    records = many(["Erratum"] * 300)
    records = [replace(record, year=2000 + index % 3) for index, record in enumerate(records)]
    assert sorted(len(ids) for ids in blocks(records).values()) == [100, 100, 100] * 2
