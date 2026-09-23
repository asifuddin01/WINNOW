"""Agreement metrics are checked against published worked examples and edge cases."""

import uuid
from typing import cast

import pytest

from app.stats import (
    Decision,
    DecisionValue,
    MaybeCountsAs,
    cohens_kappa,
    fleiss_kappa,
    percent_agreement,
)

REVIEWER_A = uuid.UUID(int=10_001)
REVIEWER_B = uuid.UUID(int=10_002)
REVIEWER_C = uuid.UUID(int=10_003)


def make_decision(record: int, reviewer: uuid.UUID, value: DecisionValue) -> Decision:
    return Decision(record_id=uuid.UUID(int=record), reviewer_id=reviewer, decision=value)


@pytest.fixture
def albert_table_five() -> tuple[Decision, ...]:
    """Expand Albert (2017), Case 4/Table 5, doi:10.5334/jbr-btr.1399."""

    cells = (
        ("include", "include", 54),
        ("include", "exclude", 68),
        ("exclude", "include", 14),
        ("exclude", "exclude", 51),
    )
    decisions: list[Decision] = []
    record = 1
    for left, right, count in cells:
        for _ in range(count):
            decisions.extend(
                (
                    make_decision(record, REVIEWER_A, left),
                    make_decision(record, REVIEWER_B, right),
                )
            )
            record += 1
    return tuple(decisions)


def test_percent_agreement_matches_albert_worked_example(
    albert_table_five: tuple[Decision, ...],
) -> None:
    # The paper reports 105 agreements among 187 paired classifications: p_o = .561.
    expected = 105 / 187
    assert percent_agreement(albert_table_five, REVIEWER_A, REVIEWER_B) == pytest.approx(expected)


def test_cohens_kappa_matches_albert_worked_example(
    albert_table_five: tuple[Decision, ...],
) -> None:
    # Exact table arithmetic gives p_e = 943/2057 and kappa = 106/557 (reported as .19).
    expected = 106 / 557
    assert cohens_kappa(albert_table_five, REVIEWER_A, REVIEWER_B) == pytest.approx(expected)


def test_fleiss_kappa_matches_fleiss_1971_table_one_binary_category() -> None:
    # Fleiss (1971), doi:10.1037/h0031619, used 30 patients and 6 psychiatrists.
    # These are his Neurosis counts versus all other diagnoses; exact kappa is 3239/6875.
    include_counts = (
        6,
        0,
        0,
        0,
        3,
        0,
        0,
        1,
        4,
        0,
        5,
        4,
        0,
        5,
        3,
        0,
        1,
        0,
        4,
        0,
        0,
        5,
        1,
        4,
        4,
        1,
        0,
        4,
        0,
        0,
    )
    reviewers = tuple(uuid.UUID(int=20_000 + index) for index in range(6))
    decisions = tuple(
        make_decision(
            record,
            reviewer,
            "include" if reviewer_index < include_count else "exclude",
        )
        for record, include_count in enumerate(include_counts, start=1)
        for reviewer_index, reviewer in enumerate(reviewers)
    )

    expected = 3239 / 6875
    assert fleiss_kappa(decisions) == pytest.approx(expected)


def test_pair_metrics_apply_project_maybe_setting_and_ignore_other_reviewers() -> None:
    decisions = (
        make_decision(1, REVIEWER_A, "include"),
        make_decision(1, REVIEWER_B, "maybe"),
        make_decision(1, REVIEWER_C, "exclude"),
        make_decision(2, REVIEWER_A, "exclude"),
        make_decision(2, REVIEWER_B, "exclude"),
        make_decision(3, REVIEWER_A, "include"),
    )

    assert percent_agreement(decisions, REVIEWER_A, REVIEWER_B) == 1.0
    assert cohens_kappa(decisions, REVIEWER_A, REVIEWER_B) == 1.0
    assert percent_agreement(
        decisions, REVIEWER_A, REVIEWER_B, maybe_counts_as="maybe"
    ) == pytest.approx(0.5)
    assert cohens_kappa(
        decisions, REVIEWER_A, REVIEWER_B, maybe_counts_as="maybe"
    ) == pytest.approx(1 / 3)


def test_no_shared_records_are_explicitly_not_calculable() -> None:
    decisions = (
        make_decision(1, REVIEWER_A, "include"),
        make_decision(2, REVIEWER_B, "include"),
    )

    assert percent_agreement(decisions, REVIEWER_A, REVIEWER_B) is None
    assert cohens_kappa(decisions, REVIEWER_A, REVIEWER_B) is None


def test_single_category_has_full_agreement_but_undefined_kappa() -> None:
    decisions = (
        make_decision(1, REVIEWER_A, "include"),
        make_decision(1, REVIEWER_B, "include"),
    )

    assert percent_agreement(decisions, REVIEWER_A, REVIEWER_B) == 1.0
    assert cohens_kappa(decisions, REVIEWER_A, REVIEWER_B) is None


def test_one_constant_reviewer_still_has_defined_kappa() -> None:
    decisions = (
        make_decision(1, REVIEWER_A, "include"),
        make_decision(1, REVIEWER_B, "include"),
        make_decision(2, REVIEWER_A, "include"),
        make_decision(2, REVIEWER_B, "exclude"),
    )

    assert cohens_kappa(decisions, REVIEWER_A, REVIEWER_B) == 0.0


def test_distinct_reviewers_are_required() -> None:
    with pytest.raises(ValueError, match="distinct reviewers"):
        percent_agreement((), REVIEWER_A, REVIEWER_A)


def test_duplicate_record_reviewer_decisions_are_rejected() -> None:
    repeated = make_decision(1, REVIEWER_A, "include")
    with pytest.raises(ValueError, match="only one decision"):
        cohens_kappa((repeated, repeated), REVIEWER_A, REVIEWER_B)


def test_invalid_maybe_mapping_is_rejected_at_runtime() -> None:
    invalid = cast("MaybeCountsAs", "exclude")
    with pytest.raises(ValueError, match="maybe_counts_as"):
        fleiss_kappa((), maybe_counts_as=invalid)


def test_decision_rejects_an_unknown_runtime_value() -> None:
    invalid = cast("DecisionValue", "unsure")
    with pytest.raises(ValueError, match="decision must be"):
        make_decision(1, REVIEWER_A, invalid)


def test_fleiss_empty_input_is_not_calculable() -> None:
    assert fleiss_kappa(()) is None


def test_fleiss_single_category_is_undefined() -> None:
    decisions = tuple(
        make_decision(1, reviewer, "include") for reviewer in (REVIEWER_A, REVIEWER_B, REVIEWER_C)
    )
    assert fleiss_kappa(decisions) is None


def test_fleiss_perfect_agreement_across_categories_is_one() -> None:
    decisions = tuple(
        make_decision(record, reviewer, value)
        for record, value in ((1, "include"), (2, "exclude"))
        for reviewer in (REVIEWER_A, REVIEWER_B, REVIEWER_C)
    )
    assert fleiss_kappa(decisions) == 1.0


def test_fleiss_applies_project_maybe_setting() -> None:
    decisions = (
        make_decision(1, REVIEWER_A, "include"),
        make_decision(1, REVIEWER_B, "maybe"),
        make_decision(1, REVIEWER_C, "include"),
        make_decision(2, REVIEWER_A, "exclude"),
        make_decision(2, REVIEWER_B, "exclude"),
        make_decision(2, REVIEWER_C, "exclude"),
    )

    assert fleiss_kappa(decisions) == 1.0
    assert fleiss_kappa(decisions, maybe_counts_as="maybe") == pytest.approx(5 / 11)


def test_fleiss_requires_at_least_three_ratings_per_record() -> None:
    decisions = (
        make_decision(1, REVIEWER_A, "include"),
        make_decision(1, REVIEWER_B, "exclude"),
    )
    with pytest.raises(ValueError, match="at least three"):
        fleiss_kappa(decisions)


def test_fleiss_requires_a_fixed_panel_size() -> None:
    decisions = (
        make_decision(1, REVIEWER_A, "include"),
        make_decision(1, REVIEWER_B, "exclude"),
        make_decision(1, REVIEWER_C, "exclude"),
        make_decision(2, REVIEWER_A, "include"),
        make_decision(2, REVIEWER_B, "exclude"),
        make_decision(2, REVIEWER_C, "exclude"),
        make_decision(2, uuid.UUID(int=10_004), "exclude"),
    )
    with pytest.raises(ValueError, match="same number"):
        fleiss_kappa(decisions)
