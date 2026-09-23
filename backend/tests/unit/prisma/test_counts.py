"""PRISMA arithmetic uses a hand-calculated flow and rejects incoherent inputs."""

from dataclasses import replace
from typing import cast

import pytest

from app.prisma import ExclusionCount, PrismaCounts, PrismaInputs, SourceCount, counts


def test_counts_matches_hand_calculated_fixture(
    prisma_inputs: PrismaInputs, expected_counts: PrismaCounts
) -> None:
    # 240 + 10 identified; 60 - 5 assessed; 12 + 13 + 10 excluded.
    assert counts(prisma_inputs) == expected_counts


def test_all_zero_flow_is_valid() -> None:
    inputs = PrismaInputs(
        database_sources=(),
        other_sources=(),
        duplicates_removed=0,
        records_removed_other_reasons=0,
        non_duplicate_records=0,
        title_abstract_excluded=0,
        title_abstract_included=0,
        reports_not_retrieved=0,
        full_text_exclusions=(),
        full_text_included=0,
    )

    result = counts(inputs)

    assert result.records_identified_total == 0
    assert result.records_screened == 0
    assert result.reports_assessed == 0
    assert result.reports_excluded_total == 0


def test_in_progress_flow_need_not_balance_to_equality(prisma_inputs: PrismaInputs) -> None:
    inputs = replace(
        prisma_inputs,
        title_abstract_excluded=100,
        title_abstract_included=40,
        reports_not_retrieved=5,
        full_text_exclusions=(ExclusionCount(reason="Wrong population", count=10),),
        full_text_included=5,
    )

    result = counts(inputs)

    assert result.records_excluded + result.reports_sought < result.records_screened
    assert result.reports_excluded_total + result.studies_included < result.reports_assessed


def test_manual_other_removals_do_not_reduce_raw_non_duplicate_bound() -> None:
    inputs = PrismaInputs(
        database_sources=(SourceCount(name="MEDLINE", count=100),),
        other_sources=(),
        duplicates_removed=10,
        records_removed_other_reasons=5,
        non_duplicate_records=90,
        title_abstract_excluded=60,
        title_abstract_included=30,
        reports_not_retrieved=0,
        full_text_exclusions=(ExclusionCount(reason="Wrong population", count=10),),
        full_text_included=20,
    )

    assert counts(inputs).records_screened == 90


@pytest.mark.parametrize(
    "field_name",
    [
        "duplicates_removed",
        "records_removed_other_reasons",
        "non_duplicate_records",
        "title_abstract_excluded",
        "title_abstract_included",
        "reports_not_retrieved",
        "full_text_included",
    ],
)
def test_input_scalar_counts_must_be_non_negative(
    prisma_inputs: PrismaInputs, field_name: str
) -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        replace(prisma_inputs, **{field_name: -1})


@pytest.mark.parametrize("value", [True, 1.5, "1"])
def test_grouped_counts_must_be_integers(value: object) -> None:
    with pytest.raises(TypeError, match="must be an integer"):
        SourceCount(name="MEDLINE", count=cast("int", value))


@pytest.mark.parametrize("value", [-1, True, 1.5, "1"])
def test_exclusion_counts_are_validated(value: object) -> None:
    error = ValueError if value == -1 else TypeError
    with pytest.raises(error):
        ExclusionCount(reason="Wrong population", count=cast("int", value))


@pytest.mark.parametrize("value", ["", "  \t\n"])
def test_source_names_must_not_be_blank(value: str) -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        SourceCount(name=value, count=1)


def test_exclusion_reasons_must_not_be_blank() -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        ExclusionCount(reason=" ", count=1)


def test_xml_invalid_characters_are_rejected() -> None:
    with pytest.raises(ValueError, match=r"XML 1\.0"):
        SourceCount(name="MED\x00LINE", count=1)


def test_source_name_must_be_a_string() -> None:
    with pytest.raises(TypeError, match="must be a string"):
        SourceCount(name=cast("str", 42), count=1)


def test_source_groups_must_be_immutable_tuples(prisma_inputs: PrismaInputs) -> None:
    mutable = cast("tuple[SourceCount, ...]", list(prisma_inputs.database_sources))
    with pytest.raises(TypeError, match="must be a tuple"):
        replace(prisma_inputs, database_sources=mutable)


def test_source_groups_must_contain_source_counts(prisma_inputs: PrismaInputs) -> None:
    invalid = cast("tuple[SourceCount, ...]", ("MEDLINE",))
    with pytest.raises(TypeError, match="SourceCount"):
        replace(prisma_inputs, database_sources=invalid)


def test_exclusion_groups_must_be_immutable_tuples(prisma_inputs: PrismaInputs) -> None:
    mutable = cast("tuple[ExclusionCount, ...]", list(prisma_inputs.full_text_exclusions))
    with pytest.raises(TypeError, match="must be a tuple"):
        replace(prisma_inputs, full_text_exclusions=mutable)


def test_exclusion_groups_must_contain_exclusion_counts(prisma_inputs: PrismaInputs) -> None:
    invalid = cast("tuple[ExclusionCount, ...]", ("Wrong population",))
    with pytest.raises(TypeError, match="ExclusionCount"):
        replace(prisma_inputs, full_text_exclusions=invalid)


def test_source_names_are_unique_after_trimming_and_casefolding(
    prisma_inputs: PrismaInputs,
) -> None:
    duplicates = (
        SourceCount(name="MEDLINE", count=1),
        SourceCount(name=" medline ", count=2),
    )
    with pytest.raises(ValueError, match="duplicate source"):
        replace(prisma_inputs, database_sources=duplicates)


def test_exclusion_reasons_are_unique_after_trimming_and_casefolding(
    prisma_inputs: PrismaInputs,
) -> None:
    duplicates = (
        ExclusionCount(reason="Wrong population", count=1),
        ExclusionCount(reason=" wrong population ", count=2),
    )
    with pytest.raises(ValueError, match="duplicate reason"):
        replace(prisma_inputs, full_text_exclusions=duplicates)


def test_source_duplicates_use_unicode_normalisation(prisma_inputs: PrismaInputs) -> None:
    duplicates = (
        SourceCount(name="Café Index", count=1),
        SourceCount(name="Cafe\u0301 Index", count=2),
    )
    with pytest.raises(ValueError, match="duplicate source"):
        replace(prisma_inputs, database_sources=duplicates)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"duplicates_removed": 241}, "removed before screening"),
        ({"non_duplicate_records": 221}, "remaining after duplicate"),
        ({"title_abstract_included": 61}, "title/abstract outcomes"),
        ({"reports_not_retrieved": 61}, "not retrieved"),
        ({"full_text_included": 21}, "full-text outcomes"),
    ],
)
def test_inconsistent_flows_are_rejected(
    prisma_inputs: PrismaInputs, changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        counts(replace(prisma_inputs, **changes))


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"records_identified_from_databases": 239}, "database source total"),
        ({"records_identified_from_other_sources": 9}, "other-source total"),
        ({"records_identified_total": 249}, "identified total"),
        ({"reports_assessed": 54}, "reports assessed"),
        ({"reports_excluded_total": 34}, "excluded total"),
    ],
)
def test_manually_constructed_outputs_must_reconcile(
    expected_counts: PrismaCounts, changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(expected_counts, **changes)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"duplicates_removed": 241}, "removed before screening"),
        ({"records_screened": 221}, "remaining after duplicate"),
        ({"records_excluded": 151}, "title/abstract outcomes"),
        (
            {"reports_sought": 4, "reports_not_retrieved": 5, "reports_assessed": 0},
            "not retrieved",
        ),
        ({"studies_included": 21}, "full-text outcomes"),
    ],
)
def test_manually_constructed_outputs_must_keep_flow_bounds(
    expected_counts: PrismaCounts, changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(expected_counts, **changes)
