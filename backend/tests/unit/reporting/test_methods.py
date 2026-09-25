"""The methods text (guide 8.15): real numbers, British spelling, and nothing the facts do
not hold."""

from datetime import date

from app.reporting import (
    Agreement,
    AiUse,
    Count,
    DatabaseSearch,
    MethodsFacts,
    Resolutions,
    methods_text,
)
from app.reporting.methods import listed, people

FULL = MethodsFacts(
    databases=(
        DatabaseSearch("PubMed", 6012, date(2026, 3, 3)),
        DatabaseSearch("Embase", 4211),
    ),
    other_sources=(Count("citation searching", 12),),
    duplicates_removed=1203,
    records_screened=9032,
    reviewers_ta=2,
    reviewers_ft=2,
    blind=True,
    agreement_ta=Agreement(kappa=0.8123, band="almost perfect", percent=0.9421),
    agreement_ft=Agreement(kappa_range=(0.61, 0.8), pairs=3, percent=None),
    resolutions_ta=Resolutions(total=312, by_discussion=280, by_third_reviewer=32),
    resolutions_ft=Resolutions(total=4, by_discussion=4),
    ranked=True,
    ai=AiUse(records=120, models=("claude-sonnet-5",)),
    reports_sought=412,
    reports_not_retrieved=12,
    reports_assessed=400,
    reports_excluded=(Count("Wrong population", 120), Count("Wrong design", 192)),
    studies_included=88,
    extraction="duplicate",
    rob_tools=("RoB 2", "ROBINS-I"),
    rob_duplicate=True,
)


def test_a_whole_review_in_two_paragraphs() -> None:
    first, second = methods_text(FULL).split("\n\n")
    assert first == (
        "We searched PubMed (6,012 records, searched 3 March 2026) and Embase (4,211 records) "
        "and identified further records through citation searching (12 records). "
        "After 1,203 duplicates were removed, two reviewers independently screened the titles "
        "and abstracts of 9,032 records, blinded to each other's decisions; agreement was "
        "94.2% (Cohen's κ = 0.81, almost perfect). "
        "Disagreements at title and abstract (312) were resolved by discussion (280) or by a "
        "third reviewer (32). "
        "Records were screened in order of predicted relevance, updated as decisions were "
        "made (active learning). "
        "An AI assistant (claude-sonnet-5) suggested decisions for 120 records; every "
        "decision was made by a reviewer."
    )
    assert second == (
        "We sought 412 full-text reports, of which 12 could not be retrieved. "
        "Two reviewers independently assessed the full texts of 400 records, blinded to each "
        "other's decisions; Cohen's κ ranged from 0.61 to 0.80 across 3 pairs of reviewers. "
        "312 reports were excluded: wrong population (120) and wrong design (192). "
        "Disagreements at full text (4) were resolved by discussion (4). "
        "88 studies were included in the review. "
        "Two reviewers extracted data independently and resolved differences. "
        "Risk of bias was assessed independently by two reviewers with RoB 2 and ROBINS-I."
    )


def test_a_minimal_review_says_only_what_it_knows() -> None:
    assert methods_text(MethodsFacts()) == ""
    text = methods_text(MethodsFacts(records_screened=40))
    assert text == "Reviewers screened the titles and abstracts of 40 records."
    assert "κ" not in text
    assert "duplicate" not in text


def test_singular_and_plural_wording() -> None:
    text = methods_text(
        MethodsFacts(
            databases=(DatabaseSearch("PubMed", 1),),
            duplicates_removed=1,
            records_screened=1,
            reviewers_ta=1,
            blind=True,
            reports_sought=1,
            reports_assessed=1,
            reviewers_ft=1,
            reports_excluded=(Count("Wrong outcome", 1),),
            studies_included=1,
            extraction="single",
            rob_tools=("QUADAS-2",),
            rob_duplicate=False,
        )
    )
    assert "PubMed (1 record)" in text
    assert (
        "After 1 duplicate was removed, one reviewer screened the titles and abstracts of 1 record."
        in text
    )
    assert "blinded" not in text  # one reviewer has nobody to be blind to
    assert "1 report was excluded: wrong outcome (1)." in text
    assert "1 study was included in the review." in text
    assert "One reviewer extracted the data." in text
    assert "Risk of bias was assessed with QUADAS-2." in text


def test_a_review_without_a_full_text_stage_yet_has_one_paragraph() -> None:
    text = methods_text(
        MethodsFacts(
            other_sources=(Count("websites", 3),),
            records_screened=500,
            reviewers_ta=3,
            blind=False,
            agreement_ta=Agreement(kappa=0.55, band="moderate", fleiss=True),
            stopping_rule="200 records in a row had been excluded",
        )
    )
    assert "\n" not in text
    assert text.startswith("We identified further records through websites (3 records). ")
    assert "three reviewers independently screened" in text.lower()
    assert "seeing each other's decisions; Fleiss' κ = 0.55, moderate." in text
    assert "when 200 records in a row had been excluded." in text


def test_agreement_without_kappa_and_resolutions_without_detail() -> None:
    text = methods_text(
        MethodsFacts(
            records_screened=10,
            reviewers_ta=2,
            agreement_ta=Agreement(percent=1.0),
            resolutions_ta=Resolutions(total=2),
            resolutions_ft=Resolutions(total=0),
            notes=("Screening was piloted on 50 records.",),
        )
    )
    assert "two reviewers independently screened" in text.lower()
    assert "; agreement was 100.0%." in text
    assert "Disagreements at title and abstract (2) were resolved." in text
    assert "full text" not in text
    assert text.endswith("\n\nScreening was piloted on 50 records.")


def test_words() -> None:
    assert listed([]) == ""
    assert listed(["a"]) == "a"
    assert listed(["a", "b", "c"]) == "a, b and c"
    assert people(0) == "no reviewers"
    assert people(12) == "12 reviewers"
