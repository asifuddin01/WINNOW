"""Hand-calculated PRISMA fixtures shared by count and rendering tests."""

import pytest

from app.prisma import ExclusionCount, PrismaCounts, PrismaInputs, SourceCount


@pytest.fixture
def prisma_inputs() -> PrismaInputs:
    return PrismaInputs(
        database_sources=(
            SourceCount(name="MEDLINE", count=120),
            SourceCount(name="Embase", count=80),
            SourceCount(name="Cochrane CENTRAL", count=40),
        ),
        other_sources=(
            SourceCount(name="Citation searching", count=6),
            SourceCount(name="Websites", count=4),
        ),
        duplicates_removed=30,
        records_removed_other_reasons=10,
        non_duplicate_records=210,
        title_abstract_excluded=150,
        title_abstract_included=60,
        reports_not_retrieved=5,
        full_text_exclusions=(
            ExclusionCount(reason="Wrong population", count=12),
            ExclusionCount(reason="Wrong intervention", count=13),
            ExclusionCount(reason="Wrong study design", count=10),
        ),
        full_text_included=20,
    )


@pytest.fixture
def expected_counts(prisma_inputs: PrismaInputs) -> PrismaCounts:
    return PrismaCounts(
        database_sources=prisma_inputs.database_sources,
        other_sources=prisma_inputs.other_sources,
        records_identified_from_databases=240,
        records_identified_from_other_sources=10,
        records_identified_total=250,
        duplicates_removed=30,
        records_removed_other_reasons=10,
        records_screened=210,
        records_excluded=150,
        reports_sought=60,
        reports_not_retrieved=5,
        reports_assessed=55,
        reports_excluded_with_reasons=prisma_inputs.full_text_exclusions,
        reports_excluded_total=35,
        studies_included=20,
    )
