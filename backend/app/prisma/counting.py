"""Pure arithmetic for PRISMA 2020 flow counts."""

from app.prisma.types import PrismaCounts, PrismaInputs


def counts(inputs: PrismaInputs) -> PrismaCounts:
    """Calculate a coherent PRISMA flow from grouped raw counts.

    Input is one project's validated database/manual aggregates; output contains ordered
    breakdowns and all derived totals. Complexity is O(d + o + r) time and output space for
    d database sources, o other sources and r exclusion reasons. The guide's grouped reason
    count is interpreted as one primary reason per excluded report to avoid double-counting.
    """

    identified_from_databases = sum(source.count for source in inputs.database_sources)
    identified_from_other_sources = sum(source.count for source in inputs.other_sources)
    identified_total = identified_from_databases + identified_from_other_sources
    removed_before_screening = inputs.duplicates_removed + inputs.records_removed_other_reasons
    if removed_before_screening > identified_total:
        raise ValueError("records removed before screening exceed records identified")
    if inputs.non_duplicate_records > identified_total - inputs.duplicates_removed:
        raise ValueError("records screened exceed records remaining after duplicate removal")
    if (
        inputs.title_abstract_excluded + inputs.title_abstract_included
        > inputs.non_duplicate_records
    ):
        raise ValueError("title/abstract outcomes exceed records screened")
    if inputs.reports_not_retrieved > inputs.title_abstract_included:
        raise ValueError("reports not retrieved exceed reports sought")

    reports_assessed = inputs.title_abstract_included - inputs.reports_not_retrieved
    reports_excluded = sum(item.count for item in inputs.full_text_exclusions)
    if reports_excluded + inputs.full_text_included > reports_assessed:
        raise ValueError("full-text outcomes exceed reports assessed")

    return PrismaCounts(
        database_sources=inputs.database_sources,
        other_sources=inputs.other_sources,
        records_identified_from_databases=identified_from_databases,
        records_identified_from_other_sources=identified_from_other_sources,
        records_identified_total=identified_total,
        duplicates_removed=inputs.duplicates_removed,
        records_removed_other_reasons=inputs.records_removed_other_reasons,
        records_screened=inputs.non_duplicate_records,
        records_excluded=inputs.title_abstract_excluded,
        reports_sought=inputs.title_abstract_included,
        reports_not_retrieved=inputs.reports_not_retrieved,
        reports_assessed=reports_assessed,
        reports_excluded_with_reasons=inputs.full_text_exclusions,
        reports_excluded_total=reports_excluded,
        studies_included=inputs.full_text_included,
    )
