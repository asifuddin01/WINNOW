"""Matching a PDF's file name to a record (guide 8.8): identifiers first, then author and
year, then title."""

import uuid

from app.fulltext.matching import Matcher, RecordKeys, fold, surname

A, B, C, D, E = (uuid.UUID(int=n) for n in range(1, 6))
RECORDS = [
    RecordKeys(
        A,
        "Deep learning for kidney segmentation in CT",
        "10.1016/j.kint.2020.01.001",
        "31234567",
        "PMC7012345",
        "Smith, Jane",
        2020,
    ),
    RecordKeys(
        B,
        "Radiomics of renal cell carcinoma: a review",
        "10.48550/arXiv.2105.01234",
        None,
        None,
        "Müller, Jörg",
        2021,
    ),
    RecordKeys(
        C, "Kidney stone detection with transformers", None, None, None, "Smith, Jane", 2021
    ),
    RecordKeys(
        D, "Kidney tumour segmentation challenge results", None, None, None, "Smith, Jane", 2021
    ),
    RecordKeys(
        E,
        "Automated measurement of total kidney volume in polycystic disease",
        None,
        None,
        None,
        "Lee, Kim",
        None,
    ),
]
MATCHER = Matcher(RECORDS)


def by(filename: str) -> tuple[uuid.UUID | None, str | None, str | None]:
    outcome = MATCHER.match(filename)
    if outcome.match is None:
        return None, None, None
    return outcome.match.record_id, outcome.match.by, outcome.match.confidence


def test_identifiers_are_sure() -> None:
    assert by("10.1016_j.kint.2020.01.001.pdf") == (A, "doi", "sure")
    assert by("10.1016-j.kint.2020.01.001 (1).PDF") == (A, "doi", "sure")
    assert by("PMC7012345.pdf") == (A, "pmcid", "sure")
    assert by("pmc_7012345.pdf") == (A, "pmcid", "sure")
    assert by("31234567.pdf") == (A, "pmid", "sure")
    assert by("PMID 31234567.pdf") == (A, "pmid", "sure")
    assert by("2105.01234v2.pdf") == (B, "arxiv", "sure")


def test_author_and_year_are_likely() -> None:
    assert by("Smith 2020 - anything.pdf") == (A, "author_year", "likely")
    assert by("Muller_2021.pdf") == (B, "author_year", "likely")


def test_the_title_decides_between_papers_by_one_author_in_one_year() -> None:
    assert by("Smith 2021 kidney stone detection transformers.pdf")[0] == C
    ambiguous = MATCHER.match("Smith 2021.pdf")
    assert ambiguous.match is None
    assert set(ambiguous.candidates) == {C, D}


def test_a_title_alone() -> None:
    assert by("Automated measurement of total kidney volume in polycystic disease.pdf") == (
        E,
        "title",
        "likely",
    )
    assert by("Automated_measurement_of_total_kidney_volume.pdf") == (E, "title", "likely")


def test_nothing_to_go_on() -> None:
    assert MATCHER.match("scan0001.pdf").match is None
    assert MATCHER.match("kidney.pdf").match is None


def test_helpers() -> None:
    assert fold("Müller\u2013Lüdenscheidt, J.") == "muller ludenscheidt j"
    assert surname("Müller, Jörg") == "muller"
    assert surname("Jane A Smith") == "smith"
