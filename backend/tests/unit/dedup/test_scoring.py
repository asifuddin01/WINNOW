"""Pairwise scores exercise every component of the guide formula."""

import uuid
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest

from app.dedup import RecordForDedup, score_pair


def make_record(record_id: int, **changes: Any) -> RecordForDedup:
    record = RecordForDedup(
        id=uuid.UUID(int=record_id),
        title="Randomised trial of exercise",
        title_norm="randomised trial of exercise",
        authors=("García, Ana",),
        year=2020,
        journal="Clinical Trials Journal",
        volume="12",
        issue="2",
        pages="10-19",
        doi_norm=None,
        pmid=None,
        abstract_present=True,
        imported_at=datetime(2026, 1, record_id, tzinfo=UTC),
    )
    return replace(record, **changes)


def test_identical_metadata_keeps_the_page_volume_bonus_unclamped() -> None:
    assert score_pair(make_record(1), make_record(2)) == pytest.approx(1.05)


def test_token_sorting_and_accent_stripping_match_equivalent_text() -> None:
    left = make_record(1, title_norm="exercise randomised trial", authors=("García, Ana",))
    right = make_record(2, title_norm="Trial—exercise, randomised", authors=("Garcia, A.",))
    assert score_pair(left, right) == pytest.approx(1.05)


def test_sequence_matcher_substitute_is_symmetric() -> None:
    left = make_record(1, title_norm="x y z tide", volume=None, pages=None)
    right = make_record(2, title_norm="x y z diet", volume=None, pages=None)
    assert score_pair(left, right) == score_pair(right, left)


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"year": None}, 0.95),
        ({"year": 2021}, 1.02),
        ({"journal": None, "volume": None, "pages": None}, 0.96),
        ({"journal": "...", "volume": None, "pages": None}, 0.96),
        ({"authors": (), "volume": None, "pages": None}, 0.94),
        ({"authors": ("",), "volume": None, "pages": None}, 0.94),
        ({"pages": "20-29"}, 1.05),
        ({"pages": "20-29", "volume": "13"}, 1.0),
    ],
)
def test_component_weights(changes: dict[str, object], expected: float) -> None:
    assert score_pair(make_record(1), make_record(2, **changes)) == pytest.approx(expected)


def test_different_authors_and_distant_years_add_no_match_weight() -> None:
    right = make_record(2, authors=("Jones, Ben",), year=2016, volume=None, pages=None)
    assert score_pair(make_record(1), right) == pytest.approx(0.78)


def test_empty_titles_are_not_treated_as_an_exact_match() -> None:
    blank = make_record(1, title="", title_norm="", volume=None, pages=None)
    other = make_record(2, title="", title_norm="", volume=None, pages=None)
    assert score_pair(blank, other) == pytest.approx(0.30)


def test_conflicting_dois_override_identical_metadata() -> None:
    left = make_record(1, doi_norm=" 10.1000/ONE ")
    right = make_record(2, doi_norm="10.1000/two")
    assert score_pair(left, right) == 0.0


def test_doi_comparison_is_case_insensitive() -> None:
    left = make_record(1, doi_norm="10.1000/ABC")
    right = make_record(2, doi_norm="10.1000/abc")
    assert score_pair(left, right) == pytest.approx(1.05)


def test_whitespace_only_pages_and_volume_do_not_earn_a_bonus() -> None:
    left = make_record(1, pages="   ", volume="\t")
    right = make_record(2, pages="\t", volume="   ")
    assert score_pair(left, right) == pytest.approx(1.0)
