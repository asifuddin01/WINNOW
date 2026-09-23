"""The advisory source catalogue is broad without restricting custom source names."""

from app.prisma import (
    COMMON_DATABASES,
    COMMON_EVIDENCE_SOURCES,
    COMMON_SEARCH_PORTALS,
    COMMON_TRIAL_REGISTRIES,
    SourceCount,
)


def test_common_catalogue_covers_major_database_families_and_registries() -> None:
    expected = {
        "arXiv",
        "CINAHL",
        "Cochrane CENTRAL",
        "Embase",
        "IEEE Xplore",
        "MEDLINE",
        "PubMed",
        "Scopus",
        "Web of Science Core Collection",
        "ClinicalTrials.gov",
        "WHO International Clinical Trials Registry Platform (ICTRP)",
    }
    assert expected <= set(COMMON_EVIDENCE_SOURCES)
    assert "WHO International Clinical Trials Registry Platform (ICTRP)" in COMMON_SEARCH_PORTALS
    assert "WHO International Clinical Trials Registry Platform (ICTRP)" not in (
        COMMON_TRIAL_REGISTRIES
    )
    assert "PubMed" in COMMON_DATABASES


def test_common_catalogue_has_no_blank_or_duplicate_names() -> None:
    normalised = [name.strip().casefold() for name in COMMON_EVIDENCE_SOURCES]
    assert all(normalised)
    assert len(normalised) == len(set(normalised))


def test_custom_database_names_remain_valid() -> None:
    custom = SourceCount(name="Kidney Specialist Index", count=7)
    assert custom.name not in COMMON_EVIDENCE_SOURCES
